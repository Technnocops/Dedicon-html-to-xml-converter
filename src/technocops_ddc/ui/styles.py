APP_STYLESHEET = """
QWidget {
    background: transparent;
    color: #edf3ff;
    font-family: "Segoe UI Variable";
    font-size: 10pt;
}
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #09111f,
        stop:0.45 #0f1c31,
        stop:1 #132844);
}
QMenuBar, QMenu {
    background: #122238;
    color: #e6eefc;
    border: 1px solid #273c5d;
}
QMenu::item:selected {
    background: #243b5d;
}
QGroupBox {
    background: rgba(13, 24, 41, 0.94);
    border: 1px solid #273c5f;
    border-radius: 18px;
    font-weight: 600;
    margin-top: 12px;
    padding: 16px 16px 14px 16px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: #8cc6ff;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #2384ff,
        stop:1 #39b2ff);
    color: white;
    border: 1px solid rgba(111, 187, 255, 0.45);
    border-radius: 11px;
    padding: 9px 15px;
    font-weight: 600;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #3a95ff,
        stop:1 #52c0ff);
}
QPushButton:pressed {
    background: #1670db;
}
QPushButton:disabled {
    background: #364b67;
    color: #9aaecb;
    border: 1px solid #415573;
}
QPushButton[variant="secondary"] {
    background: rgba(25, 43, 69, 0.92);
    color: #d9e7ff;
    border: 1px solid #35517b;
}
QPushButton[variant="secondary"]:hover {
    background: rgba(36, 58, 90, 0.95);
    border: 1px solid #4c72a7;
}
QPushButton[variant="secondary"]:pressed {
    background: #203554;
}
QLineEdit, QComboBox, QDateEdit, QSpinBox {
    background: rgba(9, 17, 30, 0.92);
    border: 1px solid #2c4567;
    border-radius: 10px;
    padding: 8px 10px;
    min-height: 22px;
    selection-background-color: #2a78d5;
    selection-color: #f4f8ff;
    color: #edf3ff;
}
QPlainTextEdit, QTextEdit, QListWidget {
    background: rgba(9, 17, 30, 0.92);
    border: 1px solid #2c4567;
    border-radius: 10px;
    padding: 8px;
    selection-background-color: #2a78d5;
    selection-color: #f4f8ff;
    color: #edf3ff;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QListWidget:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus {
    border: 1px solid #55a8ff;
}
QPlainTextEdit, QTextEdit {
    font-family: "Cascadia Mono";
}
QLineEdit[readOnly="true"], QPlainTextEdit[readOnly="true"] {
    background: rgba(7, 14, 25, 0.95);
}
QComboBox::drop-down, QDateEdit::drop-down, QSpinBox::up-button, QSpinBox::down-button {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background: #122238;
    color: #eaf2ff;
    border: 1px solid #36527a;
    selection-background-color: #27538a;
}
QListWidget {
    padding: 6px;
}
QListWidget::item {
    border-radius: 8px;
    padding: 6px 8px;
}
QListWidget::item:hover {
    background: rgba(39, 68, 105, 0.88);
}
QListWidget::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #204f8e,
        stop:1 #286ca8);
    color: #f4f8ff;
}
QProgressBar {
    background: rgba(8, 16, 28, 0.96);
    border: 1px solid #2b4565;
    border-radius: 8px;
    text-align: center;
    min-height: 18px;
    color: #e7f1ff;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #19a974,
        stop:1 #38d39f);
    border-radius: 8px;
}
QTabWidget::pane {
    border: 1px solid #2a4264;
    border-radius: 14px;
    background: rgba(12, 22, 38, 0.95);
}
QTabBar::tab {
    background: rgba(20, 35, 56, 0.95);
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    padding: 9px 15px;
    margin-right: 4px;
    color: #afc6e6;
}
QTabBar::tab:hover {
    background: rgba(32, 53, 84, 0.98);
    color: #eef4ff;
}
QTabBar::tab:selected {
    background: rgba(12, 22, 38, 0.98);
    color: #f8fbff;
}
QLabel[role="title"] {
    font-size: 15.5pt;
    font-weight: 700;
    color: #f4f8ff;
}
QLabel[role="subtitle"] {
    color: #9ab0cb;
    font-size: 9.8pt;
}
QLabel[role="section-title"] {
    color: #91cbff;
    font-size: 11pt;
    font-weight: 700;
}
QLabel[role="footer"] {
    color: #8fa6c4;
    font-size: 9pt;
}
QLabel[role="badge"] {
    background: rgba(22, 179, 123, 0.16);
    color: #98f1c6;
    border-radius: 10px;
    padding: 5px 10px;
    font-weight: 600;
    border: 1px solid rgba(66, 211, 153, 0.25);
}
QLabel[role="author-index"] {
    min-width: 64px;
    color: #89a3c6;
    font-weight: 600;
}
QLabel[role="summary-label"] {
    color: #8db2da;
    font-size: 9pt;
    font-weight: 600;
}
QLabel[role="summary-value"] {
    color: #f2f7ff;
    font-size: 10pt;
    padding-bottom: 4px;
}
QScrollArea {
    border: none;
    background: transparent;
}
QStatusBar {
    background: rgba(8, 15, 27, 0.96);
    color: #a9bfdc;
    border-top: 1px solid #243954;
}
QScrollBar:vertical {
    background: rgba(8, 16, 28, 0.96);
    width: 12px;
    margin: 2px;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background: #36547a;
    border-radius: 6px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #4670a5;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
    border: none;
}
"""
