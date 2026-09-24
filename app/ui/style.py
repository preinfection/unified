"""Application-wide stylesheet, built from the tokens in theme.py.

Every widget class the rest of the app already relies on (QPushButton,
QLineEdit, QListView, QSplitter, ...) is styled through plain Qt selectors,
so nothing has to be subclassed just for looks. Colors are pulled from
theme.py so this file and the custom-painted delegates never disagree about
what a color means.

-------------------------------------------------------------------------
WHAT CHANGED IN THE WARM-ARCHIVE PASS, AND WHY

  NO GRADIENTS. The toolbar, the sidebar and the compose button each used
  a vertical qlineargradient to fake "a lit surface". On a warm near-black
  ramp that reads as a smudge rather than as light, and a gradient-filled
  primary button is one of the most reliable tells of a generic dark theme.
  All four call sites are flat fills now; separation comes from the
  elevation ramp and a hairline, which is what actually reads.

  SELECTION IS ELEVATION, NOT HUE. Every selected state used to be an
  accent-tinted fill plus an accent border plus accent text. Now a selected
  thing sits on BG_SELECTED with primary text. It is one signal, it matches
  the delegate-painted rows exactly, and it leaves color free to mean
  something.

  THE PRIMARY BUTTON IS THE BRIGHTEST THING ON SCREEN, not the bluest:
  ACCENT is warm bone, and its label is the app floor. That is the whole
  of the emphasis system - luminance, not saturation.

  FEWER CARDS. Panels that were rounded, bordered and shadowed simply to
  look raised are now plain regions separated by a hairline. What is still
  a card is a card because it is genuinely a floating surface: menus,
  dropdown popups, toasts, dialogs.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.ui import theme as t

_arrow_cache_path: Path | None = None


def invalidate_style_cache() -> None:
    """Drop anything cached that was rendered FROM the palette.

    Called by MainWindow.set_theme_mode before rebuilding the stylesheet.
    The combo chevron is a real PNG tinted with TEXT_SECONDARY and written
    to a temp file once; without this, switching to light mode kept serving
    the dark-mode chevron - a pale grey arrow on a parchment control, which
    is the sort of single stale asset that makes a theme switch look half
    finished.
    """
    global _arrow_cache_path
    _arrow_cache_path = None


def _combo_arrow_url() -> str:
    """A real tinted chevron PNG for QComboBox's down-arrow, referenced by
    file path rather than drawn via QSS's border-triangle trick - Qt's
    style engine only partially honors a styled QComboBox's native arrow
    primitive (Fusion silently drops it once any subcontrol is QSS'd), so
    an explicit image is the only reliable way to get one back.

    Deferred until first call (not import time): rendering the pixmap
    needs a live QApplication, which does not exist yet when this module
    is first imported in app/main.py.
    """
    global _arrow_cache_path
    if _arrow_cache_path is not None:
        return _arrow_cache_path.as_posix()

    from app.ui.svg_icon import tinted_pixmap

    # Named per mode, not one shared file: Qt caches images it has loaded
    # from a URL, so re-writing the same path with different pixels can
    # leave the old arrow on screen until something evicts it.
    path = Path(tempfile.gettempdir()) / f"unified_combo_arrow_{t.MODE}.png"
    tinted_pixmap("chevron_down", 16, t.TEXT_SECONDARY).save(str(path), "PNG")
    _arrow_cache_path = path
    return path.as_posix()


def get_stylesheet() -> str:
    """Built lazily (call after QApplication exists), not as a module
    constant - see _combo_arrow_url."""
    arrow_url = _combo_arrow_url()
    return f"""
/* NO font-family AND NO font-size HERE. A stylesheet font overrides
   QWidget.setFont(), so a universal rule setting them silently flattened
   every make_font() call in the application to 13px - see the long note in
   app/main.py, which now sets the default font on QApplication instead.
   Only color is universal; type is a widget's own business. */
* {{
    color: {t.TEXT_PRIMARY};
}}

QWidget {{
    background: transparent;
    color: {t.TEXT_PRIMARY};
}}
/* Must come AFTER the QWidget rule above: Qt's stylesheet cascade treats
   "QMainWindow, QDialog" and "QWidget" as equal specificity here and
   breaks the tie by text order, not by subclass depth. With QWidget's
   "background: transparent" listed second it wins, and a transparent
   top-level QDialog/QMainWindow paints as opaque black instead of
   showing through - any gap not covered by a specifically-styled child
   widget (e.g. bare space between a QFormLayout row and a
   QDialogButtonBox) renders as a black hole instead of the app
   background. Listing it second here makes the real background win. */
QMainWindow, QDialog {{
    background: {t.BG_APP};
}}
/* QStackedWidget's page container doesn't reliably composite a
   "transparent" background through to the dialog behind it (the same
   viewport-compositing quirk QAbstractScrollArea widgets show) - give it
   an explicit color instead. */
QStackedWidget {{ background: {t.BG_APP}; }}

/* ---- Inputs ---- */
/* Focus is a full border in the parchment accent, not a colored glow: it
   is the brightest edge on screen at that moment, which is exactly what a
   focus ring should be, and it costs no hue. */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_SM}px;
    padding: 6px 9px;
    selection-background-color: {t.BG_SELECTED};
    selection-color: {t.TEXT_PRIMARY};
    color: {t.TEXT_PRIMARY};
}}
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover,
QSpinBox:hover, QComboBox:hover {{ border-color: {t.BORDER_LIGHT}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {t.ACCENT};
    background: {t.BG_HOVER};
}}
QLineEdit::placeholder {{ color: {t.TEXT_TERTIARY}; }}
/* NOT a pill. A fully-rounded search field is a web pattern that reads as
   decoration in a desktop toolbar; it now matches every other input in the
   app, which is the point of having one form-control vocabulary. */
