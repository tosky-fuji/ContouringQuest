# -*- coding: utf-8 -*-
"""参加者カラムウィジェット"""

import os
import json
import numpy as np
from typing import Dict, List

# デバッグログの有効/無効（必要な時はTrueに変更）
DEBUG = False

from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame, QLabel, QSizePolicy
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from app.common.data_models import ParticipantResult
from .image_widgets import ImageDisplayWidget


class ParticipantColumnWidget(QWidget):
    """参加者のカラム（名前＋画像表示）- 横並び用"""

    def __init__(self, result: ParticipantResult, show_name: bool = True, view_flips: dict = None):
        super().__init__()
        self.result = result
        self.show_name = show_name
        self.view_flips = view_flips or {}
        self.image_widget = None
        self.roi_colors = {}
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # 見出し（学籍番号） - show_nameがTrueの時のみ表示
        if self.show_name:
            info_widget = QFrame()
            info_widget.setFrameStyle(QFrame.StyledPanel)
            info_widget.setFixedHeight(32)
            info_layout = QVBoxLayout(info_widget)
            info_layout.setContentsMargins(3, 3, 3, 3)

            self._name_full_text = f"{self.result.participant}"
            self.name_label = QLabel(self._name_full_text)
            self.name_label.setAlignment(Qt.AlignCenter)
            self.name_label.setFont(QFont("", 10, QFont.Bold))
            self.name_label.setStyleSheet(
                "color:#e9edff;background:rgba(255,255,255,0.04);padding:4px;border-radius:10px;"
            )
            self.name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            info_layout.addWidget(self.name_label)
            layout.addWidget(info_widget)
        else:
            self.name_label = None
            self._name_full_text = ""

        # 画像表示（最大化して埋める）
        self.image_widget = ImageDisplayWidget(self.result.participant)
        self.image_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        if hasattr(self.image_widget, "set_fill_mode"):
            self.image_widget.set_fill_mode("cover")
        layout.addWidget(self.image_widget)

        # 画像エリアを優先的に広げる
        layout.setStretch(0, 0)  # 見出し
        layout.setStretch(1, 1)  # 画像

        # ラベルのエリプシス更新（中央省略）
        QTimer.singleShot(0, self._update_name_elide)

    def load_data(self):
        """データをロード（複数JSON/NIfTIを統合）"""
        try:
            # ----- 1) labels & colors を統合 -----
            merged_labels_by_name = {}
            merged_roi_colors = {}

            for jp in (self.result.json_paths or []):
                if not jp or not os.path.exists(jp):
                    continue
                with open(jp, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                for label_info in data.get('labels', []):
                    nm = label_info.get('name')
                    if not nm:
                        continue
                    merged_labels_by_name[nm] = label_info
                    color_hex = label_info.get('color', '#ff0000')
                    merged_roi_colors[nm] = color_hex

            self.roi_colors = merged_roi_colors
            self.image_widget.set_roi_colors(self.roi_colors)
            self.image_widget.set_participant_labels(list(merged_labels_by_name.values()))

            # ----- 2) ROI NIfTI を合成 -----
            nii_paths = [p for p in (self.result.nii_paths or []) if p and os.path.exists(p)]
            if nii_paths:
                import nibabel as nib
                merged = None
                base_hwz = None

                def _resize_nn(vol, target_shape):
                    if vol.shape == target_shape:
                        return vol
                    try:
                        from scipy.ndimage import zoom as _ndi_zoom
                        sy = target_shape[0] / vol.shape[0]
                        sx = target_shape[1] / vol.shape[1]
                        sz = target_shape[2] / vol.shape[2]
                        return _ndi_zoom(vol, (sy, sx, sz), order=0)
                    except Exception:
                        zt, yt, xt = target_shape[2], target_shape[0], target_shape[1]
                        zz = (np.linspace(0, vol.shape[2]-1, zt)).astype(int)
                        yy = (np.linspace(0, vol.shape[0]-1, yt)).astype(int)
                        xx = (np.linspace(0, vol.shape[1]-1, xt)).astype(int)
                        return vol[np.ix_(yy, xx, zz)]

                # 自動LR補正の状態を記録
                needs_lr = False

                for npth in nii_paths:
                    try:
                        nii = nib.load(npth)
                        vol = np.asarray(nii.dataobj).astype(np.int32)
                        if DEBUG: print(f"[DEBUG PARTICIPANT] Loaded ROI NIfTI: {os.path.basename(npth)}, shape: {vol.shape}, unique labels: {np.unique(vol)[:10]}")

                        # tf_contouring.py の load_mask と同じ自動LR補正を適用
                        try:
                            from nibabel.orientations import aff2axcodes
                            ax = aff2axcodes(nii.affine)
                            if len(ax) > 0 and ax[0] == 'R':
                                vol = vol[::-1, :, :]
                                needs_lr = True  # 最初の NIfTI の affine で判定
                                if DEBUG: print(f"[DEBUG PARTICIPANT] Applied automatic LR correction (affine check)")
                        except Exception:
                            # フォールバック
                            a = getattr(nii, "affine", None)
                            if a is not None and float(a[0, 0]) > 0:
                                vol = vol[::-1, :, :]
                                needs_lr = True
                                if DEBUG: print(f"[DEBUG PARTICIPANT] Applied automatic LR correction (fallback)")

                    except Exception as e:
                        print(f"ROI NIfTI 読み込みエラー: {npth}, {e}")
                        continue

                    if merged is None:
                        merged = vol
                        base_hwz = vol.shape
                    else:
                        if vol.shape != base_hwz and base_hwz is not None:
                            vol = _resize_nn(vol, base_hwz)
                        merged = np.maximum(merged, vol)

                if merged is not None:
                    if DEBUG: print(f"[DEBUG PARTICIPANT] Merged ROI volume, shape: {merged.shape}, unique labels: {np.unique(merged)[:10]}")
                    if DEBUG: print(f"[DEBUG PARTICIPANT] view_flips: {self.view_flips}")
                    if DEBUG: print(f"[DEBUG PARTICIPANT] needs_lr={needs_lr}")

                    # review_window.py と同じロジック: view_flips との差分を適用
                    saved_lr = self.view_flips.get("left_right", False)
                    if DEBUG: print(f"[DEBUG PARTICIPANT] saved_lr={saved_lr}, needs_lr={needs_lr}")
                    if saved_lr != needs_lr:
                        merged = merged[::-1, :, :]
                        if DEBUG: print(f"[DEBUG PARTICIPANT] Applied LR adjustment (saved_lr != needs_lr)")

                    # anterior_posterior と superior_inferior は直接適用
                    if self.view_flips.get("anterior_posterior", False):
                        merged = merged[:, ::-1, :]
                        if DEBUG: print(f"[DEBUG PARTICIPANT] Applied AP flip")
                    if self.view_flips.get("superior_inferior", False):
                        merged = merged[:, :, ::-1]
                        if DEBUG: print(f"[DEBUG PARTICIPANT] Applied SI flip")

                    if DEBUG: print(f"[DEBUG PARTICIPANT] Final ROI volume sent to image_widget")
                    self.image_widget.set_roi_volume(merged)

        except Exception as e:
            print(f"データ統合エラー ({self.result.participant}): {e}")

    def set_ct_volume(self, volume: np.ndarray):
        """CT画像をセット"""
        self.image_widget.set_ct_volume(volume)

    def set_gt_volume(self, volume: np.ndarray):
        """正解ラベル画像をセット"""
        self.image_widget.set_gt_volume(volume)

    def set_slice(self, slice_idx: int):
        """表示スライスを設定"""
        self.image_widget.set_slice(slice_idx)

    def set_visibility(self, show_ct: bool, show_gt: bool, show_roi: bool):
        """各レイヤーの表示/非表示を設定"""
        self.image_widget.set_visibility(show_ct, show_gt, show_roi)

    def set_selected_rois(self, selected_rois: set):
        """選択された臓器を設定"""
        self.image_widget.set_selected_rois(selected_rois)

    def set_gt_labels(self, gt_labels: List[Dict]):
        """正解ラベル情報を設定"""
        self.image_widget.set_gt_labels(gt_labels)

    def set_participant_labels(self, participant_labels: List[Dict]):
        """参加者ラベル情報を設定"""
        self.image_widget.set_participant_labels(participant_labels)

    def sync_zoom_pan_from_other(self, zoom_factor: float, pan_offset: List[float]):
        """他のビューからのズーム・パン同期"""
        self.image_widget.sync_zoom_pan_from_other(zoom_factor, pan_offset)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_name_elide()

    def _update_name_elide(self):
        """学籍番号ラベルを現幅に合わせて中央省略し、ツールチップで全体を見せる"""
        if not hasattr(self, "name_label") or not self.name_label or not hasattr(self, "_name_full_text"):
            return
        w = max(0, self.name_label.width() - 8)
        if w <= 0:
            return
        fm = self.name_label.fontMetrics()
        elided = fm.elidedText(self._name_full_text, Qt.ElideMiddle, w)
        self.name_label.setText(elided)
        self.name_label.setToolTip(self._name_full_text)
