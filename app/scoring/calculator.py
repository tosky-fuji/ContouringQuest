# -*- coding: utf-8 -*-
"""スコア計算ロジック（バックグラウンドスレッド）"""

import os
import json
import numpy as np
import nibabel as nib
from typing import List
from scipy.ndimage import binary_erosion, binary_dilation
from skimage.measure import perimeter
from skimage.morphology import binary_closing, disk

from PySide6.QtCore import QThread, Signal

from app.common.paths import resolve_path
from app.common.data_models import ScoreResult, GameResult

# デバッグログの有効/無効（必要な時はTrueに変更）
DEBUG = False


class ScoreCalculatorThread(QThread):
    """バックグラウンドでスコア計算を行うスレッド"""
    progress_updated = Signal(int)
    calculation_finished = Signal(object)  # GameResult
    error_occurred = Signal(str)

    def __init__(self, result_json_path: str):
        super().__init__()
        self.result_json_path = result_json_path

    def run(self):
        try:
            result = self.calculate_scores()
            self.calculation_finished.emit(result)
        except Exception as e:
            self.error_occurred.emit(str(e))

    def calculate_scores(self) -> GameResult:
        """メインのスコア計算処理（ROI名の表記ゆれを正規化して対応付けを頑健化）"""
        with open(self.result_json_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        participant = meta.get('participant', 'Unknown')
        team = meta.get('team', 'Unknown')
        session_id = meta.get('session_id', 'Unknown')
        case = meta.get('case', 'Unknown')
        roi_order_orig = meta.get('roi_order', [])
        time_limit = meta.get('time_limit_sec', 0)
        elapsed = meta.get('elapsed_sec', 0)

        def _norm(name: str) -> str:
            s = str(name or "").strip()
            s = s.replace(" ", "").replace("\u3000", "")
            s = s.replace("右腎臓", "右腎").replace("左腎臓", "左腎")
            s = s.replace("胆のう", "胆嚢")
            return s

        json_dir = os.path.dirname(self.result_json_path)
        json_base = os.path.splitext(os.path.basename(self.result_json_path))[0]
        pred_nii_path = os.path.join(json_dir, json_base.replace('_labels', '') + '_labels.nii.gz')
        if not os.path.exists(pred_nii_path):
            pred_nii_path = os.path.join(json_dir, json_base + '.nii.gz')
        if not os.path.exists(pred_nii_path):
            raise FileNotFoundError(f"予測ラベルファイルが見つかりません: {pred_nii_path}")

        pred_nii = nib.load(pred_nii_path)
        pred_vol = np.asarray(pred_nii.dataobj).astype(np.int32)

        # 予測ボリュームに tf_contouring.py の load_mask と同じ自動LR補正を適用
        try:
            from nibabel.orientations import aff2axcodes
            ax = aff2axcodes(pred_nii.affine)
            pred_needs_lr = (len(ax) > 0 and ax[0] == 'R')
        except Exception:
            a = getattr(pred_nii, "affine", None)
            pred_needs_lr = bool(a is not None and float(a[0, 0]) > 0)

        if pred_needs_lr:
            pred_vol = pred_vol[::-1, :, :]
            if DEBUG: print(f"[DEBUG] Applied automatic LR correction to pred_vol (affine-based)")

        gt_label_path = meta.get('gt_label_path')
        if not gt_label_path:
            raise ValueError("正解ラベルパスが指定されていません")
        gt_label_path = resolve_path(gt_label_path)
        if not os.path.exists(gt_label_path):
            # JSON内のパスが古い場合、設定ファイルから現在のGTパスを取得
            gt_label_path = self._resolve_gt_from_config()
            if not gt_label_path:
                raise FileNotFoundError(f"正解ラベルファイルが見つかりません")

        gt_nii = nib.load(gt_label_path)
        gt_vol = np.asarray(gt_nii.dataobj).astype(np.int32)

        # GTボリュームの自動LR補正（affineに基づく）
        try:
            from nibabel.orientations import aff2axcodes
            ax = aff2axcodes(gt_nii.affine)
            gt_needs_lr = (len(ax) > 0 and ax[0] == 'R')
        except Exception:
            a = getattr(gt_nii, "affine", None)
            gt_needs_lr = bool(a is not None and float(a[0, 0]) > 0)

        if gt_needs_lr:
            gt_vol = gt_vol[::-1, :, :]
            if DEBUG: print(f"[DEBUG] Applied automatic LR correction to gt_vol (affine-based)")

        gt_label_json_path = gt_label_path.replace('.nii.gz', '_labels.json').replace('.nii', '_labels.json')
        gt_label_mapping_raw = {}
        gt_view_flips = {}
        if not os.path.exists(gt_label_json_path):
            # glob で *_labels.json を探す
            import glob
            gt_dir = os.path.dirname(gt_label_path)
            candidates = glob.glob(os.path.join(gt_dir, '*_labels.json'))
            if candidates:
                gt_label_json_path = candidates[0]
        if os.path.exists(gt_label_json_path):
            try:
                with open(gt_label_json_path, 'r', encoding='utf-8') as f:
                    gt_json_data = json.load(f)
                    for label_info in gt_json_data.get('labels', []):
                        name = label_info.get('name', '')
                        label_num = label_info.get('label', 0)
                        if name and label_num:
                            gt_label_mapping_raw[str(name)] = int(label_num)
                    gt_view_flips = gt_json_data.get('view_flips', {})
            except Exception:
                pass

        # 予測とGTのそれぞれに view_flips を適用して同じ座標系に揃える
        # （レビュー画面やプレイ画面と同じ反転処理）
        pred_view_flips = meta.get('view_flips', {})

        if DEBUG: print(f"\n[DEBUG] pred_view_flips: {pred_view_flips}")
        if DEBUG: print(f"[DEBUG] gt_view_flips: {gt_view_flips}")
        if DEBUG: print(f"[DEBUG] pred_needs_lr (affine): {pred_needs_lr}")
        if DEBUG: print(f"[DEBUG] gt_needs_lr (affine): {gt_needs_lr}")
        if DEBUG: print(f"[DEBUG] pred_vol shape before view_flips: {pred_vol.shape}")
        if DEBUG: print(f"[DEBUG] gt_vol shape before view_flips: {gt_vol.shape}")
        if DEBUG: print(f"[DEBUG] pred_vol unique labels before view_flips: {np.unique(pred_vol)[:20]}")
        if DEBUG: print(f"[DEBUG] gt_vol unique labels before view_flips: {np.unique(gt_vol)[:20]}")

        # pred_vol: participant_column.py と同じロジック（view_flips との差分を適用）
        saved_pred_lr = pred_view_flips.get('left_right', False)
        if saved_pred_lr != pred_needs_lr:
            pred_vol = pred_vol[::-1, :, :]
            if DEBUG: print(f"[DEBUG] Applied left_right adjustment to pred_vol (saved_lr={saved_pred_lr}, needs_lr={pred_needs_lr})")

        if pred_view_flips.get('anterior_posterior', False):
            pred_vol = pred_vol[:, ::-1, :]
            if DEBUG: print(f"[DEBUG] Applied anterior_posterior flip to pred_vol")
        if pred_view_flips.get('superior_inferior', False):
            pred_vol = pred_vol[:, :, ::-1]
            if DEBUG: print(f"[DEBUG] Applied superior_inferior flip to pred_vol")

        # gt_vol: review_window.py と同じロジック（自動LR補正後の状態と保存時の状態を比較）
        saved_gt_lr = gt_view_flips.get('left_right', False)
        if saved_gt_lr != gt_needs_lr:
            gt_vol = gt_vol[::-1, :, :]
            if DEBUG: print(f"[DEBUG] Applied left_right adjustment to gt_vol (saved_lr={saved_gt_lr}, needs_lr={gt_needs_lr})")

        # gt_vol の anterior_posterior と superior_inferior
        if gt_view_flips.get('anterior_posterior', False):
            gt_vol = gt_vol[:, ::-1, :]
            if DEBUG: print(f"[DEBUG] Applied anterior_posterior flip to gt_vol")
        if gt_view_flips.get('superior_inferior', False):
            gt_vol = gt_vol[:, :, ::-1]
            if DEBUG: print(f"[DEBUG] Applied superior_inferior flip to gt_vol")

        if DEBUG: print(f"[DEBUG] pred_vol shape after view_flips: {pred_vol.shape}")
        if DEBUG: print(f"[DEBUG] gt_vol shape after view_flips: {gt_vol.shape}")
        if DEBUG: print(f"[DEBUG] pred_vol unique labels after view_flips: {np.unique(pred_vol)[:20]}")
        if DEBUG: print(f"[DEBUG] gt_vol unique labels after view_flips: {np.unique(gt_vol)[:20]}")

        if gt_vol.shape != pred_vol.shape:
            raise ValueError(f"画像サイズが一致しません。GT: {gt_vol.shape}, Pred: {pred_vol.shape}")

        def _to_int(x):
            try:
                return int(x)
            except Exception:
                return x

        labels_info_list = meta.get('labels', [])

        pred_map = {}
        for it in labels_info_list:
            nm = _norm(it.get('name', ''))
            lb = _to_int(it.get('label'))
            if nm and isinstance(lb, int):
                pred_map[nm] = lb

        gt_map = {}
        for nm_raw, lb in gt_label_mapping_raw.items():
            nm = _norm(nm_raw)
            if nm and isinstance(lb, int):
                gt_map[nm] = lb

        roi_order = [str(n) for n in roi_order_orig]
        roi_order_norm = [_norm(n) for n in roi_order]

        print(f"\n[DEBUG] ROI Mapping:")
        if DEBUG: print(f"  pred_map: {pred_map}")
        if DEBUG: print(f"  gt_map: {gt_map}")
        if DEBUG: print(f"  roi_order_norm: {roi_order_norm}")

        scores: List[ScoreResult] = []
        total_progress = max(1, len(roi_order))

        for i, (roi_name_disp, roi_name_norm) in enumerate(zip(roi_order, roi_order_norm)):
            self.progress_updated.emit(int((i / total_progress) * 100))

            pred_label_num = pred_map.get(roi_name_norm, None)
            print(f"\n[DEBUG] Processing ROI '{roi_name_disp}' (normalized: '{roi_name_norm}')")
            print(f"  pred_label_num from map: {pred_label_num}")
            if pred_label_num is None:
                score = ScoreResult(
                    roi_name=roi_name_disp, dice_score=0.0, axial_smoothness=0.0,
                    volume_smoothness=0.0, total_score=0.0,
                    details={'error': 'ROI not found in prediction results (after normalization)'}
                )
            else:
                gt_label_num = gt_map.get(roi_name_norm, 0)
                print(f"  gt_label_num from map: {gt_label_num}")
                score = self._calculate_roi_score_with_separate_labels(
                    roi_name_disp, int(pred_label_num), int(gt_label_num), pred_vol, gt_vol
                )
            scores.append(score)

        overall_score = (sum(s.total_score for s in scores) / len(scores)) if scores else 0.0
        self.progress_updated.emit(100)

        return GameResult(
            participant=participant, team=team, session_id=session_id,
            case=case, roi_order=roi_order, time_limit_sec=time_limit,
            elapsed_sec=elapsed, scores=scores, overall_score=overall_score
        )

    def _resolve_gt_from_config(self):
        """設定ファイルから現在のGTパスを取得（JSON内パスが古い場合のフォールバック）"""
        try:
            from app.common.settings import load_settings
            settings = load_settings()
            regions = settings.get("regions", {})
            for reg in regions.values():
                gt_rel = reg.get("gt_label", "")
                if gt_rel:
                    gt_abs = resolve_path(gt_rel)
                    if gt_abs and os.path.isfile(gt_abs):
                        return gt_abs
        except Exception:
            pass
        return None

    def _calculate_roi_score_with_separate_labels(self, roi_name, pred_label_num, gt_label_num, pred_vol, gt_vol):
        print(f"\n[DEBUG ROI: {roi_name}]")
        if DEBUG: print(f"  pred_label_num: {pred_label_num}, gt_label_num: {gt_label_num}")

        pred_mask = (pred_vol == pred_label_num)
        gt_mask = (gt_vol == gt_label_num)

        if DEBUG: print(f"  pred_mask voxels: {np.sum(pred_mask)}")
        if DEBUG: print(f"  gt_mask voxels: {np.sum(gt_mask)}")
        if DEBUG: print(f"  intersection voxels: {np.sum(pred_mask & gt_mask)}")

        # スライス分布を確認
        pred_slices_with_data = []
        gt_slices_with_data = []
        for z in range(pred_mask.shape[2]):
            if np.any(pred_mask[:, :, z]):
                pred_slices_with_data.append(z)
            if np.any(gt_mask[:, :, z]):
                gt_slices_with_data.append(z)

        if DEBUG: print(f"  pred slices with data: {len(pred_slices_with_data)} slices")
        if pred_slices_with_data:
            print(f"    range: {min(pred_slices_with_data)} to {max(pred_slices_with_data)}")
            print(f"    slices: {pred_slices_with_data[:10]}{'...' if len(pred_slices_with_data) > 10 else ''}")
        if DEBUG: print(f"  gt slices with data: {len(gt_slices_with_data)} slices")
        if gt_slices_with_data:
            print(f"    range: {min(gt_slices_with_data)} to {max(gt_slices_with_data)}")
            print(f"    slices: {gt_slices_with_data[:10]}{'...' if len(gt_slices_with_data) > 10 else ''}")

        # 重複するスライスを確認
        common_slices = set(pred_slices_with_data) & set(gt_slices_with_data)
        if DEBUG: print(f"  common slices: {len(common_slices)}")
        if common_slices:
            sample_slice = sorted(common_slices)[0]
            pred_2d = pred_mask[:, :, sample_slice]
            gt_2d = gt_mask[:, :, sample_slice]
            pred_coords = np.argwhere(pred_2d)
            gt_coords = np.argwhere(gt_2d)
            if len(pred_coords) > 0 and len(gt_coords) > 0:
                print(f"    sample slice {sample_slice}:")
                print(f"      pred center: ({pred_coords[:, 0].mean():.1f}, {pred_coords[:, 1].mean():.1f})")
                print(f"      gt center: ({gt_coords[:, 0].mean():.1f}, {gt_coords[:, 1].mean():.1f})")
                print(f"      intersection on this slice: {np.sum(pred_2d & gt_2d)}")

        if not np.any(gt_mask):
            print(f"  ERROR: Ground truth is empty!")
            return ScoreResult(roi_name=roi_name, dice_score=0.0, axial_smoothness=0.0,
                               volume_smoothness=0.0, total_score=0.0,
                               details={'error': 'Ground truth is empty'})

        if not np.any(pred_mask):
            print(f"  WARNING: Prediction is empty!")

        dice_score = self._calculate_dice_coefficient(pred_mask, gt_mask)
        if DEBUG: print(f"  dice_score: {dice_score}")
        axial_smoothness = self._calculate_axial_smoothness(pred_mask)
        volume_smoothness = self._calculate_volume_smoothness(pred_mask)

        weights = [0.6, 0.2, 0.2]
        total_score = dice_score * weights[0] + axial_smoothness * weights[1] + volume_smoothness * weights[2]

        details = {
            'pred_volume': int(np.sum(pred_mask)), 'gt_volume': int(np.sum(gt_mask)),
            'intersection': int(np.sum(pred_mask & gt_mask)), 'weights': weights,
            'pred_label_num': pred_label_num, 'gt_label_num': gt_label_num
        }
        return ScoreResult(roi_name=roi_name, dice_score=dice_score,
                           axial_smoothness=axial_smoothness, volume_smoothness=volume_smoothness,
                           total_score=total_score, details=details)

    def _calculate_dice_coefficient(self, pred, gt):
        intersection = np.sum(pred & gt)
        total = np.sum(pred) + np.sum(gt)
        if total == 0:
            return 1.0 if intersection == 0 else 0.0
        return 2.0 * intersection / total

    def _calculate_axial_smoothness(self, mask):
        if not np.any(mask):
            return 0.0
        smoothness_scores = []
        h, w, d = mask.shape
        for z in range(d):
            slice_mask = mask[:, :, z]
            if not np.any(slice_mask):
                continue
            try:
                area = np.sum(slice_mask)
                if area == 0:
                    continue
                ideal_ratio = 2 * np.sqrt(np.pi / area)
                actual_perimeter = perimeter(slice_mask)
                actual_ratio = actual_perimeter / area if area > 0 else float('inf')
                ratio_score = min(1.0, ideal_ratio / max(actual_ratio, 1e-6))
                smoothed = binary_closing(slice_mask, disk(2))
                smoothness_score = 1.0 - np.sum(np.logical_xor(slice_mask, smoothed)) / area
                slice_score = (ratio_score + smoothness_score) / 2
                smoothness_scores.append(max(0.0, min(1.0, slice_score)))
            except Exception:
                continue
        return np.mean(smoothness_scores) if smoothness_scores else 0.0

    def _calculate_volume_smoothness(self, mask):
        if not np.any(mask):
            return 0.0
        h, w, d = mask.shape
        if d < 2:
            return 1.0
        smoothness_scores = []
        for z in range(d - 1):
            mask1 = mask[:, :, z]
            mask2 = mask[:, :, z + 1]
            area1 = np.sum(mask1)
            area2 = np.sum(mask2)
            if area1 == 0 and area2 == 0:
                smoothness_scores.append(1.0)
            elif area1 == 0 or area2 == 0:
                smoothness_scores.append(0.0)
            else:
                intersection = np.sum(mask1 & mask2)
                dice = 2 * intersection / (area1 + area2)
                smoothness_scores.append(dice)
        volume_per_slice = [np.sum(mask[:, :, z]) for z in range(d)]
        if len(volume_per_slice) > 2:
            non_zero_volumes = [v for v in volume_per_slice if v > 0]
            if non_zero_volumes:
                volume_std = np.std(non_zero_volumes)
                volume_mean = np.mean(non_zero_volumes)
                volume_stability = max(0.0, 1.0 - volume_std / max(volume_mean, 1.0))
            else:
                volume_stability = 1.0
        else:
            volume_stability = 1.0
        slice_continuity = np.mean(smoothness_scores) if smoothness_scores else 0.0
        return (slice_continuity + volume_stability) / 2
