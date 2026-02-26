# -*- coding: utf-8 -*-
"""CSV集計・マージ関数"""

import os
import csv
import glob
import datetime as dt
from typing import List, Dict, Tuple


def _parse_dt(s: str) -> float:
    if not s:
        return 0.0
    s = s.strip()
    fmts = ["%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
            "%Y-%m-%d %H:%M", "%Y-%m-%d"]
    for f in fmts:
        try:
            return dt.datetime.strptime(s, f).timestamp()
        except Exception:
            pass
    try:
        return dt.datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


def _to_float(x, default=0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if not s:
            return default
        return float(s)
    except Exception:
        return default


def _safe_str(x) -> str:
    return "" if x is None else str(x)


def discover_record_files(records_dir: str, year: int) -> List[str]:
    pats = [
        os.path.join(records_dir, "csv", f"CQ_{year}.csv"),
        os.path.join(records_dir, "csv", f"CQ_{year}_*.csv"),
        os.path.join(records_dir, "csv", f"*{year}*.csv"),
        os.path.join(records_dir, f"CQ_{year}.csv"),
        os.path.join(records_dir, f"CQ_{year}_*.csv"),
        os.path.join(records_dir, f"*{year}*.csv"),
    ]
    found = []
    for p in pats:
        found.extend(glob.glob(p))
    uniq = []
    seen = set()
    for f in found:
        ab = os.path.abspath(f)
        if ab not in seen and os.path.isfile(ab):
            seen.add(ab)
            uniq.append(ab)
    return uniq


def load_and_merge(files: List[str], target_year: int) -> List[Dict[str, str]]:
    rows_raw = []
    all_fields = []
    for path in files:
        encs = ["utf-8-sig", "utf-8"]
        reader = None
        for enc in encs:
            try:
                with open(path, "r", newline="", encoding=enc) as f:
                    reader = list(csv.DictReader(f))
                    header = reader[0].keys() if reader else []
                    for h in header:
                        if h not in all_fields:
                            all_fields.append(h)
                    break
            except Exception:
                reader = None
        if not reader:
            continue
        for r in reader:
            y = _safe_str(r.get("year")).strip()
            if not y:
                if str(target_year) not in os.path.basename(path):
                    continue
            else:
                try:
                    if int(y) != int(target_year):
                        continue
                except Exception:
                    continue
            rows_raw.append(r)

    if not rows_raw:
        return []

    norm_rows = []
    seen = set()
    sorted_fields = sorted(all_fields)
    for r in rows_raw:
        rr = {k: _safe_str(r.get(k, "")).strip() for k in all_fields}
        signature = tuple(rr.get(k, "") for k in sorted_fields)
        if signature in seen:
            continue
        seen.add(signature)
        norm_rows.append(rr)
    return norm_rows


def write_merged_csv(rows: List[Dict[str, str]], out_path: str) -> bool:
    if not rows:
        return False
    headers = []
    for r in rows:
        for k in r.keys():
            if k not in headers:
                headers.append(k)
    try:
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in headers})
        return True
    except Exception:
        return False


def pick_latest_per_person(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    bykey = {}
    bytime = {}
    for r in rows:
        g = _safe_str(r.get("group")).strip()
        t = _safe_str(r.get("team")).strip()
        p = _safe_str(r.get("participant")).strip()
        if not (g and t and p):
            continue
        ts = _parse_dt(_safe_str(r.get("score_timestamp")))
        if ts <= 0:
            ts = _parse_dt(_safe_str(r.get("timestamp")))
        if ts <= 0:
            ts = dt.datetime.now().timestamp()
        key = (g, t, p)
        cur = bytime.get(key, -1)
        if ts >= cur:
            bytime[key] = ts
            bykey[key] = r
    return list(bykey.values())


def ensure_overall_pt(row: Dict[str, str]) -> float:
    v_pt = _to_float(row.get("overall_score_pt"), None)
    if v_pt is None:
        v = _to_float(row.get("overall_score"), None)
        if v is None:
            return 0.0
        return max(0.0, min(100.0, v * 100.0))
    return max(0.0, min(100.0, v_pt))