QLineEdit#searchField {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_SM}px;
    padding: 6px 10px 6px 8px;
}}
QLineEdit#searchField:hover {{ border-color: {t.BORDER_LIGHT}; }}
QLineEdit#searchField:focus {{ border: 1px solid {t.ACCENT}; background: {t.BG_HOVER}; }}
/* Disabled with no account to search: an outline on the band, not a
   field that looks ready to take a query. */
QLineEdit#searchField:disabled {{
    background: transparent;
    border-color: {t.BORDER};
    color: {t.TEXT_TERTIARY};
}}
QComboBox::drop-down {{ border: none; width: 22px; background: transparent; }}
QComboBox::down-arrow {{
    image: url({arrow_url});
    width: 11px;
    height: 11px;
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: {t.BG_OVERLAY};
    border: 1px solid {t.BORDER_LIGHT};
    selection-background-color: {t.BG_SELECTED};
    selection-color: {t.TEXT_PRIMARY};
    outline: none;
}}

/* ---- Custom Dropdown (components/dropdown.py) ---- */
QWidget#dropdownButton {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_SM}px;
}}
QWidget#dropdownButton:hover {{ border-color: {t.BORDER_LIGHT}; background: {t.BG_HOVER}; }}
QFrame#dropdownPopup {{
    background: {t.BG_OVERLAY};
    border: 1px solid {t.BORDER_LIGHT};
    border-radius: {t.RADIUS_LG}px;
}}
QPushButton#dropdownOption {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {t.RADIUS_XS}px;
    padding: 7px 10px;
    text-align: left;
    color: {t.TEXT_SECONDARY};
    font-weight: {t.WEIGHT_REGULAR};
}}
QPushButton#dropdownOption:hover {{ background: {t.BG_HOVER}; color: {t.TEXT_PRIMARY}; }}
QPushButton#dropdownOption[selected="true"] {{
    background: {t.BG_SELECTED};
    color: {t.TEXT_PRIMARY};
    font-weight: {t.WEIGHT_MEDIUM};
}}

/* ---- Buttons ---- */
/* Secondary buttons are quiet: no fill at rest, a hairline, and they earn
   a surface on hover. Only ONE button on any given screen is filled. */
