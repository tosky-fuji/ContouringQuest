# -*- coding: utf-8 -*-
"""テーマ定数、共通スタイルシート"""

import hashlib
import colorsys

# ------------------------------------
# カラー定数
# ------------------------------------
PRIMARY_ACCENT = "#7C5CFF"
SECONDARY_ACCENT = "#00D1B2"

BG_GRADIENT = (
    "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
    "stop:0 #0b0f2a, stop:0.5 #141a3a, stop:1 #1c2452);"
)

# ------------------------------------
# カードのスタイル
# ------------------------------------
CARD_STYLE_NORMAL = (
    "background: rgba(255,255,255,0.04);"
    "border: 1px solid rgba(255,255,255,0.10);"
    "border-radius: 18px;"
)

CARD_STYLE_HOVER = (
    "background: rgba(255,255,255,0.07);"
    "border: 2px solid {accent};"
    "border-radius: 18px;"
)

# ------------------------------------
# 入力コントロール
# ------------------------------------
INPUT_BG = "rgba(255,255,255,0.06)"
INPUT_BORDER = "rgba(255,255,255,0.12)"
INPUT_RADIUS = "10px"
INPUT_TEXT = "#e9edff"
INPUT_HOVER_BORDER = "rgba(255,255,255,0.25)"
INPUT_FOCUS_BORDER = PRIMARY_ACCENT

# ------------------------------------
# カード (汎用)
# ------------------------------------
CARD_BG = "rgba(255,255,255,0.04)"
CARD_BORDER = "rgba(255,255,255,0.10)"
CARD_RADIUS = "18px"

# ------------------------------------
# テキスト色
# ------------------------------------
TEXT_PRIMARY = "#e9edff"
TEXT_SECONDARY = "#b0b8d0"
TEXT_MUTED = "#6e7a99"
TEXT_LABEL = "#cfe4ff"

# ------------------------------------
# ダークサーフェス
# ------------------------------------
DARK_SURFACE = "#141a3a"
DARK_SURFACE_ALT = "#1c2452"

# ------------------------------------
# スコア色 (ダーク背景映え版)
# ------------------------------------
SCORE_COLOR_GOOD = "#2ecc71"
SCORE_COLOR_MEDIUM = "#f1c40f"
SCORE_COLOR_POOR = "#e74c3c"

# ------------------------------------
# ROI 固定カラーパレット（順番で自動割り当て）
# ------------------------------------
ROI_PALETTE = [
    "#e6194b",  # 赤
    "#3cb44b",  # 緑
    "#0082c8",  # 青
    "#f58231",  # オレンジ
    "#911eb4",  # 紫
    "#46f0f0",  # 水色
    "#f032e6",  # マゼンタ
    "#d2f53c",  # 黄緑
    "#fabebe",  # ピンク
    "#008080",  # ティール
    "#e6beff",  # ラベンダー
    "#aa6e28",  # ブラウン
    "#fffac8",  # クリーム
    "#800000",  # マルーン
    "#aaffc3",  # ミント
    "#808000",  # オリーブ
    "#ffd8b1",  # アプリコット
    "#000080",  # ネイビー
    "#1f77b4",  # スチールブルー
    "#ff7f0e",  # ダークオレンジ
]


def roi_color(index: int) -> str:
    """インデックスからROI色を返す（パレットを巡回）"""
    return ROI_PALETTE[index % len(ROI_PALETTE)]


# ------------------------------------
# 表彰台色
# ------------------------------------
PODIUM_GOLD = "#FFD700"
PODIUM_SILVER = "#C0C0C0"
PODIUM_BRONZE = "#CD7F32"
PODIUM_GOLD_BG = "rgba(255,215,0,0.15)"
PODIUM_SILVER_BG = "rgba(192,192,192,0.12)"
PODIUM_BRONZE_BG = "rgba(205,127,50,0.12)"

