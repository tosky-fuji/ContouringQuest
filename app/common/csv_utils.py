# -*- coding: utf-8 -*-
"""CSV読み書きヘルパー"""

import os
import csv
import socket
from typing import Dict, List

from .paths import get_project_root


def _host_tag() -> str:
    """ホスト名タグを取得（CQ_NODE_TAG / COMPUTERNAME / HOSTNAME / gethostname()）"""
    tag = (
        os.environ.get("CQ_NODE_TAG")
        or os.environ.get("COMPUTERNAME")
        or os.environ.get("HOSTNAME")
    )
    if not tag:
        try:
            tag = socket.gethostname()
        except Exception:
            tag = "node"
    tag = "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(tag))
    tag = tag.strip("_-")
    return tag or "node"


def year_csv_path(year: str) -> str:
    """年度CSVのフルパスを返す（records/csv/CQ_<year>_<node>.csv）"""
    root_dir = get_project_root()
    csv_dir = os.path.join(root_dir, "records", "csv")
    try:
        os.makedirs(csv_dir, exist_ok=True)
    except Exception:
        pass
    node = _host_tag()
    return os.path.join(csv_dir, f"CQ_{year}_{node}.csv")


def write_year_csv(year: str, row: dict, fieldnames: List[str] = None):
    """年度CSVに1行追記"""
    if fieldnames is None:
        fieldnames = [
            "timestamp", "year", "group", "team", "participant",
            "session", "region", "mode", "rois", "ct", "gt_label", "result_dir"
        ]

    path = year_csv_path(year)
    exists_and_nonempty = os.path.exists(path) and os.path.getsize(path) > 0

    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not exists_and_nonempty:
            writer.writeheader()
        sanitized = {}
        for k in fieldnames:
            val = row.get(k, "")
            sanitized[k] = "" if val is None else str(val)
        writer.writerow(sanitized)