QPushButton {{
    background: transparent;
    border: 1px solid {t.BORDER_LIGHT};
    border-radius: {t.RADIUS_SM}px;
    padding: 7px 16px;
    min-height: {t.HEIGHT_MD - 16}px;
    color: {t.TEXT_PRIMARY};
    font-weight: {t.WEIGHT_MEDIUM};
}}
QPushButton:hover {{ background: {t.BG_HOVER}; border-color: {t.TEXT_TERTIARY}; }}
QPushButton:pressed {{ background: {t.BG_PANEL}; }}
QPushButton:focus {{ border-color: {t.ACCENT}; }}
/* The one filled button: parchment fill, app-floor label, 16.1:1. */
QPushButton:default {{
    background: {t.ACCENT};
    color: {t.TEXT_ON_ACCENT};
    border: 1px solid {t.ACCENT};
    font-weight: {t.WEIGHT_SEMIBOLD};
}}
QPushButton:default:hover {{ background: {t.ACCENT_HOVER}; border-color: {t.ACCENT_HOVER}; }}
QPushButton:default:pressed {{ background: {t.ACCENT_PRESSED}; border-color: {t.ACCENT_PRESSED}; }}
QPushButton:disabled {{
    color: {t.TEXT_TERTIARY}; border-color: {t.BORDER}; background: transparent;
}}
QPushButton:default:disabled {{
    background: {t.BG_SELECTED}; color: {t.TEXT_TERTIARY}; border-color: {t.BORDER};
}}
QPushButton:checkable:checked {{
    background: {t.BG_SELECTED};
    border-color: {t.BORDER_LIGHT};
    color: {t.TEXT_PRIMARY};
}}

/* ---- The primitive vocabulary (components/primitives.py) ----
   ONE BUTTON WITH NAMED VARIANTS, and this block is the reason it can
   exist. Before it, a screen that wanted a quiet button made a bare
   QPushButton, a screen that wanted a loud one reached for
   objectName="composeButton", and the empty state accidentally wore the
   compose action's identity because that was the only filled style with a
   name. State handling now lives here once per variant instead of being
   re-derived per call site.

   ONE PRIMARY PER SCREEN. Only btn-primary is filled; everything else
   earns contrast on hover. */
/* The fill and border are painted in Button.paintEvent so they can be
   animated - QSS cannot tween, and an un-tweened :pressed swap is a
   flicker rather than a press. What stays here is everything Qt still
   lays out: the label colour, the metrics and the focus ring. A
   background here as well would be a second, static fill drawn underneath
   the animated one. */
QPushButton#btn-primary {{
    background: transparent;
    color: {t.TEXT_ON_ACCENT};
    /* A TRANSPARENT BORDER, NOT NO BORDER, and the difference was two
       visible pixels. The fill is painted in Button.paintEvent so QSS must
       not draw a second one - but `border: none` also removes the border
       from the box model, which made the primary button 30px tall while
       every other button was 32. "Cancel" and "Save" sat two pixels out of
       line in every dialog in the app. Transparent keeps the metrics and
       still lets the painted fill through. */
    border: 1px solid transparent;
    border-radius: {t.RADIUS_SM}px;
    padding: 7px 16px;
    min-height: {t.HEIGHT_MD - 16}px;
    font-weight: {t.WEIGHT_SEMIBOLD};
}}
QPushButton#btn-primary:hover {{
    background: {t.ACCENT_HOVER}; border-color: {t.ACCENT_HOVER};
}}
QPushButton#btn-primary:pressed {{
    background: {t.ACCENT_PRESSED}; border-color: {t.ACCENT_PRESSED};
}}
/* The focus ring on a filled button has to sit OUTSIDE the fill, or it is
   invisible against it. A darker outline reads on parchment. */
QPushButton#btn-primary:focus {{ border: 1px solid {t.TEXT_ON_ACCENT}; }}
QPushButton#btn-primary:disabled {{
    background: {t.BG_SELECTED}; color: {t.TEXT_TERTIARY}; border-color: {t.BORDER};
}}

QPushButton#btn-secondary {{
    background: transparent;
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER_LIGHT};
    border-radius: {t.RADIUS_SM}px;
    padding: 7px 16px;
    min-height: {t.HEIGHT_MD - 16}px;
    font-weight: {t.WEIGHT_MEDIUM};
}}
QPushButton#btn-secondary:hover {{
    background: {t.BG_HOVER}; border-color: {t.TEXT_TERTIARY};
}}
QPushButton#btn-secondary:pressed {{ background: {t.BG_PANEL}; }}
QPushButton#btn-secondary:focus {{ border-color: {t.ACCENT}; }}
QPushButton#btn-secondary:disabled {{
    color: {t.TEXT_TERTIARY}; border-color: {t.BORDER};
}}

