# -*- coding: utf-8 -*-
"""スコアリングメインウィンドウ（インプロセス化対応）"""

import os
import re
import json
import csv as _csv
import datetime as _dt

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QProgressBar, QMessageBox, QApplication
)
from PySide6.QtCore import QTimer

from app.common.paths import make_relative_path
from app.common.csv_utils import year_csv_path
from app.common.config_manager import get_config_manager
from app.common.data_models import GameResult
from app.common.styles import BASE_STYLESHEET
from app.common.settings import load_settings, fiscal_year_default

from .calculator import ScoreCalculatorThread
from .display import ScoreDisplayWidget


class ScoringMainWindow(QMainWindow):
    """スコアリングアプリのメインウィンドウ（インプロセス化対応）"""

    def __init__(self, result_json_path: str):
        super().__init__()
        self.result_json_path = result_json_path
        self.config_manager = get_config_manager()

        self.setWindowTitle("Contour Quest - スコア表示")
        self.setGeometry(200, 200, 800, 600)
        self.setStyleSheet(BASE_STYLESHEET)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("スコアを計算中... %p%")
        self.layout.addWidget(self.progress_bar)

        self.score_display = ScoreDisplayWidget()
        self.score_display.hide()
        self.layout.addWidget(self.score_display)

        self.calculation_thread = ScoreCalculatorThread(result_json_path)
        self.calculation_thread.progress_updated.connect(self.progress_bar.setValue)
        self.calculation_thread.calculation_finished.connect(self.on_calculation_finished)
        self.calculation_thread.error_occurred.connect(self.on_error)

        QTimer.singleShot(100, self.calculation_thread.start)

    def on_calculation_finished(self, game_result: GameResult):
        self.progress_bar.hide()
        self.score_display.reveal_with_animation(game_result)
        self.score_display.show()
        self.setWindowTitle(f"Contour Quest - スコア表示 ({game_result.participant})")
        try:
            self._write_score_to_csv(game_result)
        except Exception as e:
            print(f"CSV書き込みエラー: {e}")

    def on_error(self, error_message: str):
        QMessageBox.critical(self, "エラー", f"スコア計算中にエラーが発生しました:\n{error_message}")
        self.close()

    def _get_settings_year(self) -> str:
        """設定ファイルの年度を取得（フォールバック: fiscal_year_default）"""
        try:
            st = load_settings()
            return str(int(st.get("year", fiscal_year_default())))
        except Exception:
            return str(fiscal_year_default())

    def _write_score_to_csv(self, game_result: GameResult):
        year = self._get_settings_year()

        csv_path = year_csv_path(year)

        gt_path = ""
        pred_path = ""
        result_dir = ""
        try:
            with open(self.result_json_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            gt_path = meta.get("gt_label_path", "") or ""
            json_dir = os.path.dirname(self.result_json_path)
            json_base = os.path.splitext(os.path.basename(self.result_json_path))[0]
            cand1 = os.path.join(json_dir, json_base.replace("_labels", "") + "_labels.nii.gz")
            cand2 = os.path.join(json_dir, json_base + ".nii.gz")
            pred_path = cand1 if os.path.exists(cand1) else cand2
            result_dir = json_dir
        except Exception:
            pass

        def fmt_pt(x):
            return f"{max(0.0, min(1.0, float(x))) * 100.0:.1f}"

        base_fields = [
            "timestamp", "year", "group", "team", "participant",
            "session", "region", "mode", "rois", "ct", "gt_label", "result_dir"
        ]

        def colsafe(name):
            return re.sub(r"[,\t;/\\\s]+", "_", str(name)).strip("_")

        updates = {
            "score_timestamp": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "overall_score": f"{float(game_result.overall_score):.4f}",
            "overall_score_pt": fmt_pt(game_result.overall_score),
            "roi_count": str(len(game_result.roi_order)),
            "completed_roi_count": str(sum(1 for s in game_result.scores if s.total_score > 0)),
            "elapsed_time_sec": str(int(game_result.elapsed_sec)),
            "time_limit_sec": str(int(game_result.time_limit_sec)),
            "gt_label": make_relative_path(gt_path),
            "pred_label": make_relative_path(pred_path),
            "result_dir": make_relative_path(result_dir),
        }

        for sc in (game_result.scores or []):
            rn = colsafe(sc.roi_name)
            updates[f"dice_{rn}_pt"] = fmt_pt(sc.dice_score)
            updates[f"axial_{rn}_pt"] = fmt_pt(sc.axial_smoothness)
            updates[f"volume_{rn}_pt"] = fmt_pt(sc.volume_smoothness)
            updates[f"total_{rn}_pt"] = fmt_pt(sc.total_score)

        if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
            region, rois = self._extract_region_and_rois(game_result)
            out_fields = base_fields + [k for k in updates.keys() if k not in base_fields]
            row = {k: "" for k in out_fields}
            row.update({
                "year": year, "team": game_result.team or "",
                "participant": game_result.participant or "",
                "session": game_result.session_id or "",
                "region": region, "mode": "play", "rois": rois,
                "gt_label": gt_path, "result_dir": result_dir,
            })
            row.update(updates)
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                w = _csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
                w.writeheader()
                w.writerow({k: ("" if row.get(k) is None else str(row.get(k))) for k in out_fields})
            return

        try:
            with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
                reader = _csv.DictReader(f)
                rows = list(reader)
                existing_fields = list(reader.fieldnames or [])
        except Exception:
            with open(csv_path, "r", newline="", encoding="utf-8") as f:
                reader = _csv.DictReader(f)
                rows = list(reader)
                existing_fields = list(reader.fieldnames or [])

        out_fields = existing_fields + [k for k in updates.keys() if k not in existing_fields]

        target_idx = None
        sid = game_result.session_id or ""
        for i in range(len(rows) - 1, -1, -1):
            if (rows[i].get("session") or "") == sid:
                target_idx = i
                break

        if target_idx is None:
            region, rois = self._extract_region_and_rois(game_result)
            new_row = {k: "" for k in out_fields}
            new_row.update({
                "year": year, "team": game_result.team or "",
                "participant": game_result.participant or "",
                "session": sid, "region": region, "mode": "play", "rois": rois,
            })
            new_row.update(updates)
            rows.append(new_row)
        else:
            r = rows[target_idx]
            for k, v in updates.items():
                r[k] = v
            rows[target_idx] = r

        tmp = csv_path + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
            w = _csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: ("" if r.get(k) is None else str(r.get(k))) for k in out_fields})
        os.replace(tmp, csv_path)

    def _extract_region_and_rois(self, game_result):
        roi_list = ",".join(game_result.roi_order)
        roi_lower = roi_list.lower()
        if any(x in roi_lower for x in ["喉頭", "唾液腺", "甲状腺"]):
            return "頸部", roi_list
        elif any(x in roi_lower for x in ["肺", "心臓", "食道", "気管支"]):
            return "胸部", roi_list
        elif any(x in roi_lower for x in ["肝臓", "腎臓", "膵臓", "胃", "脾臓"]):
            return "腹部", roi_list
        elif any(x in roi_lower for x in ["膀胱", "直腸", "前立腺", "子宮", "小腸"]):
            return "骨盤", roi_list
        else:
            return "全身", roi_list
