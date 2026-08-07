"""Application-wide stylesheet: plain black and white, thin borders, 4-6px radii."""

STYLESHEET = """
* {
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
    color: #111111;
}

QMainWindow, QDialog, QWidget {
    background: #ffffff;
}

/* ---- Inputs ---- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {
    background: #ffffff;
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    padding: 4px 6px;
    selection-background-color: #111111;
    selection-color: #ffffff;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QComboBox:focus {
    border: 1px solid #555555;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #555555;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #c8c8c8;
    selection-background-color: #eeeeee;
    selection-color: #111111;
}

/* ---- Buttons ---- */
QPushButton {
    background: #ffffff;
    border: 1px solid #b4b4b4;
    border-radius: 4px;
    padding: 4px 14px;
    min-height: 20px;
}
QPushButton:hover { background: #f2f2f2; }
QPushButton:pressed { background: #e4e4e4; }
QPushButton:default {
    background: #111111;
    color: #ffffff;
    border: 1px solid #111111;
}
QPushButton:default:hover { background: #333333; }
QPushButton:disabled { color: #999999; border-color: #dddddd; }

/* ---- Lists / trees ---- */
QTreeWidget, QListWidget, QTreeView, QTableView {
    background: #ffffff;
    border: 1px solid #d6d6d6;
    border-radius: 4px;
    outline: none;
    alternate-background-color: #fafafa;
}
QTreeWidget::item, QListWidget::item {
    padding: 4px 2px;
    border: none;
}
QTreeWidget::item:selected, QListWidget::item:selected {
    background: #e8e8e8;
    color: #111111;
}
QTreeWidget::item:hover, QListWidget::item:hover {
    background: #f4f4f4;
}
QHeaderView::section {
    background: #ffffff;
    border: none;
    border-bottom: 1px solid #d6d6d6;
    border-right: 1px solid #eeeeee;
    padding: 4px 6px;
    font-weight: 600;
}

/* ---- Splitter ---- */
QSplitter::handle { background: #e2e2e2; width: 1px; }

/* ---- Scrollbars ---- */
QScrollBar:vertical {
    background: transparent; width: 10px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #cccccc; border-radius: 4px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #aaaaaa; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar:horizontal {
    background: transparent; height: 10px; margin: 0;
}
QScrollBar::handle:horizontal {
    background: #cccccc; border-radius: 4px; min-width: 24px;
}

/* ---- Toolbar ---- */
QToolBar {
    background: #ffffff;
    border-bottom: 1px solid #d6d6d6;
    spacing: 6px;
    padding: 6px;
}

/* ---- Menus ---- */
QMenu {
    background: #ffffff;
    border: 1px solid #c8c8c8;
    padding: 2px;
}
QMenu::item { padding: 5px 24px 5px 12px; border-radius: 3px; }
QMenu::item:selected { background: #eeeeee; }

/* ---- Progress ---- */
QProgressBar {
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    background: #ffffff;
    text-align: center;
    min-height: 14px;
    max-height: 14px;
}
QProgressBar::chunk { background: #111111; border-radius: 3px; }

/* ---- Console ---- */
QPlainTextEdit#console {
    border: 1px solid #c8c8c8;
    border-radius: 0;
    background: #ffffff;
    color: #222222;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    padding: 2px;
}

/* ---- Misc ---- */
QStatusBar {
    background: #ffffff;
    border-top: 1px solid #d6d6d6;
    color: #555555;
}
QLabel#secondary { color: #666666; }
QLabel#heading { font-size: 15px; font-weight: 600; }
QTextBrowser { border: none; }
QGroupBox {
    border: 1px solid #d6d6d6;
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    font-weight: 600;
}
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #b4b4b4; border-radius: 3px;
    background: #ffffff;
}
QCheckBox::indicator:checked { background: #111111; border-color: #111111; }
"""
