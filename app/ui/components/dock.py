"""The dock: folder navigation and the two global actions, top centre.

    [ Inbox ] [ Starred ] [ Sent ] [ Trash ]  |  [ Add account ] [ Settings ]

WHY THE FOLDERS LEFT THE SIDEBAR. The drawer was doing two jobs - WHERE
(which folder) and WHOSE (which account) - in one vertical list, and the
two answers fought: picking an account had to un-pick the folder, and the
drawer could only show one of them as current. Splitting them gives each
control one meaning. The dock answers "which folder", the sidebar answers
"whose mail", and both can be true at once without either one lying.

=========================================================================
ADAPTED FROM MAGIC UI'S DOCK

What makes that component feel like one object rather than a row of
buttons is that EVERY icon's size is a continuous function of a single
pointer position, smoothed by a spring:

    distance from pointer -> interpolated size -> spring -> icon

rather than each icon toggling its own hover state. That is the part kept
here, and the reason it matters is spatial: the icons nearest the pointer
make room for it, so the eye can see where the pointer is relative to
the whole group before it lands on one.

What was changed for a desktop mail client, and why:

  * RESTRAINT. The web component grows 40 -> 60px (1.5x). Here it is
    32 -> 40 (1.25x): enough to read as a response to the pointer,
    not enough to turn a toolbar into a launcher.
  * A COSINE FALLOFF instead of a linear one. Linear interpolation puts a
    kink at the peak that the spring has to hide; the cosine has none.
  * THE SAME SPRING, deliberately: mass 0.1, stiffness 150, damping 12.
    That is overdamped (zeta ~ 1.55), so it never bounces - the dock
    settles, it does not wobble.
  * NOTHING OUTSIDE THE DOCK MOVES. The widget reserves the most width
    magnification can ever use, so the pill grows inside a fixed box and
    the toolbar never re-lays itself out under the pointer.
  * ONE TIMER for the whole effect, running only while something is
    still settling, and never under reduced motion - where magnification
    is simply off and the dock is a static row of 32px cells.
  * THE SELECTION IS ONE SURFACE THAT TRAVELS, carried over from the
    sidebar this replaces: moving Inbox -> Trash slides one surface across
    rather than cross-fading two. It rides the cells' CURRENT geometry,
    so it stays glued to its item while the item is magnified.

Labels appear under an item after a short hover, and move instantly
between items once one is showing - the way a desktop dock names things,
rather than a tooltip that makes you wait again for every icon.
"""

from __future__ import annotations

import math

