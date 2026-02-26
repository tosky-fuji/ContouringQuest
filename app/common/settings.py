# -*- coding: utf-8 -*-
"""設定ファイルの読み書き"""

import os
import json
import datetime as _dt
from typing import Dict, Any

from .paths import get_settings_file, resolve_path


def fiscal_year_default() -> int:
    """デフォルトの年度を取得（4月始まり）"""
    now = _dt.datetime.now()
    return now.year if now.month >= 4 else now.year - 1


def load_settings() -> Dict[str, Any]:
    """統一設定ファイル contour_quest_config.json を読み込む"""
    cfg_path = get_settings_file()

    data: Dict[str, Any] = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}

    data.setdefault("group_format", "AZ")
    data.setdefault("history", {})
    try:
        now = _dt.datetime.now()
        fiscal = now.year if now.month >= 4 else now.year - 1
    except Exception:
        fiscal = 2025
    data.setdefault("year", fiscal)
    data.setdefault("group_value", "A")

    regions = data.get("regions")
    if not isinstance(regions, dict):
        time_min = 10
        try:
            tl = int(((data.get("game_settings") or {}).get("default_time_limit_sec") or 600))
            time_min = max(0, tl // 60)
        except Exception:
            pass

        file_paths = (data.get("file_paths") or {})
        nifti_dir = resolve_path(file_paths.get("nifti_dir", "./nifti"))
        records_dir = resolve_path(file_paths.get("records_dir", "./records"))

        def _first_exist(*paths) -> str:
            for p in paths:
                rp = resolve_path(p)
                if rp and os.path.isfile(rp):
                    return p
            return ""

        ct_rel = _first_exist(
            os.path.join(nifti_dir, "abdominal_ct.nii.gz"),
            os.path.join("nifti", "abdominal_ct.nii.gz")
        )
        gt_rel = _first_exist(
            os.path.join(nifti_dir, "abdominal_label.nii.gz"),
            os.path.join("nifti", "abdominal_label.nii.gz")
        )

        data["regions"] = {
            "腹部1": {
                "rois": "右腎,胃,胆嚢",
                "time_min": 15,
                "ct": ct_rel if ct_rel else "nifti/abdominal_ct.nii.gz",
                "gt_label": gt_rel if gt_rel else "nifti/abdominal_label.nii.gz",
                "outdir": file_paths.get("records_dir", "./records") or "./records",
            },
            "腹部2": {
                "rois": "左腎,脾臓,膀胱",
                "time_min": 15,
                "ct": ct_rel if ct_rel else "nifti/abdominal_ct.nii.gz",
                "gt_label": gt_rel if gt_rel else "nifti/abdominal_label.nii.gz",
                "outdir": file_paths.get("records_dir", "./records") or "./records",
            },
            "腹部3": {
                "rois": "肝臓,膵臓",
                "time_min": 20,
                "ct": ct_rel if ct_rel else "nifti/abdominal_ct.nii.gz",
                "gt_label": gt_rel if gt_rel else "nifti/abdominal_label.nii.gz",
                "outdir": file_paths.get("records_dir", "./records") or "./records",
            }
        }

    return data


def save_settings(data: Dict[str, Any]):
    """設定を contour_quest_config.json に保存"""
    cfg_path = get_settings_file()

    base: Dict[str, Any] = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                base = json.load(f) or {}
        except Exception:
            base = {}

    for k in ["regions", "group_format", "history", "year", "group_value", "files_organized"]:
        if k in data:
            base[k] = data[k]

    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(base, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"設定保存エラー: {e}")
