# -*- coding: utf-8 -*-
"""スコア表示ウィジェット（アニメーション付き）"""

from typing import List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QScrollArea, QFrame,
    QGridLayout, QProgressBar, QGraphicsOpacityEffect, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor

from app.common.data_models import ScoreResult, GameResult
from app.common.styles import (
    SCORE_COLOR_GOOD, SCORE_COLOR_MEDIUM, SCORE_COLOR_POOR,
    TEXT_SECONDARY, btn_style,
)


class ScoreDisplayWidget(QWidget):
    """スコア表示用ウィジェット"""

    def __init__(self):
        super().__init__()
        self.game_result = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        self.banner_label = QLabel("判定中…")
        f = QFont(); f.setPointSize(28); f.setBold(True)
        self.banner_label.setFont(f)
        self.banner_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.banner_label)

        self.overall_big = QLabel("総合スコア: 0.0 点")
        f2 = QFont(); f2.setPointSize(48); f2.setBold(True)
        self.overall_big.setFont(f2)
        self.overall_big.setAlignment(Qt.AlignCenter)
        self.overall_big.setStyleSheet(f"color:{TEXT_SECONDARY};")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24); shadow.setOffset(0, 2); shadow.setColor(QColor(0, 0, 0, 160))
        self.overall_big.setGraphicsEffect(shadow)
        layout.addWidget(self.overall_big)

        self.header_frame = QFrame()
        self.header_frame.setFrameStyle(QFrame.StyledPanel)
        self.header_layout = QGridLayout(self.header_frame)
        self.participant_label = QLabel("参加者: -")
        self.team_label = QLabel("チーム: -")
        self.case_label = QLabel("症例: -")
        self.time_label = QLabel("時間: -")
        header_font = QFont(); header_font.setPointSize(12); header_font.setBold(True)
        for label in [self.participant_label, self.team_label, self.case_label, self.time_label]:
            label.setFont(header_font)
        self.header_layout.addWidget(self.participant_label, 0, 0)
        self.header_layout.addWidget(self.team_label, 0, 1)
        self.header_layout.addWidget(self.case_label, 1, 0)
        self.header_layout.addWidget(self.time_label, 1, 1)
        layout.addWidget(self.header_frame)

        self.score_scroll = QScrollArea()
        self.score_widget = QWidget()
        self.score_layout = QVBoxLayout(self.score_widget)
        self.score_scroll.setWidget(self.score_widget)
        self.score_scroll.setWidgetResizable(True)
        layout.addWidget(self.score_scroll)

        self.close_button = QPushButton("閉じる")
        self.close_button.setStyleSheet(btn_style(primary=True))
        self.close_button.clicked.connect(self._close_window)
        layout.addWidget(self.close_button)

        self.table_header = None
        self.row_frames = []
        self.row_bars = []

    def _close_window(self):
        """親ウィンドウを閉じる（インプロセス化対応）"""
        parent = self.window()
        if parent and parent is not self:
            parent.close()
        else:
            self.close()

    def update_display(self, game_result: GameResult):
        self.game_result = game_result
        self.participant_label.setText(f"参加者: {game_result.participant}")
        self.team_label.setText(f"チーム: {game_result.team}")
        self.case_label.setText(f"症例: {game_result.case}")
        elapsed_min = game_result.elapsed_sec // 60
        elapsed_sec = game_result.elapsed_sec % 60
        if game_result.time_limit_sec > 0:
            limit_min = game_result.time_limit_sec // 60
            limit_sec_total = game_result.time_limit_sec % 60
            self.time_label.setText(f"時間: {elapsed_min:02d}:{elapsed_sec:02d} / {limit_min:02d}:{limit_sec_total:02d}")
        else:
            self.time_label.setText(f"時間: {elapsed_min:02d}:{elapsed_sec:02d}")
        v = max(0.0, min(1.0, game_result.overall_score)) * 100.0
        self.overall_big.setText(f"総合スコア: {v:0.1f} 点")
        self.overall_big.setStyleSheet(f"color: {self._get_score_color(v / 100.0)}")
        self._update_roi_scores(game_result.scores)

    def _update_roi_scores(self, scores: List[ScoreResult]):
        for i in reversed(range(self.score_layout.count())):
            w = self.score_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        header = QFrame()
        header.setFrameStyle(QFrame.Box)
        header_layout = QGridLayout(header)
        headers = ["ROI名", "一致", "面内滑らかさ", "立体滑らかさ", "総合"]
        for i, text in enumerate(headers):
            label = QLabel(text)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("font-weight: bold; background-color: rgba(255,255,255,0.06); border-radius: 4px; padding: 4px;")
            header_layout.addWidget(label, 0, i)
        self.score_layout.addWidget(header)

        self.table_header = header
        self.row_frames = []
        self.row_bars = []

        for sc in scores:
            row = QFrame(); row.setFrameStyle(QFrame.Box)
            gl = QGridLayout(row)
            name = QLabel(sc.roi_name); name.setAlignment(Qt.AlignCenter)
            gl.addWidget(name, 0, 0)
            vals = [sc.dice_score, sc.axial_smoothness, sc.volume_smoothness, sc.total_score]
            for j, v in enumerate(vals, 1):
                bar = QProgressBar()
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setTextVisible(False)
                bar.setFixedHeight(14)
                bar.setStyleSheet(self._style_progressbar(v))
                gl.addWidget(bar, 0, j)
                self.row_bars.append((bar, v))
            self.score_layout.addWidget(row)
            self.row_frames.append(row)

    def _get_score_color(self, score: float) -> str:
        if score >= 0.8:
            return SCORE_COLOR_GOOD
        elif score >= 0.6:
            return SCORE_COLOR_MEDIUM
        else:
            return SCORE_COLOR_POOR

    def reveal_with_animation(self, game_result: GameResult):
        self.game_result = game_result
        self.participant_label.setText(f"参加者: {game_result.participant}")
        self.team_label.setText(f"チーム: {game_result.team}")
        self.case_label.setText(f"症例: {game_result.case}")
        elapsed_min = game_result.elapsed_sec // 60
        elapsed_sec = game_result.elapsed_sec % 60
        if game_result.time_limit_sec > 0:
            limit_min = game_result.time_limit_sec // 60
            limit_sec_total = game_result.time_limit_sec % 60
            self.time_label.setText(f"時間: {elapsed_min:02d}:{elapsed_sec:02d} / {limit_min:02d}:{limit_sec_total:02d}")
        else:
            self.time_label.setText(f"時間: {elapsed_min:02d}:{elapsed_sec:02d}")

        self.overall_big.setText("総合スコア: 0.0 点")
        self.overall_big.setStyleSheet(f"color:{TEXT_SECONDARY};")

        self._update_roi_scores(game_result.scores)
        widgets = [self.table_header] + list(self.row_frames)
        for w in widgets:
            eff = QGraphicsOpacityEffect(w); w.setGraphicsEffect(eff); eff.setOpacity(0.0)

        self._fade_in_widget(self.banner_label, delay_ms=0, duration_ms=400)

        def _dots():
            base = "判定中"
            dots = ["…", "……", "………"]
            idx = (getattr(self, "_dots_i", -1) + 1) % 3
            self._dots_i = idx
            self.banner_label.setText(base + dots[idx])
        self._dots_timer = QTimer(self)
        self._dots_timer.timeout.connect(_dots)
        self._dots_timer.start(300)
        QTimer.singleShot(900, self._dots_timer.stop)

        def _reveal_title():
            self.banner_label.setText("結果発表!!")
            self._flash_background()
        QTimer.singleShot(950, _reveal_title)

        self._fade_in_widget(self.header_frame, delay_ms=950, duration_ms=400)
        self._animate_overall_score(target=game_result.overall_score, delay_ms=1100, duration_ms=1700)

        start = 1100 + 1700
        self._fade_in_widget(self.table_header, delay_ms=start, duration_ms=350)
        step = 120
        for i, row in enumerate(self.row_frames):
            self._fade_in_widget(row, delay_ms=start + 200 + i * step, duration_ms=350)

        for i, (bar, v) in enumerate(self.row_bars):
            self._animate_progressbar(bar, int(round(v * 100)), delay_ms=start + 200 + i * 40, duration_ms=500)

    def _animate_overall_score(self, target, delay_ms=600, duration_ms=1500):
        target_pt = max(0.0, min(100.0, target * 100.0))
        frames = max(1, duration_ms // 16)
        step = target_pt / frames
        self._number_timer = QTimer(self)
        self._number_timer.setInterval(16)
        self._anim_i = 0

        def _tick():
            self._anim_i += 1
            v = min(target_pt, self._anim_i * step)
            self.overall_big.setText(f"総合スコア: {v:0.1f} 点")
            self.overall_big.setStyleSheet(f"color: {self._get_score_color(v / 100.0)}")
            if self._anim_i >= frames:
                self._number_timer.stop()
                self._number_timer.deleteLater()
                self._bounce_widget(self.overall_big)

        QTimer.singleShot(delay_ms, self._number_timer.start)
        self._number_timer.timeout.connect(_tick)

    def _fade_in_widget(self, widget, delay_ms=0, duration_ms=400):
        eff = widget.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(widget); widget.setGraphicsEffect(eff); eff.setOpacity(0.0)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(duration_ms)
        anim.setStartValue(0.0); anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        if not hasattr(self, "_anims"):
            self._anims = []
        self._anims.append(anim)
        QTimer.singleShot(delay_ms, anim.start)

    def _bounce_widget(self, widget, scale_px=8, duration_ms=220):
        r = widget.geometry()
        anim = QPropertyAnimation(widget, b"geometry", self)
        anim.setDuration(duration_ms)
        anim.setEasingCurve(QEasingCurve.OutBack)
        anim.setStartValue(r)
        anim.setEndValue(r.adjusted(-scale_px, -scale_px, scale_px, scale_px))

        def _back():
            anim2 = QPropertyAnimation(widget, b"geometry", self)
            anim2.setDuration(duration_ms)
            anim2.setEasingCurve(QEasingCurve.OutCubic)
            anim2.setStartValue(widget.geometry())
            anim2.setEndValue(r)
            if not hasattr(self, "_anims"):
                self._anims = []
            self._anims.append(anim2)
            anim2.start()
        if not hasattr(self, "_anims"):
            self._anims = []
        self._anims.append(anim)
        anim.finished.connect(_back)
        anim.start()

    def _flash_background(self, duration_ms=160):
        orig = self.parentWidget().styleSheet() if self.parentWidget() else ""
        w = self.parentWidget() or self
        w.setStyleSheet("QWidget { background: rgba(124,92,255,0.3); }")
        QTimer.singleShot(duration_ms, lambda: w.setStyleSheet(orig))

    def _style_progressbar(self, v01):
        color = self._get_score_color(v01)
        return (
            "QProgressBar { background-color: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.10); border-radius: 7px; }"
            f"QProgressBar::chunk {{ background-color: {color}; border-radius: 7px; }}"
        )

    def _animate_progressbar(self, bar, target_value, delay_ms=0, duration_ms=500):
        anim = QPropertyAnimation(bar, b"value", self)
        anim.setDuration(duration_ms)
        anim.setStartValue(0)
        anim.setEndValue(int(target_value))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        if not hasattr(self, "_anims"):
            self._anims = []
        self._anims.append(anim)
        QTimer.singleShot(delay_ms, anim.start)