/* No border at rest: for inline and toolbar actions, where a row of
   bordered buttons would read as a row of boxes. */
/* Tighter horizontally than the bordered variants, and only there: a
   ghost has no edge, so the same 16px would leave it looking detached
   from whatever it sits beside. The vertical metrics are identical, so it
   still shares a baseline with them. */
QPushButton#btn-ghost {{
    background: transparent;
    color: {t.TEXT_SECONDARY};
    border: 1px solid transparent;
    border-radius: {t.RADIUS_SM}px;
    padding: 7px 12px;
    min-height: {t.HEIGHT_MD - 16}px;
    font-weight: {t.WEIGHT_MEDIUM};
}}
QPushButton#btn-ghost:hover {{ background: {t.BG_HOVER}; color: {t.TEXT_PRIMARY}; }}
QPushButton#btn-ghost:pressed {{ background: {t.BG_PANEL}; }}
QPushButton#btn-ghost:focus {{ border-color: {t.ACCENT}; color: {t.TEXT_PRIMARY}; }}
QPushButton#btn-ghost:disabled {{ color: {t.TEXT_TERTIARY}; }}
QPushButton#btn-ghost:checked {{
    background: {t.BG_SELECTED}; color: {t.TEXT_PRIMARY};
}}

/* Destructive is the error hue and NOT a filled red slab: a filled red
   button is the loudest thing on any screen it appears on, which is the
   wrong emphasis for an action nobody should be encouraged toward. It
   states its consequence in its label color and fills only on hover, at
   the moment the pointer is already committed. */
QPushButton#btn-destructive {{
    background: transparent;
    color: {t.DESTRUCTIVE};
    border: 1px solid {t.BORDER_LIGHT};
    border-radius: {t.RADIUS_SM}px;
    padding: 7px 16px;
    min-height: {t.HEIGHT_MD - 16}px;
    font-weight: {t.WEIGHT_MEDIUM};
}}
QPushButton#btn-destructive:hover {{
    background: {t.DESTRUCTIVE}; color: {t.TEXT_ON_ACCENT};
    border-color: {t.DESTRUCTIVE};
}}
QPushButton#btn-destructive:pressed {{
    background: {t.DESTRUCTIVE_HOVER}; border-color: {t.DESTRUCTIVE_HOVER};
}}
QPushButton#btn-destructive:focus {{ border-color: {t.DESTRUCTIVE}; }}
QPushButton#btn-destructive:disabled {{
    color: {t.TEXT_TERTIARY}; border-color: {t.BORDER};
}}

QPushButton#btn-icon {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {t.RADIUS_SM}px;
    padding: 0;
}}
QPushButton#btn-icon:hover {{ background: {t.BG_HOVER}; }}
QPushButton#btn-icon:pressed {{ background: {t.BG_PANEL}; }}
QPushButton#btn-icon:focus {{ border-color: {t.ACCENT}; }}
QPushButton#btn-icon:checked {{
    background: {t.BG_SELECTED}; border-color: {t.BORDER_LIGHT};
}}
/* ONE SIGNAL PER STATE. A toggle whose GLYPH changes - the star going
   from outline to filled, and from ink to the starred amber - is already
   saying that it is on. Adding the checked surface underneath turned the
   starred button into a small filled amber block: the loudest object on
   the reading pane, louder than the primary action, reporting a state the
   icon had already reported. Buttons that carry their state in the glyph
   opt out of the surface with this property. */
QPushButton#btn-icon[toggles-glyph="true"]:checked {{
    background: transparent; border-color: transparent;
}}
QPushButton#btn-icon[toggles-glyph="true"]:checked:hover {{
    background: {t.BG_HOVER};
}}

QLabel#badge {{
    background: {t.BG_SELECTED};
    color: {t.TEXT_SECONDARY};
    border-radius: {t.RADIUS_PILL}px;
    padding: 1px 7px;
    font-family: {t.FONT_MONO_CSS};
}}
QFrame#rule {{ background: {t.BORDER}; border: none; }}
QWidget#toolbarBand {{
    background: {t.BG_SIDEBAR};
    border: none;
    border-bottom: 1px solid {t.BORDER};
}}
/* A field that failed validation states it on its own edge as well as in
   its hint line, because a hint under a long form is easy to miss. */
QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"],
QComboBox[invalid="true"], QSpinBox[invalid="true"] {{
    border-color: {t.DESTRUCTIVE};
}}

/* ---- Dock (components/dock.py) ----
   The dock paints its own pill, cells and selection from tokens; only its
   floating label is a styled widget. It matches the tooltip exactly, so a
   dock label and a tooltip elsewhere read as the same thing. */
QLabel#dockLabel {{
    background: {t.BG_OVERLAY};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER_LIGHT};
    border-radius: {t.RADIUS_SM}px;
    padding: 4px 9px;
}}

/* Primary compose action. Flat parchment, no gradient, no glow. */
QPushButton#composeButton {{
    background: {t.ACCENT};
    color: {t.TEXT_ON_ACCENT};
    border: 1px solid {t.ACCENT};
    border-radius: {t.RADIUS_SM}px;
    font-weight: {t.WEIGHT_SEMIBOLD};
    padding: 8px 18px;
    min-height: {t.HEIGHT_MD - 16}px;
}}
QPushButton#composeButton:hover {{ background: {t.ACCENT_HOVER}; border-color: {t.ACCENT_HOVER}; }}
QPushButton#composeButton:pressed {{ background: {t.ACCENT_PRESSED}; border-color: {t.ACCENT_PRESSED}; }}
QPushButton#composeButton:disabled {{
    background: {t.BG_SELECTED}; color: {t.TEXT_TERTIARY}; border-color: {t.BORDER};
}}

/* Retired: the animated primary fill is now primitives.Button(PRIMARY),
   so every primary action in the app shares one press behaviour instead
   of two vocabularies disagreeing about it. Kept as a no-op shell only in
   case an out-of-tree widget still carries the name. */
QPushButton#accentButton {{
    background: transparent;
    border: none;
    border-radius: {t.RADIUS_SM}px;
    padding: 8px 20px;
    color: {t.TEXT_ON_ACCENT};
    font-weight: {t.WEIGHT_SEMIBOLD};
}}
QPushButton#accentButton:disabled {{ color: {t.TEXT_TERTIARY}; }}

/* ---- Lists / trees (Settings account list, combo popups) ---- */
QTreeWidget, QListWidget, QTreeView, QTableView, QListView {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_SM}px;
    outline: none;
    alternate-background-color: {t.BG_PANEL};
    color: {t.TEXT_PRIMARY};
}}
QTreeWidget::item, QListWidget::item {{
    padding: 5px 3px;
    border: none;
}}
QTreeWidget::item:selected, QListWidget::item:selected {{
    background: {t.BG_SELECTED};
    color: {t.TEXT_PRIMARY};
}}
QTreeWidget::item:hover, QListWidget::item:hover {{
    background: {t.BG_HOVER};
}}
QHeaderView::section {{
    background: {t.BG_PANEL};
    border: none;
    border-bottom: 1px solid {t.BORDER};
    padding: 5px 6px;
    font-weight: {t.WEIGHT_SEMIBOLD};
    color: {t.TEXT_TERTIARY};
}}

/* ---- Splitter ---- */
/* The hover state is a lighter hairline, not the accent: dragging a pane
   divider is not a state worth spending the app's brightest value on. */
QSplitter::handle {{ background: {t.BORDER}; width: 1px; }}
QSplitter::handle:hover {{ background: {t.BORDER_LIGHT}; }}

