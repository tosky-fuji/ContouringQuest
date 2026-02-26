# -*- coding: utf-8 -*-
"""パス解決ユーティリティ"""

import os
from pathlib import Path


def get_project_root() -> str:
    """プロジェクトルート（app/ の親ディレクトリ）を返す"""
    app_dir = os.path.dirname(os.path.abspath(__file__))  # common/
    return os.path.abspath(os.path.join(app_dir, os.pardir, os.pardir))


def get_app_dir() -> str:
    """app/ ディレクトリの絶対パスを返す"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def get_settings_file() -> str:
    """contour_quest_config.json の絶対パスを返す"""
    app_dir = get_app_dir()
    root_dir = get_project_root()
    candidates = [
        os.path.join(root_dir, "contour_quest_config.json"),
        os.path.join(app_dir, "contour_quest_config.json"),
        os.path.abspath("contour_quest_config.json"),
    ]
    return next((p for p in candidates if os.path.isfile(p)), candidates[0])


def resolve_path(p: str) -> str:
    """ユーザ/環境変数展開＋相対パス救済"""
    p = (p or "").strip()
    if not p:
        return ""
    p = os.path.expanduser(os.path.expandvars(p))
    p = p.replace("\\", os.sep).replace("/", os.sep)

    if os.path.isabs(p) and os.path.exists(p):
        return os.path.abspath(p)

    app_dir = get_app_dir()
    root_dir = get_project_root()
    settings_dir = os.path.dirname(get_settings_file())
    bases = [os.getcwd(), app_dir, root_dir, settings_dir]
    for base in bases:
        try:
            cand = os.path.abspath(os.path.join(base, p))
            if os.path.exists(cand):
                return cand
        except Exception:
            pass

    return os.path.abspath(p)


def make_relative_path(absolute_path: str) -> str:
    """絶対パスをプロジェクトルートからの相対パスに変換"""
    if not absolute_path:
        return ""
    root_dir = get_project_root()
    try:
        abs_path = os.path.abspath(absolute_path)
        rel_path = os.path.relpath(abs_path, root_dir)
        rel_path = rel_path.replace('\\', '/')
        return rel_path
    except (ValueError, OSError):
        return os.path.basename(absolute_path) if absolute_path else ""
