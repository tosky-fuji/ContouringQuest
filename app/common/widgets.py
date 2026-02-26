# -*- coding: utf-8 -*-
"""ゲーム風共通ウィジェット: GameCard, FunButton, SpringButton"""

import time

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, Signal, Property
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (
    QPushButton, QFrame, QVBoxLayout, QLabel, QSizePolicy,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QStyleOptionButton, QStyle,
)

try:
    import shiboken6 as _sbk
except Exception:
    _sbk = None

from .styles import btn_style, PRIMARY_ACCENT


# ---------------------------------------------------------------------------
# GameCard — ホバーで拡大・グロー、クリックで縮小するカードウィジェット
# ---------------------------------------------------------------------------
class GameCard(QFrame):
    """ホバーで拡大・グロー、クリックで縮小するカードウィジェット"""
    clicked = Signal()

    def __init__(self, icon_text: str = "", title: str = "", description: str = "",
                 accent: str = PRIMARY_ACCENT, parent=None):
        super().__init__(parent)
        self._accent = accent
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(200, 180)

        self._base_style = (
            "GameCard {"
            "  background: rgba(255,255,255,0.04);"
            "  border: 1px solid rgba(255,255,255,0.10);"
            "  border-radius: 18px;"
            "}"
        )
        self._hover_style = (
            "GameCard {"
            f"  background: rgba(255,255,255,0.07);"
            f"  border: 2px solid {accent};"
            "  border-radius: 18px;"
            "}"
        )
        self.setStyleSheet(self._base_style)

        # shadow
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setColor(QColor(0, 0, 0, 80))
        self._shadow.setOffset(0, 4)
        self._shadow.setBlurRadius(16)
        self.setGraphicsEffect(self._shadow)

        # layout
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 18, 16, 14)
        lay.setSpacing(6)

        self._icon_label = QLabel(icon_text)
        self._icon_label.setStyleSheet("font-size: 36px; background: transparent; border: none;")
        self._icon_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._icon_label)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: white; background: transparent; border: none;"
        )
        self._title_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._title_label)

        self._desc_label = QLabel(description)
        self._desc_label.setStyleSheet(
            "font-size: 12px; color: rgba(255,255,255,0.60); background: transparent; border: none;"
        )
        self._desc_label.setAlignment(Qt.AlignCenter)
        self._desc_label.setWordWrap(True)
        lay.addWidget(self._desc_label)

        lay.addStretch()

        # animation state
        self._hovered = False
        self._pressed = False

    # --- events ---
    def enterEvent(self, event):
        self._hovered = True
        self.setStyleSheet(self._hover_style)
        self._animate_shadow(blur=24, offset=6)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._pressed = False
        self.setStyleSheet(self._base_style)
        self._animate_shadow(blur=16, offset=4)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._animate_shadow(blur=10, offset=2)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            self._animate_shadow(blur=24 if self._hovered else 16,
                                 offset=6 if self._hovered else 4)
            if self.rect().contains(event.pos()):
                self.clicked.emit()
        super().mouseReleaseEvent(event)

    def _animate_shadow(self, blur: int, offset: int):
        try:
            anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
            anim.setDuration(140)
            anim.setStartValue(self._shadow.blurRadius())
            anim.setEndValue(blur)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            self._shadow_anim = anim
            self._shadow.setOffset(0, offset)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# FunButton — ふわっと浮く楽しいボタン
# ---------------------------------------------------------------------------
class FunButton(QPushButton):
    def __init__(self, text: str = "", *, big=False, primary=False,
                 secondary=False, outline=False, parent=None):
        super().__init__(text, parent)
        self._big = big

        self._effect = QGraphicsDropShadowEffect(self)
        self._effect.setColor(Qt.black)
        self._effect.setOffset(0, 8)
        self._effect.setBlurRadius(26 if big else 18)
        self.setGraphicsEffect(self._effect)

        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(btn_style(primary=primary, secondary=secondary,
                                     outline=outline, big=big))

        if big:
            self.setFixedHeight(66)
            self.setMinimumWidth(340)
            self.setMaximumWidth(480)
        else:
            self.setFixedHeight(44)
            self.setMinimumWidth(140)
            self.setMaximumWidth(320)

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def enterEvent(self, e):
        try:
            self._animate_shadow(to_blur=(32 if self._big else 24), to_offset=(0, 6))
        except Exception:
            pass
        return super().enterEvent(e)

    def leaveEvent(self, e):
        try:
            self._animate_shadow(to_blur=(26 if self._big else 18), to_offset=(0, 8))
        except Exception:
            pass
        return super().leaveEvent(e)

    def _animate_shadow(self, *, to_blur: int, to_offset):
        try:
            anim = QPropertyAnimation(self._effect, b"blurRadius", self)
            anim.setDuration(140)
            anim.setStartValue(self._effect.blurRadius())
            anim.setEndValue(to_blur)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            self._shadow_anim = anim
            if isinstance(to_offset, tuple):
                self._effect.setOffset(*to_offset)
            else:
                self._effect.setOffset(to_offset)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# SpringButton — 物理スプリングで scale を更新するボタン