/* ---- Scrollbars ---- */
/* Slim and quiet, so a scrollbar never claims a visible strip of the
   reading pane while nothing is being scrolled. */
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {t.BORDER_LIGHT}; border-radius: {t.RADIUS_XS}px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {t.TEXT_TERTIARY}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {t.BORDER_LIGHT}; border-radius: {t.RADIUS_XS}px; min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{ background: {t.TEXT_TERTIARY}; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- Toolbar ----
   The top band is primitives.Toolbar (#toolbarBand, styled above), not a
   QToolBar: it has to centre the dock, which a QToolBar cannot. */

/* ---- Menus ---- */
QMenu {{
    background: {t.BG_OVERLAY};
    border: 1px solid {t.BORDER_LIGHT};
    border-radius: {t.RADIUS_LG}px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 26px 7px 14px;
    border-radius: {t.RADIUS_XS}px;
    color: {t.TEXT_SECONDARY};
}}
QMenu::item:selected {{ background: {t.BG_SELECTED}; color: {t.TEXT_PRIMARY}; }}
QMenu::separator {{ height: 1px; background: {t.BORDER}; margin: 6px 10px; }}

/* ---- Progress ---- */
/* Parchment, not a colored bar: progress is not a verdict, and the three
   verdict colors are spoken for. */
QProgressBar {{
    border: none;
    border-radius: {t.RADIUS_XS}px;
    background: {t.BG_SELECTED};
    text-align: center;
    min-height: 3px;
    max-height: 3px;
}}
QProgressBar::chunk {{ background: {t.ACCENT}; border-radius: {t.RADIUS_XS}px; }}

/* ---- Console (console.py) ----
   A title strip on the chrome surface, one hairline, and the log on the
   app floor - the same two surfaces and one line as the toolbar above the
   list. The filters are a row of quiet chips whose checked state is the
   raised step, exactly like every other selection in the app; they were
   pills with a 999px radius, which Qt renders as square corners. */
QWidget#consolePanel {{ background: {t.BG_APP}; }}
QWidget#consoleStrip {{
    background: {t.BG_SIDEBAR};
    border: none;
    border-bottom: 1px solid {t.BORDER};
}}
QPushButton#consoleFilter {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {t.RADIUS_SM}px;
    padding: 3px 9px;
    min-height: 16px;
    font-weight: {t.WEIGHT_MEDIUM};
    color: {t.TEXT_TERTIARY};
}}
QPushButton#consoleFilter:hover {{ background: {t.BG_HOVER}; color: {t.TEXT_PRIMARY}; }}
QPushButton#consoleFilter:checked {{
    background: {t.BG_SELECTED};
    color: {t.TEXT_PRIMARY};
}}
QPushButton#consoleFilter:focus {{ border-color: {t.FOCUS_RING}; }}
QPushButton#consoleAction {{
    background: transparent;
    color: {t.TEXT_SECONDARY};
    border: 1px solid transparent;
    border-radius: {t.RADIUS_SM}px;
    padding: 3px 10px;
    min-height: 16px;
    font-weight: {t.WEIGHT_MEDIUM};
}}
QPushButton#consoleAction:hover {{ background: {t.BG_HOVER}; color: {t.TEXT_PRIMARY}; }}
QPushButton#consoleAction:focus {{ border-color: {t.FOCUS_RING}; }}
QTextEdit#console {{
    border: none;
    border-radius: 0;
    background: {t.BG_APP};
    color: {t.TEXT_SECONDARY};
    padding: 0;
    selection-background-color: {t.BG_SELECTED};
    selection-color: {t.TEXT_PRIMARY};
}}
QTextEdit#console:focus {{ border: none; background: {t.BG_APP}; }}

/* ---- Misc ---- */
/* min-height, not just padding: the status line was being clipped against
   the bottom of the window - the last message ("Recovered mailbox after an
   interrupted session") rendered with its descenders cut off. A status bar
   that cannot show a whole sentence is worse than none. */
QStatusBar {{
    background: {t.BG_SIDEBAR};
    border-top: 1px solid {t.BORDER};
    color: {t.TEXT_TERTIARY};
    padding: 0 {t.SPACE_LG}px;
    min-height: 30px;
}}
QStatusBar QLabel {{ color: {t.TEXT_TERTIARY}; }}
QStatusBar::item {{ border: none; }}
QLabel {{ background: transparent; }}

/* ---- Text roles ----
   THE REASON THEME SWITCHING WORKS AT ALL. Thirty-odd labels across the
   app used to carry their colour as an inline
   `setStyleSheet(f"color: {{t.TEXT_TERTIARY}}")`, which bakes whichever
   palette was bound at construction into the widget forever. Re-applying
   the application stylesheet - the whole mechanism for changing theme -
   cannot reach an inline rule, because an inline stylesheet outranks it.
   Switching to light mode therefore left every one of those labels still
   painted in dark-mode ink.

   A dynamic property instead of an objectName, because objectName is
   already spoken for by component identity (#searchField, #navPill) and a
   widget needs to be able to say what it IS and how loud it is at the same
   time. Qt re-evaluates these on every setStyleSheet, so a role-tagged
   label re-colours itself for free. */