from PySide6.QtCore import (
    Property,
    QElapsedTimer,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QLabel, QWidget

from app.ui import motion, theme as t
from app.ui.svg_icon import paint_icon

# ---------------------------------------------------------------- geometry

CELL = t.HEIGHT_MD          # 32: a cell at rest, the app's control height
CELL_PEAK = 40              # the most a cell grows under the pointer
GLYPH = t.ICON_SIZE_TOOLBAR  # 18: the glyph at rest; it scales with its cell
GAP = t.SPACE_XS            # between cells
PAD = 6                     # inside the pill, on every side of a rest cell
HEIGHT = CELL + 2 * PAD     # 44: fixed; magnification never changes it
SEPARATOR_SLOT = 2 * t.SPACE_SM + 1
# How far the pointer's influence reaches, in px. About three cells, which
# is the same reach Magic UI's 140px has over its 48px pitch.
REACH = 104

# Magic UI's spring. Overdamped - it settles without overshooting.
SPRING_MASS = 0.1
SPRING_STIFFNESS = 150.0
SPRING_DAMPING = 12.0
_FRAME_MS = 16
_SETTLED = 0.02

# Label timing: the first label waits long enough not to flash while the
# pointer is only crossing the dock; after that, moving between items
# re-labels at once, and a short grace period covers the gaps between
# cells so the label does not blink out between two icons.
LABEL_DELAY_MS = 380
LABEL_GRACE_MS = 140

FOLDERS = (
    ("inbox", "inbox", "Inbox"),
    ("starred", "star_outline", "Starred"),
    ("sent", "sent", "Sent"),
    ("trash", "trash", "Trash"),
)
ACTIONS = (
    ("add_account", "add_circle", "Add account"),
    ("settings", "settings", "Settings"),
)


def falloff(distance: float, reach: float = REACH) -> float:
    """1.0 with the pointer dead centre on a cell, easing to 0 at `reach`.

    A raised cosine rather than Magic UI's linear ramp: the same reach and
    the same peak, without the corner at the top that makes a linear dock
    feel like it snaps onto whichever icon is nearest.
    """
    d = abs(distance)
    if d >= reach:
        return 0.0
    return 0.5 * (1.0 + math.cos(math.pi * d / reach))


def badge_text(count: int) -> str:
    """The unread count as the dock shows it: exact to 99, then 99+.

    Beyond two digits the number stops helping anyone decide anything and
    starts widening the badge over the icon beside it.
    """
    count = max(0, int(count))
    return str(count) if count < 100 else "99+"


class DockItem(QAbstractButton):
    """One cell. Paints its own hover, press and focus; the dock paints
    the selection, because the selection is one surface shared by all the
    folder cells and it travels between them."""

    def __init__(self, key: str, icon: str, label: str, *, folder: bool,
                 parent=None):
        super().__init__(parent)
        self.key = key
        self.icon_name = icon
        self.label = label
        self.folder = folder
        self.setCheckable(folder)
        # Tab reaches it; a click does not take focus from the message
        # list, so the keyboard keeps working where the user left it.
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAccessibleName(label)
        # Current cell size, driven by the dock's spring. Float, because a
        # magnifying cell spends most of its time between whole pixels.
        self.size_now = float(CELL)
        self.size_target = float(CELL)
        self.velocity = 0.0
        self._hovered = False
        self._keyboard_focus = False

    # -- geometry the dock asks for -----------------------------------------

    def cell_rect(self) -> QRectF:
        """The visible cell, centred in this widget's (larger) hit area.

        The widget is wider and taller than the cell it draws so that the
        gaps between icons still belong to an icon: moving along the dock
        never passes over a dead strip where nothing is hovered.
        """
        s = self.size_now
        return QRectF((self.width() - s) / 2.0, (self.height() - s) / 2.0, s, s)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(CELL + GAP, HEIGHT)

    # -- state -----------------------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        # A focus ring is for the keyboard. A ring that appears on every
        # click is noise that follows the mouse around; one that appears
        # on Tab is the only way a keyboard user knows where they are.
        self._keyboard_focus = event.reason() in (
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        )
        self.update()
        dock = self.parentWidget()
        if self._keyboard_focus and isinstance(dock, Dock):
            dock.show_label_for(self, immediate=True)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._keyboard_focus = False
        self.update()
        dock = self.parentWidget()
        if isinstance(dock, Dock):
            dock.hide_label_soon()
        super().focusOutEvent(event)

    def event(self, event) -> bool:
        # THE WINDOW'S SHORTCUTS MUST NOT EAT THE DOCK'S OWN KEYS. Enter is
        # bound window-wide to "open the focused message"; without claiming
        # it here, pressing Enter on a focused dock item would open a
        # message instead of the folder the user is looking at.
        if event.type() == QEvent.Type.ShortcutOverride:
            if event.key() in (
                Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space,
                Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Home,
                Qt.Key.Key_End,
            ) and not event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier:
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        dock = self.parentWidget()
        key = event.key()
        if isinstance(dock, Dock):
            if key == Qt.Key.Key_Left:
                dock.focus_neighbour(self, -1)
                return
            if key == Qt.Key.Key_Right:
                dock.focus_neighbour(self, +1)
                return
            if key == Qt.Key.Key_Home:
                dock.focus_edge(first=True)
                return
            if key == Qt.Key.Key_End:
                dock.focus_edge(first=False)
                return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            return
        super().keyPressEvent(event)

    # -- paint -----------------------------------------------------------------

    def glyph_colour(self) -> str:
        if not self.isEnabled():
            return t.ICON_DISABLED
        if self.isChecked():
            return t.ICON_SELECTED
        if self._hovered or self.isDown() or self._keyboard_focus:
            return t.ICON_ACTIVE
        return t.ICON_SECONDARY

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        cell = self.cell_rect()
        radius = float(t.RADIUS_MD)

        # Hover is a wash, pressed is a deeper one, and neither is drawn on
        # the selected cell: the travelling surface already says "here",
        # and a second fill on top of it would argue with it.
        if not self.isChecked():
            wash = None
            if self.isDown():
                wash = t.WASH_PRESSED if t.is_dark() else t.WASH_SELECTED
            elif self._hovered:
                wash = t.WASH_HOVER
            if wash:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(t.qcolor(wash))
                painter.drawRoundedRect(cell, radius, radius)

        glyph = cell.width() * (GLYPH / CELL)
        # A press sinks the glyph a fraction: the only motion a click gets.
        sink = 0.5 if self.isDown() else 0.0
        glyph_rect = QRectF(
            cell.center().x() - glyph / 2.0,
            cell.center().y() - glyph / 2.0 + sink,
            glyph, glyph,
        )
        paint_icon(painter, self.icon_name, glyph_rect, self.glyph_colour())

        if self._keyboard_focus and self.hasFocus():
            pen = QPen(QColor(t.FOCUS_RING), t.FOCUS_WIDTH)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(cell.adjusted(0.5, 0.5, -0.5, -0.5),
                                    radius, radius)
        painter.end()


class _DockLabel(QLabel):
    """The name of the item under the pointer, centred beneath it.

    A floating label rather than QToolTip, because a QToolTip cannot be
    centred on anything - it hangs off the pointer's hotspot - and cannot
    be told to move straight to the next icon without waiting out its
    delay again.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("dockLabel")
        self.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFont(t.make_font("status"))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()


class _BadgeLayer(QWidget):
    """Paints the unread count above the cells.

    A layer of its own because the badge deliberately overhangs the inbox
    cell's corner, and a child widget cannot paint outside itself.
    Transparent to the mouse, so it never steals a click from the icon
    under it.
    """

    def __init__(self, dock: "Dock"):
        super().__init__(dock)
        self._dock = dock
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def paintEvent(self, event) -> None:  # noqa: N802
        self._dock.paint_badge(self)


class Dock(QWidget):
    """Folder navigation and the global actions, as one magnifying row."""

    folder_requested = Signal(str)
    action_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dock")
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAccessibleName("Folders")

        self.items: list[DockItem] = []
        self._folders: dict[str, DockItem] = {}
        for key, icon, label in FOLDERS:
            item = DockItem(key, icon, label, folder=True, parent=self)
            item.clicked.connect(lambda _=False, k=key: self._on_folder(k))
            self._folders[key] = item
            self.items.append(item)
        self._actions: dict[str, DockItem] = {}
        for key, icon, label in ACTIONS:
            item = DockItem(key, icon, label, folder=False, parent=self)
            item.clicked.connect(lambda _=False, k=key: self.action_requested.emit(k))
            self._actions[key] = item
            self.items.append(item)
        for item in self.items:
            item.installEventFilter(self)

        self._current = "inbox"
        self._folders["inbox"].setChecked(True)
        self._unread = 0

        # Selection position as a FLOAT INDEX over the folder cells, so the
        # surface can ride the cells' live geometry between two of them.
        self._sel = 0.0
        self._sel_anim: QPropertyAnimation | None = None

        self._pointer_x: float | None = None
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._tick)

        self._label = _DockLabel(self)
        self._label_item: DockItem | None = None
        self._label_timer = QTimer(self)
        self._label_timer.setSingleShot(True)
        self._label_timer.timeout.connect(self._show_pending_label)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_label)
        self._pending_label: DockItem | None = None

        self._badges = _BadgeLayer(self)
        self._badges.raise_()

        self.setFixedSize(self._reserved_width(), HEIGHT)
        self._layout_cells()
        self._update_inbox_name()

    # ------------------------------------------------------------ geometry

    @staticmethod
    def _rest_content_width() -> float:
        folders, actions = len(FOLDERS), len(ACTIONS)
        cells = (folders + actions) * CELL
        gaps = (folders - 1 + actions - 1) * GAP
        return float(cells + gaps + SEPARATOR_SLOT)

    @classmethod
    def _rest_centres(cls) -> list[float]:
        """Where each cell's centre sits at rest, from the content's left
        edge. Distances are measured against THESE, not the live
        positions: measuring against cells that move as they grow feeds
        the size back into its own input and makes the peak crawl."""
        centres, x = [], 0.0
        for i in range(len(FOLDERS) + len(ACTIONS)):
            if i == len(FOLDERS):
                x += SEPARATOR_SLOT - GAP
            centres.append(x + CELL / 2.0)
            x += CELL + GAP
        return centres

    @classmethod
    def max_growth(cls) -> float:
        """The most total width magnification can ever add, found by
        sweeping the pointer across the whole row. The widget reserves
        this once, so nothing outside the dock ever moves."""
        centres = cls._rest_centres()
        best = 0.0
        span = int(cls._rest_content_width()) + 1
        for px in range(0, span):
            grow = sum((CELL_PEAK - CELL) * falloff(px - c) for c in centres)
            best = max(best, grow)
        return best

    @classmethod
    def _reserved_width(cls) -> int:
        return int(math.ceil(cls._rest_content_width() + cls.max_growth())) + 2 * PAD

    def pill_rect(self) -> QRectF:
        """The dock's visible body, centred in its reserved box, as wide
        as its cells are right now."""
        content = sum(item.size_now for item in self.items)
        content += (len(FOLDERS) - 1 + len(ACTIONS) - 1) * GAP + SEPARATOR_SLOT
        width = content + 2 * PAD
        return QRectF((self.width() - width) / 2.0, 0.0, width, float(HEIGHT))

    def _layout_cells(self) -> None:
        """Place every cell from its current size.

        Each widget is its cell PLUS half the gap on either side (and the
        full pill height), so the hit areas tile the dock with no dead
        strips between icons.
        """
        pill = self.pill_rect()
        x = pill.left() + PAD
        for i, item in enumerate(self.items):
            if i == len(FOLDERS):
                x += SEPARATOR_SLOT - GAP
            s = item.size_now
            left = x - GAP / 2.0
            item.setGeometry(
                int(round(left)), 0,
                int(round(x + s + GAP / 2.0)) - int(round(left)), HEIGHT,
            )
            x += s + GAP
        self._badges.setGeometry(self.rect())
        self.update()
        self._badges.update()

    def cell_rect_in_dock(self, item: DockItem) -> QRectF:
        return item.cell_rect().translated(item.x(), item.y())

    def separator_x(self) -> float:
        last_folder = self.items[len(FOLDERS) - 1]
        cell = self.cell_rect_in_dock(last_folder)
        return cell.right() + SEPARATOR_SLOT / 2.0

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_cells()

    # ---------------------------------------------------------- magnification

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if isinstance(obj, DockItem):
            kind = event.type()
            if kind in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
                pos = event.position() if hasattr(event, "position") else event.pos()
                self._pointer_at(obj.x() + pos.x())
            elif kind == QEvent.Type.Enter:
                self.show_label_for(obj)
            elif kind == QEvent.Type.Leave:
                self.hide_label_soon()
        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._pointer_at(event.position().x())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._pointer_x = None
        # The pointer has left the whole dock, so no cell is hovered -
        # stated outright rather than trusting every cell saw its own Leave
        # (a fast exit through a cell edge can skip one).
        for item in self.items:
            if item._hovered:
                item._hovered = False
                item.update()
        self._retarget()
        self.hide_label_soon()
        super().leaveEvent(event)

    def _pointer_at(self, x: float) -> None:
        self._pointer_x = float(x)
        self._retarget()

    def _retarget(self) -> None:
        """Every cell's target from ONE pointer position."""
        if not motion.motion_enabled():
            # Reduced motion: no magnification at all. Not a faster
            # version of it - a static row, which is the correct end state.
            changed = any(item.size_now != CELL for item in self.items)
            for item in self.items:
                item.size_now = item.size_target = float(CELL)
                item.velocity = 0.0
            if changed:
                self._layout_cells()
            return

        rest_left = (self.width() - self._rest_content_width()) / 2.0
        for item, centre in zip(self.items, self._rest_centres()):
            if self._pointer_x is None:
                target = float(CELL)
            else:
                d = self._pointer_x - (rest_left + centre)
                target = CELL + (CELL_PEAK - CELL) * falloff(d)
            item.size_target = target
        if not self._timer.isActive():
            self._clock.start()
            self._timer.start()

    def _tick(self) -> None:
        """Advance every cell's spring by the real elapsed time.

        Real time, not a fixed step: if the UI thread stalls for a frame
        the springs catch up instead of the dock running in slow motion.
        Substepped, because the spring is stiff enough that one 16ms Euler
        step can overshoot.
        """
        elapsed = self._clock.restart() / 1000.0 if self._clock.isValid() else 0.016
        elapsed = min(max(elapsed, 0.001), 0.05)
        steps = max(1, int(math.ceil(elapsed / 0.004)))
        dt = elapsed / steps
        settled = True
        for item in self.items:
            x, v = item.size_now, item.velocity
            for _ in range(steps):
                accel = (-SPRING_STIFFNESS * (x - item.size_target)
                         - SPRING_DAMPING * v) / SPRING_MASS
                v += accel * dt
                x += v * dt
            if abs(x - item.size_target) < _SETTLED and abs(v) < 1.0:
                x, v = item.size_target, 0.0
            else:
                settled = False
            item.size_now, item.velocity = x, v
        self._layout_cells()
        if settled:
            self._timer.stop()

    def is_settling(self) -> bool:
        return self._timer.isActive()

    # -------------------------------------------------------------- selection

    def _get_sel(self) -> float:
        return self._sel

    def _set_sel(self, value: float) -> None:
        self._sel = float(value)
        self.update()

    selectionPos = Property(float, _get_sel, _set_sel)

    def _on_folder(self, key: str) -> None:
        # The dock does not decide what is current - the window does, and
        # tells it back through set_current_folder. A click is a request.
        # Re-assert the checked state straight away, though, because
        # QAbstractButton has already toggled it and a click on the
        # current folder must not leave it unchecked.
        self._sync_checked()
        self.folder_requested.emit(key)

    def set_current_folder(self, key: str, *, animate: bool = True) -> None:
        if key not in self._folders:
            return
        index = float(list(self._folders).index(key))
        if key == self._current:
            # Told again what it already shows - the window restates the
            # location on every sync tick. A slide still under way toward
            # this folder is left to finish rather than cut to its end.
            self._sync_checked()
            running = (self._sel_anim is not None and
                       self._sel_anim.state() == QPropertyAnimation.State.Running)
            if running or self._sel == index:
                return
        self._current = key
        self._sync_checked()
        if self._sel_anim is not None:
            self._sel_anim.stop()
            self._sel_anim = None
        if not animate or not motion.motion_enabled() or not self.isVisible():
            self._set_sel(index)
            return
        anim = QPropertyAnimation(self, b"selectionPos", self)
        anim.setDuration(t.DURATION_BASE)
        anim.setEasingCurve(motion.curve())
        anim.setStartValue(self._sel)
        anim.setEndValue(index)
        anim.start(QPropertyAnimation.DeletionPolicy.KeepWhenStopped)
        self._sel_anim = anim

    def current_folder(self) -> str:
        return self._current

    def _sync_checked(self) -> None:
        for key, item in self._folders.items():
            item.setChecked(key == self._current)

    def selection_rect(self) -> QRectF:
        """The travelling surface, interpolated over the cells' LIVE rects
        so it stays on its item while the item is magnified."""
        folders = list(self._folders.values())
        lo = max(0, min(len(folders) - 1, int(math.floor(self._sel))))
        hi = min(len(folders) - 1, lo + 1)
        frac = self._sel - lo
        a = self.cell_rect_in_dock(folders[lo])
        b = self.cell_rect_in_dock(folders[hi])
        return QRectF(
            a.left() + (b.left() - a.left()) * frac,
            a.top() + (b.top() - a.top()) * frac,
            a.width() + (b.width() - a.width()) * frac,
            a.height() + (b.height() - a.height()) * frac,
        )

    # ------------------------------------------------------------------ unread

    def set_unread(self, count: int) -> None:
        count = max(0, int(count))
        if count == self._unread:
            return
        self._unread = count
        self._update_inbox_name()
        self._badges.update()

    def unread(self) -> int:
        return self._unread

    def _update_inbox_name(self) -> None:
        inbox = self._folders["inbox"]
        if self._unread:
            inbox.setAccessibleName(f"Inbox, {self._unread} unread")
            inbox.label = f"Inbox  ·  {self._unread} unread"
        else:
            inbox.setAccessibleName("Inbox")
            inbox.label = "Inbox"
        if self._label_item is inbox and self._label.isVisible():
            self._place_label(inbox)

    @staticmethod
    def badge_font() -> QFont:
        font = QFont()
        font.setFamilies(t.FONT_MONO)
        font.setPixelSize(10)
        font.setWeight(QFont.Weight(t.WEIGHT_SEMIBOLD))
        return font

    def badge_rect(self) -> QRectF:
        """Anchored to the inbox cell's top-right corner, overhanging it the
        way a count sits on an icon rather than beside it."""
        if not self._unread:
            return QRectF()
        text = badge_text(self._unread)
        metrics = QFontMetricsF(self.badge_font())
        height = 15.0
        width = max(height, metrics.horizontalAdvance(text) + 8.0)
        cell = self.cell_rect_in_dock(self._folders["inbox"])
        right = cell.right() + 5.0
        top = cell.top() - 4.0
        return QRectF(right - width, top, width, height)

    def paint_badge(self, device: QWidget) -> None:
        rect = self.badge_rect()
        if rect.isNull():
            return
        painter = QPainter(device)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = rect.height() / 2.0
        # A ring in the pill's own colour, so the badge reads as sitting ON
        # the icon rather than colliding with its outline.
        ring = rect.adjusted(-1.5, -1.5, 1.5, 1.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t.BG_PANEL))
        painter.drawRoundedRect(ring, ring.height() / 2.0, ring.height() / 2.0)
        # NEUTRAL, NOT THE ACCENT. An unread count is information, and the
        # emphasis value belongs to the one primary action on screen.
        painter.setBrush(QColor(t.TEXT_SECONDARY))
        painter.drawRoundedRect(rect, radius, radius)
        painter.setFont(self.badge_font())
        painter.setPen(QColor(t.TEXT_ON_ACCENT))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, badge_text(self._unread))
        painter.end()

    # ------------------------------------------------------------------- paint

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pill = self.pill_rect().adjusted(0.5, 0.5, -0.5, -0.5)

        # One step up the surface ramp with a hairline, and no shadow: the
        # same material as the search field beside it, so the toolbar
        # reads as one band of controls rather than a web widget pasted
        # onto it.
        painter.setPen(QPen(QColor(t.BORDER), 1.0))
        painter.setBrush(QColor(t.BG_PANEL))
        painter.drawRoundedRect(pill, float(t.RADIUS_XL), float(t.RADIUS_XL))

        # The selected folder: one surface, sliding.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t.BG_SELECTED))
        sel = self.selection_rect()
        painter.drawRoundedRect(sel, float(t.RADIUS_MD), float(t.RADIUS_MD))

        # A real divider between "where" and "do", not a gap pretending.
        x = round(self.separator_x()) + 0.5
        painter.setPen(QPen(QColor(t.BORDER_LIGHT), 1.0))
        painter.drawLine(QRectF(x, 13.0, 0.0, HEIGHT - 26.0).topLeft(),
                         QRectF(x, 13.0, 0.0, HEIGHT - 26.0).bottomLeft())
        painter.end()

    def retheme(self) -> None:
        # Glyphs are painted from tokens at paint time, so a repaint is the
        # whole of a theme switch here.
        self.update()
        self._badges.update()
        for item in self.items:
            item.update()

    # -------------------------------------------------------------- keyboard

    def focus_neighbour(self, item: DockItem, step: int) -> None:
        index = self.items.index(item)
        target = self.items[(index + step) % len(self.items)]
        target.setFocus(Qt.FocusReason.TabFocusReason)

    def focus_edge(self, *, first: bool) -> None:
        (self.items[0] if first else self.items[-1]).setFocus(
            Qt.FocusReason.TabFocusReason
        )

    def item(self, key: str) -> DockItem:
        return self._folders.get(key) or self._actions[key]

    # ------------------------------------------------------------------ labels

    def show_label_for(self, item: DockItem, *, immediate: bool = False) -> None:
        self._hide_timer.stop()
        if immediate or self._label.isVisible():
            self._label_timer.stop()
            self._place_label(item)
            return
        self._pending_label = item
        self._label_timer.start(LABEL_DELAY_MS)

    def _show_pending_label(self) -> None:
        item = self._pending_label
        if item is not None and item.underMouse():
            self._place_label(item)

    def _place_label(self, item: DockItem) -> None:
        self._label_item = item
        self._label.setText(item.label)
        self._label.adjustSize()
        cell = self.cell_rect_in_dock(item)
        anchor = self.mapToGlobal(QPoint(int(round(cell.center().x())), HEIGHT))
        self._label.move(
            anchor.x() - self._label.width() // 2, anchor.y() + t.SPACE_XS + 2
        )
        self._label.show()
        self._label.raise_()

    def hide_label_soon(self) -> None:
        self._label_timer.stop()
        self._pending_label = None
        self._hide_timer.start(LABEL_GRACE_MS)

    def _hide_label(self) -> None:
        if any(item.underMouse() for item in self.items):
            return
        if any(item.hasFocus() and item._keyboard_focus for item in self.items):
            return
        self._label.hide()
        self._label_item = None

    def label_text(self) -> str:
        return self._label.text() if self._label.isVisible() else ""

    def hideEvent(self, event) -> None:  # noqa: N802
        self._label.hide()
        super().hideEvent(event)
