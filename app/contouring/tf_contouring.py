# -*- coding: utf-8 -*-
import sys
import os
import json
import time
import warnings
from collections import deque
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass

from app.common.paths import make_relative_path

# デバッグログの有効/無効（必要な時はTrueに変更）
DEBUG = False

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QSlider, QLineEdit, QListWidget,
    QRadioButton, QButtonGroup, QFrame, QFileDialog, QMessageBox,
    QGroupBox, QSizePolicy, QTextEdit, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsEllipseItem, QSplitter, QCheckBox,
    QDialog, QDialogButtonBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QCoreApplication, QRectF, QPointF, QSize, QObject, QEvent

from PySide6.QtGui import (
    QFont, QKeyEvent, QTransform, QPainter, QPen, QBrush, QImage, QPixmap,
    QKeySequence, QShortcut
)

import numpy as np
import nibabel as nib
from scipy.ndimage import binary_dilation, binary_erosion, binary_fill_holes, distance_transform_edt

# HiDPI は __main__.py で QApplication 作成前に設定済み

warnings.filterwarnings("ignore", message="Glyph.*missing from current font")

from app.common.config_manager import get_config_manager
from app.common.data_models import GameConfig
from app.common.styles import BASE_STYLESHEET, SECONDARY_ACCENT, btn_style


class TutorialOverlay(QWidget):
    """チュートリアル指示を表示するオーバーレイウィジェット"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QWidget { background-color: rgba(0, 0, 0, 0); }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(0)

        # 指示パネル（デフォルト: 緑色＝操作待ち状態）
        self.instruction_panel = QFrame()
        self._set_panel_style("green")

        panel_layout = QVBoxLayout(self.instruction_panel)
        panel_layout.setContentsMargins(20, 18, 20, 14)
        panel_layout.setSpacing(8)

        # 統合テキストラベル（ステップ番号 + タイトル + 詳細を1つのボックスに）
        self.content_label = QLabel()
        self.content_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.content_label.setWordWrap(True)
        self.content_label.setTextFormat(Qt.RichText)
        self.content_label.setStyleSheet(
            "QLabel { color: white; background: transparent; font-size: 15px; line-height: 1.5; }"
        )
        panel_layout.addWidget(self.content_label, stretch=1)

        # ボタン
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self.skip_button = QPushButton("スキップ")
        self.skip_button.setStyleSheet(
            "QPushButton { background-color: rgba(255,255,255,100); color: #333;"
            "  border: none; border-radius: 8px; padding: 8px 18px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: rgba(255,255,255,150); }"
        )
        button_layout.addWidget(self.skip_button)
        button_layout.addStretch()

        self.prev_button = QPushButton("<- 前へ")
        self.prev_button.setStyleSheet(
            "QPushButton { background-color: rgba(255,255,255,150); color: #333;"
            "  border: none; border-radius: 8px; padding: 8px 18px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: rgba(255,255,255,200); }"
            "QPushButton:disabled { background-color: rgba(100,100,100,80); color: #999; }"
        )
        self.prev_button.setEnabled(False)
        button_layout.addWidget(self.prev_button)

        self.next_button = QPushButton("次へ ->")
        self.next_button.setStyleSheet(
            "QPushButton { background-color: rgba(255,255,255,220); color: #2E7D32;"
            "  border: none; border-radius: 8px; padding: 8px 28px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: rgba(255,255,255,255); }"
            "QPushButton:disabled { background-color: rgba(150,150,150,100); color: #666; }"
        )
        self.next_button.setEnabled(False)
        button_layout.addWidget(self.next_button)

        panel_layout.addLayout(button_layout)
        layout.addWidget(self.instruction_panel)
        layout.addStretch()

        # リサイズハンドル
        self.resize_handle = QLabel("⋯")
        self.resize_handle.setStyleSheet("QLabel { color: rgba(255,255,255,150); font-size: 20px; padding: 5px; background: transparent; }")
        self.resize_handle.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        grip_layout = QHBoxLayout()
        grip_layout.addStretch()
        grip_layout.addWidget(self.resize_handle)
        layout.addLayout(grip_layout)

        # ドラッグ/リサイズ用変数
        self.drag_position = None
        self.resize_start_pos = None
        self.resize_start_geometry = None
        self.is_resizing = False
        self.geometry_changed_callback = None
        self.setMinimumSize(420, 160)
        self.setMouseTracking(True)
        self.restore_timer = None

        # 内部保持用
        self._current_title = ""
        self._current_detail = ""

    _PANEL_STYLES = {
        "green": "stop:0 rgba(76, 175, 80, 230), stop:1 rgba(56, 142, 60, 230)",
        "red": "stop:0 rgba(244, 67, 54, 230), stop:1 rgba(229, 57, 53, 230)",
        "blue": "stop:0 rgba(33, 150, 243, 230), stop:1 rgba(25, 118, 210, 230)",
        "orange": "stop:0 rgba(255, 152, 0, 230), stop:1 rgba(245, 124, 0, 230)",
    }

    def _set_panel_style(self, color_key):
        stops = self._PANEL_STYLES.get(color_key, self._PANEL_STYLES["green"])
        self.instruction_panel.setStyleSheet(
            f"QFrame {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,{stops});"
            "  border: 3px solid rgba(255,255,255,200); border-radius: 15px; padding: 10px; }"
        )

    def _build_content_html(self, step_text, title, detail):
        return (
            f'<div style="margin-bottom:6px;">'
            f'<span style="font-size:13px; color:rgba(255,255,255,200);">{step_text}</span>'
            f'</div>'
            f'<div style="margin-bottom:8px;">'
            f'<span style="font-size:17px; font-weight:bold; color:white;">{title}</span>'
            f'</div>'
            f'<div>'
            f'<span style="font-size:14px; color:rgba(255,255,255,220);">{detail}</span>'
            f'</div>'
        )

    def set_instruction(self, step_num, total_steps, title, detail):
        if self.restore_timer is not None:
            self.restore_timer.stop()
            self.restore_timer.deleteLater()
            self.restore_timer = None
        self._current_title = title
        self._current_detail = detail
        step_text = f"ステップ {step_num}/{total_steps}"
        self.content_label.setText(self._build_content_html(step_text, title, detail))
        self.next_button.setEnabled(False)
        self.prev_button.setEnabled(step_num > 1)
        self._set_panel_style("green")
        self._current_step_text = step_text

    def enable_next_button(self):
        self.next_button.setEnabled(True)
        self.next_button.setStyleSheet(
            "QPushButton { background-color: rgba(76,175,80,255); color: white;"
            "  border: none; border-radius: 8px; padding: 8px 28px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: rgba(56,142,60,255); }"
        )

    def show_hint(self, message, hint_type="info"):
        """hint_type: 'error', 'success', 'info'"""
        if self.restore_timer is not None:
            self.restore_timer.stop()
            self.restore_timer.deleteLater()
            self.restore_timer = None
        if hint_type == "error":
            self._set_panel_style("red")
        elif hint_type == "success":
            self._set_panel_style("blue")
        else:
            self._set_panel_style("orange")

        step_text = getattr(self, '_current_step_text', '')
        original_title = self._current_title
        original_detail = self._current_detail

        # ヒントメッセージを詳細部分に表示
        self.content_label.setText(
            self._build_content_html(step_text, original_title, message)
        )

        if hint_type == "success":
            return

        self.restore_timer = QTimer(self)
        self.restore_timer.setSingleShot(True)
        self.restore_timer.timeout.connect(lambda: [
            self._set_panel_style("green"),
            self.content_label.setText(
                self._build_content_html(step_text, original_title, original_detail)
            )
        ])
        self.restore_timer.start(2000)

    def is_in_panel_area(self, pos):
        return self.instruction_panel.geometry().contains(pos)

    def is_in_resize_area(self, pos):
        if not self.is_in_panel_area(pos):
            return False
        rect = self.instruction_panel.geometry()
        return pos.x() >= rect.right() - 30 and pos.y() >= rect.bottom() - 30

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            if not self.is_in_panel_area(pos):
                event.ignore()
                return
            if self.is_in_resize_area(pos):
                self.is_resizing = True
                self.resize_start_pos = event.globalPosition().toPoint()
                self.resize_start_geometry = self.geometry()
                event.accept()
            else:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            if self.is_resizing and self.resize_start_pos is not None:
                delta = event.globalPosition().toPoint() - self.resize_start_pos
                new_w = max(self.minimumWidth(), self.resize_start_geometry.width() + delta.x())
                new_h = max(self.minimumHeight(), self.resize_start_geometry.height() + delta.y())
                self.resize(new_w, new_h)
                event.accept()
            elif self.drag_position is not None:
                self.move(event.globalPosition().toPoint() - self.drag_position)
                event.accept()
        else:
            pos = event.position().toPoint()
            if self.is_in_panel_area(pos):
                self.setCursor(Qt.SizeFDiagCursor if self.is_in_resize_area(pos) else Qt.ArrowCursor)
            else:
                self.unsetCursor()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.is_resizing or self.drag_position is not None:
                if self.geometry_changed_callback:
                    self.geometry_changed_callback()
            self.is_resizing = False
            self.drag_position = None
            self.resize_start_pos = None
            self.resize_start_geometry = None
            event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateMask()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.updateMask)

    def updateMask(self):
        if not self.instruction_panel:
            return
        from PySide6.QtGui import QRegion, QPainterPath
        panel_rect = self.instruction_panel.geometry()
        path = QPainterPath()
        path.addRoundedRect(QRectF(panel_rect), 15, 15)
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)


class InteractiveTutorialManager(QObject):
    """インタラクティブチュートリアルの管理クラス（19ステップ＋操作検証）"""

    tutorial_completed = Signal()
    tutorial_skipped = Signal()

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.current_step = 0
        self.is_active = False
        self.wrong_action_detected = False

        self.steps = [
            {"title": "左ドラッグでブラシを使ってみましょう",
             "detail": "画像の上で左クリックしながらドラッグして、輪郭を描いてください",
             "check": self.check_brush_draw,
             "wrong_actions": ["eraser_mode", "pan_mode", "ww_wl_mode"],
             "highlight_target": None},
            {"title": "ブラシサイズバーでサイズを変更してみましょう",
             "detail": "左側の「ブラシサイズ」スライダーを動かしてサイズを変更してください",
             "check": self.check_brush_resize_slider,
             "wrong_actions": ["brush_draw", "eraser_mode"],
             "highlight_target": "brush_size_slider"},
            {"title": "右ドラッグでブラシサイズを変更してみましょう",
             "detail": "画像上で右クリックしながらドラッグしてブラシサイズを変更してください",
             "check": self.check_right_drag_resize,
             "wrong_actions": [],
             "highlight_target": None},
            {"title": "消しゴムモードに切り替えましょう",
             "detail": "左側の「消しゴム」ボタンをクリックしてください",
             "check": self.check_eraser_mode,
             "wrong_actions": ["brush_draw", "pan_mode"],
             "highlight_target": "eraser_radio"},
            {"title": "消しゴムで消してみましょう",
             "detail": "画像の上で左クリックしながらドラッグして、描いた輪郭を消してください",
             "check": self.check_eraser_draw,
             "wrong_actions": ["brush_mode"],
             "highlight_target": None},
            {"title": "消しゴムサイズを変更してみましょう",
             "detail": "左側の「消しゴムサイズ」スライダーを動かしてサイズを変更してください",
             "check": self.check_eraser_resize,
             "wrong_actions": ["brush_mode"],
             "highlight_target": "eraser_size_slider"},
            {"title": "ブラシモードに戻りましょう",
             "detail": "左側の「ブラシ」ボタンをクリックしてください",
             "check": self.check_brush_mode_return,
             "wrong_actions": ["pan_mode"],
             "highlight_target": "brush_radio"},
            {"title": "スクロールで移動してみましょう",
             "detail": "マウスホイールまたは中ボタンドラッグでスライスを移動してください",
             "check": self.check_slice_move,
             "wrong_actions": ["eraser_mode", "pan_mode"],
             "highlight_target": None},
            {"title": "塗ってみましょう",
             "detail": "別のスライスでブラシを使って描画してください",
             "check": self.check_draw_after_slice_move,
             "wrong_actions": ["eraser_mode", "pan_mode"],
             "highlight_target": None},
            {"title": "Shiftキーを押しながら消してみましょう",
             "detail": "Shiftキーを押しながら左ドラッグすると一時的に消しゴムになります",
             "check": self.check_shift_erase,
             "wrong_actions": ["eraser_mode"],
             "highlight_target": None},
            {"title": "Ctrl+Zで元に戻してみましょう",
             "detail": "Ctrl+Zキーを押して、直前の描画を元に戻してください（Undo）",
             "check": self.check_undo,
             "wrong_actions": [],
             "highlight_target": None},
            {"title": "Ctrl+Yでやり直してみましょう",
             "detail": "Ctrl+Yキーを押して、元に戻した操作をやり直してください（Redo）",
             "check": self.check_redo,
             "wrong_actions": [],
             "highlight_target": None},
            {"title": "インターポレートを試してみましょう",
             "detail": "マウスホイールで3スライス以上移動して別の場所を塗り、Enterキーを押してください（間が補間されます）",
             "check": self.check_interpolate,
             "wrong_actions": [],
             "highlight_target": None},
            {"title": "パン/ズームモードに切り替えましょう",
             "detail": "左側の「パン/ズーム」ボタンをクリックしてください",
             "check": self.check_pan_mode,
             "wrong_actions": ["brush_draw"],
             "highlight_target": "pan_radio"},
            {"title": "パンで画像を移動してみましょう",
             "detail": "パンモードのまま、画像上で左ドラッグして画像を移動してください",
             "check": self.check_pan_drag,
             "wrong_actions": [],
             "highlight_target": None},
            {"title": "パンモードでズームしてみましょう",
             "detail": "パンモードのまま、マウスホイールを回してズームしてください",
             "check": self.check_zoom,
             "wrong_actions": [],
             "highlight_target": None},
            {"title": "表示をリセットしてみましょう",
             "detail": "「表示リセット」ボタンをクリックして、ズームとパンをリセットしてください",
             "check": self.check_reset_view,
             "wrong_actions": [],
             "highlight_target": "reset_view_button"},
            {"title": "臓器_2を選択してみましょう",
             "detail": "左側のROI一覧から「臓器_2」の名前をクリックして選択してください",
             "check": self.check_roi_change,
             "wrong_actions": [],
             "highlight_target": "roi_list"},
            {"title": "臓器_2で描いてみましょう",
             "detail": "ブラシモードに戻して左ドラッグで輪郭を描いてください。臓器_1とは異なる色で描かれることを確認しましょう",
             "check": self.check_roi2_draw,
             "wrong_actions": [],
             "highlight_target": None},
        ]

        # 進行状態の追跡
        self.brush_drawn = False
        self.brush_resized_slider = False
        self.eraser_mode_activated = False
        self.eraser_drawn = False
        self.eraser_resized = False
        self.brush_mode_returned = False
        self.slice_moved = False
        self.drawn_after_slice_move = False
        self.shift_erased = False
        self.interpolated = False
        self.pan_mode_activated = False
        self.pan_dragged = False
        self.zoomed = False
        self.right_drag_resized = False
        self.view_reset = False
        self.undo_used = False
        self.redo_used = False
        self.roi_changed = False
        self.roi2_drawn = False

        self.initial_brush_size = None
        self.initial_eraser_size = None
        self.overlay = None
        self.last_undo_time = 0
        self.step_success_shown = False
        self.check_timer = None
        self.highlighted_widget = None
        self.highlight_timer = None
        self._highlight_active = False
        self._highlight_frame = None
        self.config_manager = get_config_manager()

    def save_overlay_geometry(self):
        if self.overlay and self.config_manager:
            geo = self.overlay.geometry()
            if geo.width() < 400 or geo.height() < 200:
                return
            ts = {"overlay_x": geo.x(), "overlay_y": geo.y(),
                  "overlay_width": geo.width(), "overlay_height": geo.height()}
            if not isinstance(self.config_manager.config, dict):
                return
            self.config_manager.config.setdefault('tutorial_settings', {}).update(ts)
            self.config_manager.save_config()

    def start(self):
        self.is_active = True
        self.current_step = 0

        self.overlay = TutorialOverlay(self.app)
        self.overlay.skip_button.clicked.connect(self.skip_tutorial)
        self.overlay.prev_button.clicked.connect(self.prev_step)
        self.overlay.next_button.clicked.connect(self.next_step)

        if hasattr(self.app, 'centralWidget') and self.app.centralWidget():
            self.overlay.setParent(self.app)
            self.overlay.raise_()
            self.overlay.show()

            default_x, default_y, default_w, default_h = 10, 10, 600, 280
            if self.config_manager:
                ts = self.config_manager.config.get('tutorial_settings', {})
                x = ts.get('overlay_x', default_x)
                y = ts.get('overlay_y', default_y)
                w = ts.get('overlay_width', default_w)
                h = ts.get('overlay_height', default_h)
            else:
                x, y, w, h = default_x, default_y, default_w, default_h
            self.overlay.setGeometry(x, y, w, h)

        self.overlay.geometry_changed_callback = self.save_overlay_geometry
        self.initial_brush_size = self.app.brush_size
        self.initial_eraser_size = self.app.eraser_size

        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_current_step)
        self.check_timer.start(100)

        self.create_tutorial_rois()
        self.show_current_step()

    def create_tutorial_rois(self):
        from app.common.styles import roi_color
        self.app.roi_color_map.clear()
        self.app.roi_masks.clear()
        if not hasattr(self.app, "roi_visibility"):
            self.app.roi_visibility = {}
        else:
            self.app.roi_visibility.clear()

        tutorial_rois = [
            ("臓器_1", roi_color(0)),
            ("臓器_2", roi_color(1)),
            ("臓器_3", roi_color(2)),
        ]
        for roi_name, color in tutorial_rois:
            self.app.roi_color_map[roi_name] = color
            self.app.roi_masks[roi_name] = {}
            self.app.roi_visibility[roi_name] = True

        self.app.update_roi_list()
        self.app.current_roi_name = "臓器_1"
        self.app.roi_name_edit.setText("臓器_1")

    def show_current_step(self):
        if self.current_step >= len(self.steps):
            self.complete_tutorial()
            return
        self.step_success_shown = False
        self.reset_step_flags()
        step = self.steps[self.current_step]
        self.overlay.set_instruction(
            self.current_step + 1, len(self.steps), step["title"], step["detail"])
        if self.current_step == len(self.steps) - 1:
            self.overlay.next_button.setText("完了")
        highlight_target = step.get("highlight_target")
        if highlight_target:
            self.highlight_widget(highlight_target)
        else:
            self.clear_highlight()

    def prev_step(self):
        if self.current_step > 0:
            self.clear_highlight()
            self.current_step -= 1
            if self.overlay:
                self.overlay.next_button.setText("次へ ->")
            self.show_current_step()

    def next_step(self):
        self.clear_highlight()
        self.current_step += 1
        if self.current_step >= len(self.steps):
            self.complete_tutorial()
        else:
            if self.overlay:
                self.overlay.next_button.setText("次へ ->")
            self.show_current_step()

    def complete_tutorial(self):
        self.is_active = False
        if self.check_timer:
            self.check_timer.stop()
            self.check_timer = None
        self.clear_highlight()
        if self.overlay:
            self.overlay.hide()
            self.overlay.deleteLater()
            self.overlay = None
        QMessageBox.information(
            self.app, "チュートリアル完了",
            "おめでとうございます！\nすべての操作を習得しました。\nこれで自由に練習できます。")
        self.tutorial_completed.emit()

    def reset_step_flags(self):
        self.brush_drawn = False
        self.brush_resized_slider = False
        self.eraser_mode_activated = False
        self.eraser_drawn = False
        self.eraser_resized = False
        self.brush_mode_returned = False
        self.slice_moved = False
        self.drawn_after_slice_move = False
        self.shift_erased = False
        self.interpolated = False
        self.pan_mode_activated = False
        self.pan_dragged = False
        self.zoomed = False
        self.right_drag_resized = False
        self.view_reset = False
        self.roi_changed = False

        for attr in ('_last_draw_mode', '_last_resize_method'):
            if hasattr(self.app, attr):
                setattr(self.app, attr, None)
        for attr in ('_shift_erase_used', '_interpolate_executed', '_roi_changed',
                      '_zoom_changed', '_right_drag_resize_used', '_view_reset', '_pan_dragged'):
            if hasattr(self.app, attr):
                setattr(self.app, attr, False)

        if hasattr(self.app, 'brush_size'):
            self.initial_brush_size = self.app.brush_size
        if hasattr(self.app, 'eraser_size'):
            self.initial_eraser_size = self.app.eraser_size

    def get_widget_by_name(self, widget_name):
        if not widget_name:
            return None
        widget_map = {
            "brush_size_slider": getattr(self.app, 'brush_slider', None),
            "eraser_size_slider": getattr(self.app, 'eraser_slider', None),
            "brush_radio": getattr(self.app, 'brush_mode_btn', None),
            "eraser_radio": getattr(self.app, 'eraser_mode_btn', None),
            "pan_radio": getattr(self.app, 'pan_zoom_mode_btn', None),
            "roi_list": getattr(self.app, 'roi_listbox', None),
            "reset_view_button": getattr(self.app, 'reset_view_button', None),
        }
        return widget_map.get(widget_name)

    def highlight_widget(self, widget_name):
        self.clear_highlight()
        widget = self.get_widget_by_name(widget_name)
        if not widget:
            return
        self.highlighted_widget = widget
        self._highlight_active = True

        # ウィジェットのスタイルを触らず、上に透明フレームを重ねて赤枠を描画
        parent = widget.parentWidget()
        if not parent:
            return
        self._highlight_frame = QFrame(parent)
        self._highlight_frame.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        geo = widget.geometry()
        m = 4
        self._highlight_frame.setGeometry(
            geo.x() - m, geo.y() - m,
            geo.width() + 2 * m, geo.height() + 2 * m)
        self._highlight_frame.show()
        self._highlight_frame.raise_()
        self._set_highlight_border(True)

        self.highlight_blink_state = False
        self.highlight_timer = QTimer()
        self.highlight_timer.timeout.connect(self._blink_highlight)
        self.highlight_timer.start(600)

    def _set_highlight_border(self, bright):
        if not hasattr(self, '_highlight_frame') or not self._highlight_frame:
            return
        if bright:
            self._highlight_frame.setStyleSheet(
                "QFrame { border: 3px solid rgba(255, 60, 60, 220);"
                " border-radius: 8px; background: transparent; }")
        else:
            self._highlight_frame.setStyleSheet(
                "QFrame { border: 3px solid rgba(255, 60, 60, 60);"
                " border-radius: 8px; background: transparent; }")

    def _blink_highlight(self):
        if not self._highlight_active:
            return
        self.highlight_blink_state = not self.highlight_blink_state
        self._set_highlight_border(not self.highlight_blink_state)

    def clear_highlight(self):
        self._highlight_active = False
        if self.highlight_timer:
            self.highlight_timer.stop()
            self.highlight_timer.deleteLater()
            self.highlight_timer = None
        if hasattr(self, '_highlight_frame') and self._highlight_frame:
            self._highlight_frame.hide()
            self._highlight_frame.deleteLater()
            self._highlight_frame = None
        self.highlighted_widget = None

    def skip_tutorial(self):
        reply = QMessageBox.question(
            self.app, "チュートリアルをスキップ",
            "チュートリアルをスキップしますか？\n\n後から再度見ることができます。",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.is_active = False
            if self.check_timer:
                self.check_timer.stop()
                self.check_timer = None
            self.clear_highlight()
            if self.overlay:
                self.overlay.hide()
                self.overlay.deleteLater()
                self.overlay = None
            self.tutorial_skipped.emit()

    def check_current_step(self):
        if not self.is_active or self.current_step >= len(self.steps):
            return
        step = self.steps[self.current_step]
        check_result = step["check"](None)
        if check_result:
            if not self.step_success_shown:
                self.step_success_shown = True
                self.wrong_action_detected = False
                if self.overlay:
                    self.overlay.enable_next_button()
                    self.overlay.show_hint("正解です！「次へ」ボタンをクリックして続けましょう", hint_type="success")
            return
        if not self.step_success_shown:
            wrong_action = self.detect_wrong_action(step)
            if wrong_action:
                if not self.wrong_action_detected:
                    self.wrong_action_detected = True
                    self.handle_wrong_action(wrong_action)
                    QTimer.singleShot(1000, lambda: setattr(self, 'wrong_action_detected', False))

    def detect_wrong_action(self, step):
        wrong_actions = step.get("wrong_actions", [])
        for action in wrong_actions:
            if action == "brush_draw":
                if getattr(self.app, '_last_draw_mode', None) == 'brush':
                    return "ブラシで描画しようとしています"
            elif action == "eraser_mode":
                if getattr(self.app, 'operation_mode', None) == "eraser":
                    if not hasattr(self, '_last_eraser_check') or time.time() - self._last_eraser_check > 0.5:
                        self._last_eraser_check = time.time()
                        return "消しゴムモードに切り替えようとしています"
            elif action == "brush_mode":
                if getattr(self.app, 'operation_mode', None) == "brush":
                    if not hasattr(self, '_last_brush_check') or time.time() - self._last_brush_check > 0.5:
                        self._last_brush_check = time.time()
                        return "ブラシモードに切り替えようとしています"
            elif action == "pan_mode":
                if getattr(self.app, 'operation_mode', None) == "pan_zoom":
                    if not hasattr(self, '_last_pan_check') or time.time() - self._last_pan_check > 0.5:
                        self._last_pan_check = time.time()
                        return "パンモードに切り替えようとしています"
            elif action == "ww_wl_mode":
                if getattr(self.app, 'operation_mode', None) == "ww_wl":
                    return "WW/WLモードに切り替えようとしています"
        return None

    def handle_wrong_action(self, message):
        if self.step_success_shown:
            return
        current_time = time.time()
        if current_time - self.last_undo_time > 1.0:
            self.last_undo_time = current_time
            if hasattr(self.app, 'undo_last_edit') and callable(self.app.undo_last_edit):
                try:
                    self.app.undo_last_edit()
                except Exception:
                    pass
        if self.overlay:
            self.overlay.show_hint(f"{message}\n指示に従った操作をしてください", hint_type="error")

    # ---- 各ステップのチェック関数 ----

    def check_brush_draw(self, event=None):
        if getattr(self.app, '_last_draw_mode', None) == 'brush' and not self.brush_drawn:
            self.brush_drawn = True
            return True
        return False

    def check_brush_resize_slider(self, event=None):
        current_size = getattr(self.app, 'brush_size', None)
        if (current_size is not None and self.initial_brush_size is not None
                and current_size != self.initial_brush_size
                and getattr(self.app, '_last_resize_method', None) == 'slider'):
            self.brush_resized_slider = True
            return True
        return False

    def check_right_drag_resize(self, event=None):
        if getattr(self.app, '_right_drag_resize_used', False) and not self.right_drag_resized:
            self.right_drag_resized = True
            return True
        return False

    def check_eraser_mode(self, event=None):
        if getattr(self.app, 'operation_mode', None) == "eraser" and not self.eraser_mode_activated:
            self.eraser_mode_activated = True
            return True
        return False

    def check_eraser_draw(self, event=None):
        if getattr(self.app, '_last_draw_mode', None) == 'eraser' and not self.eraser_drawn:
            self.eraser_drawn = True
            return True
        return False

    def check_eraser_resize(self, event=None):
        current_size = getattr(self.app, 'eraser_size', None)
        if (current_size is not None and self.initial_eraser_size is not None
                and current_size != self.initial_eraser_size):
            self.eraser_resized = True
            return True
        return False

    def check_brush_mode_return(self, event=None):
        if getattr(self.app, 'operation_mode', None) == "brush" and not self.brush_mode_returned:
            self.brush_mode_returned = True
            return True
        return False

    def check_slice_move(self, event=None):
        if hasattr(self.app, 'current_axial'):
            if not hasattr(self, 'slice_before_move'):
                self.slice_before_move = self.app.current_axial
                return False
            if self.app.current_axial != self.slice_before_move and not self.slice_moved:
                self.slice_moved = True
                return True
        return False

    def check_draw_after_slice_move(self, event=None):
        if getattr(self.app, '_last_draw_mode', None) == 'brush' and not self.drawn_after_slice_move:
            self.drawn_after_slice_move = True
            return True
        return False

    def check_shift_erase(self, event=None):
        if getattr(self.app, '_shift_erase_used', False) and not self.shift_erased:
            self.shift_erased = True
            return True
        return False

    def check_undo(self, event=None):
        if getattr(self.app, '_undo_used', False) and not self.undo_used:
            self.undo_used = True
            return True
        return False

    def check_redo(self, event=None):
        if getattr(self.app, '_redo_used', False) and not self.redo_used:
            self.redo_used = True
            return True
        return False

    def check_interpolate(self, event=None):
        if getattr(self.app, '_interpolate_executed', False) and not self.interpolated:
            self.interpolated = True
            return True
        return False

    def check_pan_mode(self, event=None):
        if getattr(self.app, 'operation_mode', None) == "pan_zoom" and not self.pan_mode_activated:
            self.pan_mode_activated = True
            return True
        return False

    def check_pan_drag(self, event=None):
        if getattr(self.app, '_pan_dragged', False) and not self.pan_dragged:
            self.pan_dragged = True
            return True
        return False

    def check_zoom(self, event=None):
        if getattr(self.app, '_zoom_changed', False) and not self.zoomed:
            self.zoomed = True
            return True
        return False

    def check_reset_view(self, event=None):
        if getattr(self.app, '_view_reset', False) and not self.view_reset:
            self.view_reset = True
            return True
        return False

    def check_roi_change(self, event=None):
        if getattr(self.app, 'current_roi_name', None) == "臓器_2" and not self.roi_changed:
            self.roi_changed = True
            return True
        return False

    def check_roi2_draw(self, event=None):
        if getattr(self.app, 'current_roi_name', None) == "臓器_2":
            roi2_masks = getattr(self.app, 'roi_masks', {}).get("臓器_2", {})
            if roi2_masks and not self.roi2_drawn:
                for mask in roi2_masks.values():
                    if mask is not None and np.any(mask):
                        self.roi2_drawn = True
                        return True
        return False


# -------------------- 画像⇔QImage 変換 --------------------
def to_qimage_u8(img2d: np.ndarray, levels=None) -> QImage:
    a = np.asarray(img2d)
    if levels is None:
        vmin, vmax = float(np.nanpercentile(a, 1)), float(np.nanpercentile(a, 99))
    else:
        vmin, vmax = float(levels[0]), float(levels[1])
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        vmin, vmax = 0.0, 1.0
    a = np.clip((a - vmin) * (255.0 / (vmax - vmin)), 0, 255).astype(np.uint8)
    buf = np.ascontiguousarray(a)
    h, w = buf.shape
    qimg = QImage(buf.data, w, h, int(buf.strides[0]), QImage.Format_Grayscale8)
    qimg.ndarray = buf
    return qimg


def create_colored_mask_qimage(mask: np.ndarray, color_rgba) -> QImage:
    h, w = mask.shape
    mask_u8 = mask.astype(np.uint8)
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[mask_u8 > 0] = color_rgba
    rgba_flat = np.ascontiguousarray(rgba)
    qimg = QImage(rgba_flat.data, w, h, w * 4, QImage.Format_RGBA8888)
    qimg.ndarray = rgba_flat
    return qimg


def get_color_rgba(color_name: str, alpha: int = 100):
    from PySide6.QtGui import QColor
    color_map = {
        'red': (255, 0, 0), 'blue': (0, 0, 255), 'green': (0, 255, 0),
        'yellow': (255, 255, 0), 'purple': (128, 0, 128), 'orange': (255, 165, 0),
        'pink': (255, 192, 203), 'brown': (165, 42, 42), 'cyan': (0, 255, 255),
    }
    if isinstance(color_name, str) and color_name.lower() in color_map:
        r, g, b = color_map[color_name.lower()]
        return [r, g, b, alpha]
    q = QColor(color_name)
    if q.isValid():
        return [q.red(), q.green(), q.blue(), alpha]
    return [255, 0, 0, alpha]


# -------------------- ブラシカーソル --------------------
class BrushCursor:
    def __init__(self, radius=5, color_name="yellow", line_width=2):
        from PySide6.QtGui import QColor
        self.item = QGraphicsEllipseItem()
        self.radius = radius
        self.line_width = int(line_width)
        pen = QPen(QColor(color_name), self.line_width)
        pen.setCosmetic(True)
        self.item.setPen(pen)
        self.item.setBrush(QBrush())
        self.item.setAcceptedMouseButtons(Qt.NoButton)
        self.set_radius(radius)
        self.set_visible(False)

    def set_radius(self, radius):
        self.radius = radius
        r = float(radius)
        self.item.setRect(QRectF(-r, -r, 2*r, 2*r))

    def set_visible(self, visible):
        self.item.setVisible(visible)

    def setPos(self, x, y):
        self.item.setPos(float(x), float(y))

    def set_line_width(self, w: int):
        self.line_width = max(1, int(w))
        col = self.item.pen().color()
        pen = QPen(col, self.line_width)
        pen.setCosmetic(True)
        self.item.setPen(pen)

    def set_color_name(self, color_name: str):
        from PySide6.QtGui import QColor
        pen = QPen(QColor(color_name), self.line_width)
        pen.setCosmetic(True)
        self.item.setPen(pen)

    def get_graphics_item(self):
        return self.item


class _GameKeyBlocker(QObject):
    """ゲーム時に Ctrl+O / Shift+O / Shift+S / Ctrl+S を横取りして無効化するフィルタ"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._block = False

    def set_block(self, on: bool):
        self._block = bool(on)

    def eventFilter(self, obj, event):
        if not self._block:
            return False
        et = event.type()
        if et in (QEvent.ShortcutOverride, QEvent.KeyPress, QEvent.KeyRelease):
            mods = event.modifiers()
            key = event.key()
            # Ctrl+O / Ctrl+S もしくは Shift+O / Shift+S をブロック
            if ((mods & Qt.ControlModifier and key in (Qt.Key_O, Qt.Key_S)) or
                (mods & Qt.ShiftModifier  and key in (Qt.Key_O, Qt.Key_S))):
                event.accept()
                return True
        return False



