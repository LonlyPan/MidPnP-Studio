"""深色工业风视觉主题。"""

from __future__ import annotations

COLORS = {
    "bg": "#070c11",
    "bg_soft": "#0a1118",
    "surface": "#0e171f",
    "surface2": "#121f29",
    "surface3": "#172936",
    "border": "#1e303d",
    "border_soft": "#162530",
    "text": "#e8f2f5",
    "muted": "#7e95a4",
    "faint": "#4d6472",
    "accent": "#2ee6c5",
    "accent_dim": "#176e64",
    "accent_soft": "#0f2f2e",
    "blue": "#4da3ff",
    "warn": "#ffb454",
    "danger": "#ff5d6c",
    "success": "#43d98b",
    "purple": "#a78bfa",
}

FONT_FAMILY = '"Noto Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", "DengXian", "Segoe UI", sans-serif'
MONO_FAMILY = '"Cascadia Mono", "Consolas", "SFMono-Regular", monospace'


STYLESHEET = f"""
* {{
    outline: none;
}}
QWidget {{
    color: {COLORS['text']};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}
QMainWindow, QDialog {{
    background: {COLORS['bg']};
}}
QStackedWidget {{
    background: {COLORS['bg']};
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollArea QWidget#qt_scrollarea_viewport {{
    background: transparent;
}}
QToolTip {{
    background: {COLORS['surface3']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    padding: 6px 9px;
    border-radius: 4px;
    font-size: 12px;
}}

/* ---------- frames / layout ---------- */
QFrame[cssClass="sidebar"] {{
    background: #080f15;
    border-right: 1px solid {COLORS['border_soft']};
}}
QFrame[cssClass="topbar"] {{
    background: {COLORS['bg']};
    border-bottom: 1px solid {COLORS['border_soft']};
}}
QFrame[cssClass="statusbar"] {{
    background: #080f15;
    border-top: 1px solid {COLORS['border_soft']};
}}
QFrame[cssClass="card"] {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border_soft']};
    border-radius: 10px;
}}
QFrame[cssClass="card"]:hover {{
    border-color: #263c49;
}}
QFrame[cssClass="inset"] {{
    background: {COLORS['bg_soft']};
    border: 1px solid {COLORS['border_soft']};
    border-radius: 8px;
}}
QFrame[cssClass="divider"] {{
    background: {COLORS['border_soft']};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
QFrame[cssClass="vdivider"] {{
    background: {COLORS['border_soft']};
    max-width: 1px;
    min-width: 1px;
    border: none;
}}
QFrame[cssClass="toast"] {{
    background: {COLORS['surface3']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
}}

/* ---------- text roles ---------- */
QLabel[role="pageTitle"] {{
    font-size: 22px;
    font-weight: 700;
    color: {COLORS['text']};
}}
QLabel[role="pageSub"] {{
    color: {COLORS['muted']};
    font-size: 12px;
}}
QLabel[role="section"] {{
    font-size: 15px;
    font-weight: 600;
    color: {COLORS['text']};
}}
QLabel[role="muted"] {{
    color: {COLORS['muted']};
    font-size: 12px;
}}
QLabel[role="faint"] {{
    color: {COLORS['faint']};
    font-size: 11px;
}}
QLabel[role="metric"] {{
    font-family: {MONO_FAMILY};
    font-size: 30px;
    font-weight: 700;
    color: {COLORS['text']};
}}
QLabel[role="mono"] {{
    font-family: {MONO_FAMILY};
    color: {COLORS['text']};
}}
QLabel[role="hint"] {{
    color: {COLORS['muted']};
    font-size: 12px;
    background: {COLORS['bg_soft']};
    border: 1px dashed {COLORS['border']};
    border-radius: 6px;
    padding: 8px 10px;
}}
QLabel[role="eyebrow"] {{
    color: {COLORS['muted']};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel[role="statValue"] {{
    font-family: {MONO_FAMILY};
    font-size: 24px;
    font-weight: 700;
}}
QLabel[role="dialogTitle"] {{
    font-size: 18px;
    font-weight: 700;
}}
QLabel[role="error"] {{
    color: {COLORS['danger']};
}}
QLabel[role="success"] {{
    color: {COLORS['success']};
}}
QLabel[role="warning"] {{
    color: {COLORS['warn']};
}}
QLabel[chip="true"] {{
    background: {COLORS['surface3']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    color: {COLORS['muted']};
    padding: 3px 9px;
    font-size: 11px;
}}
QLabel[chip="accent"] {{
    background: {COLORS['accent_soft']};
    border: 1px solid {COLORS['accent_dim']};
    border-radius: 10px;
    color: {COLORS['accent']};
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 600;
}}

/* ---------- buttons ---------- */
QPushButton {{
    background: {COLORS['surface2']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    color: {COLORS['text']};
    padding: 7px 14px;
    font-weight: 500;
    min-height: 18px;
}}
QPushButton:hover {{
    background: {COLORS['surface3']};
    border-color: #2b4656;
}}
QPushButton:pressed {{
    background: #0b141b;
}}
QPushButton:disabled {{
    color: {COLORS['faint']};
    background: #0c151c;
    border-color: {COLORS['border_soft']};
}}
QPushButton[variant="primary"] {{
    background: {COLORS['accent']};
    color: #04221d;
    border: 1px solid {COLORS['accent']};
    font-weight: 700;
}}
QPushButton[variant="primary"]:hover {{
    background: #62f2d8;
    border-color: #62f2d8;
}}
QPushButton[variant="primary"]:pressed {{
    background: #20c3a6;
}}
QPushButton[variant="primary"]:disabled {{
    background: #1b4a44;
    color: #6b9990;
    border-color: #1b4a44;
}}
QPushButton[variant="danger"] {{
    background: #2a1218;
    color: #ff8b96;
    border: 1px solid #5b2730;
}}
QPushButton[variant="danger"]:hover {{
    background: #3a171f;
    border-color: {COLORS['danger']};
}}
QPushButton[variant="danger"]:pressed {{
    background: {COLORS['danger']};
    color: #1c0608;
}}
QPushButton[variant="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {COLORS['muted']};
    padding: 6px 9px;
}}
QPushButton[variant="ghost"]:hover {{
    background: {COLORS['surface2']};
    color: {COLORS['text']};
}}
QPushButton[variant="subtle"] {{
    background: transparent;
    border: 1px solid {COLORS['border']};
    color: {COLORS['muted']};
}}
QPushButton[variant="subtle"]:hover {{
    color: {COLORS['text']};
    border-color: #2b4656;
}}
QPushButton[variant="subtle"]:disabled, QPushButton[variant="ghost"]:disabled {{
    color: {COLORS['faint']};
    border-color: {COLORS['border_soft']};
    background: transparent;
}}
QPushButton[variant="danger"]:disabled {{
    color: #6f3d43;
    border-color: #3a2025;
    background: #160d10;
}}
QPushButton[variant="primary"]:disabled {{
    color: #5f9088;
}}
QPushButton[variant="estop"] {{
    background: #c3273b;
    color: white;
    border: 1px solid #ff5d6c;
    border-radius: 6px;
    font-weight: 800;
    font-size: 12px;
    letter-spacing: 1px;
    padding: 9px 16px;
}}
QPushButton[variant="estop"]:hover {{
    background: #e02f45;
}}
QPushButton[variant="estop"]:pressed {{
    background: #971b2c;
}}
QPushButton[nav="true"] {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    color: {COLORS['muted']};
    text-align: left;
    padding: 0 16px;
    font-size: 13px;
    font-weight: 500;
    min-height: 44px;
}}
QPushButton[nav="true"]:hover {{
    background: #0d1821;
    color: {COLORS['text']};
}}
QPushButton[nav="true"]:checked {{
    background: #0d1e25;
    border-left: 3px solid {COLORS['accent']};
    color: {COLORS['accent']};
    font-weight: 600;
}}
QPushButton[segment="true"] {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    color: {COLORS['muted']};
    padding: 4px 8px;
    font-size: 11px;
    min-height: 16px;
}}
QPushButton[segment="true"]:checked {{
    background: {COLORS['surface3']};
    border-color: {COLORS['border']};
    color: {COLORS['text']};
}}
QPushButton[jog="true"] {{
    background: {COLORS['surface2']};
    border: 1px solid {COLORS['border']};
    border-radius: 7px;
    font-family: {MONO_FAMILY};
    font-size: 13px;
    font-weight: 700;
    min-width: 48px;
    min-height: 40px;
    padding: 0;
}}
QPushButton[jog="true"]:hover {{
    background: {COLORS['surface3']};
    border-color: {COLORS['accent_dim']};
    color: {COLORS['accent']};
}}

/* ---------- inputs ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {COLORS['bg_soft']};
    border: 1px solid {COLORS['border']};
    border-radius: 5px;
    padding: 6px 8px;
    color: {COLORS['text']};
    selection-background-color: {COLORS['accent_dim']};
    min-height: 18px;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {COLORS['accent_dim']};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {COLORS['faint']};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {COLORS['muted']};
    margin-right: 7px;
}}
QComboBox QAbstractItemView {{
    background: {COLORS['surface2']};
    border: 1px solid {COLORS['border']};
    color: {COLORS['text']};
    selection-background-color: {COLORS['accent_soft']};
    selection-color: {COLORS['accent']};
    padding: 4px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: {COLORS['surface2']};
    border: none;
    width: 16px;
}}
QCheckBox {{
    color: {COLORS['text']};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {COLORS['border']};
    border-radius: 3px;
    background: {COLORS['bg_soft']};
}}
QCheckBox::indicator:checked {{
    background: {COLORS['accent']};
    border-color: {COLORS['accent']};
    image: none;
}}
QRadioButton {{
    color: {COLORS['text']};
    spacing: 7px;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {COLORS['surface3']};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {COLORS['accent']};
    width: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {COLORS['accent_dim']};
    border-radius: 2px;
}}

/* ---------- tables ---------- */
QTableWidget, QTableView {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border_soft']};
    border-radius: 8px;
    gridline-color: {COLORS['border_soft']};
    selection-background-color: #11312f;
    selection-color: {COLORS['text']};
    alternate-background-color: #0c151c;
}}
QTableWidget::item, QTableView::item {{
    padding: 5px 8px;
    border: none;
    border-bottom: 1px solid #111d25;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background: #11312f;
    color: {COLORS['text']};
}}
QHeaderView::section {{
    background: #0b141b;
    color: {COLORS['muted']};
    border: none;
    border-bottom: 1px solid {COLORS['border']};
    border-right: 1px solid {COLORS['border_soft']};
    padding: 8px;
    font-size: 11px;
    font-weight: 600;
}}
QHeaderView::section:last {{
    border-right: none;
}}
QTableCornerButton::section {{
    background: #0b141b;
    border: none;
}}
QListWidget {{
    background: transparent;
    border: none;
}}
QListWidget::item {{
    border-radius: 6px;
    padding: 9px 10px;
    margin: 1px 0;
    color: {COLORS['muted']};
}}
QListWidget::item:selected {{
    background: {COLORS['surface3']};
    color: {COLORS['text']};
}}
QListWidget::item:hover {{
    background: {COLORS['surface2']};
}}

/* ---------- scroll areas / tabs / splitter ---------- */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #263b48;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #385463;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    border: none;
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 9px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #263b48;
    border-radius: 4px;
    min-width: 30px;
}}
QSplitter::handle {{
    background: transparent;
}}
QSplitter::handle:horizontal {{
    width: 10px;
}}
QSplitter::handle:vertical {{
    height: 10px;
}}
QTabWidget::pane {{
    border: 1px solid {COLORS['border_soft']};
    border-radius: 8px;
    background: {COLORS['surface']};
}}
QTabBar::tab {{
    background: transparent;
    color: {COLORS['muted']};
    padding: 7px 16px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {COLORS['accent']};
    border-bottom: 2px solid {COLORS['accent']};
}}
QProgressBar {{
    background: {COLORS['surface3']};
    border: none;
    border-radius: 4px;
    text-align: center;
    color: transparent;
    max-height: 8px;
}}
QProgressBar::chunk {{
    background: {COLORS['accent']};
    border-radius: 4px;
}}
QMenu {{
    background: {COLORS['surface2']};
    border: 1px solid {COLORS['border']};
    color: {COLORS['text']};
    padding: 5px;
}}
QMenu::item {{
    padding: 7px 26px 7px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {COLORS['accent_soft']};
    color: {COLORS['accent']};
}}
QDialog QLabel {{
    color: {COLORS['text']};
}}
"""
