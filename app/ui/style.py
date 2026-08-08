"""Application-wide stylesheet: dark, modern, restrained accent color use.

Redesigned to match the visual language of the project's Dribbble
reference (dark charcoal surfaces, soft card elevation, sparing accent
color) while keeping every widget class the rest of the app already
relies on (QPushButton, QLineEdit, QListView, QSplitter, etc.) styled
through plain Qt selectors - no custom widget subclassing required just
for looks. Colors are pulled from theme.py so this file and the
custom-painted delegates never disagree about what a color means.
"""

from app.ui import theme as t

STYLESHEET = f"""
* {{
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
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
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {t.ACCENT};
    selection-color: {t.TEXT_ON_ACCENT};
    color: {t.TEXT_PRIMARY};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {t.ACCENT};
}}
QLineEdit::placeholder {{ color: {t.TEXT_TERTIARY}; }}
QLineEdit#searchField {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER};
    border-radius: 15px;
    padding: 5px 10px 5px 8px;
}}
QLineEdit#searchField:focus {{ border: 1px solid {t.ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {t.TEXT_SECONDARY};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER};
    selection-background-color: {t.BG_SELECTED};
    selection-color: {t.TEXT_PRIMARY};
    outline: none;
}}

/* ---- Buttons ---- */
QPushButton {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER_LIGHT};
    border-radius: 6px;
    padding: 5px 14px;
    min-height: 20px;
    color: {t.TEXT_PRIMARY};
}}
QPushButton:hover {{ background: {t.BG_HOVER}; border-color: {t.BORDER_LIGHT}; }}
QPushButton:pressed {{ background: {t.BG_SELECTED}; }}
QPushButton:default {{
    background: {t.ACCENT};
    color: {t.TEXT_ON_ACCENT};
    border: 1px solid {t.ACCENT};
    font-weight: 600;
}}
QPushButton:default:hover {{ background: {t.ACCENT_HOVER}; border-color: {t.ACCENT_HOVER}; }}
QPushButton:default:pressed {{ background: {t.ACCENT_PRESSED}; }}
QPushButton:disabled {{ color: {t.TEXT_TERTIARY}; border-color: {t.BORDER}; background: {t.BG_PANEL}; }}
QPushButton:checkable:checked {{
    background: {t.ACCENT_SOFT_BG};
    border-color: {t.ACCENT};
    color: {t.ACCENT_HOVER};
}}

/* Flat icon-style toolbar buttons (Compose/Refresh/Console) */
QPushButton#iconButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px;
    font-weight: 500;
}}
QPushButton#iconButton:hover {{ background: {t.BG_HOVER}; }}
QPushButton#iconButton:pressed {{ background: {t.BG_SELECTED}; }}
QPushButton#iconButton:checkable:checked {{
    background: {t.ACCENT_SOFT_BG};
    color: {t.ACCENT_HOVER};
}}

/* Pill-style folder navigation (Unified Inbox / Starred / Sent / Trash) */
QPushButton#navPill {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 7px 12px;
    text-align: left;
    color: {t.TEXT_SECONDARY};
    font-weight: 500;
}}
QPushButton#navPill:hover {{ background: {t.BG_HOVER}; color: {t.TEXT_PRIMARY}; }}
QPushButton#navPill:checked {{
    background: {t.ACCENT_SOFT_BG};
    color: {t.TEXT_PRIMARY};
}}

/* Primary compose action */
QPushButton#composeButton {{
    background: {t.ACCENT};
    color: {t.TEXT_ON_ACCENT};
    border: 1px solid {t.ACCENT};
    border-radius: 6px;
    font-weight: 600;
    padding: 6px 16px;
}}
QPushButton#composeButton:hover {{ background: {t.ACCENT_HOVER}; }}
QPushButton#composeButton:pressed {{ background: {t.ACCENT_PRESSED}; }}

/* ---- Lists / trees (Settings account list, combo popups) ---- */
QTreeWidget, QListWidget, QTreeView, QTableView, QListView {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER};
    border-radius: 6px;
    outline: none;
    alternate-background-color: {t.BG_PANEL};
    color: {t.TEXT_PRIMARY};
}}
QTreeWidget::item, QListWidget::item {{
    padding: 4px 2px;
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
    padding: 4px 6px;
    font-weight: 600;
    color: {t.TEXT_SECONDARY};
}}

/* ---- Splitter ---- */
QSplitter::handle {{ background: {t.BORDER}; width: 1px; }}
QSplitter::handle:hover {{ background: {t.ACCENT}; }}

/* ---- Scrollbars ---- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {t.BORDER_LIGHT}; border-radius: 4px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {t.TEXT_TERTIARY}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {t.BORDER_LIGHT}; border-radius: 4px; min-width: 24px;
}}

/* ---- Toolbar ---- */
QToolBar {{
    background: {t.BG_APP};
    border-bottom: 1px solid {t.BORDER};
    spacing: 8px;
    padding: 10px 14px;
}}
QToolBar::separator {{ background: {t.BORDER}; width: 1px; margin: 4px 6px; }}

/* ---- Menus ---- */
QMenu {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER_LIGHT};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 5px; color: {t.TEXT_PRIMARY}; }}
QMenu::item:selected {{ background: {t.BG_SELECTED}; }}
QMenu::separator {{ height: 1px; background: {t.BORDER}; margin: 4px 8px; }}

/* ---- Progress ---- */
QProgressBar {{
    border: 1px solid {t.BORDER};
    border-radius: 6px;
    background: {t.BG_PANEL};
    text-align: center;
    min-height: 6px;
    max-height: 6px;
}}
QProgressBar::chunk {{ background: {t.ACCENT}; border-radius: 5px; }}

/* ---- Console ---- */
QPlainTextEdit#console {{
    border: 1px solid {t.BORDER};
    border-radius: 6px;
    background: {t.BG_PANEL};
    color: {t.TEXT_SECONDARY};
    font-family: "Cascadia Mono", "Consolas", "Courier New", monospace;
    font-size: 12px;
    padding: 6px;
}}

/* ---- Misc ---- */
QStatusBar {{
    background: {t.BG_APP};
    border-top: 1px solid {t.BORDER};
    color: {t.TEXT_SECONDARY};
}}
QStatusBar::item {{ border: none; }}
QLabel {{ background: transparent; }}
QLabel#secondary {{ color: {t.TEXT_SECONDARY}; }}
QLabel#tertiary {{ color: {t.TEXT_TERTIARY}; font-size: 12px; }}
QLabel#heading {{ font-size: 16px; font-weight: 700; color: {t.TEXT_PRIMARY}; }}
QLabel#sectionLabel {{
    color: {t.TEXT_TERTIARY};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}}
/* An explicit color (not "transparent") avoids a QAbstractScrollArea
   viewport-compositing quirk where a transparent background can paint
   as opaque black instead of showing the parent's color through. */
QTextBrowser {{ border: none; background: {t.BG_PANEL}; color: {t.TEXT_PRIMARY}; }}
QGroupBox {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {t.TEXT_SECONDARY};
}}
QCheckBox {{ background: transparent; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {t.BORDER_LIGHT}; border-radius: 4px;
    background: {t.BG_PANEL};
}}
QCheckBox::indicator:checked {{ background: {t.ACCENT}; border-color: {t.ACCENT}; }}
QCheckBox::indicator:hover {{ border-color: {t.ACCENT}; }}

/* ---- Tooltips ---- */
QToolTip {{
    background: {t.BG_SELECTED};
    color: {t.TEXT_PRIMARY};
    border: 1px solid {t.BORDER_LIGHT};
    border-radius: 4px;
    padding: 4px 8px;
}}

/* ---- Sidebar (account drawer) ---- */
QWidget#sidebar {{
    background: {t.BG_SIDEBAR};
    border-right: 1px solid {t.BORDER};
}}
QLabel#accountEmail {{
    color: {t.TEXT_PRIMARY};
    font-weight: 600;
}}
QLabel#unreadBadge {{
    background: {t.ACCENT};
    color: {t.TEXT_ON_ACCENT};
    border-radius: 8px;
    padding: 0px 6px;
    font-size: 11px;
    font-weight: 700;
}}

/* ---- Preview pane elevated card ---- */
QWidget#previewCard {{
    background: {t.BG_PANEL};
    border: 1px solid {t.BORDER};
    border-radius: 10px;
}}
QWidget#attachmentChip {{
    background: {t.BG_SELECTED};
    border: 1px solid {t.BORDER_LIGHT};
    border-radius: 6px;
}}
QWidget#attachmentChip QLabel {{
    color: {t.TEXT_SECONDARY};
    font-size: 12px;
}}

/* ---- Email list container ---- */
QListView#emailList {{
    background: {t.BG_APP};
    border: none;
    border-right: 1px solid {t.BORDER};
    padding: 4px;
}}
"""
