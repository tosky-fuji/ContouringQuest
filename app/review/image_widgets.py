# -*- coding: utf-8 -*-
"""画像表示ウィジェットとマスク生成関数"""

import numpy as np
from typing import Dict, List, Optional

from scipy.ndimage import binary_erosion

from PySide6.QtWidgets import QLabel, QFrame, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QColor, QImage, QTransform


# -------------------- マスク・輪郭ユーティリティ --------------------

def _border_from_mask(m: np.ndarray, thickness: int = 2) -> np.ndarray:
    """マスクから輪郭を抽出"""
    m = m.astype(bool)
    inner = m.copy()
    for _ in range(max(1, int(thickness))):
        inner = binary_erosion(inner)
    border = m & (~inner)
    return border


def create_colored_outline_qimage(mask: np.ndarray, color_rgba, thickness: int = 2) -> QImage:
    """輪郭のみの色付きQImageを作成（実線）"""
    h, w = mask.shape
    border = _border_from_mask(mask, thickness=thickness)
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[border > 0] = color_rgba
    rgba_flat = np.ascontiguousarray(rgba)
    qimg = QImage(rgba_flat.data, w, h, w * 4, QImage.Format_RGBA8888)
    qimg.ndarray = rgba_flat
    return qimg


def create_colored_mask_qimage(mask: np.ndarray, color_rgba) -> QImage:
    """マスクの色付きQImageを作成"""
    h, w = mask.shape
    mask_u8 = mask.astype(np.uint8)
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[mask_u8 > 0] = color_rgba
    rgba_flat = np.ascontiguousarray(rgba)
    qimg = QImage(rgba_flat.data, w, h, w * 4, QImage.Format_RGBA8888)
    qimg.ndarray = rgba_flat
    return qimg


def create_dotted_outline_qimage(mask: np.ndarray, color_rgba,
                                 dot_radius: int = 1, spacing: int = 3,
                                 border_thickness: int = 1) -> QImage:
    """点線の輪郭QImageを作成（正解ROI用）"""
    border = _border_from_mask(mask, thickness=max(1, int(border_thickness)))
    h, w = border.shape
    if not np.any(border):
        return create_colored_mask_qimage(np.zeros_like(border, dtype=np.uint8), [0, 0, 0, 0])

    yy, xx = np.where(border)
    cy, cx = yy.mean(), xx.mean()
    angles = np.arctan2(yy - cy, xx - cx)
    order = np.argsort(angles)
    yy = yy[order]
    xx = xx[order]

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
            y0 = max(0, y - S)
            y1 = min(h, y + S + 1)
            x0 = max(0, x - S)
            x1 = min(w, x + S + 1)
            if not dots[y0:y1, x0:x1].any():
                ys = slice(max(0, y - R), min(h, y + R + 1))
                xs = slice(max(0, x - R), min(w, x + R + 1))
                sub = dots[ys, xs]
                cy_rel = max(0, R - y)
                cx_rel = max(0, R - x)
                circle_crop = circle[cy_rel:cy_rel + sub.shape[0], cx_rel:cx_rel + sub.shape[1]]
                sub[circle_crop] = True

    return create_colored_mask_qimage(dots.astype(np.uint8), color_rgba)


