# -*- coding: utf-8 -*-
"""レビューメインウィンドウ"""

import os
import glob
import csv
import json
import numpy as np
from typing import Dict, List, Optional

# デバッグログの有効/無効（必要な時はTrueに変更）
DEBUG = False

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QCheckBox, QScrollArea, QFrame,
    QSplitter, QGroupBox, QMessageBox, QSlider, QSpinBox, QListWidget,
    QListWidgetItem, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor

from app.common.data_models import ParticipantResult, GroupData
from app.common.config_manager import get_config_manager
from app.common.styles import BASE_STYLESHEET

from .image_widgets import ImageDisplayWidget
from .participant_column import ParticipantColumnWidget


class ReviewMainWindow(QMainWindow):
    """振り返りアプリのメインウィンドウ"""

    def __init__(self, records_dir: str = None, group: str = ""):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.records_dir = records_dir
        self._fixed_group = group.strip().upper() if group else ""
        self.config_manager = get_config_manager()
        self.groups_data: Dict[str, GroupData] = {}
        self.current_group: Optional[GroupData] = None
        self.participant_columns: List = []
        self.current_slice = 0
        self.max_slices = 0
        self.roi_labels_map = {}

        self.setWindowTitle("Contour Quest - 振り返り（Review）")
        self.showMaximized()
        self.setStyleSheet(BASE_STYLESHEET)

        self.setup_ui()
        self.load_groups_data()
        self._auto_select_group()

    def setup_ui(self):
        """UIを構築"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(5)

        # 左側：コントロールパネル
        self.setup_control_panel(main_layout)

        # 右側：画像表示エリア
        self.viewer_splitter = QSplitter(Qt.Horizontal)
        self.viewer_splitter.setChildrenCollapsible(False)
        self.viewer_splitter.setHandleWidth(6)

        self.setup_image_area()

        main_layout.addWidget(self.viewer_splitter, stretch=1)

    def setup_control_panel(self, main_layout):
        """左端：コントロールパネル"""
        control_frame = QFrame()
        control_frame.setFixedWidth(320)
        control_frame.setFrameStyle(QFrame.StyledPanel)
        control_layout = QVBoxLayout(control_frame)
        control_layout.setSpacing(8)

        # === 個人選択 ===
        self.person_box = QGroupBox("個人選択")
        person_layout = QVBoxLayout(self.person_box)
        self.person_combo = QComboBox()
        self.person_combo.currentTextChanged.connect(self.on_person_changed)
        person_layout.addWidget(self.person_combo)
        control_layout.addWidget(self.person_box)

        # === スライス制御 ===
        slice_group = QGroupBox("スライス制御")
        slice_layout = QVBoxLayout(slice_group)
        slider_layout = QHBoxLayout()
        self.slice_slider = QSlider(Qt.Horizontal)
        self.slice_slider.setRange(0, 0)
        self.slice_slider.setValue(0)
        self.slice_slider.valueChanged.connect(lambda v: self.on_wheel_slice_changed(v))
        slider_layout.addWidget(self.slice_slider)
        self.slice_spinbox = QSpinBox()
        self.slice_spinbox.setRange(0, 0)
        self.slice_spinbox.setValue(0)
        self.slice_spinbox.valueChanged.connect(lambda v: self.on_wheel_slice_changed(v - 1))
        slider_layout.addWidget(self.slice_spinbox)
        slice_layout.addLayout(slider_layout)
        control_layout.addWidget(slice_group)

        # === 表示制御 ===
        display_group = QGroupBox("表示制御")
        display_layout = QVBoxLayout(display_group)
        self.show_ct_cb = QCheckBox("CT画像")
        self.show_ct_cb.setChecked(True)
        self.show_ct_cb.toggled.connect(self.on_visibility_changed)
        display_layout.addWidget(self.show_ct_cb)

        self.show_gt_cb = QCheckBox("正解ROI (緑の輪郭)")
        self.show_gt_cb.setChecked(True)
        self.show_gt_cb.toggled.connect(self.on_visibility_changed)
        display_layout.addWidget(self.show_gt_cb)

        control_layout.addWidget(display_group)

        # === ROI選択 ===
        roi_group = QGroupBox("ROI選択")
        roi_layout = QVBoxLayout(roi_group)

        btn_row = QHBoxLayout()
        self.select_all_btn = QPushButton("全選択")
        self.select_all_btn.clicked.connect(self.select_all_rois)
        self.deselect_all_btn = QPushButton("全解除")
        self.deselect_all_btn.clicked.connect(self.deselect_all_rois)
        btn_row.addWidget(self.select_all_btn)
        btn_row.addWidget(self.deselect_all_btn)
        roi_layout.addLayout(btn_row)

        self.roi_list = QListWidget()
        self.roi_list.setSelectionMode(QListWidget.MultiSelection)
        self.roi_list.itemSelectionChanged.connect(self.on_roi_selection_changed)
        roi_layout.addWidget(self.roi_list)

        control_layout.addWidget(roi_group)

        control_layout.addStretch()
        main_layout.addWidget(control_frame, stretch=0)

    def setup_image_area(self):
        """画像表示エリアをセットアップ"""
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background-color: #0a0e24;")
        self.content_layout = None
        self.scroll_area.setWidget(self.content_widget)

        self.viewer_splitter.addWidget(self.scroll_area)

    def select_all_rois(self):
        for i in range(self.roi_list.count()):
            self.roi_list.item(i).setSelected(True)

    def deselect_all_rois(self):
        self.roi_list.clearSelection()

    def on_roi_selection_changed(self):
        selected_items = self.roi_list.selectedItems()
        selected_rois = set()

        for item in selected_items:
            roi_name = item.text()
            if roi_name in self.roi_labels_map:
                selected_rois.add(self.roi_labels_map[roi_name])

        for column in self.participant_columns:
            column.set_selected_rois(selected_rois)

    def load_groups_data(self):
        """グループ（班）データを読み込み"""
        if not os.path.exists(self.records_dir):
            QMessageBox.warning(self, "警告", f"記録フォルダが見つかりません: {self.records_dir}")
            return

        csv_files = glob.glob(os.path.join(self.records_dir, "**/*.csv"), recursive=True)

        participants: Dict[str, ParticipantResult] = {}

        for csv_path in csv_files:
            try:
                with open(csv_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        group = row.get('group', 'Unknown')
                        team = row.get('team', 'Unknown')
                        participant = row.get('participant', '')
                        session_id = row.get('session', '')

                        if not participant or not session_id:
                            continue

                        json_pattern = f"**/*{session_id}*{participant}*.json"
                        json_matches = glob.glob(os.path.join(self.records_dir, json_pattern), recursive=True)
                        if not json_matches:
                            continue

                        # 各JSONファイルを個別に処理（ケースごとに分離）
                        for json_path in sorted(json_matches):
                            nii_path = self._find_roi_nii_path(json_path)

                            try:
                                with open(json_path, 'r', encoding='utf-8') as jf:
                                    json_data = json.load(jf)
                            except Exception as e:
                                print(f"JSON読み込みエラー: {json_path}, {e}")
                                continue

                            # caseを抽出
                            case = json_data.get('case', '')
                            # caseがCTファイル名の場合、session_idから部位セット名を抽出
                            if case and (".nii" in case.lower() or case == "unknown"):
                                if session_id and "-" in session_id:
                                    parts = session_id.split("-")
                                    if len(parts) >= 5:
                                        case = parts[4]
                                        if DEBUG: print(f"[DEBUG LOAD] Extracted case from session_id: {case}")

                            # ケースごとに別々のParticipantResultを作成
                            key = f"{group}_{participant}_{case}"
                            if key not in participants:
                                participants[key] = ParticipantResult(
                                    participant=participant,
                                    team=f"{group}班",
                                    session_id=session_id,
                                    case=case,
                                    json_paths=[],
                                    nii_paths=[],
                                    roi_order=[],
                                    labels=[]
                                )
                                if DEBUG: print(f"[DEBUG LOAD] Created new ParticipantResult: participant={participant}, session={session_id}, case={case}")

                            agg = participants[key]

                            # 既に追加済みのJSONはスキップ
                            if json_path in agg.json_paths:
                                continue

                            # roi_orderを追加
                            for name in json_data.get('roi_order', []):
                                if name and name not in agg.roi_order:
                                    agg.roi_order.append(name)

                            # labelsを統合
                            new_labels = json_data.get('labels', [])
                            if new_labels:
                                cur = {lbl.get('name'): lbl for lbl in agg.labels if 'name' in lbl}
                                for lbl in new_labels:
                                    nm = lbl.get('name')
                                    if not nm:
                                        continue
                                    cur[nm] = lbl
                                agg.labels = list(cur.values())

                            agg.json_paths.append(json_path)
                            agg.nii_paths.append(nii_path)

            except Exception as e:
                print(f"CSV読み込みエラー: {csv_path}, {e}")

        # 班ごとにグループ化
        groups: Dict[str, List[ParticipantResult]] = {}
        for result in participants.values():
            groups.setdefault(result.team, []).append(result)
            if DEBUG: print(f"[DEBUG LOAD] Added participant {result.participant} to {result.team}, case={result.case}")

        # configから現在のGT/CTパスを取得（JSONの古いパスより優先）
        config_gt, config_ct = self._resolve_gt_ct_from_config()

        # GroupDataを作成
        for group_name, group_participants in groups.items():
            ct_path = config_ct
            gt_path = config_gt
            roi_names = []

            if group_participants:
                first_json = group_participants[0].json_paths[0] if group_participants[0].json_paths else None
                if first_json:
                    try:
                        with open(first_json, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        roi_names = data.get('roi_order', [])

                        # configからGTが得られなかった場合のみJSONのパスを使う
                        if not gt_path:
                            json_gt = data.get('gt_label_path')
                            if json_gt:
                                from app.common.paths import resolve_path
                                gt_path = resolve_path(json_gt)
                                if not os.path.exists(gt_path):
                                    gt_path = None

                        # CTがまだ無ければ推定
                        if not ct_path and gt_path:
                            ct_dir = os.path.dirname(gt_path)
                            ct_candidates = glob.glob(os.path.join(ct_dir, "*ct*.nii*"))
                            ct_path = ct_candidates[0] if ct_candidates else None
                    except Exception as e:
                        print(f"パス推定エラー: {first_json}, {e}")

            # 正解ラベルJSONを読む（*_labels.json をGTと同じディレクトリから探す）
            gt_json_path = None
            gt_labels = []
            if gt_path and os.path.exists(gt_path):
                gt_json_candidates = [
                    gt_path.replace('.nii.gz', '_labels.json'),
                    gt_path.replace('.nii', '_labels.json'),
                ]
                # 同ディレクトリの全 *_labels.json もフォールバック
                gt_dir = os.path.dirname(gt_path)
                for lj in sorted(glob.glob(os.path.join(gt_dir, "*_labels.json"))):
                    if lj not in gt_json_candidates:
                        gt_json_candidates.append(lj)

                for candidate in gt_json_candidates:
                    if os.path.exists(candidate):
                        try:
                            with open(candidate, 'r', encoding='utf-8') as f:
                                gt_json_data = json.load(f)
                                gt_labels = gt_json_data.get('labels', [])
                                gt_json_path = candidate
                                break
                        except Exception as e:
                            print(f"正解ラベルJSON読み込みエラー: {candidate}, {e}")

            group_data = GroupData(
                team=group_name,
                participants=group_participants,
                ct_path=ct_path,
                gt_path=gt_path,
                roi_names=roi_names,
                gt_json_path=gt_json_path,
                gt_labels=gt_labels
            )

            # ケースごとのGT labelsとpathsを収集
            case_gt_labels = {}
            case_gt_paths = {}
            for participant in group_participants:
                if not participant.case or not participant.json_paths:
                    continue

                # このケースのGT labelsが既に収集されていればスキップ
                if participant.case in case_gt_labels:
                    continue

                # 参加者のJSONからgt_label_pathを取得
                for json_path in participant.json_paths:
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)

                        gt_label_path_rel = data.get('gt_label_path')
                        if not gt_label_path_rel:
                            continue

                        from app.common.paths import resolve_path
                        gt_label_path = resolve_path(gt_label_path_rel)
                        if not gt_label_path or not os.path.exists(gt_label_path):
                            continue

                        # GT NIfTI pathを保存
                        case_gt_paths[participant.case] = gt_label_path

                        # GT JSONを探す
                        gt_json_candidates = [
                            gt_label_path.replace('.nii.gz', '_labels.json'),
                            gt_label_path.replace('.nii', '_labels.json'),
                        ]

                        for gt_json_candidate in gt_json_candidates:
                            if os.path.exists(gt_json_candidate):
                                try:
                                    with open(gt_json_candidate, 'r', encoding='utf-8') as f:
                                        gt_json_data = json.load(f)
                                    case_gt_labels[participant.case] = gt_json_data.get('labels', [])
                                    if DEBUG: print(f"[DEBUG LOAD] Loaded GT for case '{participant.case}': path={os.path.basename(gt_label_path)}, {len(case_gt_labels[participant.case])} labels")
                                    break
                                except Exception as e:
                                    print(f"GT JSON読み込みエラー: {gt_json_candidate}, {e}")

                        if participant.case in case_gt_labels:
                            break

                    except Exception as e:
                        print(f"ケース別GT収集エラー: {json_path}, {e}")

            group_data.case_gt_labels = case_gt_labels
            group_data.case_gt_paths = case_gt_paths
            self.groups_data[group_name] = group_data

    def _resolve_gt_ct_from_config(self):
        """contour_quest_config.json から現在の GT / CT パスを取得"""
        from app.common.settings import load_settings
        from app.common.paths import resolve_path
        try:
            settings = load_settings()
            regions = settings.get("regions", {})
            # 最初のリージョンからGT/CTを取得
            for reg in regions.values():
                gt_rel = reg.get("gt_label", "")
                ct_rel = reg.get("ct", "")
                gt_abs = resolve_path(gt_rel) if gt_rel else ""
                ct_abs = resolve_path(ct_rel) if ct_rel else ""
                if gt_abs and os.path.isfile(gt_abs):
                    ct_out = ct_abs if (ct_abs and os.path.isfile(ct_abs)) else None
                    return gt_abs, ct_out
        except Exception as e:
            print(f"config からの GT/CT 取得エラー: {e}")
        return None, None

    def _find_roi_nii_path(self, json_path: str) -> Optional[str]:
        """JSONファイルから対応するROI NIfTIファイルを探す"""
        base_name = os.path.splitext(json_path)[0]

        candidates = [
            base_name.replace('_labels', '') + '_labels.nii.gz',
            base_name + '.nii.gz',
            base_name + '.nii'
        ]

        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return None

    def _auto_select_group(self):
        """ハブから渡された班に一致するグループを自動選択"""
        if not self._fixed_group or not self.groups_data:
            # 班指定なし or データなし → 最初のグループを使う
            if self.groups_data:
                first_key = sorted(self.groups_data.keys())[0]
                self.current_group = self.groups_data[first_key]
                self.update_person_combo()
            return

        # "X班" 形式のキーで検索
        target = f"{self._fixed_group}班"
        if target in self.groups_data:
            self.current_group = self.groups_data[target]
        else:
            # フォールバック: 部分一致
            for key in self.groups_data:
                if self._fixed_group in key:
                    self.current_group = self.groups_data[key]
                    break
            else:
                # 見つからなければ最初のグループ
                if self.groups_data:
                    first_key = sorted(self.groups_data.keys())[0]
                    self.current_group = self.groups_data[first_key]

        self.update_person_combo()

    def on_person_changed(self):
        """個人選択変更時の処理"""
        if self.current_group:
            self.display_person_comparison()

    def _merge_all_cases_for_participant(self, participant_name: str):
        """指定された参加者の全ケースを統合

        Returns:
            merged_gt_volume: 統合されたGT volume
            merged_roi_volume: 統合されたROI volume
            all_gt_labels: 統合されたGTラベル情報（色付き）
            all_participant_labels: 統合された参加者ラベル情報（色付き）
            ct_volume: CT volume（全ケース共通）
            view_flips: view_flips（最初のケースのもの）
        """
        import nibabel as nib
        from nibabel.orientations import aff2axcodes

        # 同じ参加者IDの全ケースを取得
        all_cases = [p for p in self.current_group.participants if p.participant == participant_name]

        if not all_cases:
            return None, None, [], [], None, {}

        if DEBUG: print(f"[DEBUG MERGE] Found {len(all_cases)} cases for participant {participant_name}")
        for case_data in all_cases:
            if DEBUG: print(f"[DEBUG MERGE]   Case: {case_data.case}, ROIs: {case_data.roi_order}")

        # 色パレット（GTベースで順番に使用）
        COLOR_PALETTE = [
            "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
            "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe",
            "#008080", "#e6beff", "#9a6324", "#fffac8", "#800000"
        ]

        # CT volumeを読み込み（最初のケースのもの、全ケース共通と仮定）
        ct_volume, _, view_flips = self._load_ct_gt_volumes(selected_case=all_cases[0].case)

        # 統合処理
        merged_gt = None
        merged_roi = None
        all_gt_labels = []
        all_participant_labels = []
        color_offset = 0

        for case_data in all_cases:
            # ケースのGT volumeとラベル情報を読み込む
            _, gt_volume, _ = self._load_ct_gt_volumes(selected_case=case_data.case)

            case_gt_labels = getattr(self.current_group, "case_gt_labels", {}).get(case_data.case, [])

            if not case_gt_labels:
                if DEBUG: print(f"[DEBUG MERGE] No GT labels for case {case_data.case}, skipping")
                continue

            # GTラベルごとに色を割り当て
            label_mapping = {}  # 元のラベル番号 → 新しいラベル番号

            for gt_label_info in case_gt_labels:
                old_label = gt_label_info.get('label', 0)
                if old_label == 0:
                    continue

                new_label = color_offset + 1
                label_mapping[old_label] = new_label

                # 色を割り当て
                color = COLOR_PALETTE[color_offset % len(COLOR_PALETTE)]

                new_gt_label = {
                    'label': new_label,
                    'name': gt_label_info.get('name', ''),
                    'color': color,
                    'case': case_data.case
                }
                all_gt_labels.append(new_gt_label)

                if DEBUG: print(f"[DEBUG MERGE] GT: case={case_data.case}, ROI={new_gt_label['name']}, old_label={old_label}, new_label={new_label}, color={color}")

                color_offset += 1

            # GT volumeのラベル番号を変換して統合
            if gt_volume is not None and merged_gt is None:
                merged_gt = np.zeros_like(gt_volume)

            if gt_volume is not None:
                for old_label, new_label in label_mapping.items():
                    merged_gt[gt_volume == old_label] = new_label

            # ROI volumeも同様に変換
            # 参加者のROI volumeを読み込む
            roi_volume = self._load_roi_volume_for_case(case_data)

            if roi_volume is not None and merged_roi is None:
                merged_roi = np.zeros_like(roi_volume)

            if roi_volume is not None:
                # 参加者のlabelsとGTのlabelsをマッチング
                roi_label_mapping = {}
                for participant_label in case_data.labels:
                    roi_name = participant_label.get('name', '')
                    old_roi_label = participant_label.get('label', 0)

                    if old_roi_label == 0:
                        continue

                    # GTの同じROI名を探して、新しいラベル番号を取得
                    for gt_info in case_gt_labels:
                        if gt_info.get('name') == roi_name:
                            old_gt_label = gt_info.get('label', 0)
                            if old_gt_label in label_mapping:
                                new_label = label_mapping[old_gt_label]
                                roi_label_mapping[old_roi_label] = new_label

                                # 参加者ラベル情報を作成（GTと同じ色）
                                matching_gt = next((gl for gl in all_gt_labels if gl['name'] == roi_name and gl['case'] == case_data.case), None)
                                if matching_gt:
                                    new_participant_label = {
                                        'label': new_label,
                                        'name': roi_name,
                                        'color': matching_gt['color'],
                                        'case': case_data.case
                                    }
                                    all_participant_labels.append(new_participant_label)
                                    if DEBUG: print(f"[DEBUG MERGE] ROI: case={case_data.case}, ROI={roi_name}, old_label={old_roi_label}, new_label={new_label}")
                                break

                for old_roi_label, new_label in roi_label_mapping.items():
                    merged_roi[roi_volume == old_roi_label] = new_label

        if DEBUG: print(f"[DEBUG MERGE] Merge complete: {len(all_gt_labels)} GT labels, {len(all_participant_labels)} participant labels")

        return merged_gt, merged_roi, all_gt_labels, all_participant_labels, ct_volume, view_flips

    def _load_roi_volume_for_case(self, case_data):
        """ケースの参加者ROI volumeを読み込む"""
        import nibabel as nib
        from nibabel.orientations import aff2axcodes

        if not case_data.nii_paths:
            return None

        try:
            # 複数のROI NIfTIがある場合は統合
            merged = None
            for nii_path in case_data.nii_paths:
                if not nii_path or not os.path.exists(nii_path):
                    continue

                nii = nib.load(nii_path)
                vol = np.asarray(nii.dataobj).astype(np.int32)

                # 自動LR補正を適用（participant_column.pyと同じ）
                try:
                    ax = aff2axcodes(nii.affine)
                    needs_lr = (len(ax) > 0 and ax[0] == 'R')
                except Exception:
                    a = getattr(nii, "affine", None)
                    needs_lr = bool(a is not None and float(a[0, 0]) > 0)

                if needs_lr:
                    vol = vol[::-1, :, :]

                # view_flipsとの差分を適用
                view_flips_dict = {}
                # case_dataのJSONからview_flipsを取得
                if case_data.json_paths:
                    try:
                        with open(case_data.json_paths[0], 'r', encoding='utf-8') as f:
                            json_data = json.load(f)
                        view_flips_dict = json_data.get('view_flips', {})
                    except Exception:
                        pass

                saved_lr = view_flips_dict.get("left_right", False)
                if saved_lr != needs_lr:
                    vol = vol[::-1, :, :]

                if view_flips_dict.get("anterior_posterior", False):
                    vol = vol[:, ::-1, :]
                if view_flips_dict.get("superior_inferior", False):
                    vol = vol[:, :, ::-1]

                if merged is None:
                    merged = vol
                else:
                    merged = np.maximum(merged, vol)

            return merged
        except Exception as e:
            if DEBUG: print(f"[DEBUG MERGE] ROI volume load error: {e}")
            return None

    def _get_filtered_gt_labels_for_case(self, selected_case: str):
        """選択されたケースに応じてGTラベルをフィルタリング"""
        if not selected_case or selected_case.startswith("--"):
            return getattr(self.current_group, "gt_labels", [])

        # ケース別のGT labelsが存在すればそれを使用
        case_gt_labels = getattr(self.current_group, "case_gt_labels", {})
        if selected_case in case_gt_labels:
            labels = case_gt_labels[selected_case]
            if DEBUG: print(f"[DEBUG CASE] Using case-specific GT labels for '{selected_case}': {len(labels)} labels")
            return labels

        # ケース別GT labelsが無い場合は、従来のフィルタリング方式を使用
        if DEBUG: print(f"[DEBUG CASE] No case-specific GT labels found for '{selected_case}', using roi_order filtering")

        # 選択されたケースの参加者からroi_orderを取得
        case_roi_order = []
        for participant in self.current_group.participants:
            if participant.case == selected_case:
                for roi_name in participant.roi_order:
                    if roi_name and roi_name not in case_roi_order:
                        case_roi_order.append(roi_name)

        if DEBUG: print(f"[DEBUG CASE] Selected case: {selected_case}, roi_order: {case_roi_order}")

        # roi_orderに含まれるROIのみをフィルタ
        all_gt_labels = getattr(self.current_group, "gt_labels", [])
        if not case_roi_order:
            if DEBUG: print(f"[DEBUG CASE] No roi_order found for case, returning all GT labels")
            return all_gt_labels

        filtered_labels = []
        for label in all_gt_labels:
            label_name = label.get('name', '')
            if label_name in case_roi_order:
                filtered_labels.append(label)

        if DEBUG: print(f"[DEBUG CASE] Filtered {len(filtered_labels)} labels from {len(all_gt_labels)} total GT labels")
        return filtered_labels

    def update_person_combo(self):
        """個人選択コンボボックスを更新（参加者IDのみ表示、重複排除）"""
        self.person_combo.blockSignals(True)
        try:
            self.person_combo.clear()
            current_group = self.current_group

            if not current_group:
                self.person_combo.addItem("-- グループを選択してください --")
                return

            if not hasattr(current_group, 'participants'):
                self.person_combo.addItem("-- グループを選択してください --")
                return

            try:
                participants = current_group.participants
                if not participants:
                    self.person_combo.addItem("-- 参加者がいません --")
                    return
            except AttributeError:
                self.person_combo.addItem("-- グループを選択してください --")
                return

            # 参加者IDのみを抽出（重複排除）
            participant_ids = set()
            for p in participants:
                participant_ids.add(p.participant)

            if not participant_ids:
                self.person_combo.addItem("-- 参加者がいません --")
                return

            self.person_combo.addItem("-- 個人を選択してください --")
            for participant_id in sorted(participant_ids):
                self.person_combo.addItem(participant_id)
        finally:
            self.person_combo.blockSignals(False)

    def clear_display(self):
        """表示をクリア"""
        for column in getattr(self, "participant_columns", []):
            try:
                column.setParent(None)
                column.deleteLater()
            except Exception:
                pass
        self.participant_columns = []

        old_widget = None
        try:
            old_widget = self.scroll_area.takeWidget()
        except Exception:
            old_widget = getattr(self, "content_widget", None)
            if old_widget is not None:
                try:
                    old_widget.setParent(None)
                except Exception:
                    pass

        self.content_widget = QWidget()
        self.content_layout = None
        self.scroll_area.setWidget(self.content_widget)

        if old_widget is not None and old_widget is not self.content_widget:
            try:
                old_widget.deleteLater()
            except Exception:
                pass

        if hasattr(self, "roi_list"):
            self.roi_list.clear()
        self.roi_labels_map = {}

        self.current_slice = 0
        self.max_slices = 0
        self.slice_slider.blockSignals(True)
        self.slice_spinbox.blockSignals(True)
        self.slice_slider.setRange(0, 0)
        self.slice_slider.setValue(0)
        self.slice_spinbox.setRange(0, 0)
        self.slice_spinbox.setValue(0)
        self.slice_slider.blockSignals(False)
        self.slice_spinbox.blockSignals(False)

    def _load_ct_gt_volumes(self, selected_case: str = None):
        """CT/GT ボリュームを読み込む（共通処理）
        GTの _labels.json に保存された view_flips を読み取り、
        CT・GT両方に同じ反転を適用してコンツーリングアプリと同じ向きで表示する。

        Args:
            selected_case: 選択されたケース名。指定された場合、ケース別のGT pathを使用
        """
        ct_volume = None
        gt_volume = None
        flip_lr_flag = False

        try:
            import nibabel as nib
            from nibabel.orientations import aff2axcodes
        except Exception:
            nib = None

        if nib is None:
            return ct_volume, gt_volume, flip_lr_flag

        # CT
        ct_needs_lr = False
        if getattr(self.current_group, "ct_path", None):
            ct_path = self.current_group.ct_path
            if not os.path.isabs(ct_path):
                app_dir = os.path.dirname(os.path.abspath(__file__))
                root_dir = os.path.abspath(os.path.join(app_dir, os.pardir, os.pardir))
                ct_path = os.path.join(root_dir, ct_path.replace("/", os.sep).replace("\\", os.sep))
            if os.path.exists(ct_path):
                ct_nii = nib.load(ct_path)
                ct_volume = np.asarray(ct_nii.dataobj).astype(np.float32)
                if DEBUG: print(f"[DEBUG REVIEW] CT loaded, shape: {ct_volume.shape}")
                # コンツーリングアプリと同じ自動LR補正
                try:
                    ax = aff2axcodes(ct_nii.affine)
                    ct_needs_lr = (len(ax) > 0 and ax[0] == 'R')
                except Exception:
                    a = getattr(ct_nii, "affine", None)
                    ct_needs_lr = bool(a is not None and float(a[0, 0]) > 0)
                if DEBUG: print(f"[DEBUG REVIEW] CT affine check: ct_needs_lr={ct_needs_lr}")
                if ct_needs_lr:
                    ct_volume = ct_volume[::-1, :, :]
                    if DEBUG: print(f"[DEBUG REVIEW] CT: Applied automatic LR correction")

        # GT - ケース別のGT pathがあればそれを使用
        gt_needs_lr = False
        gt_path = None

        # ケース別のGT pathを優先的に使用
        if selected_case:
            case_gt_paths = getattr(self.current_group, "case_gt_paths", {})
            if selected_case in case_gt_paths:
                gt_path = case_gt_paths[selected_case]
                if DEBUG: print(f"[DEBUG REVIEW] Using case-specific GT path for '{selected_case}': {os.path.basename(gt_path)}")

        # ケース別のGT pathが無い場合はデフォルトのGT pathを使用
        if not gt_path and getattr(self.current_group, "gt_path", None):
            gt_path = self.current_group.gt_path
            if DEBUG: print(f"[DEBUG REVIEW] Using default GT path: {os.path.basename(gt_path)}")

        if gt_path:
            if not os.path.isabs(gt_path):
                app_dir = os.path.dirname(os.path.abspath(__file__))
                root_dir = os.path.abspath(os.path.join(app_dir, os.pardir, os.pardir))
                gt_path = os.path.join(root_dir, gt_path.replace("/", os.sep).replace("\\", os.sep))
            if os.path.exists(gt_path):
                gt_nii = nib.load(gt_path)
                gt_volume = np.asarray(gt_nii.dataobj).astype(np.int32)
                if DEBUG: print(f"[DEBUG REVIEW] GT loaded, shape: {gt_volume.shape}, unique labels: {np.unique(gt_volume)[:10]}")
                # GT の自動LR補正チェック
                try:
                    ax = aff2axcodes(gt_nii.affine)
                    gt_needs_lr = (len(ax) > 0 and ax[0] == 'R')
                except Exception:
                    a = getattr(gt_nii, "affine", None)
                    gt_needs_lr = bool(a is not None and float(a[0, 0]) > 0)
                if DEBUG: print(f"[DEBUG REVIEW] GT affine check: gt_needs_lr={gt_needs_lr}")
                if gt_needs_lr:
                    gt_volume = gt_volume[::-1, :, :]
                    if DEBUG: print(f"[DEBUG REVIEW] GT: Applied automatic LR correction")

        # GTの _labels.json から view_flips を読み取って CT/GT に適用
        view_flips = self._load_gt_view_flips()
        # 現在の flip_lr 状態（自動LR補正後）を保存時の状態に合わせる
        saved_lr = view_flips.get("left_right", False)
        saved_ap = view_flips.get("anterior_posterior", False)
        saved_si = view_flips.get("superior_inferior", False)

        if DEBUG: print(f"[DEBUG REVIEW] view_flips from GT JSON: {view_flips}")
        if DEBUG: print(f"[DEBUG REVIEW] ct_needs_lr={ct_needs_lr}, gt_needs_lr={gt_needs_lr}")
        if DEBUG: print(f"[DEBUG REVIEW] saved_lr={saved_lr}, saved_ap={saved_ap}, saved_si={saved_si}")

        # 自動LR補正後の状態 (ct_needs_lr) と保存時の状態が異なれば追加反転
        if saved_lr != ct_needs_lr:
            if DEBUG: print(f"[DEBUG REVIEW] Applying LR adjustment: saved_lr({saved_lr}) != ct_needs_lr({ct_needs_lr})")
            if ct_volume is not None:
                ct_volume = ct_volume[::-1, :, :]
                if DEBUG: print(f"[DEBUG REVIEW] CT: Applied LR adjustment")
            if gt_volume is not None:
                gt_volume = gt_volume[::-1, :, :]
                if DEBUG: print(f"[DEBUG REVIEW] GT: Applied LR adjustment")
        if saved_ap:
            if DEBUG: print(f"[DEBUG REVIEW] Applying AP flip (saved_ap={saved_ap})")
            if ct_volume is not None:
                ct_volume = ct_volume[:, ::-1, :]
                if DEBUG: print(f"[DEBUG REVIEW] CT: Applied AP flip")
            if gt_volume is not None:
                gt_volume = gt_volume[:, ::-1, :]
                if DEBUG: print(f"[DEBUG REVIEW] GT: Applied AP flip")
        if saved_si:
            if DEBUG: print(f"[DEBUG REVIEW] Applying SI flip (saved_si={saved_si})")
            if ct_volume is not None:
                ct_volume = ct_volume[:, :, ::-1]
            if gt_volume is not None:
                gt_volume = gt_volume[:, :, ::-1]

        # 最終的な反転状態を返す（参加者ROI NIfTIにも同じ反転を適用するため）
        final_flips = {
            "left_right": saved_lr,
            "anterior_posterior": saved_ap,
            "superior_inferior": saved_si,
        }
        return ct_volume, gt_volume, final_flips

    def _load_gt_view_flips(self):
        """GT の _labels.json から view_flips を読み取る"""
        gt_json_path = getattr(self.current_group, "gt_json_path", None)
        if not gt_json_path or not os.path.exists(gt_json_path):
            return {}
        try:
            with open(gt_json_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            return meta.get("view_flips", {})
        except Exception:
            return {}

    def _update_slice_ui(self, ct_volume):
        """スライスUIの範囲設定"""
        if ct_volume is not None and getattr(ct_volume, "ndim", 0) == 3 and ct_volume.shape[2] > 0:
            self.max_slices = int(ct_volume.shape[2])
            self.current_slice = min(self.current_slice, max(0, self.max_slices - 1))
            self.slice_slider.blockSignals(True)
            self.slice_spinbox.blockSignals(True)
            self.slice_slider.setRange(0, self.max_slices - 1)
            self.slice_slider.setValue(self.current_slice)
            self.slice_spinbox.setRange(1, self.max_slices)
            self.slice_spinbox.setValue(self.current_slice + 1)
            self.slice_slider.blockSignals(False)
            self.slice_spinbox.blockSignals(False)
        else:
            self.max_slices = 0
            self.slice_slider.blockSignals(True)
            self.slice_spinbox.blockSignals(True)
            self.slice_slider.setRange(0, 0)
            self.slice_slider.setValue(0)
            self.slice_spinbox.setRange(0, 0)
            self.slice_spinbox.setValue(0)
            self.slice_slider.blockSignals(False)
            self.slice_spinbox.blockSignals(False)

    def _replace_content_widget(self):
        """ScrollArea の中身を安全に入れ替え"""
        old_widget = None
        try:
            old_widget = self.scroll_area.takeWidget()
        except Exception:
            old_widget = getattr(self, "content_widget", None)
            if old_widget is not None:
                try:
                    old_widget.setParent(None)
                except Exception:
                    pass

        self.content_widget = QWidget()
        self.content_layout = None
        self.scroll_area.setWidget(self.content_widget)

        if old_widget is not None and old_widget is not self.content_widget:
            try:
                old_widget.deleteLater()
            except Exception:
                pass

        for column in getattr(self, "participant_columns", []):
            try:
                column.setParent(None)
                column.deleteLater()
            except Exception:
                pass
        self.participant_columns = []

    def display_group(self):
        """現在選択中の班を表示（個人比較モードに委譲）"""
        if not self.current_group:
            return
        self.display_person_comparison()

    def update_roi_mapping(self, gt_volume):
        """ROI名とラベル番号のマッピングを更新"""
        self.roi_labels_map = {}
        self.roi_list.clear()

        if not self.current_group or not self.current_group.gt_labels:
            self.on_roi_selection_changed()
            return

        # 選択されたケースに応じてGTラベルをフィルタリング
        selected_case = self.case_combo.currentText()
        filtered_gt_labels = self._get_filtered_gt_labels_for_case(selected_case)

        for gt_label in filtered_gt_labels:
            roi_name = gt_label.get('name')
            label_num = gt_label.get('label')
            if roi_name and label_num:
                self.roi_labels_map[roi_name] = label_num
                item = QListWidgetItem(roi_name)
                self.roi_list.addItem(item)

        existing_labels = set()
        if gt_volume is not None:
            try:
                unique_labels = np.unique(gt_volume)
                existing_labels = set(int(x) for x in unique_labels if int(x) > 0)
            except Exception:
                existing_labels = set()

        for i in range(self.roi_list.count()):
            item = self.roi_list.item(i)
            roi_name = item.text()
            label_num = int(self.roi_labels_map.get(roi_name, 0))
            if label_num <= 0 or (existing_labels and label_num not in existing_labels):
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                item.setBackground(QColor(100, 100, 100))

        blocked = self.roi_list.blockSignals(True)
        for i in range(self.roi_list.count()):
            item = self.roi_list.item(i)
            enabled = bool(item.flags() & Qt.ItemIsEnabled)
            item.setSelected(enabled)
        self.roi_list.blockSignals(blocked)

        self.on_roi_selection_changed()

    def on_wheel_slice_changed(self, new_slice: int):
        """マウスホイールでスライス変更された時の同期処理"""
        self.current_slice = new_slice

        self.slice_slider.blockSignals(True)
        self.slice_spinbox.blockSignals(True)
        self.slice_slider.setValue(self.current_slice)
        self.slice_spinbox.setValue(self.current_slice + 1)
        self.slice_slider.blockSignals(False)
        self.slice_spinbox.blockSignals(False)

        for column in self.participant_columns:
            if isinstance(column, ImageDisplayWidget):
                if column.current_slice != new_slice:
                    column.current_slice = new_slice
                    column.update_display()
            elif hasattr(column, 'image_widget'):
                if column.image_widget.current_slice != new_slice:
                    column.image_widget.current_slice = new_slice
                    column.image_widget.update_display()

    def on_slice_changed(self, value: int):
        self.current_slice = value
        self.slice_spinbox.blockSignals(True)
        self.slice_spinbox.setValue(value + 1)
        self.slice_spinbox.blockSignals(False)
        self.update_all_slices()

    def on_slice_changed_spinbox(self, value: int):
        slice_idx = value - 1
        self.current_slice = slice_idx
        self.slice_slider.blockSignals(True)
        self.slice_slider.setValue(slice_idx)
        self.slice_slider.blockSignals(False)
        self.update_all_slices()

    def update_all_slices(self):
        for column in self.participant_columns:
            column.set_slice(self.current_slice)

    def sync_all_zoom_pan(self, zoom_factor: float, pan_offset: List[float], source_column):
        for column in self.participant_columns:
            if column != source_column:
                column.sync_zoom_pan_from_other(zoom_factor, pan_offset)

    def on_visibility_changed(self):
        show_ct = self.show_ct_cb.isChecked()
        show_gt = self.show_gt_cb.isChecked()
        show_roi = True  # show_roi_cb was removed; default True

        for column in self.participant_columns:
            column.set_visibility(show_ct, show_gt, show_roi)

    def _init_ww_wl_presets(self):
        """WW/WL プリセット定義"""
        presets = {
            "縦隔": (50, 350),
            "脳": (40, 80),
            "肺": (-600, 1500),
            "骨": (400, 1500),
        }

        try:
            if self.config_manager:
                ds = self.config_manager.get_display_settings() or {}
                ctw = ds.get("ct_windows") or {}
                for k in list(presets.keys()):
                    if k in ctw and isinstance(ctw[k], (list, tuple)) and len(ctw[k]) == 2:
                        wl, ww = ctw[k]
                        presets[k] = (float(wl), float(ww))
        except Exception:
            pass

        self.ww_wl_presets = presets
        self.ww_wl_shortcuts = {
            "1": "縦隔",
            "2": "脳",
            "3": "肺",
            "4": "骨",
        }

    def apply_ww_wl_preset(self, name: str):
        if not hasattr(self, "ww_wl_presets"):
            self._init_ww_wl_presets()

        if name not in self.ww_wl_presets:
            return

        wl, ww = self.ww_wl_presets[name]
        for col in self.participant_columns:
            if hasattr(col, "image_widget") and hasattr(col.image_widget, "set_window"):
                col.image_widget.set_window(wl, ww)

    def display_person_comparison(self):
        """個人表示：全ケースを統合してGT点線＋回答実線を表示"""
        person_name = self.person_combo.currentText()

        if not person_name or person_name.startswith("--"):
            self.clear_display()
            return

        if DEBUG: print(f"[DEBUG DISPLAY] Displaying all cases for participant {person_name}")

        self._replace_content_widget()

        # 全ケースを統合
        merged_gt, merged_roi, all_gt_labels, all_participant_labels, ct_volume, view_flips = self._merge_all_cases_for_participant(person_name)

        if merged_gt is None and ct_volume is None:
            if DEBUG: print(f"[DEBUG DISPLAY] No data found for participant {person_name}")
            self.clear_display()
            return

        self._current_view_flips = view_flips
        self._update_slice_ui(ct_volume)

        # ROI マッピング（統合されたGTラベルを使用）
        self.roi_labels_map = {}
        self.roi_list.clear()

        for gt_label in all_gt_labels:
            roi_name = gt_label.get('name')
            label_num = gt_label.get('label')
            case_name = gt_label.get('case', '')
            if roi_name and label_num:
                # ケース名を含めた表示名
                display_name = f"{roi_name} ({case_name})" if case_name else roi_name
                self.roi_labels_map[display_name] = label_num
                item = QListWidgetItem(display_name)
                self.roi_list.addItem(item)

        # 全ROIを選択状態にする
        self.roi_list.blockSignals(True)
        for i in range(self.roi_list.count()):
            item = self.roi_list.item(i)
            item.setSelected(True)
        self.roi_list.blockSignals(False)

        # レイアウト
        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(6)
        self.content_layout.setContentsMargins(6, 6, 6, 6)
        self.content_widget.setLayout(self.content_layout)

        # ダミーのParticipantResultを作成（統合データ用）
        from app.common.data_models import ParticipantResult
        merged_participant = ParticipantResult(
            participant=person_name,
            team=self.current_group.team,
            session_id="merged",
            case="all_cases",
            json_paths=[],
            nii_paths=[],
            roi_order=[],
            labels=all_participant_labels
        )

        # 統合されたGT/ROIを表示
        person_column = ParticipantColumnWidget(merged_participant, show_name=True, view_flips=view_flips)
        person_column.image_widget._flip_lr = False  # CT/GTは既に反転済み
        person_column.image_widget._is_person_mode = True

        if ct_volume is not None:
            person_column.set_ct_volume(ct_volume)

        # 統合されたGT volumeとラベルを設定
        if merged_gt is not None:
            person_column.image_widget.set_gt_volume(merged_gt)
            person_column.set_gt_labels(all_gt_labels)

        # 統合されたROI volumeとラベルを設定
        if merged_roi is not None:
            person_column.image_widget.set_roi_volume(merged_roi)
            person_column.set_participant_labels(all_participant_labels)

        person_column.set_slice(self.current_slice)
        person_column.image_widget.slice_change_callback = self.on_wheel_slice_changed
        self.content_layout.addWidget(person_column)

        self.participant_columns = [person_column]
        self.content_layout.setStretch(0, 1)

        self.on_roi_selection_changed()

    def keyPressEvent(self, event):
        """数字キー 1/2/3/4 で WW/WL プリセットを切り替える"""
        if not hasattr(self, "ww_wl_presets"):
            self._init_ww_wl_presets()

        key_to_digit = {
            Qt.Key_1: "1",
            Qt.Key_2: "2",
            Qt.Key_3: "3",
            Qt.Key_4: "4",
        }

        digit = None
        k = event.key()
        if (event.modifiers() & Qt.KeypadModifier) and k in (Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4):
            digit = str(k - Qt.Key_0)
        else:
            digit = key_to_digit.get(k)

        if digit and digit in self.ww_wl_shortcuts:
            name = self.ww_wl_shortcuts[digit]
            self.apply_ww_wl_preset(name)
            event.accept()
            return

        super().keyPressEvent(event)