QLabel[role="primary"] {{ color: {t.TEXT_PRIMARY}; }}
QLabel[role="secondary"] {{ color: {t.TEXT_SECONDARY}; }}
QLabel[role="tertiary"] {{ color: {t.TEXT_TERTIARY}; }}
QLabel[role="danger"] {{ color: {t.DESTRUCTIVE}; }}
QLabel[role="warning"] {{ color: {t.WARNING}; }}
QLabel[role="success"] {{ color: {t.SUCCESS}; }}
QLabel[role="on-accent"] {{ color: {t.TEXT_ON_ACCENT}; }}

QLabel#secondary {{ color: {t.TEXT_SECONDARY}; }}
QLabel#tertiary {{ color: {t.TEXT_TERTIARY}; font-size: {t.SIZE_SM}px; }}
QLabel#heading {{
    font-size: {t.SIZE_XL}px;
    font-weight: {t.WEIGHT_SEMIBOLD};
    color: {t.TEXT_PRIMARY};
}}
QLabel#sectionLabel {{
    color: {t.TEXT_TERTIARY};
    font-size: {t.SIZE_XS}px;
    font-weight: {t.WEIGHT_SEMIBOLD};
    letter-spacing: 1.1px;
}}
QLabel#mono {{
    font-family: {t.FONT_MONO_CSS};
    color: {t.TEXT_TERTIARY};
    font-size: {t.SIZE_SM}px;
}}
/* An explicit color (not "transparent") avoids a QAbstractScrollArea
   viewport-compositing quirk where a transparent background can paint
   as opaque black instead of showing the parent's color through. */
QTextBrowser {{
    border: none;
    background: {t.BG_APP};
    color: {t.TEXT_PRIMARY};
    padding: 14px 16px;
}}
/* THE READING PANE IS A PAGE. No card, no border, no radius, no shadow:
   the message body sits directly on the app floor with generous padding,
   and html_view.py caps the measure so a line never runs past ~72
   characters. A bordered rounded box around body text is a container
   pretending to be a document. */
QTextBrowser#emailBody {{
    border: none;
    background: {t.BG_APP};
    padding: {t.SPACE_XL}px {t.SPACE_XL}px;
}}
QGroupBox {{
    background: transparent;
    border: none;
    border-top: 1px solid {t.BORDER};
    margin-top: 14px;
    padding-top: 14px;
    font-weight: {t.WEIGHT_SEMIBOLD};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 0px;
    padding: 0 8px 0 0;
    color: {t.TEXT_TERTIARY};
    font-size: {t.SIZE_XS}px;
    letter-spacing: 1.1px;
}}
QCheckBox {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {t.BORDER_LIGHT}; border-radius: {t.RADIUS_XS}px;
    background: {t.BG_PANEL};
}}
QCheckBox::indicator:checked {{ background: {t.ACCENT}; border-color: {t.ACCENT}; }}
QCheckBox::indicator:hover {{ border-color: {t.TEXT_TERTIARY}; }}

/* ---- Tooltips ---- */
QToolTip {{
    background: {t.BG_OVERLAY};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER_LIGHT};
    border-radius: {t.RADIUS_SM}px;
    padding: 5px 9px;
}}

/* ---- Sidebar (account drawer) ---- */
QWidget#sidebar {{
    background: {t.BG_SIDEBAR};
    border: none;
    border-right: 1px solid {t.BORDER};
}}
/* Account rows. Selected is the raised step and nothing else, exactly
   like a selected message row - one signal per state. A property, not an
   inline stylesheet, so a theme switch reaches it. The focus ring shows
   for the keyboard only: the rows take focus from Tab, never from a
   click. */
