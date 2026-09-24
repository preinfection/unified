"""The top band: Compose and search on the left, the dock in the centre,
utilities on the right.

    [Compose] [search ......]        [ dock ]        [Update] [sync] [log]

WHY IT IS NOT A QToolBar ANY MORE. A QToolBar lays its widgets out in a
row and can only centre nothing; the dock has to sit on the window's
centre line whatever the two sides hold. QToolBar also brought a
right-click menu that could hide the whole band and an overflow chevron,
neither of which this app wants. It is the primitives.Toolbar band with
its children placed by hand, which is a dozen lines of arithmetic and the
only way to get a true centre.

THE SEARCH FIELD IS SIZED TO WHAT IT HOLDS. It used to expand through the
whole middle of the bar - 1,100px of empty field on a normal monitor, the
widest and most prominent object in the window on a first run with no mail
in it. A query is a few words; the field is as wide as a few words need
(up to 360px) and sits directly above the list it filters.

WHEN THE WINDOW NARROWS, THINGS GIVE WAY IN ORDER OF IMPORTANCE. The
search field shrinks first, then the dock moves off true centre rather
than overlapping anything, then Compose drops its label. Nothing is ever
clipped or pushed off the edge.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtWidgets import QLineEdit, QPushButton, QSizePolicy

from app.ui import theme as t
from app.ui.components.dock import Dock
from app.ui.components.primitives import Button, IconButton, Toolbar, Variant
from app.ui.svg_icon import simple_icon

SEARCH_MIN = 160
SEARCH_MAX = 360
# Below this, the search field stops shrinking and Compose gives up its
# label instead: a field too short to show "Search" is worse than a
# button that is only an icon.
SEARCH_FLOOR = 120


class TopToolBar(Toolbar):
    compose_clicked = Signal()
    refresh_clicked = Signal()
    console_toggled = Signal(bool)
    search_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent, manual=True)
        # A bare QWidget subclass only paints its QSS background with this.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.compose_btn = Button(" Compose", Variant.PRIMARY, parent=self)
        # Through the primitive, so the glyph is re-tinted on a theme
        # switch - set with setIcon() directly it stayed dark-mode ink on
        # the light theme's dark fill.
        self.compose_btn.set_icon("compose")
        self.compose_btn.setAccessibleName("Compose")
        self.compose_btn.clicked.connect(self.compose_clicked.emit)
        self._compose_compact = False
        self._compose_enabled = True

        self.search_edit = QLineEdit(self)
        self.search_edit.setObjectName("searchField")
        self.search_edit.setPlaceholderText("Search all accounts")
        self.search_edit.setAccessibleName("Search")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedHeight(t.HEIGHT_MD)
        self._search_icon = self.search_edit.addAction(
            simple_icon("search", 15, t.TEXT_TERTIARY),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.search_edit.textChanged.connect(self.search_changed.emit)

        self.dock = Dock(self)

        self.refresh_btn = IconButton("refresh", "Sync all accounts", parent=self)
        self.refresh_btn.clicked.connect(self.refresh_clicked.emit)

        self.console_btn = IconButton(
            "console", "Show or hide the console", checkable=True, parent=self
        )
        self.console_btn.toggled.connect(self.console_toggled.emit)

        # Extra widgets on the right (the update notice), laid out before
        # the two utilities and only while visible - an absent control
        # leaves no gap behind it.
        self._trailing: list[QPushButton] = []

        # Tab order follows reading order across the band.
        self.setTabOrder(self.compose_btn, self.search_edit)
        self.setTabOrder(self.search_edit, self.dock.items[0])
        for a, b in zip(self.dock.items, self.dock.items[1:]):
            self.setTabOrder(a, b)
        self.setTabOrder(self.dock.items[-1], self.refresh_btn)
        self.setTabOrder(self.refresh_btn, self.console_btn)

    # ----------------------------------------------------------------- layout

    def add_trailing(self, widget: QPushButton) -> None:
        """A control that sits right of centre, before the utilities."""
        widget.setParent(self)
        self._trailing.append(widget)
        self.setTabOrder(self.dock.items[-1], widget)
        self.setTabOrder(widget, self.refresh_btn)
        self.relayout()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        pad = t.SPACE_LG
        right = self._right_cluster_width()
        width = (pad + t.HEIGHT_MD + 16 + t.SPACE_LG + SEARCH_FLOOR + t.SPACE_LG
                 + self.dock.width() + t.SPACE_LG + right + pad)
        return QSize(width, t.TOOLBAR_HEIGHT)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(1280, t.TOOLBAR_HEIGHT)

    def _right_cluster_width(self) -> int:
        widgets = [w for w in self._trailing if not w.isHidden()]
        width = sum(w.sizeHint().width() for w in widgets)
        width += t.SPACE_SM * len(widgets)
        width += self.refresh_btn.width() + t.SPACE_XS + self.console_btn.width()
        return width

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.relayout()

    def event(self, event) -> bool:
        # With no layout of its own, the band is sent a LayoutRequest
        # whenever a child's size hint changes - Compose once the style
        # sheet has given it its padding, the update button appearing.
        # Placing everything again then is what keeps the arithmetic in
        # step with what the children actually measure.
        if event.type() in (QEvent.Type.LayoutRequest, QEvent.Type.StyleChange,
                            QEvent.Type.FontChange, QEvent.Type.Show):
            self.relayout()
        return super().event(event)

    def relayout(self) -> None:
        """Place the three groups. The dock is centred on the BAND, which
        spans the window, so it sits on the window's centre line."""
        W, H = self.width(), self.height()
        pad = t.SPACE_LG

        def vcentre(h: int) -> int:
            return (H - 1 - h) // 2   # -1: the hairline under the band

        # Right cluster, laid from the edge inwards.
        x_right = W - pad
        for w in (self.console_btn, self.refresh_btn):
            x_right -= w.width()
            w.move(x_right, vcentre(w.height()))
            x_right -= t.SPACE_XS
        x_right += t.SPACE_XS
        for w in reversed(self._trailing):
            if w.isHidden():
                continue
            hint = w.sizeHint()
            x_right -= t.SPACE_SM + hint.width()
            w.setGeometry(x_right, vcentre(t.HEIGHT_MD), hint.width(), t.HEIGHT_MD)
        right_edge = x_right - t.SPACE_LG     # nothing to the left may pass this

        dock_w = self.dock.width()

        def place(compact: bool) -> tuple[int, int, int]:
            compose_w = self._compose_width(compact)
            search_x = pad + compose_w + t.SPACE_LG
            dock_x = (W - dock_w) // 2
            room = dock_x - t.SPACE_LG - search_x
            search_w = max(SEARCH_MIN, min(SEARCH_MAX, room))
            if room < SEARCH_MIN:
                # Off true centre, to the right, before anything overlaps.
                dock_x = search_x + SEARCH_MIN + t.SPACE_LG
            overflow = dock_x + dock_w - right_edge
            if overflow > 0:
                dock_x -= overflow
                search_w = max(SEARCH_FLOOR, dock_x - t.SPACE_LG - search_x)
            return compose_w, search_w, dock_x

        compose_w, search_w, dock_x = place(False)
        compact = search_w <= SEARCH_FLOOR and (
            dock_x - t.SPACE_LG - (pad + compose_w + t.SPACE_LG) < SEARCH_FLOOR
        )
        if compact:
            compose_w, search_w, dock_x = place(True)
        self._set_compose_compact(compact)

        self.compose_btn.setGeometry(pad, vcentre(t.HEIGHT_MD), compose_w, t.HEIGHT_MD)
        search_x = pad + compose_w + t.SPACE_LG
        self.search_edit.setGeometry(search_x, vcentre(t.HEIGHT_MD), search_w,
                                     t.HEIGHT_MD)
        self.dock.move(dock_x, vcentre(self.dock.height()))

    def _compose_width(self, compact: bool) -> int:
        if compact:
            return t.HEIGHT_MD + 16
        return max(self.compose_btn.sizeHint().width(), 96)

    def _set_compose_compact(self, compact: bool) -> None:
        if compact == self._compose_compact:
            return
        self._compose_compact = compact
        self.compose_btn.setText("" if compact else " Compose")
        self._refresh_compose_tooltip()

    def _refresh_compose_tooltip(self) -> None:
        if not self._compose_enabled:
            tip = "Add an account before writing a message"
        elif self._compose_compact:
            tip = "Compose"
        else:
            tip = ""
        self.compose_btn.setToolTip(tip)

    # ------------------------------------------------------------------ state

    def set_compose_enabled(self, enabled: bool) -> None:
        """Compose is only an offer once there is an account to send from.

        It used to stay lit with zero accounts and answer a click with a
        modal telling the user off. A disabled control that explains itself
        on hover is the honest version of that: the interface stops
        promising something it cannot do, and nobody has to dismiss a box
        to find out.
        """
        self._compose_enabled = bool(enabled)
        self.compose_btn.setEnabled(enabled)
        self._refresh_compose_tooltip()

    def set_mailbox_available(self, available: bool) -> None:
        """Search and sync mean nothing with no account to search or sync.

        Same rule as Compose: with zero accounts the field and the sync
        button used to accept input and answer with "No results" or a
        status-bar line. They now say, on hover, what would make them work.
        """
        self.search_edit.setEnabled(available)
        self.refresh_btn.setEnabled(available)
        if available:
            self.search_edit.setToolTip("")
            self.refresh_btn.setToolTip("Sync all accounts")
        else:
            self.search_edit.setToolTip("Add an account to search")
            self.refresh_btn.setToolTip("Add an account to sync")

    def set_search_placeholder(self, text: str) -> None:
        self.search_edit.setPlaceholderText(text)

    def search_text(self) -> str:
        return self.search_edit.text().strip()

    def retheme(self) -> None:
        self._search_icon.setIcon(simple_icon("search", 15, t.TEXT_TERTIARY))
