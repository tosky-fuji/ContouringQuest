# -*- coding: utf-8 -*-
"""
Contour Quest 設定管理モジュール

統一設定ファイルの読み込みと管理を行う
既存のNIfTI関連JSONを優先しつつ、新規ROIにはデフォルト設定を適用
"""

import json
import os
from typing import Dict, List, Any, Optional
from pathlib import Path


class ConfigManager:
    """統一設定管理クラス"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            from .paths import get_settings_file
            config_path = get_settings_file()

        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._base_dir = self.config_path.parent

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return self._get_default_config()
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        return {
            "game_settings": {"default_time_limit_sec": 600},
            "display_settings": {"default_window_level": {"window": 400, "level": 40}},
            "file_paths": {"nifti_dir": "./nifti", "records_dir": "./records"}
        }

    def get_roi_definitions(self, existing_json_path: str = None) -> List[Dict]:
        from app.common.styles import roi_color
        if existing_json_path and os.path.exists(existing_json_path):
            try:
                with open(existing_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'labels' in data:
                        return data['labels']
            except Exception:
                pass
        # configに roi_definitions があれば使うが、色はパレットで上書き
        defs = self.config.get('roi_definitions', {}).get('default_rois', [])
        for i, d in enumerate(defs):
            d['color'] = roi_color(i)
        return defs

    def get_game_settings(self) -> Dict[str, Any]:
        return self.config.get('game_settings', {})

    def get_display_settings(self) -> Dict[str, Any]:
        return self.config.get('display_settings', {})

    def get_contouring_settings(self) -> Dict[str, Any]:
        return self.config.get('contouring_settings', {})

    def get_review_settings(self) -> Dict[str, Any]:
        return self.config.get('review_settings', {})

    def get_scoring_settings(self) -> Dict[str, Any]:
        return self.config.get('scoring_settings', {})

    def get_file_path(self, path_key: str) -> Path:
        file_paths = self.config.get('file_paths', {})
        relative_path = file_paths.get(path_key, '.')
        if not os.path.isabs(relative_path):
            return (self._base_dir / relative_path).resolve()
        return Path(relative_path)

    def get_ui_settings(self) -> Dict[str, Any]:
        return self.config.get('ui_settings', {})

    def get_shortcuts(self) -> Dict[str, Dict[str, str]]:
        return self.config.get('keyboard_shortcuts', {})

    def get_advanced_settings(self) -> Dict[str, Any]:
        return self.config.get('advanced_settings', {})

    def get_ct_window(self, window_name: str = None) -> Dict[str, int]:
        display_settings = self.get_display_settings()
        if window_name:
            ct_windows = display_settings.get('ct_windows', {})
            if window_name in ct_windows:
                return ct_windows[window_name]
        return display_settings.get('default_window_level', {"window": 400, "level": 40})

    def save_config(self, config: Dict[str, Any] = None):
        if config is None:
            config = self.config
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"設定ファイル保存エラー: {e}")

    def update_setting(self, key_path: str, value: Any):
        keys = key_path.split('.')
        current = self.config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
        self.save_config()

    def merge_with_existing_json(self, json_path: str, data: Dict) -> Dict:
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    data.update(existing_data)
            except Exception:
                pass
        return data


_config_manager = None


def get_config_manager() -> ConfigManager:
    """設定マネージャーのシングルトンインスタンスを取得"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