# ------------------------------------
# 統一スタイルシート
# ------------------------------------
BASE_STYLESHEET = f"""
/* ===== ウィンドウ/ダイアログ背景 ===== */
QMainWindow, QDialog {{
    {BG_GRADIENT}
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', 'Yu Gothic UI', 'Arial', sans-serif;
}}

/* ===== ラベル ===== */
QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}

/* ===== ボタン ===== */
QPushButton {{
    background: #2b2f66;
    color: {TEXT_PRIMARY};
    border: none;
    border-radius: 12px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: #33387a;
}}
QPushButton:pressed {{
    background: #262a5a;
}}
QPushButton:disabled {{
    background: rgba(255,255,255,0.05);
    color: {TEXT_MUTED};
}}

/* ===== コンボボックス ===== */
QComboBox {{
    background: {INPUT_BG};
    color: {INPUT_TEXT};
    border: 1px solid {INPUT_BORDER};
    border-radius: {INPUT_RADIUS};
    padding: 8px;
    font-size: 14px;
}}
QComboBox:hover {{
    border-color: {INPUT_HOVER_BORDER};
}}
QComboBox:focus {{
    border-color: {INPUT_FOCUS_BORDER};
}}
QComboBox::drop-down {{
    border: none;
}}
QComboBox QAbstractItemView {{
    background: #1e244c;
    color: white;
    selection-background-color: {PRIMARY_ACCENT};
    border: 1px solid rgba(255,255,255,0.12);
}}

/* ===== ラインエディット ===== */
QLineEdit {{
    background: {INPUT_BG};
    color: {INPUT_TEXT};
    border: 1px solid {INPUT_BORDER};
    border-radius: {INPUT_RADIUS};
    padding: 8px;
    font-size: 14px;
}}
QLineEdit:hover {{
    border-color: {INPUT_HOVER_BORDER};
}}
QLineEdit:focus {{
    border-color: {INPUT_FOCUS_BORDER};
}}

/* ===== スピンボックス ===== */
QSpinBox {{
    background: {INPUT_BG};
    color: {INPUT_TEXT};
    border: 1px solid {INPUT_BORDER};
    border-radius: {INPUT_RADIUS};
    padding: 6px 8px;
    font-size: 14px;
}}
QSpinBox:hover {{
    border-color: {INPUT_HOVER_BORDER};
}}
QSpinBox:focus {{
    border-color: {INPUT_FOCUS_BORDER};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: transparent;
    border: none;
}}

/* ===== テーブル ===== */
QTableView {{
    background: {DARK_SURFACE};
    alternate-background-color: {DARK_SURFACE_ALT};
    gridline-color: rgba(255,255,255,0.06);
    font-size: 15px;
    color: {TEXT_PRIMARY};
    selection-background-color: rgba(124,92,255,0.35);
    selection-color: white;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
}}
QHeaderView::section {{
    background: #1a2050;
    color: {TEXT_SECONDARY};
    font-size: 13px;
    font-weight: 700;
    padding: 6px;
    border: 0;
    border-right: 1px solid rgba(255,255,255,0.06);
    border-bottom: 1px solid rgba(255,255,255,0.08);
}}

/* ===== リストウィジェット ===== */
QListWidget {{
    background: {DARK_SURFACE};
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    color: {TEXT_PRIMARY};
    selection-background-color: rgba(124,92,255,0.35);
    font-size: 13px;
}}
QListWidget::item {{
    padding: 5px 10px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}}
QListWidget::item:hover {{
    background: rgba(255,255,255,0.05);
}}
QListWidget::item:selected {{
    background: rgba(124,92,255,0.35);
    color: white;
}}

/* ===== スライダー ===== */
QSlider::groove:horizontal {{
    border: 1px solid rgba(255,255,255,0.10);
    height: 6px;
    background: rgba(255,255,255,0.08);
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {PRIMARY_ACCENT};
    border: none;
    width: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    background: #8C73FF;
}}
QSlider::groove:vertical {{
    border: 1px solid rgba(255,255,255,0.10);
    width: 6px;
    background: rgba(255,255,255,0.08);
    border-radius: 3px;
}}
QSlider::handle:vertical {{
    background: {PRIMARY_ACCENT};
    border: none;
    height: 16px;
    margin: 0 -5px;
    border-radius: 8px;
}}

/* ===== チェックボックス / ラジオボタン ===== */
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.20);
    border-radius: 4px;
}}
QCheckBox::indicator:hover {{
    border-color: {PRIMARY_ACCENT};
}}
QCheckBox::indicator:checked {{
    background: {PRIMARY_ACCENT};
    border-color: {PRIMARY_ACCENT};
}}
QRadioButton {{
    color: {TEXT_PRIMARY};
    spacing: 8px;
}}
QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.20);
    border-radius: 9px;
}}
QRadioButton::indicator:checked {{
    background: {PRIMARY_ACCENT};
    border-color: {PRIMARY_ACCENT};
}}

/* ===== スクロールバー ===== */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,0.15);
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(255,255,255,0.25);
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: rgba(255,255,255,0.15);
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: rgba(255,255,255,0.25);
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ===== プログレスバー ===== */
QProgressBar {{
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 7px;
    text-align: center;
    color: {TEXT_PRIMARY};
    font-size: 12px;
}}
QProgressBar::chunk {{
    background: {PRIMARY_ACCENT};
    border-radius: 7px;
}}

/* ===== メニュー / ツールチップ ===== */
QMenu {{
    background: {DARK_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item:selected {{
    background: rgba(124,92,255,0.35);
}}
QMenuBar {{
    background: {DARK_SURFACE};
    color: {TEXT_PRIMARY};
}}
QMenuBar::item:selected {{
    background: rgba(124,92,255,0.35);
}}
QToolTip {{
    background: #1a2050;
    color: {TEXT_PRIMARY};
    border: 1px solid rgba(255,255,255,0.12);
    padding: 6px 8px;
    font-size: 13px;
    border-radius: 6px;
}}

/* ===== グループボックス ===== */
QGroupBox {{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
    margin-top: 1.5ex;
    font-weight: 600;
    font-size: 13px;
    color: {TEXT_SECONDARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 15px;
    padding: 0 8px;
    color: {TEXT_LABEL};
}}

/* ===== スプリッター ===== */
QSplitter::handle {{
    background: rgba(255,255,255,0.06);
}}

/* ===== テキストエディット ===== */
QTextEdit {{
    background: {DARK_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 8px;
    font-size: 13px;
}}

/* ===== スクロールエリア ===== */
QScrollArea {{
    background: #0a0e24;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 4px;
}}
QScrollArea > QWidget > QWidget {{
    background: #0a0e24;
}}

/* ===== ダイアログボタンボックス ===== */
QDialogButtonBox > QPushButton {{
    min-width: 80px;
    padding: 8px 20px;
}}

/* ===== フレーム ===== */
QFrame {{
    color: {TEXT_PRIMARY};
}}
"""