# ---------------------------------------------------------------------------
class SpringButton(QPushButton):
    PRESS_SCALE = 0.94
    HOVER_SCALE = 1.00
    REST_SCALE = 1.00
    MASS = 1.0
    STIFFNESS = 180.0
    DAMPING = 16.0
    RELEASE_BOOST_V = 4.0
    FPS = 120
    MIN_SCALE = 0.88
    MAX_SCALE = 0.999
    SHADOW_BLUR = 32
    SHADOW_BASE_OFFSET = 8
    SHADOW_MIN_OFFSET = 2

    scaleChanged = Signal(float)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setStyleSheet("""
            QPushButton {
                border-radius: 14px;
                padding: 12px 18px;
                font-size: 18px;
                font-weight: 600;
            }
        """)
        self._scale = 1.0
        self._target = 1.0
        self._vel = 0.0
        self._shadow = None
        self._suspend_shadow = False
        self._create_shadow()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step_physics)
        self._timer.setInterval(int(1000 / self.FPS))
        self._last_t = time.perf_counter()
        self.scaleChanged.connect(self.update)

    def _shadow_valid(self) -> bool:
        if self._shadow is None:
            return False
        if _sbk is not None:
            try:
                if not _sbk.isValid(self._shadow):
                    return False
            except Exception:
                pass
        return isinstance(self.graphicsEffect(), QGraphicsDropShadowEffect)

    def _create_shadow(self):
        if self._suspend_shadow:
            return
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(self.SHADOW_BLUR)
        self._shadow.setColor(QColor(0, 0, 0, 120))
        self._shadow.setOffset(self.SHADOW_BASE_OFFSET, self.SHADOW_BASE_OFFSET)
        self.setGraphicsEffect(self._shadow)

    def _ensure_shadow(self):
        if self._suspend_shadow:
            return
        if not self._shadow_valid():
            self._create_shadow()

    def _apply_shadow(self):
        if self._suspend_shadow:
            return
        self._ensure_shadow()
        t = (self._scale - self.PRESS_SCALE) / (self.REST_SCALE - self.PRESS_SCALE + 1e-6)
        t = max(0.0, min(1.0, t))
        off = self.SHADOW_MIN_OFFSET + (self.SHADOW_BASE_OFFSET - self.SHADOW_MIN_OFFSET) * t
        try:
            if self._shadow_valid():
                self._shadow.setOffset(off, off)
        except RuntimeError:
            pass

    @Property(float, notify=scaleChanged)
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, v: float):
        v = max(self.MIN_SCALE, min(self.MAX_SCALE, float(v)))
        if v != self._scale:
            self._scale = v
            self._apply_shadow()
            self.scaleChanged.emit(v)

    def _ensure_running(self):
        if not self._timer.isActive():
            self._last_t = time.perf_counter()
            self._timer.start()

    def _step_physics(self):
        now = time.perf_counter()
        dt = max(1.0 / self.FPS, min(0.050, now - self._last_t))
        self._last_t = now
        x = self._scale
        v = self._vel
        a = (-self.STIFFNESS * (x - self._target) - self.DAMPING * v) / self.MASS
        v += a * dt
        x += v * dt
        self._vel = v
        self.scale = x
        if abs(self._scale - self._target) < 1e-3 and abs(self._vel) < 1e-3:
            self.scale = self._target
            self._vel = 0.0
            self._timer.stop()

    def _to(self, target: float, kick_vel: float = 0.0):
        self._target = max(self.MIN_SCALE, min(self.MAX_SCALE, float(target)))
        if kick_vel:
            self._vel += kick_vel
        self._ensure_running()

    def enterEvent(self, e):
        super().enterEvent(e)
        if not self.isDown():
            self._to(self.HOVER_SCALE)

    def leaveEvent(self, e):
        super().leaveEvent(e)
        if not self.isDown():
            self._to(self.REST_SCALE)

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        self._to(self.PRESS_SCALE)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        self._to(self.REST_SCALE, kick_vel=self.RELEASE_BOOST_V)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        painter.translate(w / 2.0, h / 2.0)
        painter.scale(self._scale, self._scale)
        painter.translate(-w / 2.0, -h / 2.0)
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        self.style().drawControl(QStyle.CE_PushButton, opt, painter, self)