QWidget#accountItem {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {t.RADIUS_MD}px;
}}
QWidget#accountItem:hover {{ background: {t.BG_HOVER}; }}
QWidget#accountItem[selected="true"] {{ background: {t.BG_SELECTED}; }}
QWidget#accountItem:focus {{ border-color: {t.FOCUS_RING}; }}
QLabel#accountEmail {{
    color: {t.TEXT_PRIMARY};
    font-weight: {t.WEIGHT_MEDIUM};
}}
/* A count, so it is set in the mono face and reads as a value. Not filled
   with the accent: an unread count is information, not the primary action
   on the screen, and a bright chip per account would be four of them. */
QLabel#unreadBadge {{
    background: {t.BG_SELECTED};
    color: {t.TEXT_SECONDARY};
    border-radius: {t.RADIUS_PILL}px;
    padding: 1px 7px;
    font-family: {t.FONT_MONO_CSS};
    font-size: {t.SIZE_XS}px;
    font-weight: {t.WEIGHT_SEMIBOLD};
}}

/* ---- Preview pane ---- */
/* THE READING PANE IS ONE SURFACE. The header, the action row and the
   body all sit on the app floor and are divided by hairlines, not by
   nested bordered boxes. What was here before was a card inside a card:
   a rounded, bordered, drop-shadowed header block stacked on a rounded,
   bordered, drop-shadowed body block - which in light mode read as two
   white slabs floating on parchment. */
QWidget#previewHeader, QWidget#previewActions {{
    background: transparent;
    border: none;
}}
/* Kept for any caller still naming the old block. */
QWidget#previewCard {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {t.BORDER};
}}
/* Privacy notice shown when a message's remote images were withheld.
   This one IS bordered: it is an interruption in the reading flow and has
   to read as inserted rather than as part of the message. */
QWidget#blockedImagesBar {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER_LIGHT};
    border-radius: {t.RADIUS_SM}px;
}}

QWidget#attachmentChip {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_SM}px;
}}
QWidget#attachmentChip:hover {{ border-color: {t.BORDER_LIGHT}; }}
QWidget#attachmentChip QLabel {{
    color: {t.TEXT_SECONDARY};
    font-size: {t.SIZE_SM}px;
}}

/* ---- Email list container ---- */
QListView#emailList {{
    background: {t.BG_APP};
    border: none;
    border-right: 1px solid {t.BORDER};
    padding: {t.SPACE_XS}px {t.SPACE_SM}px;
}}

/* ---- Compose ---- */
/* Label-left field rows with a bottom rule instead of a full box border -
   the "borderless field, divider between rows" pattern real mail
   composers use instead of stacking boxed QLineEdits. */
QLineEdit#composeField, QComboBox#composeField {{
    background: transparent;
    border: none;
    border-radius: 0;
    padding: {t.SPACE_XS}px 0;
}}
QLineEdit#composeField:focus, QComboBox#composeField:focus {{
    background: transparent;
    border: none;
}}
QWidget#composeFieldRow {{
    border-bottom: 1px solid {t.BORDER};
}}
QWidget#composeFields {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {t.BORDER};
    border-radius: 0;
}}
/* No padding at all: the body's first character has to land on the same
   x as the "From"/"To"/"Subject" captions, and QPlainTextEdit already adds
   a document margin of its own on top of anything set here (zeroed in
   compose_dialog.py, since QSS cannot reach it). No font-size either - the
   widget asks for the reading preset with setFont, and a size here would
   override it exactly the way the old universal rule did. */
QPlainTextEdit#composeBody {{
    background: transparent;
    border: none;
    padding: 0;
}}

/* ---- Settings ---- */
QWidget#settingsPanel {{
    background: transparent;
    border: none;
}}
QWidget#settingsRow {{
    background: transparent;
    border-bottom: 1px solid {t.BORDER};
}}
QSpinBox#settingsControl {{
    background: {t.BG_PANEL};
    min-width: 90px;
}}
QToolButton#settingsRailItem {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {t.RADIUS_MD}px;
    padding: 10px 4px;
    color: {t.TEXT_SECONDARY};
    font-weight: {t.WEIGHT_MEDIUM};
}}
QToolButton#settingsRailItem:hover {{ background: {t.BG_HOVER}; color: {t.TEXT_PRIMARY}; }}
QToolButton#settingsRailItem:checked {{
    background: {t.BG_SELECTED};
    border: 1px solid transparent;
    color: {t.TEXT_PRIMARY};
}}
"""