# ------------------------------------
# ヘルパー関数
# ------------------------------------
def accent_from_text(text: str) -> str:
    """テキストから安定したアクセント色(#RRGGBB)を生成（HSL色相ハッシュ）"""
    if not text:
        return PRIMARY_ACCENT
    h = int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:6], 16) % 360
    return hsl_to_hex(h, 0.70, 0.55)


def hsl_to_hex(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l, s)
    return "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))


def hex_to_rgb(hex_color: str) -> tuple:
    x = hex_color.lstrip("#")
    return int(x[0:2], 16), int(x[2:4], 16), int(x[4:6], 16)


def shade(hex_color: str, delta_l: float) -> str:
    """明るさを±して別トーンを作る（hover/press用）"""
    r, g, b = hex_to_rgb(hex_color)
    rr, gg, bb = (r / 255.0, g / 255.0, b / 255.0)
    h, l, s = colorsys.rgb_to_hls(rr, gg, bb)
    l = max(0.0, min(1.0, l + delta_l))
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return "#{:02X}{:02X}{:02X}".format(int(r2 * 255), int(g2 * 255), int(b2 * 255))


def btn_style(*, primary=False, secondary=False, outline=False, big=False) -> str:
    """共通ボタンスタイルシート生成"""
    radius = 18 if not big else 22
    pad_y = 12 if not big else 16
    pad_x = 18 if not big else 26
    if primary:
        bg = PRIMARY_ACCENT; fg = "white"; hover = "#8C73FF"; press = "#6A55E6"
    elif secondary:
        bg = SECONDARY_ACCENT; fg = "#04151f"; hover = "#00E5C3"; press = "#00B89A"
    elif outline:
        return (
            "QPushButton{border:1px solid rgba(255,255,255,0.40); color:#dbe6ff;"
            f"padding:{pad_y}px {pad_x}px; border-radius:{radius}px; background:transparent; "
            f"font-size:{18 if big else 14}px; font-weight:600;"
            "}"
            "QPushButton:hover{border-color:white;}"
            "QPushButton:pressed{border-color:#aaccff;}"
        )
    else:
        bg = "#2b2f66"; fg = "#e9edff"; hover = "#33387a"; press = "#262a5a"
    return (
        "QPushButton{" f"background:{bg}; color:{fg}; border:none; border-radius:{radius}px;"
        f"padding:{pad_y}px {pad_x}px; font-size:{20 if big else 16}px; font-weight:600;" "}"
        "QPushButton:hover{" f"background:{hover};" "}"
        "QPushButton:pressed{" f"background:{press};" "}"
    )
