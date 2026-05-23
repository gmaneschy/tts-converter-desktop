"""
ui/theme.py — paleta e QSS para o TTS Converter.
Estética: dark industrial/utilitarian com acentos âmbar.
"""

PALETTE = {
    "bg0":       "#0f0f0f",   # fundo raiz
    "bg1":       "#171717",   # painéis
    "bg2":       "#1f1f1f",   # inputs / cards
    "bg3":       "#2a2a2a",   # hover / bordas ativas
    "border":    "#2e2e2e",
    "border_hi": "#4a4a4a",
    "accent":    "#c8922a",   # âmbar
    "accent_lo": "#7a5418",
    "accent_hi": "#e0a83a",
    "text":      "#d4d0c8",
    "text_dim":  "#6e6a62",
    "text_lo":   "#3e3a32",
    "danger":    "#b04040",
    "success":   "#4a8c5c",
}

QSS = """
/* ── Root ──────────────────────────────────────────── */
QMainWindow, QWidget#root {
    background: %(bg0)s;
}

QWidget {
    color: %(text)s;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 12px;
}

/* ── Panels ─────────────────────────────────────────── */
QFrame#panel {
    background: %(bg1)s;
    border: 1px solid %(border)s;
    border-radius: 4px;
}

QLabel#section_title {
    color: %(accent)s;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 2px;
    text-transform: uppercase;
    padding: 0 0 4px 0;
}

QLabel#status_label {
    color: %(text_dim)s;
    font-size: 11px;
    padding: 4px 0;
}

/* ── Text area ──────────────────────────────────────── */
QPlainTextEdit {
    background: %(bg2)s;
    border: 1px solid %(border)s;
    border-radius: 3px;
    color: %(text)s;
    padding: 8px;
    selection-background-color: %(accent_lo)s;
}
QPlainTextEdit:focus {
    border-color: %(accent)s;
}

/* ── ComboBox ───────────────────────────────────────── */
QComboBox {
    background: %(bg2)s;
    border: 1px solid %(border)s;
    border-radius: 3px;
    padding: 4px 8px;
    min-height: 26px;
    color: %(text)s;
}
QComboBox:hover  { border-color: %(border_hi)s; }
QComboBox:focus  { border-color: %(accent)s; }
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid %(text_dim)s;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background: %(bg2)s;
    border: 1px solid %(border_hi)s;
    selection-background-color: %(accent_lo)s;
    outline: none;
}

/* ── SpinBox / DoubleSpinBox ────────────────────────── */
QSpinBox, QDoubleSpinBox {
    background: %(bg2)s;
    border: 1px solid %(border)s;
    border-radius: 3px;
    padding: 4px 6px;
    min-height: 26px;
    color: %(text)s;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: %(accent)s; }
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background: %(bg3)s;
    border: none;
    width: 18px;
}

/* ── Slider ─────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 3px;
    background: %(bg3)s;
    border-radius: 1px;
}
QSlider::sub-page:horizontal {
    background: %(accent)s;
    border-radius: 1px;
}
QSlider::handle:horizontal {
    background: %(accent_hi)s;
    border: none;
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
}

/* ── CheckBox ───────────────────────────────────────── */
QCheckBox {
    spacing: 8px;
    color: %(text)s;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid %(border_hi)s;
    border-radius: 2px;
    background: %(bg2)s;
}
QCheckBox::indicator:checked {
    background: %(accent)s;
    border-color: %(accent_hi)s;
}

/* ── LineEdit ───────────────────────────────────────── */
QLineEdit {
    background: %(bg2)s;
    border: 1px solid %(border)s;
    border-radius: 3px;
    padding: 4px 8px;
    min-height: 26px;
    color: %(text)s;
}
QLineEdit:focus { border-color: %(accent)s; }

/* ── Buttons ─────────────────────────────────────────── */
QPushButton {
    background: %(bg2)s;
    border: 1px solid %(border_hi)s;
    border-radius: 3px;
    padding: 6px 16px;
    color: %(text)s;
    font-weight: bold;
    letter-spacing: 1px;
}
QPushButton:hover {
    background: %(bg3)s;
    border-color: %(accent)s;
    color: %(accent_hi)s;
}
QPushButton:pressed {
    background: %(accent_lo)s;
    border-color: %(accent)s;
}
QPushButton:disabled {
    color: %(text_lo)s;
    border-color: %(text_lo)s;
    background: %(bg1)s;
}

QPushButton#btn_primary {
    background: %(accent_lo)s;
    border-color: %(accent)s;
    color: %(accent_hi)s;
    letter-spacing: 2px;
}
QPushButton#btn_primary:hover {
    background: %(accent)s;
    color: %(bg0)s;
}
QPushButton#btn_primary:pressed {
    background: %(accent_lo)s;
}
QPushButton#btn_primary:disabled {
    background: %(bg1)s;
    border-color: %(text_lo)s;
    color: %(text_lo)s;
}

QPushButton#btn_danger {
    border-color: %(danger)s;
    color: %(danger)s;
}
QPushButton#btn_danger:hover {
    background: %(danger)s;
    color: %(text)s;
}

/* ── Progress bar ─────────────────────────────────────── */
QProgressBar {
    background: %(bg2)s;
    border: 1px solid %(border)s;
    border-radius: 2px;
    height: 4px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: %(accent)s;
    border-radius: 2px;
}

/* ── Scroll bars ─────────────────────────────────────── */
QScrollBar:vertical {
    background: %(bg1)s;
    width: 8px;
    border: none;
}
QScrollBar::handle:vertical {
    background: %(bg3)s;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover { background: %(border_hi)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QScrollBar:horizontal {
    background: %(bg1)s;
    height: 8px;
    border: none;
}
QScrollBar::handle:horizontal {
    background: %(bg3)s;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover { background: %(border_hi)s; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Splitter ─────────────────────────────────────────── */
QSplitter::handle {
    background: %(border)s;
}
QSplitter::handle:hover { background: %(accent_lo)s; }

/* ── Tooltip ──────────────────────────────────────────── */
QToolTip {
    background: %(bg2)s;
    border: 1px solid %(accent_lo)s;
    color: %(text)s;
    padding: 4px 8px;
}

/* ── TabWidget ────────────────────────────────────────── */
QTabBar::tab {
    background: %(bg1)s;
    border: 1px solid %(border)s;
    border-bottom: none;
    padding: 6px 14px;
    color: %(text_dim)s;
    font-size: 11px;
    letter-spacing: 1px;
}
QTabBar::tab:selected {
    background: %(bg2)s;
    border-top-color: %(accent)s;
    color: %(accent_hi)s;
}
QTabBar::tab:hover:!selected { color: %(text)s; }
QTabWidget::pane {
    border: 1px solid %(border)s;
    background: %(bg2)s;
}

/* ── GroupBox ─────────────────────────────────────────── */
QGroupBox {
    border: 1px solid %(border)s;
    border-radius: 3px;
    margin-top: 10px;
    padding-top: 6px;
    color: %(text_dim)s;
    font-size: 10px;
    letter-spacing: 1px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    color: %(accent)s;
}
""" % PALETTE


def apply(app):
    """Aplica o QSS e paleta à QApplication."""
    app.setStyleSheet(QSS)