# -------------------- 改良ビュー --------------------
class ImprovedMedicalView(QGraphicsView):
    def __init__(self, app, view_type="axial"):
        super().__init__()
        self.app = app
        self.view_type = view_type
        self._interp_enabled = True
        self.initial_zoom_multiplier = 1.0  # ★ フィット時の倍率（Axial=1、他で3を上書き）

        self.setBackgroundBrush(Qt.black)
        self.setRenderHints(
            self.renderHints()
            | QPainter.SmoothPixmapTransform
            | QPainter.Antialiasing
            | QPainter.TextAntialiasing
        )
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.NoDrag)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.image_item = QGraphicsPixmapItem()
        self.image_item.setTransformationMode(Qt.SmoothTransformation)
        self.image_item.setZValue(0)
        self.image_item.setAcceptedMouseButtons(Qt.NoButton)
        self.scene.addItem(self.image_item)

        self.mask_items = {}
        self.temp_mask_item = None
        self.preview_item = None

        if self.view_type == "axial":
            self.brush_cursor = BrushCursor(5)
            self.brush_cursor.get_graphics_item().setZValue(50)
            self.scene.addItem(self.brush_cursor.get_graphics_item())
        else:
            self.brush_cursor = None

        self.crosshair_items = {"ax": None, "sag": None, "cor": None}

        self.img_w = 1
        self.img_h = 1
        self.base_scale = 1.0
        self._initialized = False
        self._fit_mode = True
        self.rotation_deg = -90

        self.drawing_mode = False
        self.pan_mode = False

        self.wl_start = None
        self.wl0 = 0
        self.ww0 = 0

    # --- 補間（描画品質） ---
    def set_interpolation(self, enabled: bool):
        self._interp_enabled = bool(enabled)
        self.setRenderHint(QPainter.SmoothPixmapTransform, self._interp_enabled)
        mode = Qt.SmoothTransformation if self._interp_enabled else Qt.FastTransformation
        try:
            self.image_item.setTransformationMode(mode)
        except AttributeError:
            pass
        for it in self.mask_items.values():
            try:
                it.setTransformationMode(mode)
            except AttributeError:
                pass
        if self.temp_mask_item is not None:
            try:
                self.temp_mask_item.setTransformationMode(mode)
            except AttributeError:
                pass
        if hasattr(self, "preview_item") and self.preview_item is not None:
            try:
                self.preview_item.setTransformationMode(mode)
            except AttributeError:
                pass

        pix = self.image_item.pixmap()
        if not pix.isNull():
            self.image_item.setPixmap(pix.copy())
            try:
                self.image_item.setTransformationMode(mode)
            except AttributeError:
                pass

        self.scene.invalidate(self.scene.sceneRect(), QGraphicsScene.AllLayers)
        try:
            self.resetCachedContent()
        except Exception:
            pass
        self.viewport().update()

    # --- 画像サイズ・パン領域 ---
    def set_image_size(self, w: int, h: int):
        self.img_w, self.img_h = max(1, int(w)), max(1, int(h))
        MARGIN_FACTOR = 150.0
        margin_w = self.img_w * MARGIN_FACTOR
        margin_h = self.img_h * MARGIN_FACTOR
        self.scene.setSceneRect(QRectF(-margin_w, -margin_h,
                                       self.img_w + 2 * margin_w,
                                       self.img_h + 2 * margin_h))

    def set_slice_image(self, qimg: QImage):
        self.image_item.setPixmap(QPixmap.fromImage(qimg))
        mode = Qt.SmoothTransformation if getattr(self, "_interp_enabled", True) else Qt.FastTransformation
        try:
            self.image_item.setTransformationMode(mode)
        except AttributeError:
            pass

        w, h = qimg.width(), qimg.height()
        if not self._initialized:
            self.set_image_size(w, h)
            QTimer.singleShot(0, self.fit_to_view)
            self._initialized = True
            return
        if w != self.img_w or h != self.img_h:
            self.set_image_size(w, h)
            QTimer.singleShot(0, self.fit_to_view)

    # --- スケール合成 ---
    def _compose_transform(self, base_scale: float, zoom_scale: float) -> QTransform:
        fx_mm_per_px, fy_mm_per_px = self._pixel_size_factors()
        sx = max(1e-9, base_scale * zoom_scale * fx_mm_per_px)
        sy = max(1e-9, base_scale * zoom_scale * fy_mm_per_px)
        t = QTransform()
        t.scale(sx, sy)
        t.rotate(self.rotation_deg)
        return t

    # --- フィット：毎回 multiplier を適用する（最大化時に小さくならない） ---
    def fit_to_view(self):
        if self.img_w <= 0 or self.img_h <= 0:
            return

        vw = max(1, self.viewport().width())
        vh = max(1, self.viewport().height())

        fx_mm_per_px, fy_mm_per_px = self._pixel_size_factors()
        phys_w = self.img_w * fx_mm_per_px
        phys_h = self.img_h * fy_mm_per_px

        rot = (self.rotation_deg % 180) != 0
        if rot:
            phys_w, phys_h = phys_h, phys_w

        if phys_w <= 0 or phys_h <= 0:
            self.base_scale = 1.0
        else:
            self.base_scale = min(vw / phys_w, vh / phys_h)

        # ★ 常に initial_zoom_multiplier を適用（Axial=1、Sagi/Cor=3）
        mult = float(getattr(self, "initial_zoom_multiplier", 1.0))
        self.zoom_scale = max(0.01, mult)

        self.setTransform(self._compose_transform(self.base_scale, self.zoom_scale))
        self.centerOn(self.img_w * 0.5, self.img_h * 0.5)
        self._fit_mode = True

    def _pixel_size_factors(self) -> tuple[float, float]:
        vx = max(1e-6, float(getattr(self.app, 'vx', 1.0)))
        vy = max(1e-6, float(getattr(self.app, 'vy', 1.0)))
        vz = max(1e-6, float(getattr(self.app, 'vz', 1.0)))
        if self.view_type == "axial":
            return (1.0 / vy, 1.0 / vx)
        elif self.view_type == "sagittal":
            return (1.0 / vz, 1.0 / vy)
        elif self.view_type == "coronal":
            return (1.0 / vz, 1.0 / vx)
        else:
            return (1.0, 1.0)

    def _current_scale(self) -> float:
        m = self.transform()
        from math import hypot
        return hypot(m.m11(), m.m12())

    def zoom_percent(self) -> int:
        if not hasattr(self, "zoom_scale") or self.base_scale == 0:
            return 100
        return int(round(self.zoom_scale * 100))

    # --- 入力 ---
    def update_brush_cursor(self, scene_pos):
        if not self.brush_cursor or self.app.nifti_data is None:
            return
        anchor = getattr(self, "_brush_size_anchor_scene", None)
        lock = getattr(self, "_lock_brush_pos", False)
        if lock and anchor is not None:
            scene_pos = anchor
        view_pos = self.mapToScene(self.mapFromScene(scene_pos))
        slice_data = self.app.get_slice_data(self.view_type, self.app.get_current_slice_for_view(self.view_type))
        if slice_data is None:
            self.brush_cursor.set_visible(False)
            return
        h, w = slice_data.shape
        if 0 <= view_pos.x() <= w and 0 <= view_pos.y() <= h:
            self.brush_cursor.setPos(view_pos.x(), view_pos.y())
            self.brush_cursor.set_visible(True)
        else:
            self.brush_cursor.set_visible(False)

    def wheelEvent(self, ev):
        if self.app.nifti_data is None:
            ev.ignore()
            return
        dy = ev.angleDelta().y()
        mods = ev.modifiers()

        # パン/ズームモード：修飾キー不要でズーム
        if self.app.operation_mode == "pan_zoom" and dy != 0:
            steps = dy / 120.0
            factor = 1.15 ** steps
            if not hasattr(self, "zoom_scale"):
                self.zoom_scale = 1.0
            self.zoom_scale = max(0.02, min(self.zoom_scale * factor, 100.0))
            self.setTransform(self._compose_transform(self.base_scale, self.zoom_scale))
            self._fit_mode = False
            self.app._zoom_changed = True
            ev.accept()
            return

        # 他のモード：Ctrl+スクロールでズーム（従来通り）
        if (mods & Qt.ControlModifier) and dy != 0:
            steps = dy / 120.0
            factor = 1.15 ** steps
            if not hasattr(self, "zoom_scale"):
                self.zoom_scale = 1.0
            self.zoom_scale = max(0.02, min(self.zoom_scale * factor, 100.0))
            self.setTransform(self._compose_transform(self.base_scale, self.zoom_scale))
            self._fit_mode = False
            self.app._zoom_changed = True
            ev.accept()
            return

        current_slice = self.app.get_current_slice_for_view(self.view_type)
        max_slice = self.app.get_max_slice_for_view(self.view_type)
        if dy > 0 and current_slice < max_slice:
            self.app.set_current_slice_for_view(self.view_type, current_slice + 1)
        elif dy < 0 and current_slice > 0:
            self.app.set_current_slice_for_view(self.view_type, current_slice - 1)
        else:
            ev.accept()
            return

        if self.view_type == "axial":
            self.app.temp_mask = None
            self.app.is_drawing = False
            self.app.drawing_points = []
        self.app.update_display()
        self.app.update_slice_labels()
        ev.accept()

    def mousePressEvent(self, ev):
        if self.app.nifti_data is None:
            super().mousePressEvent(ev)
            return

        # --- 中ボタンドラッグ：スライス移動（全ビュー）＋OSカーソル＆ブラシ円を非表示 ---
        if ev.button() == Qt.MiddleButton:
            self._middle_dragging = True
            self._middle_last_pos = ev.pos()
            self._middle_drag_accum = 0.0
            # OSカーソル非表示
            try:
                self.viewport().setCursor(Qt.BlankCursor)
                self._cursor_hidden_by_middle = True
            except Exception:
                self._cursor_hidden_by_middle = False
            # ブラシ円も非表示（Axialのみ持っている）
            if getattr(self, "brush_cursor", None):
                try:
                    item = self.brush_cursor.get_graphics_item()
                    self._brush_visible_backup_middle = bool(item.isVisible())
                except Exception:
                    self._brush_visible_backup_middle = False
                self.brush_cursor.set_visible(False)
            ev.accept()
            return

        # --- Axial 限定の編集・調整 ---
        if self.view_type != "axial":
            super().mousePressEvent(ev)
            return

        # === モード別の左ボタン処理 ===
        if ev.button() == Qt.LeftButton:
            mode = self.app.operation_mode

            # パン/ズームモード
            if mode == "pan_zoom":
                self.setDragMode(QGraphicsView.ScrollHandDrag)
                self.pan_mode = True
                self._fit_mode = False
                super().mousePressEvent(ev)
                return

            # WW/WLモード
            elif mode == "ww_wl":
                self.wl_start = self.mapToScene(ev.pos())
                self.wl0 = self.app.window_level
                self.ww0 = self.app.window_width
                ev.accept()
                return

            # ブラシモード
            elif mode == "brush":
                self.drawing_mode = True
                self.app.current_tool_mode = "brush"
                scene_pos = self.mapToScene(ev.pos())
                self.app.start_drawing(scene_pos)
                ev.accept()
                return

            # 消しゴムモード
            elif mode == "eraser":
                self.drawing_mode = True
                self.app.current_tool_mode = "eraser"
                scene_pos = self.mapToScene(ev.pos())
                self.app.start_drawing(scene_pos)
                ev.accept()
                return

        # 右ドラッグ = ブラシサイズ調整（位置ロック＋カーソル非表示）
        if ev.button() == Qt.RightButton:
            self._brush_drag_start_pos = ev.pos()
            # ブラシモードか消しゴムモードかで適切な初期サイズを保存
            if self.app.operation_mode == "brush":
                self._brush_size_start = self.app.brush_size
            elif self.app.operation_mode == "eraser":
                self._brush_size_start = self.app.eraser_size
            else:
                self._brush_size_start = self.app.brush_size  # デフォルト
            self._brush_size_adjusting = True
            self._brush_size_anchor_scene = self.mapToScene(ev.pos())
            self._lock_brush_pos = True
            if self.brush_cursor and self._brush_size_anchor_scene is not None:
                self.brush_cursor.setPos(self._brush_size_anchor_scene.x(), self._brush_size_anchor_scene.y())
                self.brush_cursor.set_visible(True)
            try:
                self.viewport().setCursor(Qt.BlankCursor)
                self._cursor_hidden = True
            except Exception:
                self._cursor_hidden = False
            ev.accept()
            return

        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        scene_pos = self.mapToScene(ev.pos())

        # Axialのブラシカーソル更新（中ドラッグ中は常に隠す）
        if self.view_type == "axial":
            if getattr(self, "_middle_dragging", False):
                if getattr(self, "brush_cursor", None):
                    self.brush_cursor.set_visible(False)
            else:
                if getattr(self, "_lock_brush_pos", False) and getattr(self, "_brush_size_anchor_scene", None) is not None:
                    self.update_brush_cursor(self._brush_size_anchor_scene)
                else:
                    self.update_brush_cursor(scene_pos)

        # --- 中ボタンドラッグ中はスライス移動（全ビュー） ---
        if getattr(self, "_middle_dragging", False) and (ev.buttons() & Qt.MiddleButton):
            dy = ev.pos().y() - getattr(self, "_middle_last_pos", ev.pos()).y()
            self._middle_drag_accum += dy
            self._middle_last_pos = ev.pos()

            # 1スライスあたりの移動量（px）
            pix_per_slice = 6.0
            steps = int(self._middle_drag_accum / pix_per_slice)
            if steps != 0:
                self._middle_drag_accum -= steps * pix_per_slice
                current_slice = self.app.get_current_slice_for_view(self.view_type)
                max_slice = self.app.get_max_slice_for_view(self.view_type)
                # 下へドラッグ（dy+）でスライス+、上で-
                new_slice = int(np.clip(current_slice + steps, 0, max_slice))
                if new_slice != current_slice:
                    self.app.set_current_slice_for_view(self.view_type, new_slice)
                    if self.view_type == "axial":
                        self.app.temp_mask = None
                        self.app.is_drawing = False
                        self.app.drawing_points = []
                    self.app.update_display()
                    self.app.update_slice_labels()
            ev.accept()
            return

        # --- Axial: 描画 ---
        if self.drawing_mode and self.view_type == "axial":
            self.app.continue_drawing(scene_pos)
            ev.accept()
            return

        # --- Axial: WW/WLモードでの左ドラッグ ---
        if self.view_type == "axial" and (ev.buttons() & Qt.LeftButton):
            if self.app.operation_mode == "ww_wl" and self.wl_start is not None:
                dx = scene_pos.x() - self.wl_start.x()
                dy = scene_pos.y() - self.wl_start.y()
                new_wl = self.wl0 + (-dy) * 1.5
                new_ww = max(1.0, self.ww0 + dx * 3.0)
                self.app.set_window(new_wl, new_ww)
                ev.accept()
                return

        # --- Axial: 右ドラッグ中の処理（ブラシサイズ調整） ---
        if self.view_type == "axial" and (ev.buttons() & Qt.RightButton):
            if hasattr(self, "_brush_drag_start_pos") and hasattr(self, "_brush_size_start"):
                dx = ev.pos().x() - self._brush_drag_start_pos.x()
                new_size = int(self._brush_size_start + (dx / 3.0))
                new_size = max(1, min(30, new_size))
                # ブラシモードか消しゴムモードかで適切なスライダーを更新
                if self.app.operation_mode == "brush":
                    self.app.brush_slider.setValue(new_size)
                elif self.app.operation_mode == "eraser":
                    self.app.eraser_slider.setValue(new_size)
                if self.brush_cursor and getattr(self, "_brush_size_anchor_scene", None) is not None:
                    self.brush_cursor.setPos(self._brush_size_anchor_scene.x(), self._brush_size_anchor_scene.y())
                    self.brush_cursor.set_visible(True)
                ev.accept()
                return

        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        # 中ボタンドラッグ終了：OSカーソル＆ブラシ円を復帰
        if ev.button() == Qt.MiddleButton and getattr(self, "_middle_dragging", False):
            self._middle_dragging = False
            self._middle_drag_accum = 0.0
            # OSカーソルを元へ
            if getattr(self, "_cursor_hidden_by_middle", False):
                try:
                    self.viewport().unsetCursor()
                except Exception:
                    pass
                self._cursor_hidden_by_middle = False
            # ブラシ円の可視状態を元へ（Axialのみ）
            if getattr(self, "brush_cursor", None):
                want_show = bool(getattr(self, "_brush_visible_backup_middle", False))
                # 現在位置が画像内の時だけ表示（元々非表示ならそのまま）
                if want_show:
                    try:
                        self.update_brush_cursor(self.mapToScene(ev.pos()))
                    except Exception:
                        self.brush_cursor.set_visible(True)
                else:
                    self.brush_cursor.set_visible(False)
                self._brush_visible_backup_middle = False
            ev.accept()
            return

        if self.pan_mode and ev.button() == Qt.LeftButton:
            self.setDragMode(QGraphicsView.NoDrag)
            self.pan_mode = False
            self.app._pan_dragged = True

        if self.drawing_mode and ev.button() == Qt.LeftButton and self.view_type == "axial":
            self.drawing_mode = False
            self.app.finish_drawing()
            ev.accept()
            return

        if ev.button() == Qt.RightButton:
            # 右ドラッグでサイズ変更が行われた場合を追跡
            if getattr(self, '_brush_size_adjusting', False):
                start_size = getattr(self, '_brush_size_start', None)
                if start_size is not None:
                    current_size = (self.app.brush_size if self.app.operation_mode == "brush"
                                    else self.app.eraser_size)
                    if current_size != start_size:
                        self.app._right_drag_resize_used = True
            self.wl_start = None
            self._brush_size_adjusting = False
            self._lock_brush_pos = False
            self._brush_size_anchor_scene = None
            if hasattr(self, "_brush_drag_start_pos"):
                self._brush_drag_start_pos = None
            if hasattr(self, "_brush_size_start"):
                self._brush_size_start = None
            if getattr(self, "_cursor_hidden", False):
                try:
                    self.viewport().unsetCursor()
                except Exception:
                    pass
                self._cursor_hidden = False
            ev.accept()
            return

        super().mouseReleaseEvent(ev)

    def resizeEvent(self, ev):
        prev_center = self.mapToScene(self.viewport().rect().center())
        super().resizeEvent(ev)
        if not self._initialized:
            return
        if getattr(self, "_fit_mode", False):
            # ★ フィットモード中は、最大化/リサイズで毎回 multiplier を適用したフィット
            self.fit_to_view()
        else:
            self.centerOn(prev_center)

    # --- オーバーレイ更新（省略せず現状のまま） ---
    def update_mask_overlays(self):
        # 既存アイテムをクリーンアップ
        for item in self.mask_items.values():
            self.scene.removeItem(item)
        self.mask_items.clear()

        if getattr(self, "preview_item", None) is not None:
            self.scene.removeItem(self.preview_item)
            self.preview_item = None

        if self.temp_mask_item is not None:
            self.scene.removeItem(self.temp_mask_item)
            self.temp_mask_item = None

        if self.app.nifti_data is None:
            self.update_crosshair_lines()
            return

        current_slice = self.app.get_current_slice_for_view(self.view_type)
        slice_data = self.app.get_slice_data(self.view_type, current_slice)
        if slice_data is None:
            self.update_crosshair_lines()
            return

        mode = Qt.SmoothTransformation if self._interp_enabled else Qt.FastTransformation
        curr_visible = getattr(self.app, "roi_visibility", {}).get(self.app.current_roi_name, True)

        # --- プレビュー（点線の輪郭） ---
        # 以前は塗りつぶしシアンを下地に敷いていたが（create_colored_mask_qimage）、
        # 常に輪郭だけ表示するため dotted outline に変更。
        prev_mask = self.app.get_preview_mask_for_view(self.view_type, current_slice)
        if self.view_type == "axial" and curr_visible and prev_mask is not None and np.any(prev_mask):
            color = self.app.roi_color_map.get(self.app.current_roi_name, 'red')
            color_rgba = get_color_rgba(color, 230)
            spacing = getattr(self.app, "preview_dot_spacing", 2)
            qimg_prev = create_dotted_outline_qimage(
                prev_mask, color_rgba, dot_radius=1, spacing=spacing, border_thickness=1
            )
            self.preview_item = QGraphicsPixmapItem(QPixmap.fromImage(qimg_prev))
            try:
                self.preview_item.setTransformationMode(mode)
            except AttributeError:
                pass
            self.preview_item.setZValue(15)  # 最前面（確定輪郭より上）
            self.preview_item.setAcceptedMouseButtons(Qt.NoButton)
            self.scene.addItem(self.preview_item)

        # --- 確定済み ROI（実線の輪郭） ---
        # 描画中（temp_maskがある時）は、編集中のROIの確定済み輪郭を非表示にする
        is_editing_current_roi = (self.view_type == "axial"
                                  and self.app.temp_mask is not None
                                  and np.any(self.app.temp_mask))

        if self.app.roi_masks:
            thickness = max(1, int(getattr(self.app, "roi_outline_thickness", 2)))
            vis_map = getattr(self.app, "roi_visibility", {})
            for roi_name in self.app.roi_masks.keys():
                if not vis_map.get(roi_name, True):
                    continue
                # 現在編集中のROIは確定済み輪郭を非表示にする
                if is_editing_current_roi and roi_name == self.app.current_roi_name:
                    continue
                mask = self.app.get_roi_mask_for_view(roi_name, self.view_type, current_slice)
                if mask is not None and np.any(mask):
                    color = self.app.roi_color_map.get(roi_name, 'red')
                    color_rgba = get_color_rgba(color, 255)
                    qimg = create_outline_qimage(mask, color_rgba, thickness=thickness)
                    item = QGraphicsPixmapItem(QPixmap.fromImage(qimg))
                    try:
                        item.setTransformationMode(mode)
                    except AttributeError:
                        pass
                    item.setZValue(12)
                    item.setAcceptedMouseButtons(Qt.NoButton)
                    self.scene.addItem(item)
                    self.mask_items[roi_name] = item

        # --- テンポラリ描画（実線の輪郭） ---
        # 以前の塗りつぶし表示を輪郭表示に変更。
        if (self.view_type == "axial"
            and curr_visible
            and self.app.temp_mask is not None
            and np.any(self.app.temp_mask)):
            thickness = max(1, int(getattr(self.app, "roi_outline_thickness", 2)))
            color = self.app.roi_color_map.get(self.app.current_roi_name, 'red')
            color_rgba = get_color_rgba(color, 255)
            qimg = create_outline_qimage(self.app.temp_mask, color_rgba, thickness=thickness)
            self.temp_mask_item = QGraphicsPixmapItem(QPixmap.fromImage(qimg))
            try:
                self.temp_mask_item.setTransformationMode(mode)
            except AttributeError:
                pass
            self.temp_mask_item.setZValue(14)  # 確定輪郭より上、プレビューより下
            self.temp_mask_item.setAcceptedMouseButtons(Qt.NoButton)
            self.scene.addItem(self.temp_mask_item)

        self.update_crosshair_lines()

    def update_temp_mask(self):
        if self.temp_mask_item is not None:
            self.scene.removeItem(self.temp_mask_item)
            self.temp_mask_item = None

        curr_visible = getattr(self.app, "roi_visibility", {}).get(self.app.current_roi_name, True)
        if self.view_type == "axial" and curr_visible and self.app.temp_mask is not None and np.any(self.app.temp_mask):
            thickness = max(1, int(getattr(self.app, "roi_outline_thickness", 2)))
            color = self.app.roi_color_map.get(self.app.current_roi_name, 'red')
            color_rgba = get_color_rgba(color, 255)
            qimg = create_outline_qimage(self.app.temp_mask, color_rgba, thickness=thickness)
            self.temp_mask_item = QGraphicsPixmapItem(QPixmap.fromImage(qimg))
            mode = Qt.SmoothTransformation if self._interp_enabled else Qt.FastTransformation
            try:
                self.temp_mask_item.setTransformationMode(mode)
            except AttributeError:
                pass
            self.temp_mask_item.setZValue(10)
            self.temp_mask_item.setAcceptedMouseButtons(Qt.NoButton)
            self.scene.addItem(self.temp_mask_item)

    def set_display_rotation(self, degrees: int):
        self.rotation_deg = int(degrees) % 360
        base = getattr(self, "base_scale", 1.0)
        zoom = getattr(self, "zoom_scale", 1.0)
        self.setTransform(self._compose_transform(base, zoom))
        self.centerOn(self.img_w * 0.5, self.img_h * 0.5)

    def rotate_display_step(self, delta_deg: int):
        self.set_display_rotation(self.rotation_deg + delta_deg)

    # 点線プレビュー
    def update_preview_overlays(self):
        if self.preview_item is not None:
            self.scene.removeItem(self.preview_item)
            self.preview_item = None
        if self.app.nifti_data is None:
            return
        if not getattr(self.app, "roi_visibility", {}).get(self.app.current_roi_name, True):
            return
        current_slice = self.app.get_current_slice_for_view(self.view_type)
        mask = self.app.get_preview_mask_for_view(self.view_type, current_slice)
        if mask is None or not np.any(mask):
            return
        color = self.app.roi_color_map.get(self.app.current_roi_name, 'red')
        color_rgba = get_color_rgba(color, 230)
        spacing = self.app.preview_dot_spacing
        qimg = create_dotted_outline_qimage(
            mask, color_rgba, dot_radius=1, spacing=spacing, border_thickness=1
        )
        self.preview_item = QGraphicsPixmapItem(QPixmap.fromImage(qimg))
        try:
            self.preview_item.setTransformationMode(
                Qt.SmoothTransformation if self._interp_enabled else Qt.FastTransformation
            )
        except AttributeError:
            pass
        self.preview_item.setZValue(15)
        self.preview_item.setAcceptedMouseButtons(Qt.NoButton)
        self.scene.addItem(self.preview_item)

    def update_crosshair_lines(self):
        from PySide6.QtWidgets import QGraphicsLineItem
        from PySide6.QtGui import QColor
        if self.app.nifti_data is None:
            for k in self.crosshair_items:
                if self.crosshair_items[k]:
                    self.crosshair_items[k].setVisible(False)
            return
        current_slice = self.app.get_current_slice_for_view(self.view_type)
        slice_data = self.app.get_slice_data(self.view_type, current_slice)
        if slice_data is None:
            for k in self.crosshair_items:
                if self.crosshair_items[k]:
                    self.crosshair_items[k].setVisible(False)
            return
        h, w = slice_data.shape

        def ensure_line(key: str, color: QColor, z: float):
            line = self.crosshair_items.get(key)
            if line is None:
                line = QGraphicsLineItem()
                pen = QPen(color, 1)
                pen.setCosmetic(True)
                pen.setStyle(Qt.DashLine)
                line.setPen(pen)
                line.setZValue(z)
                line.setAcceptedMouseButtons(Qt.NoButton)
                self.scene.addItem(line)
                self.crosshair_items[key] = line
            line.setVisible(True)
            return line

        col_ax  = QColor(0, 255, 255)
        col_sag = QColor(255, 0, 255)
        col_cor = QColor(255, 255, 0)

        if self.view_type == "axial":
            r_sag = int(np.clip(self.app.current_sagittal, 0, h-1))
            c_cor = int(np.clip(self.app.current_coronal,  0, w-1))
            sag_line = ensure_line("sag", col_sag, 20)
            cor_line = ensure_line("cor", col_cor, 20)
            sag_line.setLine(0, float(r_sag), float(w-1), float(r_sag))
            cor_line.setLine(float(c_cor), 0, float(c_cor), float(h-1))
            if self.crosshair_items.get("ax"):
                self.crosshair_items["ax"].setVisible(False)

        elif self.view_type == "sagittal":
            r_cor = int(np.clip(self.app.current_coronal, 0, h-1))
            c_ax  = int(np.clip(self.app.current_axial,   0, w-1))
            cor_line = ensure_line("cor", col_cor, 20)
            ax_line  = ensure_line("ax",  col_ax,  20)
            cor_line.setLine(0, float(r_cor), float(w-1), float(r_cor))
            ax_line.setLine(float(c_ax), 0, float(c_ax), float(h-1))
            if self.crosshair_items.get("sag"):
                self.crosshair_items["sag"].setVisible(False)

        else:
            r_sag = int(np.clip(self.app.current_sagittal, 0, h-1))
            c_ax  = int(np.clip(self.app.current_axial,    0, w-1))
            sag_line = ensure_line("sag", col_sag, 20)
            ax_line  = ensure_line("ax",  col_ax,  20)
            sag_line.setLine(0, float(r_sag), float(w-1), float(r_sag))
            ax_line.setLine(float(c_ax), 0, float(c_ax), float(h-1))
            if self.crosshair_items.get("cor"):
                self.crosshair_items["cor"].setVisible(False)


