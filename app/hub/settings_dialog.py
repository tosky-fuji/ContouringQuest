# -*- coding: utf-8 -*-
"""ハブ設定ダイアログ（パスワード: kochi）"""

import os
from typing import Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QSpinBox, QFormLayout, QDialogButtonBox,
    QFileDialog, QMessageBox, QInputDialog,
)
from PySide6.QtCore import Signal

from app.common.paths import resolve_path, make_relative_path
from app.common.settings import load_settings, save_settings, fiscal_year_default
from app.common.styles import BASE_STYLESHEET, btn_style

MAX_REGIONS = 4


class SettingsDialog(QDialog):
    # GTエディタ起動要求（hub が受け取ってウィンドウ遷移を管理する）
    gt_editor_requested = Signal(object)  # GameConfig

    def __init__(self, parent=None, settings: Dict[str, Any] | None = None):
        super().__init__(parent)
        self.setWindowTitle("設定（部位セットの保存）")
        self.setMinimumWidth(620)
        self.setStyleSheet(BASE_STYLESHEET)
        self._settings = settings or {
            "regions": {},
            "group_format": "AZ",
            "history": {},
            "year": fiscal_year_default(),
            "group_value": "A",
        }

        v = QVBoxLayout(self)

        head = QLabel("部位ごとのセットを管理します。\n"
                       "「年度」と「班の型式」もここで設定します。")
        head.setStyleSheet("color:#e9edff;")
        v.addWidget(head)

        form = QFormLayout()

        # 班の型式（A-Z or 1-99）
        self.groupfmt_combo = QComboBox()
        self.groupfmt_combo.addItems(["A-Z", "1-99"])
        cur_fmt = self._settings.get("group_format", "AZ")
        self.groupfmt_combo.setCurrentIndex(0 if cur_fmt == "AZ" else 1)
        form.addRow("班の型式", self.groupfmt_combo)

        # 年度
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2000, 2100)
        self.year_spin.setValue(int(self._settings.get("year", fiscal_year_default())))
        form.addRow("年度", self.year_spin)

        # 部位セット選択 + 追加/名前変更/削除ボタン
        region_row = QHBoxLayout()
        self.region_combo = QComboBox()
        region_row.addWidget(self.region_combo, stretch=1)

        self._add_btn = QPushButton("＋追加")
        self._add_btn.setStyleSheet(btn_style(secondary=True))
        self._add_btn.clicked.connect(self._add_region)
        region_row.addWidget(self._add_btn)

        self._rename_btn = QPushButton("名前変更")
        self._rename_btn.setStyleSheet(btn_style(outline=True))
        self._rename_btn.clicked.connect(self._rename_region)
        region_row.addWidget(self._rename_btn)

        self._del_btn = QPushButton("削除")
        self._del_btn.setStyleSheet(btn_style(outline=True))
        self._del_btn.clicked.connect(self._delete_region)
        region_row.addWidget(self._del_btn)

        form.addRow("部位セット", region_row)

        self.roi_edit = QLineEdit()
        form.addRow("ROI（カンマ区切り）", self.roi_edit)

        self.time_spin = QSpinBox()
        self.time_spin.setRange(0, 180)
        self.time_spin.setSuffix(" 分")
        form.addRow("制限時間", self.time_spin)

        # CT
        self.ct_edit = QLineEdit()
        ct_btn = QPushButton("参照…")
        ct_btn.setStyleSheet(btn_style(outline=True))
        ct_btn.clicked.connect(self._choose_ct)
        ct_row = QHBoxLayout()
        ct_row.addWidget(self.ct_edit)
        ct_row.addWidget(ct_btn)
        form.addRow("CT NIfTI", ct_row)

        # 正解ラベル NIfTI
        self.gt_edit = QLineEdit()
        gt_btn = QPushButton("参照…")
        gt_btn.setStyleSheet(btn_style(outline=True))
        gt_btn.clicked.connect(self._choose_gt)
        gt_row = QHBoxLayout()
        gt_row.addWidget(self.gt_edit)
        gt_row.addWidget(gt_btn)
        # 正解データ作成/編集ボタン
        self.gt_create_btn = QPushButton("作成/編集")
        self.gt_create_btn.setStyleSheet(btn_style(secondary=True))
        self.gt_create_btn.clicked.connect(self._open_gt_editor)
        gt_row.addWidget(self.gt_create_btn)
        form.addRow("正解ラベル NIfTI", gt_row)

        # 保存先
        self.outdir_edit = QLineEdit()
        out_btn = QPushButton("参照…")
        out_btn.setStyleSheet(btn_style(outline=True))
        out_btn.clicked.connect(self._choose_outdir)
        out_row = QHBoxLayout()
        out_row.addWidget(self.outdir_edit)
        out_row.addWidget(out_btn)
        form.addRow("保存先(Play)", out_row)

        v.addLayout(form)

        # コンボにリージョンを投入
        self._populate_region_combo()

        # ボタン
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    # ---- リージョン管理 ----

    def _populate_region_combo(self):
        """コンボボックスにリージョンを投入し、最初の項目を選択"""
        self.region_combo.blockSignals(True)
        self.region_combo.clear()
        region_names = list((self._settings.get("regions") or {}).keys())
        if region_names:
            self.region_combo.addItems(region_names)
        self.region_combo.blockSignals(False)

        # シグナル接続（一度だけ）
        try:
            self.region_combo.currentTextChanged.disconnect(self._load_region_values)
        except RuntimeError:
            pass
        self.region_combo.currentTextChanged.connect(self._load_region_values)

        if region_names:
            self._load_region_values(self.region_combo.currentText())
        else:
            self._clear_fields()

        self._update_button_states()

    def _update_button_states(self):
        count = self.region_combo.count()
        self._add_btn.setEnabled(count < MAX_REGIONS)
        self._rename_btn.setEnabled(count > 0)
        self._del_btn.setEnabled(count > 0)

    def _add_region(self):
        if self.region_combo.count() >= MAX_REGIONS:
            QMessageBox.warning(self, "上限", f"部位セットは最大{MAX_REGIONS}個です。")
            return

        name, ok = QInputDialog.getText(self, "新しい部位セット", "名前を入力:")
        if not ok or not name.strip():
            return
        name = name.strip()

        existing = [self.region_combo.itemText(i) for i in range(self.region_combo.count())]
        if name in existing:
            QMessageBox.warning(self, "重複", f"「{name}」は既に存在します。")
            return

        # 空のリージョンを設定に追加
        self._settings.setdefault("regions", {})[name] = {
            "rois": "", "time_min": 10, "ct": "", "gt_label": "", "outdir": "records",
        }
        self.region_combo.addItem(name)
        self.region_combo.setCurrentText(name)
        self._update_button_states()

    def _rename_region(self):
        old_name = self.region_combo.currentText()
        if not old_name:
            return

        new_name, ok = QInputDialog.getText(self, "名前変更", "新しい名前:", text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()

        existing = [self.region_combo.itemText(i) for i in range(self.region_combo.count())]
        if new_name in existing:
            QMessageBox.warning(self, "重複", f"「{new_name}」は既に存在します。")
            return

        # 設定内のキーを差し替え
        regions = self._settings.get("regions", {})
        if old_name in regions:
            regions[new_name] = regions.pop(old_name)

        idx = self.region_combo.currentIndex()
        self.region_combo.setItemText(idx, new_name)

    def _delete_region(self):
        name = self.region_combo.currentText()
        if not name:
            return

        ans = QMessageBox.question(
            self, "削除確認", f"「{name}」を削除しますか？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return

        regions = self._settings.get("regions", {})
        regions.pop(name, None)
        self.region_combo.removeItem(self.region_combo.currentIndex())
        self._update_button_states()

        if self.region_combo.count() == 0:
            self._clear_fields()

    def _clear_fields(self):
        self.roi_edit.setText("")
        self.time_spin.setValue(10)
        self.ct_edit.setText("")
        self.gt_edit.setText("")
        self.outdir_edit.setText("")

    # ---- ファイル選択 ----

    def _choose_ct(self):
        # デフォルトディレクトリを root/nifti に設定
        default_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "nifti")
        if not os.path.exists(default_dir):
            default_dir = ""
        path, _ = QFileDialog.getOpenFileName(self, "CT NIfTI を選択", default_dir, "NIfTI (*.nii *.nii.gz)")
        if path:
            self.ct_edit.setText(path)

    def _choose_gt(self):
        # デフォルトディレクトリを root/nifti に設定
        default_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "nifti")
        if not os.path.exists(default_dir):
            default_dir = ""
        path, _ = QFileDialog.getOpenFileName(self, "正解ラベル NIfTI を選択", default_dir, "NIfTI (*.nii *.nii.gz)")
        if path:
            self.gt_edit.setText(path)

    def _choose_outdir(self):
        path = QFileDialog.getExistingDirectory(self, "保存先フォルダを選択")
        if path:
            self.outdir_edit.setText(path)

    # ---- GT エディタ ----

    def _open_gt_editor(self):
        """正解データ作成/編集 — config を作ってハブに委譲する"""
        from app.common.data_models import GameConfig

        ct_path = self.ct_edit.text().strip()
        if not ct_path:
            QMessageBox.warning(self, "エラー", "CT NIfTI のパスを先に設定してください。")
            return

        ct_resolved = resolve_path(ct_path)
        if not os.path.isfile(ct_resolved):
            QMessageBox.warning(self, "エラー", f"CT ファイルが見つかりません:\n{ct_resolved}")
            return

        roi_text = self.roi_edit.text().strip()
        roi_names = [r.strip() for r in roi_text.replace("、", ",").split(",") if r.strip()] if roi_text else None

        gt_path = self.gt_edit.text().strip()
        gt_resolved = resolve_path(gt_path) if gt_path else None
        if gt_resolved and not os.path.isfile(gt_resolved):
            gt_resolved = None

        config = GameConfig(
            enabled=True,
            ct_path=ct_resolved,
            roi_names=roi_names,
            time_limit_sec=0,
            gt_label_path=gt_resolved,
            gt_edit_mode=True,
        )

        # ハブにGTエディタ起動を委譲（ハブが全ウィンドウ遷移を管理する）
        self.gt_editor_requested.emit(config)
        self.hide()

    # ---- ロード/セーブ ----

    def _load_region_values(self, region: str):
        reg = (self._settings or {}).get("regions", {}).get(region, {})
        if reg:
            self.roi_edit.setText(reg.get("rois", ""))
            self.time_spin.setValue(int(reg.get("time_min", 10)))
            self.ct_edit.setText(reg.get("ct", ""))
            self.gt_edit.setText(reg.get("gt_label", ""))
            self.outdir_edit.setText(reg.get("outdir", ""))
        else:
            self._clear_fields()

    def _save(self):
        """現在表示中のリージョンを保存（リージョンが無い場合は作成を促す）"""
        region = self.region_combo.currentText().strip()
        if not region:
            QMessageBox.warning(self, "エラー", "部位セットを追加してから保存してください。")
            return

        data = load_settings()

        data["group_format"] = "AZ" if self.groupfmt_combo.currentIndex() == 0 else "NN"
        data["year"] = int(self.year_spin.value())
        data["group_value"] = data.get("group_value", "A" if data["group_format"] == "AZ" else "1")

        ct_raw = self.ct_edit.text().strip()
        gt_raw = self.gt_edit.text().strip()
        od_raw = self.outdir_edit.text().strip()

        # 全リージョンを保存（削除されたものは除外）
        existing_regions = {}
        for i in range(self.region_combo.count()):
            name = self.region_combo.itemText(i)
            if name == region:
                # 現在編集中のリージョンはフォームから取得
                existing_regions[name] = {
                    "rois": self.roi_edit.text().replace("、", ","),
                    "time_min": int(self.time_spin.value()),
                    "ct": make_relative_path(resolve_path(ct_raw)) if ct_raw else "",
                    "gt_label": make_relative_path(resolve_path(gt_raw)) if gt_raw else "",
                    "outdir": make_relative_path(resolve_path(od_raw)) if od_raw else "records",
                }
            else:
                # 他のリージョンは設定から取得
                existing_regions[name] = self._settings.get("regions", {}).get(name, {
                    "rois": "", "time_min": 10, "ct": "", "gt_label": "", "outdir": "records",
                })

        data["regions"] = existing_regions

        save_settings(data)
        self._settings = data
        QMessageBox.information(self, "保存", f"設定を保存しました。")
        self.accept()