def hex_to_rgba(hex_color: str, alpha: int = 255) -> List[int]:
    """HEX色コードをRGBAに変換"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        return [int(hex_color[i:i+2], 16) for i in (0, 2, 4)] + [alpha]
    return [255, 0, 0, alpha]  # デフォルトは赤


# -------------------- ImageDisplayWidget --------------------

class ImageDisplayWidget(QLabel):
    """画像表示用ウィジェット（CTとROI重ね合わせ）"""

    def __init__(self, title: str = ""):
        super().__init__()
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.setStyleSheet("""
            border: 1px solid rgba(255,255,255,0.08);
            background: #0a0e24;
            border-radius: 4px;
        """)
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(False)

        # データ
        self.ct_volume = None
        self.roi_volume = None
        self.gt_volume = None
        self.current_slice = 0
        self.title = title

        # 表示パラメータ
        self.ct_window = (-200, 300)
        self.show_ct = True
        self.show_gt = True
        self.show_roi = True
        self.roi_alpha = 180
        self.gt_alpha = 150
        self.selected_rois = set()
        self.roi_colors = {}
        self.gt_labels = []

        # パン・ズーム
        self.zoom_factor = 1.0
        self.pan_offset = [0, 0]
        self.is_panning = False
        self.last_pan_point = None

        # cover（余白ゼロで埋める）を既定に
        self._fill_mode = "cover"

        # スライス変更コールバック
        self.slice_change_callback = None

        self.setText(f"{title}\n(データなし)")

    def set_ct_volume(self, volume: np.ndarray):
        """CT画像をセット"""
        self.ct_volume = volume
        if self.ct_volume is not None and self.ct_volume.ndim == 3:
            self.current_slice = max(0, min(self.current_slice, self.ct_volume.shape[2] - 1))
        self.update_display()
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.update_display)
        except Exception:
            pass

    def set_roi_volume(self, volume: np.ndarray):
        """ROI画像をセット"""
        self.roi_volume = volume
        if self.ct_volume is not None and self.ct_volume.ndim == 3:
            self.current_slice = max(0, min(self.current_slice, self.ct_volume.shape[2] - 1))
        self.update_display()
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.update_display)
        except Exception:
            pass

    def set_gt_volume(self, volume: np.ndarray):
        """正解ラベル画像をセット"""
        self.gt_volume = volume
        if self.ct_volume is not None and self.ct_volume.ndim == 3:
            self.current_slice = max(0, min(self.current_slice, self.ct_volume.shape[2] - 1))
        self.update_display()
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.update_display)
        except Exception:
            pass

    def set_slice(self, slice_idx: int):
        """表示スライスを設定"""
        self.current_slice = slice_idx
        self.update_display()

    def set_visibility(self, show_ct: bool, show_gt: bool, show_roi: bool):
        """各レイヤーの表示/非表示を設定"""
        self.show_ct = show_ct
        self.show_gt = show_gt
        self.show_roi = show_roi
        self.update_display()

    def set_selected_rois(self, selected_rois: set):
        """選択された臓器を設定"""
        self.selected_rois = selected_rois
        self.update_display()

    def set_roi_colors(self, roi_colors: Dict[str, str]):
        """ROI色マッピングを設定"""
        self.roi_colors = roi_colors
        self.update_display()

    def set_gt_labels(self, gt_labels: List[Dict]):
        """正解ラベル情報を設定"""
        self.gt_labels = gt_labels

    def set_participant_labels(self, participant_labels: List[Dict]):
        """参加者ラベル情報を設定"""
        self.participant_labels = participant_labels

    def sync_zoom_pan_from_other(self, zoom_factor: float, pan_offset: List[float]):
        """他のビューからのズーム・パン同期"""
        self.zoom_factor = zoom_factor
        self.pan_offset = pan_offset.copy()
        self.update_display()

    def wheelEvent(self, event):
        """マウスホイール：Ctrl+スクロールでズーム、通常スクロールでスライス移動"""
        if self.ct_volume is None:
            return

        delta = event.angleDelta().y()

        # Ctrl+スクロール = ズーム
        if event.modifiers() & Qt.ControlModifier:
            old_zoom = self.zoom_factor
            if delta > 0:
                self.zoom_factor = min(self.zoom_factor * 1.2, 5.0)
            else:
                self.zoom_factor = max(self.zoom_factor / 1.2, 0.2)

            if self.zoom_factor != old_zoom:
                mouse_pos = [event.position().x(), event.position().y()]
                self._adjust_pan_for_zoom(mouse_pos, old_zoom)
                self.update_display()
                if hasattr(self, 'sync_zoom_pan_callback'):
                    self.sync_zoom_pan_callback(self.zoom_factor, self.pan_offset)
        else:
            if delta > 0 and self.current_slice < self.ct_volume.shape[2] - 1:
                self.current_slice += 1
                self.update_display()
                if self.slice_change_callback:
                    self.slice_change_callback(self.current_slice)
            elif delta < 0 and self.current_slice > 0:
                self.current_slice -= 1
                self.update_display()
                if self.slice_change_callback:
                    self.slice_change_callback(self.current_slice)

        event.accept()

    def mousePressEvent(self, event):
        """マウス押下：左ドラッグでパン開始"""
        if event.button() == Qt.LeftButton:
            self.is_panning = True
            self.last_pan_point = [event.x(), event.y()]
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """マウス移動：パン操作"""
        if self.is_panning and self.last_pan_point:
            delta_x = event.x() - self.last_pan_point[0]
            delta_y = event.y() - self.last_pan_point[1]

            self.pan_offset[0] += delta_x
            self.pan_offset[1] += delta_y

            self.last_pan_point = [event.x(), event.y()]
            self.update_display()
            if hasattr(self, 'sync_zoom_pan_callback'):
                self.sync_zoom_pan_callback(self.zoom_factor, self.pan_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """マウス解放：パン終了・右クリックでリセット"""
        if event.button() == Qt.LeftButton and self.is_panning:
            self.is_panning = False
            self.last_pan_point = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
        elif event.button() == Qt.RightButton:
            self.zoom_factor = 1.0
            self.pan_offset = [0, 0]
            self.update_display()
            if hasattr(self, 'sync_zoom_pan_callback'):
                self.sync_zoom_pan_callback(self.zoom_factor, self.pan_offset)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _adjust_pan_for_zoom(self, zoom_center, old_zoom):
        """ズーム時のパンオフセット調整（マウス中心）"""
        if old_zoom == 0:
            return

        widget_center_x = self.width() / 2
        widget_center_y = self.height() / 2

        mouse_offset_x = zoom_center[0] - widget_center_x
        mouse_offset_y = zoom_center[1] - widget_center_y

        zoom_ratio = self.zoom_factor / old_zoom

        pan_adjust_x = mouse_offset_x * (zoom_ratio - 1)
        pan_adjust_y = mouse_offset_y * (zoom_ratio - 1)

        self.pan_offset[0] = self.pan_offset[0] * zoom_ratio - pan_adjust_x
        self.pan_offset[1] = self.pan_offset[1] * zoom_ratio - pan_adjust_y

    def update_display(self):
        """画像を更新して表示（coverで余白ゼロ、必要に応じてクロップ）"""
        if self.ct_volume is None:
            self.setText(f"{self.title}\n(CTデータなし)")
            return

        if self.current_slice >= self.ct_volume.shape[2]:
            self.current_slice = self.ct_volume.shape[2] - 1
        if self.current_slice < 0:
            self.current_slice = 0

        # --- CT（90度反時計回り） ---
        ct_slice = self.ct_volume[:, :, self.current_slice]
        ct_slice = np.rot90(ct_slice, k=1)

        # 追加：左右反転（フラグが立っているとき）
        if getattr(self, "_flip_lr", False):
            ct_slice = np.fliplr(ct_slice)

        h, w = ct_slice.shape

        # ベースRGB
        rgb_image = np.zeros((h, w, 3), dtype=np.uint8)
        if self.show_ct:
            ct_normalized = self._normalize_ct(ct_slice)
            rgb_image[:, :, 0] = ct_normalized
            rgb_image[:, :, 1] = ct_normalized
            rgb_image[:, :, 2] = ct_normalized

        # QImage → QPixmap
        rgb_flat = np.ascontiguousarray(rgb_image)
        qimg = QImage(rgb_flat.data, w, h, w * 3, QImage.Format_RGB888)
        qimg.ndarray = rgb_flat
        pixmap = QPixmap.fromImage(qimg)

        # --- ROI/GT オーバーレイ ---
        if len(self.selected_rois) > 0:
            rgba_image = np.zeros((h, w, 4), dtype=np.uint8)
            rgba_image[:, :, :3] = rgb_image
            rgba_image[:, :, 3] = 255

            def _resize_nn(slice2d, target_hw):
                th, tw = target_hw
                if slice2d.shape == (th, tw):
                    return slice2d
                try:
                    from scipy.ndimage import zoom as _ndi_zoom
                    sy = th / slice2d.shape[0]
                    sx = tw / slice2d.shape[1]
                    return _ndi_zoom(slice2d, (sy, sx), order=0)
                except Exception:
                    yy = (np.linspace(0, slice2d.shape[0]-1, th)).astype(int)
                    xx = (np.linspace(0, slice2d.shape[1]-1, tw)).astype(int)
                    return slice2d[yy][:, xx]

            # --- 正解（個人比較モードでは実線、それ以外は点線） ---
            if self.show_gt and self.gt_volume is not None and self.current_slice < self.gt_volume.shape[2]:
                gt_slice = np.rot90(self.gt_volume[:, :, self.current_slice], k=1)
                if getattr(self, "_flip_lr", False):
                    gt_slice = np.fliplr(gt_slice)
                gt_slice = _resize_nn(gt_slice, (h, w))

                is_gt_only_mode = getattr(self, "_is_gt_only_mode", False)

                for gt_label_num in self.selected_rois:
                    if isinstance(gt_label_num, int) and gt_label_num > 0:
                        gt_mask = gt_slice == gt_label_num
                        if np.any(gt_mask):
                            gt_color = self._get_gt_color_by_label(gt_label_num)
                            if is_gt_only_mode:
                                gt_rgba = hex_to_rgba(gt_color, 255)
                                border = _border_from_mask(gt_mask.astype(np.uint8), thickness=2)
                                y_coords, x_coords = np.where(border)
                                rgba_image[y_coords, x_coords] = gt_rgba
                            else:
                                gt_rgba = hex_to_rgba(gt_color, 200)
                                border = _border_from_mask(gt_mask.astype(np.uint8), thickness=2)
                                y_coords, x_coords = np.where(border)
                                dotted_mask = ((y_coords + x_coords) % 6) < 3
                                rgba_image[y_coords[dotted_mask], x_coords[dotted_mask]] = gt_rgba

            # --- 参加者（実線） ---
            if self.show_roi and self.roi_volume is not None and self.current_slice < self.roi_volume.shape[2]:
                roi_slice = np.rot90(self.roi_volume[:, :, self.current_slice], k=1)
                if getattr(self, "_flip_lr", False):
                    roi_slice = np.fliplr(roi_slice)
                roi_slice = _resize_nn(roi_slice, (h, w))

                for selected_gt_label in self.selected_rois:
                    name = self._get_gt_roi_name_by_label(selected_gt_label)
                    if not name:
                        continue
                    participant_label = self._get_participant_label_by_name(name)
                    if participant_label is None:
                        continue
                    roi_mask = roi_slice == participant_label
                    if np.any(roi_mask):
                        border = _border_from_mask(roi_mask.astype(np.uint8), thickness=2)
                        roi_color = self._get_gt_color_by_label(selected_gt_label)
                        roi_rgba = hex_to_rgba(roi_color, 255)
                        y_coords, x_coords = np.where(border)
                        rgba_image[y_coords, x_coords] = roi_rgba

            rgba_flat = np.ascontiguousarray(rgba_image)
            qimg = QImage(rgba_flat.data, w, h, w * 4, QImage.Format_RGBA8888)
            qimg.ndarray = rgba_flat
            pixmap = QPixmap.fromImage(qimg)

        # --- cover / fit → 追加ズーム → 中央配置 + パン ---
        widget_w = max(1, self.width())
        widget_h = max(1, self.height())
        final_pixmap = QPixmap(widget_w, widget_h)
        final_pixmap.fill(QColor(26, 26, 26))

        if getattr(self, "_fill_mode", "cover") == "cover":
            scaled = pixmap.scaled(widget_w, widget_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        else:
            scaled = pixmap.scaled(widget_w, widget_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        if abs(self.zoom_factor - 1.0) > 0.001:
            zw = max(1, int(scaled.width() * self.zoom_factor))
            zh = max(1, int(scaled.height() * self.zoom_factor))
            scaled = scaled.scaled(zw, zh, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        draw_x = (widget_w - scaled.width()) // 2 + int(self.pan_offset[0])
        draw_y = (widget_h - scaled.height()) // 2 + int(self.pan_offset[1])

        painter = QPainter(final_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(draw_x, draw_y, scaled)
        painter.end()

        self.setPixmap(final_pixmap)
        self._qimg_ref = qimg
        self._pixmap_ref = final_pixmap

    def _get_gt_roi_name_by_label(self, label_num: int) -> Optional[str]:
        """正解ラベル番号からROI名を取得"""
        for gt_label in self.gt_labels:
            if gt_label.get('label') == label_num:
                return gt_label.get('name')
        return None

    def _get_participant_label_by_name(self, roi_name: str) -> Optional[int]:
        """ROI名から参加者のラベル番号を取得"""
        if hasattr(self, 'participant_labels') and self.participant_labels:
            for p_label in self.participant_labels:
                if p_label.get('name') == roi_name:
                    return p_label.get('label')

        if self.roi_colors and roi_name in self.roi_colors:
            roi_names = list(self.roi_colors.keys())
            try:
                index = roi_names.index(roi_name)
                return index + 1
            except ValueError:
                pass
        return None

    def _get_gt_color_by_label(self, label_num: int) -> str:
        """正解ラベル番号から色を取得"""
        for gt_label in self.gt_labels:
            if gt_label.get('label') == label_num:
                return gt_label.get('color', '#ff0000')
        return '#ff0000'

    def _get_roi_color_by_label(self, label_num: int) -> str:
        """ラベル番号からROI色を取得"""
        if self.roi_colors:
            colors = list(self.roi_colors.values())
            if label_num <= len(colors):
                return colors[label_num - 1]
            else:
                return colors[0]

        color_map = {
            1: '#e6194b',
            2: '#3cb44b',
            3: '#ffe119',
            4: '#4363d8',
            5: '#f58231',
        }
        return color_map.get(label_num, '#ff0000')

    def _normalize_ct(self, ct_slice: np.ndarray) -> np.ndarray:
        """CTを0-255に正規化"""
        window_min, window_max = self.ct_window
        clipped = np.clip(ct_slice, window_min, window_max)
        normalized = ((clipped - window_min) / (window_max - window_min) * 255).astype(np.uint8)
        return normalized

    def set_fill_mode(self, mode: str):
        """画像のフィット方式を設定"""
        m = (mode or "").lower()
        self._fill_mode = "cover" if m not in ("fit", "cover") else m
        self._refit_view()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refit_view()

    def _refit_view(self):
        """QGraphicsView フィッティング（存在すれば）"""
        try:
            item = getattr(self, "_image_item", None) or getattr(self, "image_item", None)
            if item is None:
                return
            br = item.mapRectToScene(item.boundingRect())
            if br.isEmpty():
                return

            vw = max(1, self.viewport().width())
            vh = max(1, self.viewport().height())
            sx = vw / br.width()
            sy = vh / br.height()

            mode = getattr(self, "_fill_mode", "cover")
            s = max(sx, sy) if mode == "cover" else min(sx, sy)

            t = QTransform()
            t.scale(s, s)
            self.setTransform(t)
            self.setSceneRect(br)
            self.centerOn(br.center())

            self.setFrameShape(QFrame.NoFrame)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setAlignment(Qt.AlignCenter)

        except Exception:
            pass

    def set_window(self, window_level: float, window_width: float):
        """WW/WL を適用"""
        try:
            ww = float(window_width)
            wl = float(window_level)
        except Exception:
            return

        if ww <= 0:
            ww = 1.0

        vmin = wl - ww / 2.0
        vmax = wl + ww / 2.0
        if vmin >= vmax:
            vmax = vmin + 1.0

        self.ct_window = (vmin, vmax)
        self.update_display()

    def showEvent(self, event):
        super().showEvent(event)
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.update_display)
        except Exception:
            pass