# -------------------- メインアプリ --------------------
class SimpleNiftiContouringApp(QMainWindow):
    # カスタムシグナル: ウィンドウが閉じる前に発火
    window_closing = Signal()

    def __init__(self):
        super().__init__()

        # 統一設定マネージャーを初期化
        self.config_manager = get_config_manager() if get_config_manager() else None

        self.setWindowTitle("3断面表示 NIfTI Contouring Tool - 新レイアウト＋WW/WLプリセット")
        self.setStyleSheet(BASE_STYLESHEET)
        # 初期状態で全画面表示
        self.showMaximized()

        # ---- データ ----
        self.nifti_data = None
        self.nifti_img = None

        # 3断面位置
        self.current_axial = 0
        self.current_sagittal = 0
        self.current_coronal = 0
        self.max_axial = 0
        self.max_sagittal = 0
        self.max_coronal = 0

        # voxel size
        self.vx = 1.0; self.vy = 1.0; self.vz = 1.0

        # ROI / 描画
        self.roi_masks = {}
        self.current_roi_name = "ROI_1"

        # ★ ROI色は固定パレットから順番に割り当て
        from app.common.styles import ROI_PALETTE, roi_color
        self.roi_colors = list(ROI_PALETTE)
        self.roi_color_map = {"ROI_1": roi_color(0)}

        self.brush_size = 5
        self.eraser_size = 5  # 消しゴム専用のサイズ
        self.is_drawing = False
        self.tool_mode = "brush"
        self.current_tool_mode = "brush"

        # 操作モード（ボタンで切り替え）
        self.operation_mode = "brush"  # "brush", "eraser", "pan_zoom", "ww_wl"

        self.temp_mask = None
        self.last_update_time = 0
        self.update_interval = 0.016
        self.last_draw_pos = None
        self.drawing_points = []

        # チュートリアル追跡フラグ
        self._last_draw_mode = None       # 'brush' or 'eraser'
        self._last_resize_method = None   # 'slider' or 'right_drag'
        self._shift_erase_used = False
        self._interpolate_executed = False
        self._undo_used = False
        self._redo_used = False
        self._zoom_changed = False
        self._right_drag_resize_used = False
        self._view_reset = False
        self._pan_dragged = False
        self._roi_changed = False
        self._tutorial_manager = None

        # 表示（統一設定から取得）
        if self.config_manager:
            default_wl = self.config_manager.get_ct_window()
            self.window_level = default_wl.get('level', 128)
            self.window_width = default_wl.get('window', 256)
            # CTウィンドウプリセットを設定から取得
            display_settings = self.config_manager.get_display_settings()
            ct_windows = display_settings.get('ct_windows', {})
            self.ww_wl_presets = {}
            for name, values in ct_windows.items():
                if isinstance(values, dict) and 'window' in values and 'level' in values:
                    japanese_name = {
                        'soft_tissue': '腹部',
                        'lung': '肺野',
                        'bone': '骨',
                        'brain': '脳',
                        'liver': '腹部',
                        'abdomen': '腹部',
                    }.get(name, name)
                    self.ww_wl_presets[japanese_name] = {'wl': values['level'], 'ww': values['window']}
        else:
            # フォールバック
            self.window_level = 128
            self.window_width  = 256

        # 4ボタン分のデフォルト値（設定に無いプリセットを補完）
        _default_presets = {
            "腹部": {"wl": 50, "ww": 350},
            "肺野": {"wl": -600, "ww": 1500},
            "脳":   {"wl": 40, "ww": 80},
            "骨":   {"wl": 400, "ww": 1500},
        }
        if not hasattr(self, "ww_wl_presets"):
            self.ww_wl_presets = {}
        for key, val in _default_presets.items():
            self.ww_wl_presets.setdefault(key, val)

        # キー
        self.shift_pressed = False
        self.ctrl_pressed  = False

        # ブラシカーネル
        self.brush_kernels = {}
        self._precompute_brush_kernels()

        # FPS
        self.fps_counter = 0
        self.fps_start_time = time.time()

        # プレビュー
        self.preview_masks = {}
        self._preview_dirty = False
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.recompute_interpolation_preview)

        # 表示カスタム
        self.roi_outline_thickness = 1
        self.preview_dot_spacing   = 3

        # UI
        self.setup_ui()
        self.setup_timers()

    def _precompute_brush_kernels(self):
        for size in range(1, 31):
            y, x = np.ogrid[-size:size+1, -size:size+1]
            kernel = (x*x + y*y) <= size*size
            coords = np.column_stack(np.where(kernel))
            coords = coords - size
            self.brush_kernels[size] = coords

    # -------------------- UI --------------------
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(5)

        self.setup_control_panel(main_layout)

        self.viewer_splitter = QSplitter(Qt.Horizontal)
        self.viewer_splitter.setChildrenCollapsible(False)
        self.viewer_splitter.setHandleWidth(6)

        axial_widget = self.setup_axial_area()
        right_widget = self.setup_sagittal_coronal_area()

        self.viewer_splitter.addWidget(axial_widget)
        self.viewer_splitter.addWidget(right_widget)
        self.viewer_splitter.setStretchFactor(0, 1)
        self.viewer_splitter.setStretchFactor(1, 1)
        main_layout.addWidget(self.viewer_splitter, stretch=1)
        QTimer.singleShot(0, lambda: self.viewer_splitter.setSizes([100, 100]))

    def setup_control_panel(self, main_layout):
        """左端：コントロールパネル（リストは色変更・表示トグル付き、編集はテキスト欄のみ）"""
        # ★ プレビュー格納（z -> 2D bool mask）
        self.preview_masks: Dict[int, np.ndarray] = {}

        control_frame = QFrame()
        control_frame.setFixedWidth(300)
        control_frame.setFrameStyle(QFrame.StyledPanel)
        control_layout = QVBoxLayout(control_frame)

        # ファイル読み込みとチュートリアル
        button_layout = QHBoxLayout()
        
        self.load_btn = QPushButton("NIfTIを開く")
        self.load_btn.clicked.connect(self.load_nifti_file)
        self.load_btn.setShortcut(QKeySequence("Ctrl+O"))
        self.load_btn.setToolTip("NIfTIを開く（Ctrl+O）")
        button_layout.addWidget(self.load_btn)

        self.tutorial_btn = QPushButton("チュートリアル")
        self.tutorial_btn.clicked.connect(self.show_tutorial)
        self.tutorial_btn.setToolTip("操作方法を学ぶ")
        self.tutorial_btn.setStyleSheet(btn_style(secondary=True))
        button_layout.addWidget(self.tutorial_btn)

        control_layout.addLayout(button_layout)

        # WW/WLプリセット（固定4ボタン: 腹部/肺野/脳/骨）
        preset_group = QGroupBox("WW/WL プリセット")
        preset_layout = QGridLayout(preset_group)
        preset_buttons = [
            ("腹部", "1", 0, 0),
            ("肺野", "2", 0, 1),
            ("脳",   "3", 1, 0),
            ("骨",   "4", 1, 1),
        ]
        for name, seq, row, col in preset_buttons:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, preset_name=name: self.apply_ww_wl_preset(preset_name))
            btn.setMaximumHeight(35)
            btn.setShortcut(QKeySequence(seq))
            btn.setToolTip(f"{name}（{seq}）")
            preset_layout.addWidget(btn, row, col)
        control_layout.addWidget(preset_group)

        # 操作モード切替
        mode_group = QGroupBox("操作モード")
        mode_layout = QVBoxLayout(mode_group)

        self.mode_button_group = QButtonGroup(self)
        mode_buttons_layout = QGridLayout()

        self.brush_mode_btn = QRadioButton("🖌 ブラシ")
        self.brush_mode_btn.setChecked(True)
        self.brush_mode_btn.setToolTip("左ドラッグでブラシ描画")
        self.mode_button_group.addButton(self.brush_mode_btn, 0)

        self.eraser_mode_btn = QRadioButton("🧹 消しゴム")
        self.eraser_mode_btn.setToolTip("左ドラッグで消去")
        self.mode_button_group.addButton(self.eraser_mode_btn, 1)

        self.pan_zoom_mode_btn = QRadioButton("🔍 パン/ズーム")
        self.pan_zoom_mode_btn.setToolTip("左ドラッグでパン、スクロールでズーム")
        self.mode_button_group.addButton(self.pan_zoom_mode_btn, 2)

        self.ww_wl_mode_btn = QRadioButton("🎚 WW/WL調整")
        self.ww_wl_mode_btn.setToolTip("左ドラッグでウィンドウレベル/幅調整")
        self.mode_button_group.addButton(self.ww_wl_mode_btn, 3)

        mode_buttons_layout.addWidget(self.brush_mode_btn, 0, 0)
        mode_buttons_layout.addWidget(self.eraser_mode_btn, 0, 1)
        mode_buttons_layout.addWidget(self.pan_zoom_mode_btn, 1, 0)
        mode_buttons_layout.addWidget(self.ww_wl_mode_btn, 1, 1)

        self.mode_button_group.buttonClicked.connect(self.on_mode_changed)

        mode_layout.addLayout(mode_buttons_layout)

        # 現在のモード表示
        self.mode_status_label = QLabel("現在: ブラシモード")
        self.mode_status_label.setAlignment(Qt.AlignCenter)
        self.mode_status_label.setStyleSheet("font-weight: bold; color: #2196F3; padding: 4px;")
        mode_layout.addWidget(self.mode_status_label)

        control_layout.addWidget(mode_group)

        # ブラシサイズ
        brush_group = QGroupBox("ブラシサイズ")
        brush_layout = QVBoxLayout(brush_group)
        self.brush_slider = QSlider(Qt.Horizontal)
        self.brush_slider.setRange(1, 30)
        self.brush_slider.setValue(5)
        self.brush_slider.valueChanged.connect(self.update_brush_size)
        brush_layout.addWidget(self.brush_slider)
        self.brush_label = QLabel("5 px")
        self.brush_label.setAlignment(Qt.AlignCenter)
        brush_layout.addWidget(self.brush_label)
        control_layout.addWidget(brush_group)

        # 消しゴムサイズ
        eraser_group = QGroupBox("消しゴムサイズ")
        eraser_layout = QVBoxLayout(eraser_group)
        self.eraser_slider = QSlider(Qt.Horizontal)
        self.eraser_slider.setRange(1, 30)
        self.eraser_slider.setValue(5)
        self.eraser_slider.valueChanged.connect(self.update_eraser_size)
        eraser_layout.addWidget(self.eraser_slider)
        self.eraser_label = QLabel("5 px")
        self.eraser_label.setAlignment(Qt.AlignCenter)
        eraser_layout.addWidget(self.eraser_label)
        control_layout.addWidget(eraser_group)

        # ▼ 表示操作（反転 + リセット + プレビューON/OFF）
        display_group = QGroupBox("表示操作")
        display_layout = QVBoxLayout(display_group)

        # 反転/リセット：2x2配置
        grid = QGridLayout()
        self.btn_flip_lr = QPushButton("左右反転")
        self.btn_flip_ap = QPushButton("前後反転")
        self.btn_flip_si = QPushButton("頭尾反転")
        self.reset_view_button = QPushButton("表示リセット")
        btn_reset = self.reset_view_button

        self.btn_flip_lr.setToolTip("左右（X軸）を反転")
        self.btn_flip_ap.setToolTip("前後（Y軸）を反転")
        self.btn_flip_si.setToolTip("頭尾（Z軸）を反転")
        btn_reset.setToolTip("回転・ズーム・パンを初期状態に戻す")

        self.btn_flip_lr.clicked.connect(self.flip_left_right)
        self.btn_flip_ap.clicked.connect(self.flip_anterior_posterior)
        self.btn_flip_si.clicked.connect(self.flip_superior_inferior)
        btn_reset.clicked.connect(self.reset_display_all)

        grid.addWidget(self.btn_flip_lr, 0, 0)
        grid.addWidget(self.btn_flip_ap, 0, 1)
        grid.addWidget(self.btn_flip_si, 1, 0)
        grid.addWidget(btn_reset,        1, 1)
        display_layout.addLayout(grid)

        # インターポレートのプレビュー ON/OFF
        # 既定は ON（True）
        self.auto_preview_enabled = True
        self.chk_preview = QCheckBox("インターポレートのプレビューを表示")
        self.chk_preview.setChecked(True)
        self.chk_preview.setToolTip("補間プレビューの点線表示をON/OFFします")
        self.chk_preview.stateChanged.connect(self.on_toggle_auto_preview)
        display_layout.addWidget(self.chk_preview)

        control_layout.addWidget(display_group)

        # ROI管理（テキストボックスで改名）
        roi_group = QGroupBox("ROI管理")
        roi_layout = QVBoxLayout(roi_group)
        roi_layout.addWidget(QLabel("現在のROI:"))
        self.roi_name_edit = QLineEdit("ROI_1")
        self.roi_name_edit.returnPressed.connect(self.change_roi_name)
        self.roi_name_edit.editingFinished.connect(self.change_roi_name)
        roi_layout.addWidget(self.roi_name_edit)
        roi_button_layout = QHBoxLayout()
        new_roi_btn = QPushButton("新ROI")
        new_roi_btn.clicked.connect(self.create_new_roi)
        new_roi_btn.setShortcut(QKeySequence("Ctrl+N"))
        new_roi_btn.setToolTip("新ROI（Ctrl+N）")
        delete_roi_btn = QPushButton("ROI削除")
        delete_roi_btn.clicked.connect(self.delete_current_roi)
        roi_button_layout.addWidget(new_roi_btn)
        roi_button_layout.addWidget(delete_roi_btn)
        roi_layout.addLayout(roi_button_layout)

        # 現在のスライスのROIを消すボタン
        clear_slice_btn = QPushButton("🗑 現在スライスのROIを消去")
        clear_slice_btn.clicked.connect(self.clear_current_slice_roi)
        clear_slice_btn.setShortcut(QKeySequence("Delete"))
        clear_slice_btn.setToolTip("現在表示中のスライスのROIを消去（Delete）")
        clear_slice_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 6px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:pressed {
                background-color: #a93226;
            }
        """)
        roi_layout.addWidget(clear_slice_btn)

        control_layout.addWidget(roi_group)

        # ROIリスト（色■と表示●/○）
        roi_list_group = QGroupBox("ROIリスト")
        roi_list_layout = QVBoxLayout(roi_list_group)
        self.roi_listbox = QListWidget()
        self.roi_listbox.setMaximumHeight(160)
        self.roi_listbox.itemClicked.connect(self.select_roi_from_list)
        roi_list_layout.addWidget(self.roi_listbox)
        control_layout.addWidget(roi_list_group)

        # 保存・読み込み
        self.file_group = QGroupBox("ファイル")
        file_layout = QVBoxLayout(self.file_group)
        self.save_btn = QPushButton("マスクを保存（NIfTI）")
        self.save_btn.clicked.connect(self.save_masks)
        self.save_btn.setShortcut(QKeySequence("Shift+S"))
        self.save_btn.setToolTip("マスク保存（Shift+S）")
        self.load_mask_btn = QPushButton("マスクを読み込み（NIfTI）")
        self.load_mask_btn.clicked.connect(self.load_masks)
        self.load_mask_btn.setShortcut(QKeySequence("Shift+O"))
        self.load_mask_btn.setToolTip("マスク読み込み（Shift+O）")
        file_layout.addWidget(self.save_btn)
        file_layout.addWidget(self.load_mask_btn)
        control_layout.addWidget(self.file_group)

        # fps_label（非表示ダミー：他コードからの参照用）
        self.fps_label = QLabel("FPS: --")
        self.fps_label.setVisible(False)

        control_layout.addStretch()

        # 中断ボタン（Playモード専用・パネル最下部）
        self.abort_game_btn = QPushButton("中断（保存しない）")
        self.abort_game_btn.setToolTip("ゲームを中断し、スコアを保存せずにハブに戻る")
        self.abort_game_btn.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; font-weight: bold; "
            "padding: 6px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #e74c3c; }"
        )
        self.abort_game_btn.clicked.connect(self._abort_game)
        self.abort_game_btn.setVisible(False)
        control_layout.addWidget(self.abort_game_btn)

        main_layout.addWidget(control_frame, stretch=0)

        # プレビュー確定のショートカット
        QShortcut(QKeySequence("Return"), self, activated=self.confirm_preview_to_roi)
        QShortcut(QKeySequence("Enter"),  self, activated=self.confirm_preview_to_roi)
        # Ctrl+S 上書き保存のショートカット
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_masks_quick)

        # 最後に保存したパスを記憶する変数を初期化
        self._last_saved_path = None
        # （Ctrl+Enter で現在スライスのみ確定を実装している場合はそのまま維持）
        # （Ctrl+Enter で現在スライスのみ確定を実装している場合はそのまま維持してください）

    def set_interpolation_enabled(self, enabled: bool):
        for view in (getattr(self, "axial_view", None),
                     getattr(self, "sagittal_view", None),
                     getattr(self, "coronal_view", None)):
            if view:
                view.set_interpolation(enabled)
        self.update_display()

    def setup_axial_area(self) -> QWidget:
        axial_widget = QWidget()
        axial_layout = QHBoxLayout(axial_widget)
        axial_layout.setSpacing(5)
        axial_layout.setContentsMargins(0, 0, 0, 0)

        axial_slider_widget = QWidget()
        axial_slider_layout = QVBoxLayout(axial_slider_widget)
        axial_slider_layout.setContentsMargins(0, 0, 0, 0)
        axial_label = QLabel("Axial")
        axial_label.setAlignment(Qt.AlignCenter)
        axial_slider_layout.addWidget(axial_label)

        self.axial_slider = QSlider(Qt.Vertical)
        self.axial_slider.valueChanged.connect(self.update_axial_slice)
        axial_slider_layout.addWidget(self.axial_slider)
        axial_slider_widget.setFixedWidth(60)

        self.axial_view = ImprovedMedicalView(self, "axial")  # initial_zoom_multiplier=1.0
        axial_layout.addWidget(axial_slider_widget)
        axial_layout.addWidget(self.axial_view)
        return axial_widget

    def setup_sagittal_coronal_area(self) -> QWidget:
        self.right_splitter = QSplitter(Qt.Vertical)
        self.right_splitter.setChildrenCollapsible(False)
        self.right_splitter.setHandleWidth(6)

        sagittal_container = QWidget()
        sagittal_layout = QHBoxLayout(sagittal_container)
        sagittal_layout.setSpacing(5)
        sagittal_layout.setContentsMargins(0, 0, 0, 0)

        self.sagittal_view = ImprovedMedicalView(self, "sagittal")
        self.sagittal_view.initial_zoom_multiplier = 3.0  # ★ ここで 3×
        sagittal_slider_widget = QWidget()
        sagittal_slider_layout = QVBoxLayout(sagittal_slider_widget)
        sagittal_slider_layout.setContentsMargins(0, 0, 0, 0)
        sagittal_label = QLabel("Sagittal")
        sagittal_label.setAlignment(Qt.AlignCenter)
        sagittal_slider_layout.addWidget(sagittal_label)
        self.sagittal_slider = QSlider(Qt.Vertical)
        self.sagittal_slider.valueChanged.connect(self.update_sagittal_slice)
        sagittal_slider_layout.addWidget(self.sagittal_slider)
        sagittal_slider_widget.setFixedWidth(60)
        sagittal_layout.addWidget(self.sagittal_view)
        sagittal_layout.addWidget(sagittal_slider_widget)

        coronal_container = QWidget()
        coronal_layout = QHBoxLayout(coronal_container)
        coronal_layout.setSpacing(5)
        coronal_layout.setContentsMargins(0, 0, 0, 0)

        self.coronal_view = ImprovedMedicalView(self, "coronal")
        self.coronal_view.initial_zoom_multiplier = 3.0  # ★ ここで 3×
        coronal_slider_widget = QWidget()
        coronal_slider_layout = QVBoxLayout(coronal_slider_widget)
        coronal_slider_layout.setContentsMargins(0, 0, 0, 0)
        coronal_label = QLabel("Coronal")
        coronal_label.setAlignment(Qt.AlignCenter)
        coronal_slider_layout.addWidget(coronal_label)
        self.coronal_slider = QSlider(Qt.Vertical)
        self.coronal_slider.valueChanged.connect(self.update_coronal_slice)
        coronal_slider_layout.addWidget(self.coronal_slider)
        coronal_slider_widget.setFixedWidth(60)
        coronal_layout.addWidget(self.coronal_view)
        coronal_layout.addWidget(coronal_slider_widget)

        self.right_splitter.addWidget(sagittal_container)
        self.right_splitter.addWidget(coronal_container)
        self.right_splitter.setStretchFactor(0, 1)
        self.right_splitter.setStretchFactor(1, 1)
        QTimer.singleShot(0, lambda: self.right_splitter.setSizes([100, 100]))
        return self.right_splitter

    # ------------- 動作系 -------------
    def apply_ww_wl_preset(self, preset_name):
        if preset_name in self.ww_wl_presets:
            preset = self.ww_wl_presets[preset_name]
            self.set_window(preset["wl"], preset["ww"])
            self.update_ww_wl_label()

    def update_ww_wl_label(self):
        if hasattr(self, "ww_wl_label"):
            self.ww_wl_label.setText(f"WL: {self.window_level:.0f}, WW: {self.window_width:.0f}")

    def setup_timers(self):
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.update_fps_display)
        self.fps_timer.start(1000)
        self.zoom_timer = QTimer()
        self.zoom_timer.timeout.connect(self.update_zoom_label)
        self.zoom_timer.start(120)

    def update_fps_display(self):
        current_time = time.time()
        elapsed = current_time - self.fps_start_time
        if elapsed >= 1.0:
            fps = self.fps_counter / elapsed
            self.fps_label.setText(f"FPS: {fps:.1f}")
            self.fps_counter = 0
            self.fps_start_time = current_time

    # ★ フィットとリセットを統合
    def fit_all_views(self):
        for view in [self.axial_view, self.sagittal_view, self.coronal_view]:
            view._fit_mode = True
            view.fit_to_view()
        self.update_zoom_label()

    # 互換のために残す（内部で統合関数を呼ぶ）
    def reset_zoom_pan(self):
        """従来の互換API：現在は表示全体のリセットに委譲"""
        self.reset_display_all()

    def fit_to_window(self):
        self.fit_all_views()

    def get_current_slice_for_view(self, view_type):
        if view_type == "axial":
            return self.current_axial
        elif view_type == "sagittal":
            return self.current_sagittal
        elif view_type == "coronal":
            return self.current_coronal
        return 0

    def set_current_slice_for_view(self, view_type, slice_idx):
        if view_type == "axial":
            self.current_axial = slice_idx
            self.axial_slider.setValue(slice_idx)
        elif view_type == "sagittal":
            self.current_sagittal = slice_idx
            self.sagittal_slider.setValue(slice_idx)
        elif view_type == "coronal":
            self.current_coronal = slice_idx
            self.coronal_slider.setValue(slice_idx)

    def get_max_slice_for_view(self, view_type):
        if view_type == "axial":
            return self.max_axial
        elif view_type == "sagittal":
            return self.max_sagittal
        elif view_type == "coronal":
            return self.max_coronal
        return 0

    def get_slice_data(self, view_type, slice_idx):
        if self.nifti_data is None:
            return None
        if view_type == 'axial':
            return self.nifti_data[:, :, slice_idx]
        elif view_type == 'sagittal':
            return self.nifti_data[slice_idx, :, :]
        elif view_type == 'coronal':
            return self.nifti_data[:, slice_idx, :]
        else:
            return None

    def get_roi_mask_for_view(self, roi_name, view_type, slice_idx):
        if roi_name not in self.roi_masks:
            return None
        if view_type == 'axial':
            m = self.roi_masks[roi_name].get(slice_idx, None)
            if m is None or not np.any(m):
                return None
            return m
        h, w, d = self.nifti_data.shape
        if view_type == 'sagittal':
            x = int(slice_idx)
            if x < 0 or x >= h:
                return None
            sagittal_mask = np.zeros((w, d), dtype=bool)
            for z_slice, mask in self.roi_masks[roi_name].items():
                if mask is None or not np.any(mask):
                    continue
                if x < mask.shape[0]:
                    sagittal_mask[:, z_slice] = mask[x, :]
            return sagittal_mask if np.any(sagittal_mask) else None

        if view_type == 'coronal':
            y = int(slice_idx)
            if y < 0 or y >= w:
                return None
            coronal_mask = np.zeros((h, d), dtype=bool)
            for z_slice, mask in self.roi_masks[roi_name].items():
                if mask is None or not np.any(mask):
                    continue
                if y < mask.shape[1]:
                    coronal_mask[:, z_slice] = mask[:, y]
            return coronal_mask if np.any(coronal_mask) else None
        return None

    def keyPressEvent(self, event: QKeyEvent):
        # 修飾キー状態
        if event.key() in (Qt.Key_Shift, Qt.Key_Control):
            if event.key() == Qt.Key_Shift:
                self.shift_pressed = True
                self.current_tool_mode = "eraser"
            elif event.key() == Qt.Key_Control:
                self.ctrl_pressed = True
            super().keyPressEvent(event)
            return

        # H: 詳細ヘルプ
        if event.key() == Qt.Key_H:
            self.show_help_dialog()
            return

        # Ctrl+Z = Undo
        if (event.key() == Qt.Key_Z) and (event.modifiers() & Qt.ControlModifier):
            self.undo_last_edit()
            return

        # Ctrl+Y = Redo
        if (event.key() == Qt.Key_Y) and (event.modifiers() & Qt.ControlModifier):
            self.redo_last_edit()
            return

        # 表示回転
        if event.key() == Qt.Key_BracketLeft:   # '[' で -90°
            for view in [self.axial_view, self.sagittal_view, self.coronal_view]:
                view.rotate_display_step(-90)
            self.update_zoom_label()
            super().keyPressEvent(event)
            return
        elif event.key() == Qt.Key_BracketRight:  # ']' で +90°
            for view in [self.axial_view, self.sagittal_view, self.coronal_view]:
                view.rotate_display_step(+90)
            self.update_zoom_label()
            super().keyPressEvent(event)
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Shift, Qt.Key_Control):
            if event.key() == Qt.Key_Shift:
                self.shift_pressed = False
                self.current_tool_mode = "brush"
            elif event.key() == Qt.Key_Control:
                self.ctrl_pressed = False
        super().keyReleaseEvent(event)

    def load_nifti_file(self):
        # ★ゲーム中はユーザー操作からの読み込みを封印（自動読込は別経路）
        if getattr(self, "game_lock_roi", False):
            QMessageBox.information(self, "情報", "ゲームモードでは手動のファイル読み込みはできません。")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "NIfTIファイルを選択", "",
            "NIfTI files (*.nii *.nii.gz);All files (*.*)"
        )
        if not file_path:
            return

        try:
            self.nifti_img = nib.load(file_path)
            data = self.nifti_img.get_fdata()

            # 4Dの場合は最初のボリュームを使う（必要に応じて調整）
            if data.ndim == 4:
                data = data[..., 0]
            self.nifti_data = data

            # --- 反転フラグを読み込み時にリセット（保存時の「元に戻す」基準になる） ---
            self.flip_lr = False  # 左右
            self.flip_ap = False  # 前後
            self.flip_si = False  # 頭尾

            # ★ ここから自動LR補正（affineのx軸がR→Lへ合わせる）
            # いまのUIの“正しく見える”基準（abdominal_ct）に合わせて、配列x軸を常に'L'に統一する
            try:
                ax = nib.aff2axcodes(self.nifti_img.affine)  # 例: ('R','A','S') / ('L','A','S') など
                if len(ax) >= 1 and ax[0] == 'R':
                    # x軸がR向き = 画面左右が逆に見えるので、配列x方向を反転
                    self.nifti_data = self.nifti_data[::-1, :, :]
                    # 保存時に元の向きへ戻せるよう、反転フラグも立てておく
                    self.flip_lr = True
            except Exception:
                # 何かあっても表示は続行（失敗時はそのまま）
                pass
            # ★ 自動LR補正ここまで

            # ボクセルサイズ
            zooms = self.nifti_img.header.get_zooms()
            self.vx = float(zooms[0]) if len(zooms) > 0 else 1.0
            self.vy = float(zooms[1]) if len(zooms) > 1 else 1.0
            self.vz = float(zooms[2]) if len(zooms) > 2 else 1.0

            # 各軸のスライス数
            h, w, d = self.nifti_data.shape

            # Axial (z)
            self.max_axial = d - 1
            self.current_axial = self.max_axial // 2
            self.axial_slider.setRange(0, self.max_axial)
            self.axial_slider.setValue(self.current_axial)

            # Sagittal (x)
            self.max_sagittal = h - 1
            self.current_sagittal = self.max_sagittal // 2
            self.sagittal_slider.setRange(0, self.max_sagittal)
            self.sagittal_slider.setValue(self.current_sagittal)

            # Coronal (y)
            self.max_coronal = w - 1
            self.current_coronal = self.max_coronal // 2
            self.coronal_slider.setRange(0, self.max_coronal)
            self.coronal_slider.setValue(self.current_coronal)

            # 初期 WL/WW（ここはプリセットで上書き可能）
            self.window_level = 50
            self.window_width = 350

            # マスク初期化
            self.roi_masks = {}
            # 既定色セットが30色に拡張済みの前提
            self.roi_color_map = {"ROI_1": self.roi_colors[0] if hasattr(self, "roi_colors") else 'red'}
            self.current_roi_name = "ROI_1"
            self.roi_name_edit.setText("ROI_1")
            self.update_roi_list()
            self.update_brush_cursor_style()  # ブラシ色/太さ反映

            # プレビュー初期化
            self.preview_masks.clear()

            # ツール状態の確実なリセット
            self.shift_pressed = False
            self.ctrl_pressed = False
            self.current_tool_mode = "brush"

            # 表示更新
            self.update_display()
            self.update_slice_labels()
            self.update_ww_wl_label()

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"ファイルの読み込みに失敗しました:\n{str(e)}")

    def update_brush_cursor_style(self):
        if hasattr(self, "axial_view") and self.axial_view and hasattr(self.axial_view, "brush_cursor"):
            color = self.roi_color_map.get(self.current_roi_name, "yellow")
            try:
                self.axial_view.brush_cursor.set_line_width(2)
                self.axial_view.brush_cursor.set_color_name(color)
            except Exception:
                pass

    def update_display(self):
        if self.nifti_data is None:
            return
        vmin = self.window_level - self.window_width / 2
        vmax = self.window_level + self.window_width / 2
        levels = (vmin, vmax)
        views = [
            (self.axial_view, "axial", self.current_axial),
            (self.sagittal_view, "sagittal", self.current_sagittal),
            (self.coronal_view, "coronal", self.current_coronal)
        ]
        for view, view_type, slice_idx in views:
            slice_data = self.get_slice_data(view_type, slice_idx)
            if slice_data is not None:
                qimg = to_qimage_u8(slice_data, levels)
                view.set_slice_image(qimg)
                view.update_mask_overlays()
                view.update_temp_mask()
        self.refresh_preview_overlays()
        self.fps_counter += 1

    def update_axial_slice(self, value):
        if self.nifti_data is None:
            return
        new_slice = int(value)
        if new_slice == self.current_axial:
            return
        self.current_axial = new_slice
        self.temp_mask = None
        self.is_drawing = False
        self.drawing_points = []
        self.last_draw_pos = None
        self.update_display()
        self.update_slice_labels()

    def update_sagittal_slice(self, value):
        if self.nifti_data is None:
            return
        new_slice = int(value)
        if new_slice == self.current_sagittal:
            return
        self.current_sagittal = new_slice
        self.update_display()
        self.update_slice_labels()

    def update_coronal_slice(self, value):
        if self.nifti_data is None:
            return
        new_slice = int(value)
        if new_slice == self.current_coronal:
            return
        self.current_coronal = new_slice
        self.update_display()
        self.update_slice_labels()

    def update_slice_labels(self):
        if hasattr(self, "axial_slice_label") and self.axial_slice_label:
            self.axial_slice_label.setText(f"Axial: {self.current_axial + 1} / {self.max_axial + 1}")
        if hasattr(self, "sagittal_slice_label") and self.sagittal_slice_label:
            self.sagittal_slice_label.setText(f"Sagittal: {self.current_sagittal + 1} / {self.max_sagittal + 1}")
        if hasattr(self, "coronal_slice_label") and self.coronal_slice_label:
            self.coronal_slice_label.setText(f"Coronal: {self.current_coronal + 1} / {self.max_coronal + 1}")

    def update_zoom_label(self):
        """ズーム表示ラベルが存在する場合のみ更新（現在はラベル非表示）"""
        if not hasattr(self, "axial_view") or self.axial_view is None:
            return
        if not hasattr(self, "zoom_label") or self.zoom_label is None:
            return
        zoom_percent = self.axial_view.zoom_percent()
        try:
            self.zoom_label.setText(f"ズーム : {zoom_percent}%")
        except Exception:
            pass

    def update_brush_size(self, value):
        self.brush_size = value
        self.brush_label.setText(f"{value} px")
        self._last_resize_method = 'slider'
        # ブラシモードの時のみカーソルサイズを更新
        if self.operation_mode == "brush":
            if hasattr(self.axial_view, 'brush_cursor') and self.axial_view.brush_cursor:
                self.axial_view.brush_cursor.set_radius(value)

    def update_eraser_size(self, value):
        self.eraser_size = value
        self.eraser_label.setText(f"{value} px")
        self._last_resize_method = 'slider'
        # 消しゴムモードの時のみカーソルサイズを更新
        if self.operation_mode == "eraser":
            if hasattr(self.axial_view, 'brush_cursor') and self.axial_view.brush_cursor:
                self.axial_view.brush_cursor.set_radius(value)

    def on_mode_changed(self, button):
        """操作モード切替ハンドラ"""
        if button == self.brush_mode_btn:
            self.operation_mode = "brush"
            self.mode_status_label.setText("現在: ブラシモード")
            self.mode_status_label.setStyleSheet("font-weight: bold; color: #2196F3; padding: 4px;")
            # ブラシサイズでカーソルを更新
            if hasattr(self.axial_view, 'brush_cursor') and self.axial_view.brush_cursor:
                self.axial_view.brush_cursor.set_radius(self.brush_size)
        elif button == self.eraser_mode_btn:
            self.operation_mode = "eraser"
            self.mode_status_label.setText("現在: 消しゴムモード")
            self.mode_status_label.setStyleSheet("font-weight: bold; color: #F44336; padding: 4px;")
            # 消しゴムサイズでカーソルを更新
            if hasattr(self.axial_view, 'brush_cursor') and self.axial_view.brush_cursor:
                self.axial_view.brush_cursor.set_radius(self.eraser_size)
        elif button == self.pan_zoom_mode_btn:
            self.operation_mode = "pan_zoom"
            self.mode_status_label.setText("現在: パン/ズームモード")
            self.mode_status_label.setStyleSheet("font-weight: bold; color: #FF9800; padding: 4px;")
        elif button == self.ww_wl_mode_btn:
            self.operation_mode = "ww_wl"
            self.mode_status_label.setText("現在: WW/WL調整モード")
            self.mode_status_label.setStyleSheet("font-weight: bold; color: #9C27B0; padding: 4px;")

    # --- 描画開始/継続/終了（略：元の実装を維持） ---
    def start_drawing(self, scene_pos):
        """描画開始時に実キーボード状態からモードを決め直す（Shift取りこぼし対策）"""
        if self.nifti_data is None:
            return

        slice_data = self.get_slice_data("axial", self.current_axial)
        if slice_data is None:
            return
        h, w = slice_data.shape
        row = int(round(scene_pos.y()))
        col = int(round(scene_pos.x()))
        if not (0 <= row < h and 0 <= col < w):
            return

        # --- スタック初期化（40段階） ---
        if not hasattr(self, "undo_stack"):
            self.undo_stack = deque(maxlen=40)
        if not hasattr(self, "redo_stack"):
            self.redo_stack = deque(maxlen=40)

        # 描画開始時にUndo用の状態を保存（まだUndoスタックには積まない）
        prev = None
        if (self.current_roi_name in self.roi_masks and
            self.current_axial in self.roi_masks[self.current_roi_name]):
            prev = self.roi_masks[self.current_roi_name][self.current_axial]
            prev = prev.copy() if prev is not None else None
        else:
            prev = None

        # 描画開始時の状態を保存（finish_drawingでUndoスタックに追加する）
        self._drawing_undo_state = (self.current_roi_name, self.current_axial, prev)

        if prev is not None:
            self._prev_mask_snapshot = prev.copy()
        else:
            self._prev_mask_snapshot = np.zeros((h, w), dtype=bool)

        self.redo_stack.clear()

        # ★ 修飾キーを実測してモード決定（フラグ取りこぼし対策）
        # ただし、消しゴムモードボタンが選択されている場合は常に消しゴム
        mods = QApplication.keyboardModifiers()
        self.shift_pressed = bool(mods & Qt.ShiftModifier)
        if self.operation_mode == "eraser":
            self.current_tool_mode = "eraser"
        elif self.operation_mode == "brush":
            # ブラシモード時はShiftで一時的に消しゴムに切り替え
            self.current_tool_mode = "eraser" if self.shift_pressed else "brush"
        # それ以外のモード（pan_zoom, ww_wl）の場合は既存の設定を保持

        # 作業用一時マスク（リアルタイム反映のため直接roi_masksを操作）
        if (self.current_roi_name in self.roi_masks and
            self.current_axial in self.roi_masks[self.current_roi_name] and
            self.roi_masks[self.current_roi_name][self.current_axial] is not None):
            self.temp_mask = self.roi_masks[self.current_roi_name][self.current_axial].copy()
        else:
            self.temp_mask = np.zeros((h, w), dtype=bool)

        self.drawing_points = [(row, col)]
        self.is_drawing = True
        self.last_draw_pos = (row, col)
        self._fast_draw_at_position(row, col)
        # リアルタイム反映：temp_maskをroi_masksに即座に反映
        self._apply_temp_mask_to_roi()
        self.update_display()

    def continue_drawing(self, scene_pos):
        """描画継続中も実キーボード状態を反映（Shift押し/離しを追従）"""
        if not self.is_drawing or self.temp_mask is None:
            return

        # ★ 実測で毎回更新
        # ただし、消しゴムモードボタンが選択されている場合は常に消しゴム
        mods = QApplication.keyboardModifiers()
        if self.operation_mode == "eraser":
            self.current_tool_mode = "eraser"
        elif self.operation_mode == "brush":
            # ブラシモード時はShiftで一時的に消しゴムに切り替え
            self.current_tool_mode = "eraser" if (mods & Qt.ShiftModifier) else "brush"
        # それ以外のモード（pan_zoom, ww_wl）の場合は既存の設定を保持

        slice_data = self.get_slice_data("axial", self.current_axial)
        if slice_data is None:
            return
        h, w = slice_data.shape
        row = int(round(scene_pos.y()))
        col = int(round(scene_pos.x()))
        if not (0 <= row < h and 0 <= col < w):
            return

        if self.last_draw_pos:
            self._fast_draw_line(self.last_draw_pos, (row, col))
        else:
            self._fast_draw_at_position(row, col)

        self.last_draw_pos = (row, col)
        self.drawing_points.append((row, col))
        # リアルタイム反映：temp_maskをroi_masksに即座に反映
        self._apply_temp_mask_to_roi()
        self.update_display()

    def finish_drawing(self):
        """描画終了：ROIベースで閉ループが出来ていたら内側を確実に塗りつぶす"""
        if not self.is_drawing:
            return

        self.is_drawing = False

        # 何も描けていなければ通常更新
        if self.temp_mask is None:
            self.drawing_points = []
            self.last_draw_pos = None
            self.update_display()
            return

        # ブラシモードのときだけ「閉ループ→内側塗り」を行う
        if self.current_tool_mode == "brush":
            prev_mask = getattr(self, "_prev_mask_snapshot", None)
            slice_data = self.get_slice_data("axial", self.current_axial)
            if slice_data is None:
                prev_mask = None
            if prev_mask is None:
                h, w = self.temp_mask.shape
                prev_mask = np.zeros((h, w), dtype=bool)

            # operation_modeに基づいてサイズを決定（Shift+左ドラッグ時もbrush_size）
            current_size = self.brush_size if self.operation_mode == "brush" else self.eraser_size
            rad = max(1, int(current_size // 2))
            yy, xx = np.ogrid[-rad:rad+1, -rad:rad+1]
            se = (xx*xx + yy*yy) <= rad*rad

            work = binary_dilation(self.temp_mask, structure=se, iterations=1)
            prev_holes = binary_fill_holes(prev_mask) & (~prev_mask)
            filled = binary_fill_holes(work)
            new_holes = (filled & (~work)) & (~prev_holes)
            work = work | new_holes
            work = binary_erosion(work, structure=se, iterations=1)
            self.temp_mask = work

        # 最終的なtemp_maskをroi_masksに反映
        self._apply_temp_mask_to_roi()

        # 描画終了時にUndo履歴に追加
        if hasattr(self, '_drawing_undo_state'):
            self.undo_stack.append(self._drawing_undo_state)
            self._drawing_undo_state = None

        self.drawing_points = []
        self.last_draw_pos = None
        self._prev_mask_snapshot = None
        self.temp_mask = None

        # チュートリアル追跡: 描画モードを記録
        if self.operation_mode == "eraser":
            self._last_draw_mode = 'eraser'
        elif self.operation_mode == "brush":
            if self.shift_pressed:
                self._shift_erase_used = True
                self._last_draw_mode = 'eraser'
            else:
                self._last_draw_mode = 'brush'

        # 表示更新
        self.update_display()

        # ★ 自動プレビューONのときだけ再計算
        if getattr(self, "auto_preview_enabled", True):
            self.recompute_preview_for_current_roi()

    def undo_last_edit(self):
        """最後の編集をアンドゥ（最大40段階）。インターポレート確定の一括変更は1ステップ扱い。"""
        if not hasattr(self, "undo_stack") or len(self.undo_stack) == 0:
            return
        if not hasattr(self, "redo_stack"):
            self.redo_stack = deque(maxlen=40)

        self._undo_used = True
        entry = self.undo_stack.pop()

        # --- グループ（インターポレート確定など）のUndo ---
        if isinstance(entry, dict) and entry.get("group", False):
            changes = entry.get("changes", [])
            redo_changes = []
            for (roi_name, z_slice, prev_mask) in changes:
                # 現在状態を Redo 用に保存
                curr_mask = None
                if roi_name in self.roi_masks and z_slice in self.roi_masks[roi_name]:
                    curr_mask = self.roi_masks[roi_name][z_slice]
                    curr_mask = curr_mask.copy() if curr_mask is not None else None
                redo_changes.append((roi_name, z_slice, curr_mask))

                # 以前の状態へ戻す
                if roi_name not in self.roi_masks:
                    self.roi_masks[roi_name] = {}
                if prev_mask is None:
                    if z_slice in self.roi_masks[roi_name]:
                        del self.roi_masks[roi_name][z_slice]
                else:
                    self.roi_masks[roi_name][z_slice] = prev_mask.copy()

            # グループとしてRedoに積む
            self.redo_stack.append({"group": True, "changes": redo_changes})
            self.update_display()
            self.recompute_preview_for_current_roi()
            return

        # --- 通常（1スライス）のUndo ---
        roi_name, z_slice, prev_mask = entry

        # 現在状態を Redo 用に保存
        curr_mask = None
        if roi_name in self.roi_masks and z_slice in self.roi_masks[roi_name]:
            curr_mask = self.roi_masks[roi_name][z_slice]
            curr_mask = curr_mask.copy() if curr_mask is not None else None
        self.redo_stack.append((roi_name, z_slice, curr_mask))

        # 以前の状態へ戻す
        if roi_name not in self.roi_masks:
            self.roi_masks[roi_name] = {}
        if prev_mask is None:
            if z_slice in self.roi_masks[roi_name]:
                del self.roi_masks[roi_name][z_slice]
        else:
            self.roi_masks[roi_name][z_slice] = prev_mask.copy()

        self.update_display()
        self.recompute_preview_for_current_roi()

    def redo_last_edit(self):
        """やり直し（最大40段階）。インターポレート確定の一括変更は1ステップ扱い。"""
        if not hasattr(self, "redo_stack") or len(self.redo_stack) == 0:
            return
        if not hasattr(self, "undo_stack"):
            self.undo_stack = deque(maxlen=40)

        self._redo_used = True
        entry = self.redo_stack.pop()

        # --- グループ（インターポレート確定など）のRedo ---
        if isinstance(entry, dict) and entry.get("group", False):
            changes = entry.get("changes", [])
            undo_changes = []
            for (roi_name, z_slice, next_mask) in changes:
                # 現在状態を Undo 用に保存
                curr_mask = None
                if roi_name in self.roi_masks and z_slice in self.roi_masks[roi_name]:
                    curr_mask = self.roi_masks[roi_name][z_slice]
                    curr_mask = curr_mask.copy() if curr_mask is not None else None
                undo_changes.append((roi_name, z_slice, curr_mask))

                # 次の状態へ進める
                if roi_name not in self.roi_masks:
                    self.roi_masks[roi_name] = {}
                if next_mask is None:
                    if z_slice in self.roi_masks[roi_name]:
                        del self.roi_masks[roi_name][z_slice]
                else:
                    self.roi_masks[roi_name][z_slice] = next_mask.copy()

            # グループとしてUndoに積む
            self.undo_stack.append({"group": True, "changes": undo_changes})
            self.update_display()
            self.recompute_preview_for_current_roi()
            return

        # --- 通常（1スライス）のRedo ---
        roi_name, z_slice, next_mask = entry

        # 現在状態を Undo 用に保存
        curr_mask = None
        if roi_name in self.roi_masks and z_slice in self.roi_masks[roi_name]:
            curr_mask = self.roi_masks[roi_name][z_slice]
            curr_mask = curr_mask.copy() if curr_mask is not None else None
        self.undo_stack.append((roi_name, z_slice, curr_mask))

        # 次の状態へ進める
        if roi_name not in self.roi_masks:
            self.roi_masks[roi_name] = {}
        if next_mask is None:
            if z_slice in self.roi_masks[roi_name]:
                del self.roi_masks[roi_name][z_slice]
        else:
            self.roi_masks[roi_name][z_slice] = next_mask.copy()

        self.update_display()
        self.recompute_preview_for_current_roi()

    def _fast_draw_at_position(self, row: int, col: int):
        if row is None or col is None or self.temp_mask is None:
            return
        h, w = self.temp_mask.shape
        r = int(row)
        c = int(col)
        if not (0 <= r < h and 0 <= c < w):
            return
        # operation_modeに基づいてサイズを決定
        # ブラシモード（Shift押下含む）: brush_size
        # 消しゴムモードボタン選択時: eraser_size
        current_size = self.brush_size if self.operation_mode == "brush" else self.eraser_size
        kernel_coords = self.brush_kernels.get(current_size, np.array([[0, 0]], dtype=np.int32))
        pts = kernel_coords + np.array([r, c], dtype=np.int32)
        valid = (pts[:, 0] >= 0) & (pts[:, 0] < h) & (pts[:, 1] >= 0) & (pts[:, 1] < w)
        pts = pts[valid]
        if pts.size == 0:
            return
        if self.current_tool_mode == "brush":
            self.temp_mask[pts[:, 0], pts[:, 1]] = True
        else:
            self.temp_mask[pts[:, 0], pts[:, 1]] = False

    def _fast_draw_line(self, start_pos: Tuple[int, int], end_pos: Tuple[int, int]):
        if start_pos is None or end_pos is None:
            return
        r1, c1 = start_pos
        r2, c2 = end_pos
        dist = float(np.hypot(r2 - r1, c2 - c1))
        n = max(1, int(dist))
        if n > 1:
            t = np.linspace(0.0, 1.0, n)
            rs = r1 + t * (r2 - r1)
            cs = c1 + t * (c2 - c1)
            for rr, cc in zip(rs, cs):
                self._fast_draw_at_position(int(round(rr)), int(round(cc)))
        else:
            self._fast_draw_at_position(r2, c2)

    def _apply_temp_mask_to_roi(self):
        """temp_maskをroi_masksに即座に反映する（リアルタイム描画用）"""
        if self.temp_mask is None:
            return
        if self.current_roi_name not in self.roi_masks:
            self.roi_masks[self.current_roi_name] = {}
        cleaned = self.temp_mask.astype(bool)
        z = self.current_axial
        if not np.any(cleaned):
            if z in self.roi_masks[self.current_roi_name]:
                del self.roi_masks[self.current_roi_name][z]
        else:
            self.roi_masks[self.current_roi_name][z] = cleaned.copy()

    def _commit_temp_mask(self):
        """互換性のため残す（古い処理で使われている可能性がある）"""
        self._apply_temp_mask_to_roi()
        self.temp_mask = None

    def change_roi_name(self):
            # ゲーム時は改名禁止
            if getattr(self, "game_lock_roi", False):
                # 見た目も既にReadOnlyにしているが、直接Returnでも来得るため二重でガード
                if hasattr(self, "roi_name_edit"):
                    self.roi_name_edit.setText(self.current_roi_name)
                QMessageBox.information(self, "情報", "ゲームモードではROI名の変更はできません。")
                return

            new_name = self.roi_name_edit.text().strip()
            old_name = self.current_roi_name
            if not new_name or new_name == old_name:
                return
            if new_name in self.roi_color_map:
                QMessageBox.warning(self, "警告", f"ROI名 '{new_name}' は既に存在します。")
                self.roi_name_edit.setText(old_name)
                return
            if old_name in self.roi_masks:
                self.roi_masks[new_name] = self.roi_masks.pop(old_name)
            if old_name in self.roi_color_map:
                self.roi_color_map[new_name] = self.roi_color_map.pop(old_name)
            if hasattr(self, "roi_visibility"):
                self.roi_visibility[new_name] = self.roi_visibility.pop(old_name, True)
            self.current_roi_name = new_name
            self.update_roi_list()
            self.update_brush_cursor_style()
            self.update_display()

    def create_new_roi(self):
            # ゲーム時は新規追加禁止
            if getattr(self, "game_lock_roi", False):
                QMessageBox.information(self, "情報", "ゲームモードではROIの追加はできません。")
                return
            roi_count = len(self.roi_color_map) + 1
            new_name = f"ROI_{roi_count}"
            while new_name in self.roi_color_map:
                roi_count += 1
                new_name = f"ROI_{roi_count}"
            self.current_roi_name = new_name
            self.roi_name_edit.setText(new_name)
            color_index = len(self.roi_color_map) % len(self.roi_colors)
            self.roi_color_map[new_name] = self.roi_colors[color_index]
            self.roi_visibility = getattr(self, "roi_visibility", {})
            self.roi_visibility[new_name] = True
            self.update_roi_list()
            self.update_brush_cursor_style()
            self.update_display()
            # 新ROI作成時もプレビューを再計算
            self.schedule_preview_recompute(immediate=True)

    def delete_current_roi(self):
            # ゲーム時は削除禁止
            if getattr(self, "game_lock_roi", False):
                QMessageBox.information(self, "情報", "ゲームモードではROIの削除はできません。")
                return

            if self.current_roi_name in self.roi_masks or self.current_roi_name in self.roi_color_map:
                reply = QMessageBox.question(
                    self, "確認", f"ROI '{self.current_roi_name}' を削除しますか？",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    if self.current_roi_name in self.roi_masks:
                        del self.roi_masks[self.current_roi_name]
                    if self.current_roi_name in self.roi_color_map:
                        del self.roi_color_map[self.current_roi_name]
                    if hasattr(self, "roi_visibility") and self.current_roi_name in self.roi_visibility:
                        del self.roi_visibility[self.current_roi_name]
                    if self.roi_color_map:
                        self.current_roi_name = list(self.roi_color_map.keys())[0]
                        self.roi_name_edit.setText(self.current_roi_name)
                    else:
                        self.create_new_roi()
                    self.update_roi_list()
                    self.update_display()
                    self.preview_masks.clear()
                    self.refresh_preview_overlays()

    def clear_current_slice_roi(self):
        """現在表示中のスライスのROIを消去（Undo対応、インターポレートプレビュー更新）"""
        if self.nifti_data is None:
            QMessageBox.warning(self, "警告", "画像を読み込んでから実行してください。")
            return

        roi_name = self.current_roi_name
        z = self.current_axial

        # 現在のスライスにROIがあるか確認
        if roi_name not in self.roi_masks or z not in self.roi_masks[roi_name]:
            QMessageBox.information(self, "情報", "現在のスライスにはROIがありません。")
            return

        current_mask = self.roi_masks[roi_name].get(z, None)
        if current_mask is None or not np.any(current_mask):
            QMessageBox.information(self, "情報", "現在のスライスにはROIがありません。")
            return

        # Undo/Redo用のスタック初期化
        if not hasattr(self, "undo_stack"):
            self.undo_stack = deque(maxlen=40)
        if not hasattr(self, "redo_stack"):
            self.redo_stack = deque(maxlen=40)

        # Undoスタックに現在の状態を保存
        self.undo_stack.append((roi_name, z, current_mask.copy()))
        self.redo_stack.clear()

        # ROIを削除
        del self.roi_masks[roi_name][z]

        # 描画中の一時データもクリア
        self.temp_mask = None
        self.is_drawing = False
        self.drawing_points = []

        # 表示更新
        self.update_display()

        # インターポレートプレビューを再計算（上下のスライスから補間）
        self.schedule_preview_recompute(immediate=True)

        QMessageBox.information(self, "完了", f"スライス {z + 1} のROIを消去しました。")

    def select_roi_from_list(self, item):
        roi_name = item.data(Qt.UserRole) or item.text()
        self.current_roi_name = roi_name
        self._roi_changed = True
        self.roi_name_edit.setText(roi_name)
        self.update_brush_cursor_style()
        self.update_display()
        # ROI変更時にプレビューを再計算
        self.schedule_preview_recompute(immediate=True)

    def update_roi_list(self):
        """ROIリスト更新（行ウィジェットで表示。アイテムtextは空にして二重表示を回避）"""
        from PySide6.QtWidgets import QListWidgetItem, QWidget, QHBoxLayout, QLabel, QPushButton
        from PySide6.QtCore import QSize

        if not hasattr(self, "roi_visibility"):
            self.roi_visibility = {}

        self.roi_listbox.blockSignals(True)
        self.roi_listbox.clear()

        for roi_name in sorted(self.roi_color_map.keys()):
            self.roi_visibility.setdefault(roi_name, True)
            color = self.roi_color_map.get(roi_name, "red")
            visible = self.roi_visibility.get(roi_name, True)

            item = QListWidgetItem()             # ← text を入れない
            item.setText("")                      # ← 念のため明示的に空
            item.setData(Qt.UserRole, roi_name)   # 選択・保存のための実名は UserRole に格納
            item.setSizeHint(QSize(260, 26))
            self.roi_listbox.addItem(item)

            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(6, 0, 6, 0)
            lay.setSpacing(8)

            # 色■ボタン
            color_btn = QPushButton()
            color_btn.setFixedSize(18, 18)
            color_btn.setToolTip("色を変更")
            color_btn.setStyleSheet(
                f"QPushButton{{background-color:{color}; border:1px solid #666;}}"
                "QPushButton:pressed{border:1px solid #333;}"
            )
            color_btn.clicked.connect(lambda _=False, r=roi_name: self.choose_roi_color(r))
            lay.addWidget(color_btn, 0)

            # ROI名ラベル（表示はここだけ）
            lbl = QLabel(roi_name)
            lbl.setToolTip(roi_name)
            lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            lay.addWidget(lbl, 1)

            # 表示切替（●=表示 / ○=非表示）
            vis_btn = QPushButton("●" if visible else "○")
            vis_btn.setFixedWidth(26)
            vis_btn.setToolTip("表示切替（●=表示 / ○=非表示）")
            vis_btn.setStyleSheet("QPushButton{border:none; font-size:14px;}")
            vis_btn.clicked.connect(lambda _=False, r=roi_name: self.toggle_roi_visibility(r))
            lay.addWidget(vis_btn, 0)

            self.roi_listbox.setItemWidget(item, row)

        # 現在ROIを UserRole で選択
        target = self.current_roi_name
        for i in range(self.roi_listbox.count()):
            it = self.roi_listbox.item(i)
            if (it.data(Qt.UserRole) == target):
                self.roi_listbox.setCurrentItem(it)
                break

        self.roi_listbox.blockSignals(False)

    def set_window(self, wl, ww):
        self.window_level = float(wl)
        self.window_width = float(max(1.0, ww))
        self.update_display()
        self.update_ww_wl_label()

    # --- 補間（確定/プレビュー）関係：既存実装を維持 ---
    def interpolate_all_slices(self):
        """全スライス補間（“実体あり”の端点間だけ）。Undo/Redoでは一括変更を1ステップ扱い。"""
        if self.current_roi_name not in self.roi_masks:
            QMessageBox.warning(self, "警告", "インターポレートするROIがありません")
            return

        roi_data = self.roi_masks[self.current_roi_name]
        slice_numbers = sorted([z for z, m in roi_data.items() if m is not None and np.any(m)])
        if len(slice_numbers) < 2:
            QMessageBox.warning(self, "警告", "インターポレートには最低2つのスライスが必要です")
            return

        try:
            if not hasattr(self, "undo_stack"):
                self.undo_stack = deque(maxlen=40)
            if not hasattr(self, "redo_stack"):
                self.redo_stack = deque(maxlen=40)
            self.redo_stack.clear()

            total_count = 0
            grouped_changes = []  # [(roi_name, z, prev_mask)]

            for i in range(len(slice_numbers) - 1):
                start_slice = slice_numbers[i]
                end_slice = slice_numbers[i + 1]
                if end_slice - start_slice > 1:
                    count, changes = self._perform_smart_interpolation(start_slice, end_slice)
                    total_count += count
                    # 変更があった分だけ前状態をグループに集約
                    for (z, prev_mask) in changes:
                        grouped_changes.append((self.current_roi_name, z, None if prev_mask is None else prev_mask.copy()))

            if total_count > 0 and grouped_changes:
                # まとめて1ステップとしてUndoに積む
                self.undo_stack.append({"group": True, "changes": grouped_changes})
                self._interpolate_executed = True
                QMessageBox.information(
                    self, "成功",
                    f"ROI '{self.current_roi_name}' で {total_count} スライスを補間しました"
                )
            else:
                # チュートリアルでは試行も検出
                cfg = getattr(self, "game_config", None)
                if cfg and cfg.tutorial_mode:
                    self._interpolate_executed = True
                QMessageBox.information(self, "情報", "補間するスライスがありませんでした")

            self.update_display()
            self.recompute_preview_for_current_roi()

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"インターポレートに失敗しました:\n{str(e)}")

    def _perform_smart_interpolation(self, start_slice: int, end_slice: int) -> tuple[int, list[tuple[int, Optional[np.ndarray]]]]:
        """
        スマート補間処理（空マスクは保存しない）
        返り値: (interpolated_count, changes)
          changes: [(slice_idx, prev_mask_before)]  ※Undoグループ用に“上書き前の状態”だけ返す
        """
        roi_data = self.roi_masks[self.current_roi_name]

        start_mask = roi_data.get(start_slice, None)
        end_mask   = roi_data.get(end_slice, None)
        if start_mask is None or end_mask is None:
            return 0, []
        if not np.any(start_mask) or not np.any(end_mask):
            return 0, []

        start_mask = start_mask.astype(bool)
        end_mask   = end_mask.astype(bool)

        start_dist = self._compute_signed_distance_transform(start_mask)
        end_dist   = self._compute_signed_distance_transform(end_mask)

        interpolated_count = 0
        changes: list[tuple[int, Optional[np.ndarray]]] = []

        for slice_idx in range(start_slice + 1, end_slice):
            alpha = (slice_idx - start_slice) / (end_slice - start_slice)
            interpolated_dist = (1 - alpha) * start_dist + alpha * end_dist
            interpolated_mask = (interpolated_dist <= 0)

            # 整形
            if np.any(interpolated_mask):
                interpolated_mask = binary_erosion(interpolated_mask, iterations=1)
                interpolated_mask = binary_dilation(interpolated_mask, iterations=1)

            # 既存の状態を保存（Undo用）
            prev_mask = roi_data.get(slice_idx, None)
            prev_mask = prev_mask.copy() if prev_mask is not None else None

            # 空ならキー削除、非空なら上書き
            if np.any(interpolated_mask):
                roi_data[slice_idx] = interpolated_mask.astype(bool)
                interpolated_count += 1
                changes.append((slice_idx, prev_mask))
            else:
                # 空にする（既存があれば削除）
                if slice_idx in roi_data and (roi_data[slice_idx] is not None):
                    changes.append((slice_idx, prev_mask))
                    del roi_data[slice_idx]

        return interpolated_count, changes

    def _compute_signed_distance_transform(self, mask: np.ndarray) -> np.ndarray:
        internal_dist = -distance_transform_edt(mask)
        external_dist = distance_transform_edt(~mask)
        return np.where(mask, internal_dist, external_dist)

    def save_masks(self):
        """マスク保存（NIfTI 3Dラベルマップ + 付随JSON）。表示上の反転は保存前に"元に戻す"。"""
        # ★ゲーム中は手動保存を封印。ただし自動保存だけは通す。GT編集モードでは許可。
        cfg = getattr(self, "game_config", None)
        if getattr(self, "game_lock_roi", False) and not getattr(self, "_allow_game_autosave", False):
            if not (cfg and cfg.gt_edit_mode):
                QMessageBox.information(self, "情報", "ゲームモードでは手動の保存はできません（終了時に自動保存されます）。")
                return

        if self.nifti_data is None:
            QMessageBox.warning(self, "警告", "画像を読み込んでから保存してください。")
            return
        if not self.roi_masks:
            QMessageBox.warning(self, "警告", "保存するマスクがありません。")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "マスクを保存（NIfTI 3Dラベルマップ）", "",
            "NIfTI files (*.nii.gz *.nii)"
        )
        if not file_path:
            return

        try:
            h, w, d = self.nifti_data.shape
            label_vol = np.zeros((h, w, d), dtype=np.uint16)

            # ROIの保存順：UIのリスト順（UserRoleにROI名を格納済みの想定）
            roi_order_ui = []
            for i in range(self.roi_listbox.count()):
                it = self.roi_listbox.item(i)
                name = it.data(Qt.UserRole) or it.text() or ""
                name = name.strip()
                if name:
                    roi_order_ui.append(name)

            # 実体ありのROIのみ（空は除外）
            roi_names = []
            for roi_name in roi_order_ui:
                if roi_name in self.roi_masks and any(
                    (m is not None and np.any(m)) for m in self.roi_masks[roi_name].values()
                ):
                    roi_names.append(roi_name)

            if len(roi_names) == 0:
                QMessageBox.information(self, "情報", "ラベルが含まれていません（全て空）。")
                return

            # ラベル→名前/色 のメタ
            label_meta = []
            for idx, roi_name in enumerate(roi_names, start=1):
                # ボリュームに反映（"現在の向き"のzで塗る）
                for z_slice, mask in self.roi_masks[roi_name].items():
                    if mask is None or not np.any(mask):
                        continue
                    if mask.shape != (h, w):
                        continue
                    label_vol[:, :, int(z_slice)][mask.astype(bool)] = idx

                # JSON用メタ
                color = self.roi_color_map.get(roi_name, 'red')
                label_meta.append({
                    "label": int(idx),
                    "name": str(roi_name),
                    "color": str(color)
                })

            # --- 重要：保存直前に"元の向き"へ戻す（読み込み以降の反転を打ち消す） ---
            if getattr(self, "flip_lr", False):
                label_vol = label_vol[::-1, :, :]
            if getattr(self, "flip_ap", False):
                label_vol = label_vol[:, ::-1, :]
            if getattr(self, "flip_si", False):
                label_vol = label_vol[:, :, ::-1]

            # NIfTI保存（元画像と同じaffineを使う）
            affine = self.nifti_img.affine if self.nifti_img is not None else np.eye(4)
            nii = nib.Nifti1Image(label_vol.astype(np.uint16), affine)
            nii.header['descrip'] = b'Label map with external JSON for names/colors'
            nib.save(nii, file_path)

            # JSON保存（同じベース名 + "_labels.json"）
            lower = file_path.lower()
            if lower.endswith(".nii.gz"):
                base = file_path[:-7]
            else:
                base = os.path.splitext(file_path)[0]
            json_path = base + "_labels.json"

            meta = {
                "version": 1,
                "image_shape": [int(h), int(w), int(d)],
                "labels": label_meta,
                "view_flips": {
                    "left_right": bool(getattr(self, "flip_lr", False)),
                    "anterior_posterior": bool(getattr(self, "flip_ap", False)),
                    "superior_inferior": bool(getattr(self, "flip_si", False)),
                }
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            QMessageBox.information(
                self, "成功",
                f"NIfTIとラベルJSONを保存しました。\n{os.path.basename(file_path)}\n{os.path.basename(json_path)}"
            )

            # ★ 保存成功：直近保存ポイントを更新（未保存フラグの判定に使う）
            if not hasattr(self, "undo_stack"):
                # まだ編集スタックがなければ "0" を保存済み長として扱う
                self._last_save_undo_len = 0
            else:
                self._last_save_undo_len = len(self.undo_stack)

            # ★ 保存成功：パスを記憶（Ctrl+S用）
            self._last_saved_path = file_path

            # GT編集モードなら保存パスを記録（設定ダイアログに返す用）
            cfg = getattr(self, "game_config", None)
            if cfg and cfg.gt_edit_mode:
                self._gt_saved_path = file_path

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"NIfTI保存に失敗しました:\n{str(e)}")

    def load_masks(self):
        """3Dラベルマップ(NIfTI)と付帯JSONを読み込んで ROI を復元（名前ズレ防止版）"""
        # ★ゲーム中は封印
        if getattr(self, "game_lock_roi", False):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "情報", "ゲームモードでは手動のマスク読み込みはできません。")
            return

        import os, json
        import numpy as np
        import nibabel as nib
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from nibabel.orientations import aff2axcodes

        file_path, _ = QFileDialog.getOpenFileName(
            self, "マスクを読み込み（NIfTI 3Dラベルマップ）", "",
            "NIfTI files (*.nii.gz *.nii);All files (*.*)"
        )
        if not file_path:
            return
        try:
            nii = nib.load(file_path)
            # dtypeがfloatでもOK（丸めてintへ）
            label_vol = np.asarray(nii.dataobj)
            if np.issubdtype(label_vol.dtype, np.floating):
                label_vol = np.rint(label_vol).astype(np.int32)
            else:
                label_vol = label_vol.astype(np.int32)

            if label_vol.ndim != 3:
                QMessageBox.critical(self, "エラー", "3Dラベルマップ（X,Y,Z）ではありません。")
                return
            if self.nifti_data is None:
                QMessageBox.warning(self, "警告", "先に対象のNIfTI画像を読み込んでください。")
                return
            if tuple(label_vol.shape) != tuple(self.nifti_data.shape):
                QMessageBox.critical(self, "エラー",
                                     f"画像サイズが一致しません。\nラベル: {label_vol.shape}, 画像: {self.nifti_data.shape}")
                return

            # ★ CT側と同じ基準に合わせる：ax[0]=='R' のとき左右反転して 'L' 基準に統一
            try:
                ax = aff2axcodes(nii.affine)
                if len(ax) > 0 and ax[0] == 'R':
                    label_vol = label_vol[::-1, :, :]
            except Exception:
                # フォールバック：a[0,0] > 0 を “R” とみなして反転
                a = getattr(nii, "affine", None)
                if a is not None and float(a[0, 0]) > 0:
                    label_vol = label_vol[::-1, :, :]

            # 付帯JSON（名前・色）の読み取り（_labels.json を優先）
            lower = file_path.lower()
            base = file_path[:-7] if lower.endswith(".nii.gz") else os.path.splitext(file_path)[0]
            candidates = [base + "_labels.json", base + ".json"]
            meta_map = {}
            for json_path in candidates:
                if os.path.exists(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        for ent in meta.get("labels", []):
                            lab = int(ent.get("label", 0))
                            if lab > 0:
                                meta_map[lab] = {
                                    "name": str(ent.get("name", f"ROI_{lab}")),
                                    "color": str(ent.get("color", "#e6194b")),
                                }
                        break
                    except Exception:
                        meta_map = {}

            # ラベル値ごとに ROI を組み立て
            uniq = np.unique(label_vol)
            labels = [int(v) for v in uniq if int(v) > 0]
            if len(labels) == 0:
                QMessageBox.information(self, "情報", "ラベルが含まれていません（全て0）。")
                return

            self.roi_masks = {}
            self.roi_color_map = {}
            # パレット（fallback用）
            palette = getattr(self, "roi_colors", ["#e6194b"])
            h, w, d = label_vol.shape

            for lab in sorted(labels):
                roi_name = meta_map.get(lab, {}).get("name", f"ROI_{lab}")
                roi_color = meta_map.get(lab, {}).get("color", palette[(lab - 1) % len(palette)])

                self.roi_masks[roi_name] = {}
                self.roi_color_map[roi_name] = roi_color

                # zごとに抽出
                for z in range(d):
                    mask2d = (label_vol[:, :, z] == lab)
                    if np.any(mask2d):
                        self.roi_masks[roi_name][z] = mask2d.astype(bool)

            # --- ここから UI 同期（名前ズレ防止の肝）---
            # 現在ROIをセットし、QLineEditに反映（シグナルは一時停止して不要な rename を防ぐ）
            self.current_roi_name = list(self.roi_masks.keys())[0]
            if hasattr(self, "roi_name_edit"):
                try:
                    self.roi_name_edit.blockSignals(True)
                    self.roi_name_edit.setText(self.current_roi_name)
                finally:
                    self.roi_name_edit.blockSignals(False)

            # 可視フラグを新しい ROI 名で初期化
            self.roi_visibility = {name: True for name in self.roi_masks.keys()}

            # ROI リスト再構築（表示名・色の反映）
            if hasattr(self, "update_roi_list"):
                self.update_roi_list()

            # 表示・プレビュー再描画
            self.preview_masks.clear()
            if hasattr(self, "refresh_preview_overlays"):
                self.refresh_preview_overlays()
            self.update_display()
            if hasattr(self, "update_slice_labels"):
                self.update_slice_labels()

            QMessageBox.information(self, "成功", "ラベルを読み込みました。")

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"ラベル読み込みに失敗しました:\n{str(e)}")

    def load_masks_from_path(self, file_path: str):
        """パス指定でマスクを読み込み（GT編集モード用、ダイアログなし）"""
        import os, json
        import numpy as np
        import nibabel as nib
        from nibabel.orientations import aff2axcodes

        if not file_path or not os.path.exists(file_path):
            return

        nii = nib.load(file_path)
        label_vol = np.asarray(nii.dataobj)
        if np.issubdtype(label_vol.dtype, np.floating):
            label_vol = np.rint(label_vol).astype(np.int32)
        else:
            label_vol = label_vol.astype(np.int32)

        if label_vol.ndim != 3 or self.nifti_data is None:
            return
        if tuple(label_vol.shape) != tuple(self.nifti_data.shape):
            return

        try:
            ax = aff2axcodes(nii.affine)
            if len(ax) > 0 and ax[0] == 'R':
                label_vol = label_vol[::-1, :, :]
        except Exception:
            a = getattr(nii, "affine", None)
            if a is not None and float(a[0, 0]) > 0:
                label_vol = label_vol[::-1, :, :]

        lower = file_path.lower()
        base = file_path[:-7] if lower.endswith(".nii.gz") else os.path.splitext(file_path)[0]
        candidates = [base + "_labels.json", base + ".json"]
        meta_map = {}
        for json_path in candidates:
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    for ent in meta.get("labels", []):
                        lab = int(ent.get("label", 0))
                        if lab > 0:
                            meta_map[lab] = {
                                "name": str(ent.get("name", f"ROI_{lab}")),
                                "color": str(ent.get("color", "#e6194b")),
                            }
                    break
                except Exception:
                    meta_map = {}

        uniq = np.unique(label_vol)
        labels = [int(v) for v in uniq if int(v) > 0]
        if len(labels) == 0:
            return

        palette = getattr(self, "roi_colors", ["#e6194b"])
        h, w, d = label_vol.shape

        for lab in sorted(labels):
            roi_name = meta_map.get(lab, {}).get("name", f"ROI_{lab}")
            roi_color = meta_map.get(lab, {}).get("color", palette[(lab - 1) % len(palette)])

            if roi_name not in self.roi_masks:
                self.roi_masks[roi_name] = {}
            self.roi_color_map[roi_name] = roi_color

            for z in range(d):
                mask2d = (label_vol[:, :, z] == lab)
                if np.any(mask2d):
                    self.roi_masks[roi_name][z] = mask2d.astype(bool)

        if self.roi_masks:
            self.current_roi_name = list(self.roi_masks.keys())[0]
            if hasattr(self, "roi_name_edit"):
                try:
                    self.roi_name_edit.blockSignals(True)
                    self.roi_name_edit.setText(self.current_roi_name)
                finally:
                    self.roi_name_edit.blockSignals(False)

            self.roi_visibility = {name: True for name in self.roi_masks.keys()}
            if hasattr(self, "update_roi_list"):
                self.update_roi_list()
            self.preview_masks.clear()
            if hasattr(self, "refresh_preview_overlays"):
                self.refresh_preview_overlays()
            self.update_display()

    def schedule_preview_recompute(self, immediate: bool = False):
        """補間プレビューの再計算をスケジュール（短いディレイで間引き）。"""
        if not getattr(self, "auto_preview_enabled", True):
            # OFF のときはプレビューを消すだけ
            self.preview_masks.clear()
            self.refresh_preview_overlays()
            return
        if self.nifti_data is None:
            return
        self._preview_dirty = True
        if immediate:
            if self.preview_timer.isActive():
                self.preview_timer.stop()
            self.recompute_preview_for_current_roi()
            self._preview_dirty = False
        else:
            self.preview_timer.start(150)

    def recompute_interpolation_preview(self):
        """互換用エントリ。内部は常にフラット辞書で現在ROIのみ再計算。"""
        if not getattr(self, "auto_preview_enabled", True):
            self.preview_masks.clear()
            self.refresh_preview_overlays()
            return
        if not self._preview_dirty or self.nifti_data is None:
            return
        self.recompute_preview_for_current_roi()
        self._preview_dirty = False

    def get_preview_mask_for_view(self, *args):
        if len(args) == 2:
            view_type, slice_idx = args
        elif len(args) == 3:
            _, view_type, slice_idx = args
        else:
            raise TypeError("get_preview_mask_for_view expects 2 or 3 args")
        if self.nifti_data is None:
            return None
        z = int(slice_idx)
        flat = self.preview_masks
        if view_type == 'axial':
            return flat.get(z, None)
        h, w, d = self.nifti_data.shape
        if view_type == 'sagittal':
            x = z
            if x < 0 or x >= h:
                return None
            sag = np.zeros((w, d), dtype=bool)
            for zz, m in flat.items():
                if m is not None and x < m.shape[0]:
                    sag[:, zz] = m[x, :]
            return sag if np.any(sag) else None
        if view_type == 'coronal':
            y = z
            if y < 0 or y >= w:
                return None
            cor = np.zeros((h, d), dtype=bool)
            for zz, m in flat.items():
                if m is not None and y < m.shape[1]:
                    cor[:, zz] = m[:, y]
            return cor if np.any(cor) else None
        return None

    def refresh_preview_overlays(self):
        """3ビューの点線プレビューだけを更新（OFF時は既存プレビューを消す）"""
        if not getattr(self, "auto_preview_enabled", True):
            # OFF でも各ビューに「いったん消してね」と伝える
            for v in (self.axial_view, self.sagittal_view, self.coronal_view):
                if v and getattr(v, "preview_item", None) is not None:
                    v.update_preview_overlays()
            return
        for v in (self.axial_view, self.sagittal_view, self.coronal_view):
            if v:
                v.update_preview_overlays()

    def recompute_preview_for_current_roi(self):
        """現在のROIについて、確定ROIだけを使ってインターポレート結果をプレビューに再計算"""
        # 自動プレビューOFFなら消すだけ
        if not getattr(self, "auto_preview_enabled", True):
            self.preview_masks.clear()
            self.refresh_preview_overlays()
            return

        self.preview_masks.clear()

        if self.nifti_data is None:
            for v in [self.axial_view, self.sagittal_view, self.coronal_view]:
                v.update_mask_overlays()
            return

        roi_name = self.current_roi_name
        if roi_name not in self.roi_masks:
            for v in [self.axial_view, self.sagittal_view, self.coronal_view]:
                v.update_mask_overlays()
            return

        roi_data = self.roi_masks[roi_name]

        # 実体のあるスライスのみ端点候補にする
        seed_slices = sorted([z for z, m in roi_data.items() if m is not None and np.any(m)])
        if len(seed_slices) < 2:
            for v in [self.axial_view, self.sagittal_view, self.coronal_view]:
                v.update_mask_overlays()
            return

        for i in range(len(seed_slices) - 1):
            s0 = seed_slices[i]
            s1 = seed_slices[i + 1]
            if s1 - s0 <= 1:
                continue

            start_mask = roi_data[s0].astype(bool)
            end_mask   = roi_data[s1].astype(bool)

            start_dist = self._compute_signed_distance_transform(start_mask)
            end_dist   = self._compute_signed_distance_transform(end_mask)

            for z in range(s0 + 1, s1):
                alpha = (z - s0) / (s1 - s0)
                interp_dist = (1 - alpha) * start_dist + alpha * end_dist
                interp_mask = (interp_dist <= 0)

                if np.any(interp_mask):
                    # 軽整形
                    interp_mask = binary_erosion(interp_mask, iterations=1)
                    interp_mask = binary_dilation(interp_mask, iterations=1)

                    # 既に確定があればプレビュー出さない
                    if z not in roi_data or not np.any(roi_data.get(z, False)):
                        self.preview_masks[z] = interp_mask.astype(bool)

        # 表示更新（プレビューは overlay 内で下層に描く）
        for v in [self.axial_view, self.sagittal_view, self.coronal_view]:
            v.update_mask_overlays()

    def confirm_preview_to_roi(self):
        """プレビューの内容を"現在のROI"にコピーして確定。Undo/Redoでは一括変更を1ステップ扱い。"""
        if not self.preview_masks:
            QMessageBox.information(self, "情報", "確定するプレビューがありません。")
            return

        roi_name = self.current_roi_name
        if roi_name not in self.roi_masks:
            self.roi_masks[roi_name] = {}

        if not hasattr(self, "undo_stack"):
            self.undo_stack = deque(maxlen=40)
        if not hasattr(self, "redo_stack"):
            self.redo_stack = deque(maxlen=40)
        self.redo_stack.clear()

        changes = []  # [(roi_name, z, prev_mask)]
        applied = 0

        for z, pmask in sorted(self.preview_masks.items()):
            if pmask is None or not np.any(pmask):
                continue

            # 既に確定があれば上書きしない（仕様踏襲）
            existing = self.roi_masks[roi_name].get(z, None)
            if existing is not None and np.any(existing):
                continue

            prev = None if existing is None else existing.copy()
            changes.append((roi_name, z, prev))

            self.roi_masks[roi_name][z] = pmask.copy()
            applied += 1

        # 変更があった時だけグループでUndoに積む
        if applied > 0 and changes:
            self.undo_stack.append({"group": True, "changes": changes})

        # プレビューはクリアして表示更新
        self.preview_masks.clear()
        self.update_display()

        if applied > 0:
            self._interpolate_executed = True
            QMessageBox.information(self, "成功", f"プレビューから {applied} スライスを確定しました。")
        else:
            QMessageBox.information(self, "情報", "上書きすべきスライスがありませんでした（既に確定済みか空）。")

    def interpolate_all_rois_silently(self):
        """全ROIを自動的にインターポレート（メッセージなし、終了時用）"""
        if self.nifti_data is None:
            return

        total_applied = 0
        original_roi = self.current_roi_name

        # 全ROIを順番に処理
        for roi_name in self.roi_color_map.keys():
            self.current_roi_name = roi_name

            # このROI用のプレビューを再計算
            self.preview_masks.clear()
            self.recompute_preview_for_current_roi()

            # プレビューがあれば確定
            if self.preview_masks:
                if roi_name not in self.roi_masks:
                    self.roi_masks[roi_name] = {}

                for z, pmask in self.preview_masks.items():
                    if pmask is None or not np.any(pmask):
                        continue

                    # 既に確定があれば上書きしない
                    existing = self.roi_masks[roi_name].get(z, None)
                    if existing is not None and np.any(existing):
                        continue

                    self.roi_masks[roi_name][z] = pmask.copy()
                    total_applied += 1

        # 元のROIに戻す
        self.current_roi_name = original_roi
        self.preview_masks.clear()

        return total_applied

    def update_outline_thickness(self, value: int):
        self.roi_outline_thickness = int(value)
        if hasattr(self, "outline_label"):
            self.outline_label.setText(f"{self.roi_outline_thickness} px")
        self.update_display()

    def update_preview_spacing(self, value: int):
        self.preview_dot_spacing = int(value)
        if hasattr(self, "dot_spacing_label"):
            self.dot_spacing_label.setText(f"{self.preview_dot_spacing} px")
        self.refresh_preview_overlays()

    def choose_roi_color(self, roi_name: str):
        from PySide6.QtWidgets import QColorDialog
        from PySide6.QtGui import QColor
        current = self.roi_color_map.get(roi_name, "red")
        qc = QColor(current)
        if not qc.isValid():
            qc = QColor("red")
        color = QColorDialog.getColor(qc, self, f"ROI '{roi_name}' の色を選択")
        if color.isValid():
            self.roi_color_map[roi_name] = color.name()
            if roi_name == self.current_roi_name:
                self.update_brush_cursor_style()
            self.update_roi_list()
            self.update_display()

    def toggle_roi_visibility(self, roi_name: str):
        self.roi_visibility = getattr(self, "roi_visibility", {})
        self.roi_visibility[roi_name] = not self.roi_visibility.get(roi_name, True)
        self.update_roi_list()
        self.update_display()
        self.refresh_preview_overlays()
    def finish_roi_name_editing(self):
        """ROI名入力欄で Enter を押したとき：編集を終了するだけ（確定処理は editingFinished -> change_roi_name）"""
        if hasattr(self, "roi_name_edit"):
            self.roi_name_edit.clearFocus()  # これで editingFinished が発火し change_roi_name が呼ばれる
    def confirm_preview_shortcut(self):
        """Enter/Return のラッパ：ROI名入力中はプレビュー確定を抑止し、まず編集を終了"""
        if hasattr(self, "roi_name_edit") and self.roi_name_edit.hasFocus():
            self.roi_name_edit.clearFocus()   # 名前編集を確定させるだけ
            return
        self.confirm_preview_to_roi()
    def confirm_preview_current_slice_shortcut(self):
        """Ctrl+Enter/Return のラッパ：ROI名入力中は抑止して編集終了のみ"""
        if hasattr(self, "roi_name_edit") and self.roi_name_edit.hasFocus():
            self.roi_name_edit.clearFocus()
            return
        self.confirm_preview_current_slice()
    def confirm_preview_current_slice(self):
        """
        現在表示中（Axial）の1スライスだけ、プレビューを確定する。
        既存の確定マスクがあっても **上書き** する（Undo に積む）。
        """
        if self.nifti_data is None:
            return
        if not getattr(self, "preview_masks", None):
            QMessageBox.information(self, "情報", "確定するプレビューがありません。")
            return

        z = int(self.current_axial)
        pmask = self.preview_masks.get(z, None)
        if pmask is None or not np.any(pmask):
            QMessageBox.information(self, "情報", "このスライスにプレビューはありません。")
            return

        roi_name = self.current_roi_name
        if roi_name not in self.roi_masks:
            self.roi_masks[roi_name] = {}

        # Undo / Redo 準備
        if not hasattr(self, "undo_stack"):
            self.undo_stack = deque(maxlen=40)
        if not hasattr(self, "redo_stack"):
            self.redo_stack = deque(maxlen=40)
        self.redo_stack.clear()

        prev = self.roi_masks[roi_name].get(z, None)
        prev = prev.copy() if prev is not None else None
        self.undo_stack.append((roi_name, z, prev))

        # 上書きで確定
        self.roi_masks[roi_name][z] = pmask.copy()

        # このスライスのプレビューは消す
        if z in self.preview_masks:
            del self.preview_masks[z]

        self.update_display()
        QMessageBox.information(self, "成功", f"スライス {z+1} を確定しました。")
    def on_toggle_auto_preview(self, state: int):
        """自動プレビュー表示のON/OFF"""
        self.auto_preview_enabled = (state != 0)
        if not self.auto_preview_enabled:
            # 既存プレビューを消す
            self.preview_masks.clear()
            self.refresh_preview_overlays()
        else:
            # すぐ再計算
            self.schedule_preview_recompute(immediate=True)
    def show_help_dialog(self):
        """Hキーと同じヘルプダイアログを表示"""
        QMessageBox.information(
            self, "ヘルプ",
            "【基本操作】\n"
            "・ドラッグ: ブラシ描画（Axialのみ）\n"
            "・Shift+ドラッグ: 消しゴム（Axialのみ）\n"
            "・スクロール: スライス移動（Ctrl+スクロールでズーム）\n"
            "・中ボタンドラッグ: スライス移動（全ビュー）\n"
            "・Ctrl+ドラッグ: パン（全ビュー）\n"
            "・右ドラッグ: WL/WW調整（Axialのみ）\n"
            "・[ / ] : 表示回転（-90° / +90°）\n"
            "・Enter/Return: プレビュー確定（ROI名入力中は確定しません）\n"
            "・Ctrl+Enter: 今スライスのみプレビュー確定\n"
            "・H: このヘルプ\n\n"
            "【ROIリスト】\n"
            "・左の■をクリックで色変更\n"
            "・右の●/○で表示ON/OFF切替（●=表示 / ○=非表示）\n"
            "・名称変更は上の『現在のROI』欄に入力→Enter かフォーカスアウト\n"
        )
    def flip_left_right(self):
        """左右（X軸）反転：画像・ROI・プレビュー・スライス位置を同期反転。保存時に元に戻せるようフラグもトグル。"""
        if self.nifti_data is None:
            return

        # 画像X反転
        self.nifti_data = self.nifti_data[::-1, :, :]

        # ROI（各zスライス2Dマスクを左右反転）
        for roi_name, zdict in self.roi_masks.items():
            for z in list(zdict.keys()):
                m = zdict[z]
                if m is not None:
                    zdict[z] = m[::-1, :]

        # プレビュー（z→2Dマスクを左右反転）
        for z in list(self.preview_masks.keys()):
            m = self.preview_masks[z]
            if m is not None:
                self.preview_masks[z] = m[::-1, :]

        # スライス位置（Sagittal=x）を反転
        self.current_sagittal = self.max_sagittal - self.current_sagittal

        # フラグをトグル（奇数回→True, 偶数回→False）
        self.flip_lr = not getattr(self, "flip_lr", False)

        self.update_display()
        self.update_slice_labels()
    def flip_anterior_posterior(self):
        """前後（Y軸）反転：画像・ROI・プレビュー・スライス位置を同期反転。保存時に元に戻せるようフラグもトグル。"""
        if self.nifti_data is None:
            return

        # 画像Y反転
        self.nifti_data = self.nifti_data[:, ::-1, :]

        # ROI（各zスライス2Dマスクを前後反転）
        for roi_name, zdict in self.roi_masks.items():
            for z in list(zdict.keys()):
                m = zdict[z]
                if m is not None:
                    zdict[z] = m[:, ::-1]

        # プレビュー（z→2Dマスクを前後反転）
        for z in list(self.preview_masks.keys()):
            m = self.preview_masks[z]
            if m is not None:
                self.preview_masks[z] = m[:, ::-1]

        # スライス位置（Coronal=y）を反転
        self.current_coronal = self.max_coronal - self.current_coronal

        # フラグトグル
        self.flip_ap = not getattr(self, "flip_ap", False)

        self.update_display()
        self.update_slice_labels()
    def flip_superior_inferior(self):
        """頭尾（Z軸）反転：画像・ROI・プレビュー・スライス位置を同期反転。保存時に元に戻せるようフラグもトグル。"""
        if self.nifti_data is None:
            return

        # 画像Z反転
        self.nifti_data = self.nifti_data[:, :, ::-1]

        # ROI（zインデックスを入れ替え）
        new_masks = {}
        for roi_name, zdict in self.roi_masks.items():
            new_masks[roi_name] = {}
            for z, m in zdict.items():
                new_z = self.max_axial - z
                new_masks[roi_name][new_z] = m.copy() if m is not None else None
        self.roi_masks = new_masks

        # プレビュー（zキーを入れ替え）
        new_prev = {}
        for z, m in self.preview_masks.items():
            new_z = self.max_axial - z
            new_prev[new_z] = m.copy() if m is not None else None
        self.preview_masks = new_prev

        # スライス位置（Axial=z）を反転
        self.current_axial = self.max_axial - self.current_axial

        # フラグトグル
        self.flip_si = not getattr(self, "flip_si", False)

        self.update_display()
        self.update_slice_labels()
    
    def show_tutorial(self):
        """インタラクティブチュートリアルを開始"""
        # 既存のチュートリアルマネージャーが動いている場合は停止
        if self._tutorial_manager and self._tutorial_manager.is_active:
            return
        self._tutorial_manager = InteractiveTutorialManager(self)
        self._tutorial_manager.start()
    
    def reset_display_all(self):
        """
        表示の総リセット：
          - 反転ボタンが使えるモードでは反転も戻す
          - 回転角を初期値（-90°）に戻す
          - ズーム・パンをフィットに戻す
        """
        # 反転ボタンが非表示（練習/プレイ）なら反転はリセットしない
        flip_visible = getattr(self, "btn_flip_lr", None) and self.btn_flip_lr.isVisible()
        if flip_visible and getattr(self, "nifti_data", None) is not None:
            if getattr(self, "flip_lr", False):
                self.flip_left_right()
            if getattr(self, "flip_ap", False):
                self.flip_anterior_posterior()
            if getattr(self, "flip_si", False):
                self.flip_superior_inferior()

        # 回転・ズーム・パンを初期化
        for view in [self.axial_view, self.sagittal_view, self.coronal_view]:
            if view is None:
                continue
            view.rotation_deg = -90
            view._fit_mode = True
            view.fit_to_view()

        # ラベル等を更新
        self.update_slice_labels()
        self.update_zoom_label()
        self._view_reset = True

    def apply_game_config(self, cfg: 'GameConfig'):
        """ゲーム設定適用（ROI固定・改名/追加/削除封印、ショートカット遮断）"""
        import os

        self.game_config = cfg
        # チュートリアルモードでは制限を緩くする
        self.game_lock_roi = bool(cfg.enabled and not cfg.tutorial_mode)

        # ROI固定（指定があれば差し替え）※チュートリアルモードでは固定しない
        if cfg.enabled and cfg.roi_names and not cfg.tutorial_mode:
            from app.common.styles import roi_color

            # コンポーネント初期化
            self.roi_masks = {}
            self.roi_color_map = {}
            self.roi_visibility = {}

            for i, disp_name in enumerate(cfg.roi_names):
                color = roi_color(i)
                self.roi_masks[disp_name] = {}
                self.roi_color_map[disp_name] = color
                self.roi_visibility[disp_name] = True

            # 現在ROI・UI更新
            self.current_roi_name = cfg.roi_names[0]
            if hasattr(self, "roi_name_edit"):
                self.roi_name_edit.setText(self.current_roi_name)
                self.roi_name_edit.setReadOnly(True)
            if hasattr(self, "roi_listbox"):
                self.roi_listbox.setEnabled(True)
            self.update_roi_list()
            self.update_brush_cursor_style()
            self.update_display()
        else:
            if hasattr(self, "roi_name_edit"):
                self.roi_name_edit.setReadOnly(False)

        # ショートカット封印（チュートリアルモードでは制限なし）
        self._set_game_shortcut_blocking(bool(cfg.enabled and not cfg.tutorial_mode and not cfg.gt_edit_mode))

        # GT編集モード対応
        if cfg.gt_edit_mode:
            self.game_lock_roi = False
            if hasattr(self, "roi_name_edit"):
                self.roi_name_edit.setReadOnly(False)
            self._gt_saved_path = None
            self.setWindowTitle("【正解データ編集】 3断面表示 NIfTI Contouring Tool")

        # モード別UI表示制御
        self._apply_mode_visibility()

    def _apply_gt_view_flips(self, cfg):
        """GTラベルのJSONに保存された反転状態をCT表示に適用する。
        CT読込時の自動LR補正で flip_lr=True になる場合があるため、
        保存時の状態と現在の状態を比較して一致させる。
        """
        if not cfg or not cfg.gt_label_path:
            return
        gt_path = cfg.gt_label_path
        lower = gt_path.lower()
        base = gt_path[:-7] if lower.endswith(".nii.gz") else os.path.splitext(gt_path)[0]
        json_path = base + "_labels.json"
        if not os.path.exists(json_path):
            import glob
            gt_dir = os.path.dirname(gt_path)
            candidates = glob.glob(os.path.join(gt_dir, "*_labels.json"))
            if candidates:
                json_path = candidates[0]
            else:
                return
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            flips = meta.get("view_flips", {})
            # 保存時の状態と現在の状態が異なる場合にトグルして一致させる
            if flips.get("left_right", False) != getattr(self, "flip_lr", False):
                self.flip_left_right()
            if flips.get("anterior_posterior", False) != getattr(self, "flip_ap", False):
                self.flip_anterior_posterior()
            if flips.get("superior_inferior", False) != getattr(self, "flip_si", False):
                self.flip_superior_inferior()
        except Exception:
            pass

    def _apply_mode_visibility(self):
        """モードに応じてボタン/グループの表示・非表示を制御する。"""
        cfg = getattr(self, "game_config", None)
        is_tutorial = bool(cfg and cfg.tutorial_mode)
        is_play = bool(cfg and cfg.enabled and not cfg.tutorial_mode and not cfg.gt_edit_mode)
        is_edit = bool(cfg and cfg.gt_edit_mode)

        # NIfTI開くボタン
        if hasattr(self, "load_btn"):
            self.load_btn.setVisible(not is_tutorial and not is_play)
            if is_edit:
                self.load_btn.setText("CT NIfTI を開く")

        # チュートリアルボタン
        if hasattr(self, "tutorial_btn"):
            self.tutorial_btn.setVisible(is_tutorial)

        # ファイルグループ（保存/読込）
        if hasattr(self, "file_group"):
            self.file_group.setVisible(not is_tutorial and not is_play)
            if is_edit:
                self.file_group.setTitle("マスク保存/読込")

        # 中断ボタン（Playモードのみ表示）
        if hasattr(self, "abort_game_btn"):
            self.abort_game_btn.setVisible(is_play)

        # 表示操作：練習・プレイでは「表示リセット」のみ表示
        hide_display_extras = is_tutorial or is_play
        for attr in ("btn_flip_lr", "btn_flip_ap", "btn_flip_si", "chk_preview"):
            w = getattr(self, attr, None)
            if w:
                w.setVisible(not hide_display_extras)

    def start_game_if_needed(self):
        """ゲームモードならCT自動読み込み→タイマー開始＋Axial上にカウンター"""
        cfg = getattr(self, "game_config", None)
        if not cfg or not cfg.enabled:
            if hasattr(self, "_axial_timer_label"):
                self._axial_timer_label.hide()
            return

        # CT自動読込
        if cfg.ct_path:
            ok = self.load_nifti_from_path(cfg.ct_path)
            if not ok:
                QMessageBox.critical(self, "エラー", f"CTファイルを開けませんでした:\n{cfg.ct_path}")
                return

        # GTラベルのJSONから保存時の反転状態を読み取って適用
        self._apply_gt_view_flips(cfg)

        # GT編集モード: 既存GTラベルがあればロードして編集開始
        if cfg.gt_edit_mode:
            if cfg.gt_label_path and os.path.isfile(cfg.gt_label_path):
                try:
                    self.load_masks_from_path(cfg.gt_label_path)
                except Exception as e:
                    print(f"GTラベル読み込みエラー: {e}")
            # タイマーなし
            if hasattr(self, "_axial_timer_label"):
                self._axial_timer_label.hide()
            return

        # タイマーUI準備
        self._ensure_axial_timer_label()
        self.game_time_remaining = int(max(0, cfg.time_limit_sec))
        self._game_started_at = time.time()

        base = "3断面表示 NIfTI Contouring Tool - 新レイアウト＋WW/WLプリセット"
        if self.game_time_remaining > 0:
            self._game_timer = QTimer(self)
            self._game_timer.timeout.connect(self._game_tick)
            self._game_timer.start(1000)
            self._update_title_with_timer()
        else:
            self.setWindowTitle(base + "  [GAME]")
            if hasattr(self, "_axial_timer_label"):
                self._axial_timer_label.hide()
    def _update_title_with_timer(self):
        """残り時間をタイトル＋Axialラベルに反映"""
        cfg = getattr(self, "game_config", None)
        base = "3断面表示 NIfTI Contouring Tool - 新レイアウト＋WW/WLプリセット"
        rem = int(getattr(self, "game_time_remaining", 0))
        mm, ss = max(0, rem) // 60, max(0, rem) % 60

        if cfg and cfg.enabled and rem > 0:
            self.setWindowTitle(f"{base}  [GAME {mm:02d}:{ss:02d}]")
            self._ensure_axial_timer_label()
            self._axial_timer_label.setText(f"{mm:02d}:{ss:02d}")
            self._axial_timer_label.show()
        elif cfg and cfg.enabled and (cfg.time_limit_sec or 0) > 0:
            self.setWindowTitle(f"{base}  [GAME 00:00]")
            self._ensure_axial_timer_label()
            self._axial_timer_label.setText("00:00")
            self._axial_timer_label.show()
        else:
            self.setWindowTitle(base + ("  [GAME]" if cfg and cfg.enabled else ""))
            if hasattr(self, "_axial_timer_label"):
                self._axial_timer_label.hide()
    def _game_tick(self):
        """1秒ごとのカウントダウン"""
        self.game_time_remaining -= 1
        if self.game_time_remaining <= 0:
            try:
                if hasattr(self, "_game_timer"):
                    self._game_timer.stop()
                self._update_title_with_timer()  # 00:00 を表示
                self.end_game_and_export()
            finally:
                self.close()
            return
        self._update_title_with_timer()
    def load_nifti_from_path(self, file_path: str) -> bool:
        """ゲーム等でダイアログ無しにNIfTI読み込み。voxel sizeも正しく設定"""
        import os
        if not file_path or not os.path.exists(file_path):
            return False
        try:
            import numpy as np
            import nibabel as nib
            from nibabel.orientations import aff2axcodes

            self.nifti_img = nib.load(file_path)
            data = np.asarray(self.nifti_img.dataobj)
            if data.ndim == 4:
                data = data[..., 0]  # 4Dなら先頭ボリューム
            self.nifti_data = data

            # 反転フラグ初期化
            self.flip_lr = False
            self.flip_ap = False
            self.flip_si = False

            # ★ affineでLR判定して必要ならX反転（'R' のとき反転して 'L' に統一）
            try:
                ax = aff2axcodes(self.nifti_img.affine)
                needs_lr_flip = (len(ax) > 0 and ax[0] == 'R')
            except Exception:
                a = getattr(self.nifti_img, "affine", None)
                needs_lr_flip = bool(a is not None and float(a[0, 0]) > 0)  # >0 を “R”
            if needs_lr_flip:
                self.nifti_data = self.nifti_data[::-1, :, :]
                self.flip_lr = True

            # voxel size（affine優先→header.get_zooms フォールバック）
            try:
                from nibabel.affines import voxel_sizes as _voxel_sizes
                vs = None
                if getattr(self.nifti_img, "affine", None) is not None:
                    vs = _voxel_sizes(self.nifti_img.affine)
                if vs is None or not np.all(np.isfinite(vs[:3])):
                    zooms = self.nifti_img.header.get_zooms()
                    vs = (zooms[0], zooms[1], zooms[2]) if len(zooms) >= 3 else (1.0, 1.0, 1.0)
                self.vx, self.vy, self.vz = [float(max(1e-6, v)) for v in vs[:3]]
            except Exception:
                self.vx = self.vy = self.vz = 1.0

            # スライスとスライダなど（略：元の処理をそのまま）
            h, w, d = self.nifti_data.shape
            self.max_axial = d - 1
            self.current_axial = self.max_axial // 2
            self.axial_slider.setRange(0, self.max_axial)
            self.axial_slider.setValue(self.current_axial)

            self.max_sagittal = h - 1
            self.current_sagittal = self.max_sagittal // 2
            self.sagittal_slider.setRange(0, self.max_sagittal)
            self.sagittal_slider.setValue(self.current_sagittal)

            self.max_coronal = w - 1
            self.current_coronal = self.max_coronal // 2
            self.coronal_slider.setRange(0, self.max_coronal)
            self.coronal_slider.setValue(self.current_coronal)

            # 以降は元の初期化処理を踏襲
            self.window_level = 50
            self.window_width  = 350

            if not hasattr(self, "roi_visibility"):
                self.roi_visibility = {}
            if not hasattr(self, "roi_color_map") or not self.roi_color_map:
                self.roi_color_map = {"ROI_1": self.roi_colors[0] if hasattr(self, "roi_colors") else 'red'}
            self.current_roi_name = list(self.roi_color_map.keys())[0]
            if hasattr(self, "roi_name_edit"):
                self.roi_name_edit.setText(self.current_roi_name)

            self.update_display()
            self.update_slice_labels()
            return True
        except Exception:
            return False
    def end_game_and_export(self):
        """ゲーム終了処理：
        - Practice（操作練習）: 何も保存せずスコアも起動せず、ただちにウィンドウを閉じてランチャーへ復帰
        - Play: これまで通り NIfTI と JSON を保存し、（_auto_score が True なら）スコアアプリを起動
        """
        # NIfTI未読込なら何もしないで閉じる
        if getattr(self, "nifti_data", None) is None:
            try:
                # 念のためタイマー停止
                if hasattr(self, "game_timer"):
                    self.game_timer.stop()
            except Exception:
                pass
            self.close()
            return

        cfg = getattr(self, "game_config", None)

        # ---- Practice（操作練習）判定 ----
        # game起動かつ result_dir 未指定（game.py の practice は --result-dir を付けません）
        is_practice = bool(cfg and cfg.enabled and not cfg.out_dir)
        if is_practice:
            # 何も保存せず・スコアも出さずに即終了
            try:
                if hasattr(self, "game_timer"):
                    self.game_timer.stop()
                # ショートカット封印などを戻す（存在すれば）
                if hasattr(self, "_set_game_shortcut_blocking"):
                    self._set_game_shortcut_blocking(False)
            except Exception:
                pass
            self.close()
            return

        # ---- ここから Play（保存＆スコア）の従来処理 ----

        # エクスポート前に全ROIを自動インターポレート
        try:
            applied = self.interpolate_all_rois_silently()
            if applied and applied > 0:
                print(f"エクスポート前に自動インターポレート: {applied} スライスを補間しました。")
        except Exception as e:
            print(f"エクスポート前の自動インターポレートでエラー: {e}")

        # ラベルボリューム生成（空ROIは除外）
        h, w, d = self.nifti_data.shape
        label_vol = np.zeros((h, w, d), dtype=np.uint16)

        if cfg and cfg.roi_names:
            roi_order = [n for n in cfg.roi_names if n in self.roi_masks or n in self.roi_color_map]
        else:
            roi_order = sorted(self.roi_color_map.keys())

        label_meta = []
        lab = 0
        for roi_name in roi_order:
            have_any = False
            for z_slice, mask in self.roi_masks.get(roi_name, {}).items():
                if mask is None or not np.any(mask):
                    continue
                have_any = True
            if not have_any:
                continue

            lab += 1
            for z_slice, mask in self.roi_masks.get(roi_name, {}).items():
                if mask is None or not np.any(mask):
                    continue
                if mask.shape != (h, w):
                    continue
                label_vol[:, :, int(z_slice)][mask.astype(bool)] = lab

            color = self.roi_color_map.get(roi_name, 'red')
            label_meta.append({"label": int(lab), "name": str(roi_name), "color": str(color)})

        # 反転表示を保存前に元へ戻す
        if getattr(self, "flip_lr", False):
            label_vol = label_vol[::-1, :, :]
        if getattr(self, "flip_ap", False):
            label_vol = label_vol[:, ::-1, :]
        if getattr(self, "flip_si", False):
            label_vol = label_vol[:, :, ::-1]

        # 出力ディレクトリ（Playは cfg.out_dir 指定がある想定。無ければ従来の fallback）
        if cfg and cfg.out_dir:
            out_dir = cfg.out_dir
        else:
            base_dir = os.path.dirname(cfg.ct_path) if (cfg and cfg.ct_path) else os.getcwd()
            out_dir = os.path.join(base_dir, "game_results")
        os.makedirs(out_dir, exist_ok=True)

        # ファイル名
        ts = time.strftime("%Y%m%d_%H%M%S")
        pid  = (cfg.participant or "student")
        team = (cfg.team or "team")
        sess = (cfg.session_id or "session")

        # session_idから部位セット名（ケース名）を抽出
        # フォーマット: YYYY-MM-DD-HHMM-<region_name>-<mode>
        # 例: "2026-02-14-2140-hukubu2-Play"
        case = "unknown"
        if sess and "-" in sess:
            parts = sess.split("-")
            # 4番目のパーツが部位セット名（0:年, 1:月, 2:日, 3:時分, 4:部位セット名）
            if len(parts) >= 5:
                case = parts[4]

        # フォールバック：session_idから抽出できなかった場合はCTファイル名を使用
        if case == "unknown":
            case = os.path.splitext(os.path.basename(cfg.ct_path))[0] if (cfg and cfg.ct_path) else "case"

        base = f"{sess}_{team}_{pid}_{case}_{ts}"

        # NIfTI保存
        affine = self.nifti_img.affine if self.nifti_img is not None else np.eye(4)
        nii_path = os.path.join(out_dir, f"{base}_labels.nii.gz")
        nii = nib.Nifti1Image(label_vol.astype(np.uint16), affine)
        nii.header['descrip'] = b'Label map for GAME'
        nib.save(nii, nii_path)

        # 正解ラベルパス（相対パスに変換）
        gt_label_path = None
        if cfg and hasattr(cfg, 'gt_label_path') and cfg.gt_label_path:
            gt_label_path = make_relative_path(cfg.gt_label_path)

        # 経過時間
        elapsed = 0
        if cfg and cfg.time_limit_sec:
            elapsed = int(cfg.time_limit_sec - max(0, getattr(self, "game_time_remaining", 0)))

        # JSON保存（正解ラベルパス・反転状態含む）
        meta = {
            "version": 1,
            "case": case,
            "session_id": sess,
            "team": team,
            "participant": pid,
            "roi_order": roi_order,
            "labels": label_meta,
            "time_limit_sec": int(cfg.time_limit_sec if cfg else 0),
            "elapsed_sec": int(elapsed),
            "image_shape": [int(h), int(w), int(d)],
            "gt_label_path": gt_label_path,
            "view_flips": {
                "left_right": bool(getattr(self, "flip_lr", False)),
                "anterior_posterior": bool(getattr(self, "flip_ap", False)),
                "superior_inferior": bool(getattr(self, "flip_si", False)),
            }
        }
        json_path = os.path.join(out_dir, f"{base}_labels.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        # JSONパスを保存して main.py からアクセス可能にする
        self._last_export_json = json_path
        if DEBUG: print(f"[DEBUG tf_contouring] _last_export_json を設定しました: {json_path}")

        # 自動スコア起動は game.py 側で制御するため、ここでは無効化
        # （重複起動防止のため）
        if False:  # 旧: getattr(self, "_auto_score", True):
            try:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                scoring_app_path = os.path.join(current_dir, "scoring_app.py")
                if os.path.exists(scoring_app_path):
                    import subprocess
                    subprocess.Popen([sys.executable, scoring_app_path, json_path], cwd=current_dir)
                else:
                    print(f"警告: スコアリングアプリが見つかりません: {scoring_app_path}")
            except Exception as e:
                print(f"スコアリングアプリの起動に失敗しました: {e}")
    def _ensure_axial_timer_label(self):
        """Axialビュー左上にタイムカウンターラベルを用意"""
        from PySide6.QtWidgets import QLabel
        from PySide6.QtGui import QFont
        from PySide6.QtCore import Qt
        if getattr(self, "_axial_timer_label", None) is not None:
            return
        parent = self.axial_view.viewport() if hasattr(self, "axial_view") else self
        lbl = QLabel(parent)
        f = QFont()
        f.setPointSize(22)
        f.setBold(True)
        lbl.setFont(f)
        lbl.setStyleSheet(
            "QLabel {"
            "  background-color: rgba(0,0,0,150);"
            "  color: white;"
            "  border-radius: 6px;"
            "  padding: 4px 10px;"
            "}"
        )
        lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lbl.move(10, 10)
        lbl.hide()
        self._axial_timer_label = lbl
    def _set_game_shortcut_blocking(self, blocked: bool):
        """ゲームモード時にショートカットとボタンを封印／解除する（Ctrl+S追加版）"""
        # イベントフィルタ（アプリ全体）の用意・登録
        if not hasattr(self, "_game_key_filter"):
            self._game_key_filter = _GameKeyBlocker(self)
            QCoreApplication.instance().installEventFilter(self._game_key_filter)
        self._game_key_filter.set_block(blocked)

        # ボタンを取得（setup_control_panel を触らない版）
        lb, sb, lmb = self._get_file_buttons()

        # ボタン活性/非活性
        if lb:  lb.setEnabled(not blocked)
        if sb:  sb.setEnabled(not blocked)
        if lmb: lmb.setEnabled(not blocked)

        # ショートカットそのものを外す/戻す
        if blocked:
            if lb:  lb.setShortcut(QKeySequence())               # Ctrl+O 消し
            if sb:  sb.setShortcut(QKeySequence())               # Shift+S 消し
            if lmb: lmb.setShortcut(QKeySequence())              # Shift+O 消し

            # Ctrl+S用のショートカットも無効化（QShortcutを直接探して無効化）
            for shortcut in self.findChildren(QShortcut):
                if shortcut.key().toString() == "Ctrl+S":
                    shortcut.setEnabled(False)
        else:
            if lb:  lb.setShortcut(QKeySequence("Ctrl+O"))
            if sb:  sb.setShortcut(QKeySequence("Shift+S"))
            if lmb: lmb.setShortcut(QKeySequence("Shift+O"))

            # Ctrl+S用のショートカットも復活
            for shortcut in self.findChildren(QShortcut):
                if shortcut.key().toString() == "Ctrl+S":
                    shortcut.setEnabled(True)
    def _is_forbidden_sequence(self, seq) -> bool:
        """禁止ショートカット判定"""
        from PySide6.QtGui import QKeySequence
        if seq is None:
            return False
        s = seq.toString()
        return s in {QKeySequence("Shift+S").toString(),
                     QKeySequence("Shift+O").toString(),
                     QKeySequence("Ctrl+O").toString()}
    def eventFilter(self, obj, event):
        """ゲーム中は Shift+S / Shift+O / Ctrl+O を完全に無効化"""
        from PySide6.QtCore import QEvent, Qt
        cfg = getattr(self, "game_config", None)
        game_on = bool(cfg and cfg.enabled)

        if game_on:
            et = event.type()
            # QShortcut発火前の段階で握りつぶす
            if et in (QEvent.ShortcutOverride, QEvent.Shortcut):
                try:
                    seq = event.key()  # QKeySequence
                    if self._is_forbidden_sequence(seq):
                        return True
                except Exception:
                    pass
            # KeyPress レベルでも保険をかける
            if et == QEvent.KeyPress:
                try:
                    k = event.key()
                    mods = event.modifiers()
                    if (mods & Qt.ShiftModifier and (k == Qt.Key_S or k == Qt.Key_O)) \
                       or (mods & Qt.ControlModifier and k == Qt.Key_O):
                        return True
                except Exception:
                    pass

        try:
            return super().eventFilter(obj, event)
        except Exception:
            return False
    def _get_file_buttons(self):
        """インスタンス変数から直接返す。"""
        return (getattr(self, "load_btn", None),
                getattr(self, "save_btn", None),
                getattr(self, "load_mask_btn", None))
    def game_autosave_now(self):
        """ゲーム終了時の自動保存ヘルパ"""
        self._allow_game_autosave = True
        try:
            self.save_masks()
        finally:
            self._allow_game_autosave = False

    def _abort_game(self):
        """中断ボタン: スコアを保存せずにゲームを中断する。"""
        reply = QMessageBox.question(
            self,
            "ゲーム中断",
            "ゲームを中断しますか？\nスコアは保存されません。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._game_aborted = True
            # タイマー停止
            if hasattr(self, "_game_timer"):
                try:
                    self._game_timer.stop()
                except Exception:
                    pass
            self.close()

    def closeEvent(self, event):
        """
        ウィンドウ右上の × で閉じるときの確認ダイアログ制御。

        - ゲームモード中: 残り時間があるなら「時間まだですが終了しますか？」と確認。
        - 通常モード: 直近の編集が未保存なら「保存しますか？」(保存/破棄/キャンセル) を確認。
          ただし、上書き保存済みの場合は確認不要。
        """
        # --- 中断フラグが立っている場合はスコア保存をスキップ ---
        if getattr(self, "_game_aborted", False):
            # タイマー停止・シグナル発火のみ行い、end_game_and_export はスキップ
            pass

        else:
            # --- ゲームモードの早期終了確認 ---
            cfg = getattr(self, "game_config", None)
            is_game = bool(cfg and getattr(cfg, "enabled", False))

            if is_game:
                # 残り時間を取得（正しい変数名を使用）
                time_left = int(getattr(self, "game_time_remaining", 0))
                if time_left > 0:
                    mm = time_left // 60
                    ss = time_left % 60
                    reply = QMessageBox.question(
                        self,
                        "確認",
                        f"時間はまだ {mm:02d}:{ss:02d} 残っています。終了しますか？",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if reply == QMessageBox.No:
                        event.ignore()
                        return
                    # Yes の場合：ゲーム終了処理を呼んでから終了を許可
                    try:
                        self.end_game_and_export()
                    except Exception as e:
                        print(f"ゲーム終了処理でエラー: {e}")

            # --- 通常モード：未保存チェック ---
            else:
                # 直近保存時点の undo_stack 長と、現在の undo_stack 長を比較して
                # "保存後に編集が増えているか" を判定（編集がなければ undo_stack 自体が無い場合もある）
                last_saved_len = int(getattr(self, "_last_save_undo_len", 0))
                current_len = int(len(self.undo_stack)) if hasattr(self, "undo_stack") else 0
                has_unsaved = current_len > last_saved_len

                # 上書き保存用パスがあって編集後の変更がない場合は、確認を出さない
                has_quick_save_path = bool(getattr(self, "_last_saved_path", None))

                if has_unsaved and not (has_quick_save_path and current_len == last_saved_len):
                    box = QMessageBox(self)
                    box.setIcon(QMessageBox.Warning)
                    box.setWindowTitle("保存の確認")

                    # 上書き保存パスがある場合とない場合でメッセージを変える
                    if has_quick_save_path:
                        filename = os.path.basename(self._last_saved_path)
                        box.setText(f"ROI の変更内容が保存されていません。\n保存先: {filename}\n保存しますか？")
                        # 上書き保存オプションを追加
                        save_btn = box.addButton("上書き保存", QMessageBox.AcceptRole)
                        save_as_btn = box.addButton("名前を付けて保存", QMessageBox.AcceptRole)
                        discard_btn = box.addButton("破棄", QMessageBox.DestructiveRole)
                        cancel_btn = box.addButton("キャンセル", QMessageBox.RejectRole)
                        box.setDefaultButton(save_btn)
                        res = box.exec()

                        if box.clickedButton() == save_btn:
                            # 上書き保存
                            try:
                                self.save_masks_quick()
                                # save_masks_quick が成功すれば _last_save_undo_len が更新される
                            except Exception as e:
                                # 上書き保存に失敗した場合は終了をキャンセル
                                QMessageBox.critical(self, "エラー", f"上書き保存に失敗しました:\n{str(e)}")
                                event.ignore()
                                return
                        elif box.clickedButton() == save_as_btn:
                            # 名前を付けて保存
                            prev_len = int(getattr(self, "_last_save_undo_len", 0))
                            self.save_masks()
                            new_len = int(getattr(self, "_last_save_undo_len", prev_len))
                            if new_len == prev_len:
                                # 保存がキャンセルされた場合
                                event.ignore()
                                return
                        elif box.clickedButton() == cancel_btn:
                            event.ignore()
                            return
                        # discard_btn の場合はそのまま終了
                    else:
                        # 従来通りの保存確認
                        box.setText("ROI の変更内容が保存されていません。保存しますか？")
                        box.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
                        box.setDefaultButton(QMessageBox.Save)
                        res = box.exec()

                        if res == QMessageBox.Save:
                            # 保存ダイアログ内でキャンセルされた場合に備えて、保存前の長さを保持しておく
                            prev_len = int(getattr(self, "_last_save_undo_len", 0))
                            self.save_masks()
                            # save_masks 成功時は _last_save_undo_len が更新される想定。
                            new_len = int(getattr(self, "_last_save_undo_len", prev_len))
                            if new_len == prev_len:
                                # たぶん保存をキャンセルしているので終了もキャンセル
                                event.ignore()
                                return
                        elif res == QMessageBox.Cancel:
                            event.ignore()
                            return
                        # Discard の場合はそのまま終了

        # ゲームタイマーがあれば停止
        if hasattr(self, "_game_timer"):
            try:
                self._game_timer.stop()
            except Exception:
                pass

        # 終了前に全ROIを自動インターポレート
        try:
            applied = self.interpolate_all_rois_silently()
            if applied and applied > 0:
                print(f"終了時に自動インターポレート: {applied} スライスを補間しました。")
        except Exception as e:
            print(f"自動インターポレートでエラー: {e}")

        # ウィンドウを閉じる前にシグナルを発火（main.pyがスコアリングアプリを起動するため）
        try:
            print("[DEBUG tf_contouring] window_closing シグナルを発火します")
            self.window_closing.emit()
        except Exception as e:
            if DEBUG: print(f"[DEBUG tf_contouring] window_closing 発火エラー: {e}")

        # 親クラスに委譲して閉じる
        super().closeEvent(event)
    def save_masks_quick(self):
        """Ctrl+S用の上書き保存機能。前回保存したパスに確認なしで上書き保存する。"""
        # ゲーム中は封印
        if getattr(self, "game_lock_roi", False):
            QMessageBox.information(self, "情報", "ゲームモードでは上書き保存はできません。")
            return

        if self.nifti_data is None:
            QMessageBox.warning(self, "警告", "画像を読み込んでから保存してください。")
            return

        if not self.roi_masks:
            QMessageBox.warning(self, "警告", "保存するマスクがありません。")
            return

        # 前回保存したパスがない場合は通常の保存ダイアログを開く
        if not hasattr(self, '_last_saved_path') or not self._last_saved_path:
            self.save_masks()
            return

        file_path = self._last_saved_path

        try:
            h, w, d = self.nifti_data.shape
            label_vol = np.zeros((h, w, d), dtype=np.uint16)

            # ROIの保存順：UIのリスト順（UserRoleにROI名を格納済みの想定）
            roi_order_ui = []
            for i in range(self.roi_listbox.count()):
                it = self.roi_listbox.item(i)
                name = it.data(Qt.UserRole) or it.text() or ""
                name = name.strip()
                if name:
                    roi_order_ui.append(name)

            # 実体ありのROIのみ（空は除外）
            roi_names = []
            for roi_name in roi_order_ui:
                if roi_name in self.roi_masks and any(
                    (m is not None and np.any(m)) for m in self.roi_masks[roi_name].values()
                ):
                    roi_names.append(roi_name)

            if len(roi_names) == 0:
                QMessageBox.information(self, "情報", "ラベルが含まれていません（全て空）。")
                return

            # ラベル→名前/色 のメタ
            label_meta = []
            for idx, roi_name in enumerate(roi_names, start=1):
                # ボリュームに反映（"現在の向き"のzで塗る）
                for z_slice, mask in self.roi_masks[roi_name].items():
                    if mask is None or not np.any(mask):
                        continue
                    if mask.shape != (h, w):
                        continue
                    label_vol[:, :, int(z_slice)][mask.astype(bool)] = idx

                # JSON用メタ
                color = self.roi_color_map.get(roi_name, 'red')
                label_meta.append({
                    "label": int(idx),
                    "name": str(roi_name),
                    "color": str(color)
                })

            # --- 重要：保存直前に"元の向き"へ戻す（読み込み以降の反転を打ち消す） ---
            if getattr(self, "flip_lr", False):
                label_vol = label_vol[::-1, :, :]
            if getattr(self, "flip_ap", False):
                label_vol = label_vol[:, ::-1, :]
            if getattr(self, "flip_si", False):
                label_vol = label_vol[:, :, ::-1]

            # NIfTI保存（元画像と同じaffineを使う）
            affine = self.nifti_img.affine if self.nifti_img is not None else np.eye(4)
            nii = nib.Nifti1Image(label_vol.astype(np.uint16), affine)
            nii.header['descrip'] = b'Label map with external JSON for names/colors'
            nib.save(nii, file_path)

            # JSON保存（同じベース名 + "_labels.json"）
            lower = file_path.lower()
            if lower.endswith(".nii.gz"):
                base = file_path[:-7]
            else:
                base = os.path.splitext(file_path)[0]
            json_path = base + "_labels.json"

            meta = {
                "version": 1,
                "image_shape": [int(h), int(w), int(d)],
                "labels": label_meta,
                "view_flips": {
                    "left_right": bool(getattr(self, "flip_lr", False)),
                    "anterior_posterior": bool(getattr(self, "flip_ap", False)),
                    "superior_inferior": bool(getattr(self, "flip_si", False)),
                }
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            # 上書き保存成功メッセージ（簡潔に）
            filename = os.path.basename(file_path)
            QMessageBox.information(self, "保存完了", f"上書き保存しました:\n{filename}")

            # ★ 保存成功：直近保存ポイントを更新（未保存フラグの判定に使う）
            if not hasattr(self, "undo_stack"):
                self._last_save_undo_len = 0
            else:
                self._last_save_undo_len = len(self.undo_stack)

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"上書き保存に失敗しました:\n{str(e)}")

        # 解除時は特に何もしなくても、eventFilter側の分岐で通す設計


# ------- 輪郭抽出・点線生成（ユーティリティ） -------
def _binary_erode_once_8n(a: np.ndarray) -> np.ndarray:
    p = a.astype(bool)
    e = p.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            e &= np.roll(np.roll(p, dy, axis=0), dx, axis=1)
    return e

def _border_from_mask(m: np.ndarray, thickness: int = 2) -> np.ndarray:
    m = m.astype(bool)
    inner = m.copy()
    for _ in range(max(1, int(thickness))):
        inner = _binary_erode_once_8n(inner)
    border = m & (~inner)
    return border

def create_outline_qimage(mask: np.ndarray, color_rgba, thickness: int = 2) -> QImage:
    border = _border_from_mask(mask, thickness=max(1, int(thickness)))
    return create_colored_mask_qimage(border.astype(mask.dtype), color_rgba)

def create_dotted_outline_qimage(mask: np.ndarray, color_rgba,
                                 dot_radius: int = 1, spacing: int = 2,
                                 border_thickness: int = 1) -> QImage:
    border = _border_from_mask(mask, thickness=max(1, int(border_thickness)))
    h, w = border.shape
    if not np.any(border):
        return create_colored_mask_qimage(np.zeros_like(border, dtype=np.uint8), [0, 0, 0, 0])
    yy, xx = np.where(border)
    cy, cx = yy.mean(), xx.mean()
    angles = np.arctan2(yy - cy, xx - cx)
    order = np.argsort(angles)
    yy = yy[order]; xx = xx[order]
    dots = np.zeros_like(border, dtype=bool)
    R = max(0, int(dot_radius))
    S = max(1, int(spacing))
    if R == 0:
        last_y, last_x = -9999, -9999
        for y, x in zip(yy, xx):
            if abs(y - last_y) + abs(x - last_x) >= S:
                dots[y, x] = True
                last_y, last_x = y, x
    else:
        ry, rx = np.ogrid[-R:R+1, -R:R+1]
        circle = (ry*ry + rx*rx) <= R*R
        for y, x in zip(yy, xx):
            y0 = max(0, y - S); y1 = min(h, y + S + 1)
            x0 = max(0, x - S); x1 = min(w, x + S + 1)
            if not dots[y0:y1, x0:x1].any():
                ys = slice(max(0, y - R), min(h, y + R + 1))
                xs = slice(max(0, x - R), min(w, x + R + 1))
                sub = dots[ys, xs]
                cy0 = R - (y - ys.start)
                cx0 = R - (x - xs.start)
                circle_crop = circle[cy0:cy0+sub.shape[0], cx0:cx0+sub.shape[1]]
                dots[ys, xs] = sub | circle_crop
    return create_colored_mask_qimage(dots.astype(np.uint8), color_rgba)


# -------------------- main --------------------
def main():
    import argparse
    os.environ.setdefault("QT_OPENGL", "software")
    try:
        from PySide6.QtCore import QCoreApplication, Qt as _Qt
        QCoreApplication.setAttribute(_Qt.AA_UseSoftwareOpenGL, True)
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="NIfTI Contouring Tool / Game Mode")
    parser.add_argument("--game", action="store_true", help="ゲームモードで起動")
    parser.add_argument("--ct", type=str, default=None, help="CT NIfTIパス（ゲーム時に自動読込）")
    parser.add_argument("--rois", type=str, default=None, help="カンマ区切りROI名（例：膀胱,直腸）")
    parser.add_argument("--time-limit", type=int, default=0, help="制限時間（秒）")
    parser.add_argument("--result-dir", type=str, default=None, help="結果出力ディレクトリ")
    parser.add_argument("--participant", type=str, default=None, help="学籍番号等")
    parser.add_argument("--team", type=str, default=None, help="チーム名")
    parser.add_argument("--session", type=str, default=None, help="セッションID")
    parser.add_argument("--gt-label", type=str, default=None, help="正解ラベル NIfTIパス")
    parser.add_argument("--year", type=str, default=None, help="年度")
    parser.add_argument("--group", type=str, default=None, help="班")
    # ★ 追加：ランチャー側でスコアリングを起動する場合のオプトアウト
    parser.add_argument("--no-auto-score", action="store_true", help="ゲーム終了時にスコアリングアプリを自動起動しない")
    parser.add_argument("--tutorial", action="store_true", help="チュートリアルモードで起動")
    args, _ = parser.parse_known_args()

    roi_names = [s.strip() for s in args.rois.split(",")] if args.rois else None
    cfg = GameConfig(
        enabled=bool(args.game),
        ct_path=args.ct,
        roi_names=roi_names,
        time_limit_sec=int(args.time_limit or 0),
        out_dir=args.result_dir,
        participant=args.participant,
        team=args.team,
        session_id=args.session,
        gt_label_path=args.gt_label,
        tutorial_mode=bool(args.tutorial)
    )

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = SimpleNiftiContouringApp()
    # ゲーム設定適用＆起動
    win.apply_game_config(cfg)
    # ★ 追加：自動スコア起動の可否をウィンドウに持たせる（デフォルトは True）
    setattr(win, "_auto_score", not bool(args.no_auto_score))

    win.show()
    win.start_game_if_needed()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        import nibabel as nib
        import numpy as np
        from scipy.ndimage import binary_dilation, binary_erosion, binary_fill_holes, distance_transform_edt
        print("必要なライブラリが確認できました")
        main()
    except ImportError as e:
        print(f"必要なライブラリがインストールされていません: {e}")
        print("以下のコマンドでインストールしてください:")
        print("pip install PySide6 nibabel numpy scipy")