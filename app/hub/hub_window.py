# -*- coding: utf-8 -*-
"""HubWindow - カード型グリッドのメイン画面"""

import os
import csv as _csv
import datetime as _dt
import shutil
from typing import Dict, Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QLineEdit, QMessageBox, QInputDialog, QSizePolicy,
    QFrame, QGraphicsDropShadowEffect,
)

from app.common.paths import resolve_path, make_relative_path, get_project_root
from app.common.settings import load_settings, save_settings, fiscal_year_default
from app.common.config_manager import get_config_manager
from app.common.data_models import GameConfig
from app.common.styles import (
    PRIMARY_ACCENT, BG_GRADIENT, BASE_STYLESHEET, accent_from_text, hex_to_rgb, shade, btn_style,
)
from app.common.widgets import GameCard, FunButton
from app.common.csv_utils import year_csv_path

from .settings_dialog import SettingsDialog


APP_TITLE = "Contour Quest"


class HubWindow(QMainWindow):
    """カード型グリッドのハブ画面"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1024, 700)
        self.setStyleSheet(BASE_STYLESHEET)

        self._settings = load_settings()
        self._contouring_window = None
        self._scoring_window = None
        self._leaderboard_window = None
        self._review_window = None

        root = QWidget()
        self.setCentralWidget(root)
        self.v = QVBoxLayout(root)
        self.v.setContentsMargins(28, 28, 28, 28)
        self.v.setSpacing(18)

        self._build_header()
        self._build_inputs()
        self._build_cards()

        self._organize_existing_files_once()

    # ---- Header ----

    def _build_header(self):
        head = QHBoxLayout()

        title = QLabel("Contour Quest")
        title.setStyleSheet("color:white; font-size: 48px; font-weight:900;")
        glow = QGraphicsDropShadowEffect(self)
        glow.setColor(Qt.white)
        glow.setOffset(0, 0)
        glow.setBlurRadius(28)
        title.setGraphicsEffect(glow)

        subtitle = QLabel("放射線治療の輪郭の付け方を学ぼう！")
        subtitle.setStyleSheet("color:#d0d3ff; font-size:14px;")

        left = QVBoxLayout()
        left.addWidget(title)
        left.addWidget(subtitle)
        head.addLayout(left, 1)

        self.settings_btn = FunButton("設定", outline=True)
        self.settings_btn.clicked.connect(self._open_settings)
        right = QHBoxLayout()
        right.addWidget(self.settings_btn)
        head.addLayout(right)

        self.v.addLayout(head)

    # ---- Inputs (group / team / ID / region) ----

    def _build_inputs(self):
        card = QFrame()
        card.setObjectName("inputCard")
        card.setStyleSheet(
            "#inputCard{"
            f"border-radius: 24px; {BG_GRADIENT} border:1px solid rgba(255,255,255,0.08);"
            "}"
        )
        self._input_card = card

        cv = QVBoxLayout(card)
        cv.setContentsMargins(28, 28, 28, 28)
        cv.setSpacing(18)

        # 班名選択
        row_group = QHBoxLayout()
        self.group_combo = QComboBox()
        group_format = self._settings.get("group_format", "AZ")
        if group_format == "AZ":
            self.group_combo.addItems(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
            current_group = str(self._settings.get("group_value", "A")).upper()
            if current_group in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                self.group_combo.setCurrentText(current_group)
        else:
            self.group_combo.addItems([str(i) for i in range(1, 100)])
            try:
                current_group_num = int(self._settings.get("group_value", 1))
                if 1 <= current_group_num <= 99:
                    self.group_combo.setCurrentText(str(current_group_num))
            except Exception:
                self.group_combo.setCurrentIndex(0)

        self.group_combo.setStyleSheet(
            "QComboBox{background: rgba(255,255,255,0.06); color:#e9edff; border:1px solid rgba(255,255,255,0.12);"
            "border-radius: 10px; padding:8px; font-size:16px;}"
            "QComboBox QAbstractItemView{ background:#1e244c; color:white; }"
        )
        g_box = QVBoxLayout()
        g_lab = QLabel("班名")
        g_lab.setStyleSheet("color:#cfe4ff; font-size:13px;")
        g_box.addWidget(g_lab)
        g_box.addWidget(self.group_combo)
        row_group.addLayout(g_box)
        cv.addLayout(row_group)

        # チーム名
        row_team = QHBoxLayout()
        self.team_combo = QComboBox()
        self.team_combo.setEditable(True)
        self.team_combo.setInsertPolicy(QComboBox.NoInsert)
        self.team_combo.lineEdit().setPlaceholderText("チーム名を入力または選択")
        self.team_combo.setStyleSheet(
            "QComboBox{background: rgba(255,255,255,0.06); color:#e9edff; border:1px solid rgba(255,255,255,0.12);"
            "border-radius: 10px; padding:8px; font-size:16px;}"
            "QComboBox QAbstractItemView{ background:#1e244c; color:white; }"
            "QLineEdit{background: transparent; color:#e9edff;}"
        )
        t_box = QVBoxLayout()
        t_lab = QLabel("チーム名（候補から選択または自由入力）")
        t_lab.setStyleSheet("color:#cfe4ff; font-size:13px;")
        t_box.addWidget(t_lab)
        t_box.addWidget(self.team_combo)
        row_team.addLayout(t_box)
        cv.addLayout(row_team)

        # ID
        row_id = QHBoxLayout()
        self.id_edit = self._labeled_line(row_id, "ID (学籍/参加者番号)")
        cv.addLayout(row_id)

        # 対象部位（横並びボタン）
        region_box = QVBoxLayout()
        r_lab = QLabel("対象部位")
        r_lab.setStyleSheet("color:#cfe4ff; font-size:13px;")
        region_box.addWidget(r_lab)

        self.region_buttons_widget = QWidget()
        self.region_buttons_layout = QHBoxLayout(self.region_buttons_widget)
        self.region_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.region_buttons_layout.setSpacing(8)
        region_box.addWidget(self.region_buttons_widget)
        cv.addLayout(region_box)

        self.v.addWidget(card)

        self._refresh_team_candidates()
        self._refresh_region_choices()
        self.group_combo.currentTextChanged.connect(self._on_group_changed)

    # ---- Cards ----

    def _build_cards(self):
        row = QHBoxLayout()
        row.setSpacing(18)

        self.card_play = GameCard(
            icon_text="Play",
            title="プレイ",
            description="本番開始",
        )
        self.card_play.clicked.connect(lambda: self._confirm_and_launch(mode="play"))

        self.card_practice = GameCard(
            icon_text="Practice",
            title="練習",
            description="時間無制限",
        )
        self.card_practice.clicked.connect(lambda: self._launch(mode="practice"))

        self.card_leaderboard = GameCard(
            icon_text="Ranking",
            title="ランキング",
            description="成績一覧",
        )
        self.card_leaderboard.clicked.connect(self._open_leaderboard)

        self.card_review = GameCard(
            icon_text="Review",
            title="レビュー",
            description="比較評価",
        )
        self.card_review.clicked.connect(self._open_review)

        for c in [self.card_play, self.card_practice, self.card_leaderboard, self.card_review]:
            row.addWidget(c)

        self.v.addLayout(row)
        self.v.addStretch(1)

    # ---- Helpers ----

    def _labeled_line(self, row: QHBoxLayout, label: str, value: str = "", placeholder: str = "") -> QLineEdit:
        box = QVBoxLayout()
        lab = QLabel(label)
        lab.setStyleSheet("color:#cfe4ff; font-size:13px;")
        edit = QLineEdit(value)
        edit.setPlaceholderText(placeholder)
        edit.setStyleSheet(
            "QLineEdit{background: rgba(255,255,255,0.06); color:#e9edff; border:1px solid rgba(255,255,255,0.12);"
            "border-radius: 10px; padding:10px; font-size:16px;}"
        )
        box.addWidget(lab)
        box.addWidget(edit)
        row.addLayout(box)
        return edit

    # ---- Settings ----

    def _open_settings(self):
        prev = dict(self._settings) if isinstance(self._settings, dict) else {}
        prev_year = prev.get("year", None)
        prev_group_format = prev.get("group_format", "AZ")

        pwd, ok = QInputDialog.getText(self, "設定パスワード", "Password:", QLineEdit.Password)
        if not ok:
            return
        if pwd != "kochi":
            QMessageBox.warning(self, "認証失敗", "パスワードが違います。")
            return

        dlg = SettingsDialog(self, settings=self._settings)
        dlg.gt_editor_requested.connect(lambda cfg: self._launch_gt_editor(cfg, dlg))
        if dlg.exec():
            self._settings = load_settings()
            self._refresh_region_choices()

            cur_year = self._settings.get("year", None)
            cur_group_format = self._settings.get("group_format", "AZ")

            if cur_group_format != prev_group_format:
                self._rebuild_group_combo()

            self._refresh_team_candidates()

            if cur_year != prev_year or cur_group_format != prev_group_format:
                try:
                    self.team_combo.blockSignals(True)
                    self.team_combo.setEditText("")
                    if self.team_combo.lineEdit() is not None:
                        self.team_combo.lineEdit().clear()
                finally:
                    self.team_combo.blockSignals(False)
        else:
            new_settings = load_settings()
            self._settings = new_settings
            self._refresh_region_choices()
            self._refresh_team_candidates()

    def _rebuild_group_combo(self):
        try:
            self.group_combo.blockSignals(True)
            self.group_combo.clear()

            group_format = self._settings.get("group_format", "AZ")
            if group_format == "AZ":
                self.group_combo.addItems(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
                self.group_combo.setCurrentText("A")
            else:
                self.group_combo.addItems([str(i) for i in range(1, 100)])
                self.group_combo.setCurrentText("1")

            self.group_combo.blockSignals(False)

            new_group = self.group_combo.currentText().strip()
            if new_group:
                settings = load_settings()
                settings["group_value"] = new_group
                save_settings(settings)
                self._settings = settings

        except Exception:
            pass

    # ---- Region selection ----

    def _refresh_region_choices(self):
        try:
            st = load_settings()
            self._settings = st
            region_map = (st or {}).get("regions", {}) or {}
            names = list(region_map.keys())

            if hasattr(self, "region_buttons_layout"):
                while self.region_buttons_layout.count():
                    item = self.region_buttons_layout.takeAt(0)
                    w = item.widget()
                    if w is not None:
                        try:
                            w.setParent(None)
                            w.deleteLater()
                        except Exception:
                            pass

            self._region_btns = {}

            if not names:
                placeholder = QLabel("（contour_quest_config.json の regions が未設定）")
                placeholder.setStyleSheet("color:#cfe4ff;")
                self.region_buttons_layout.addWidget(placeholder)
                self.card_play.setEnabled(False)
                self.card_practice.setEnabled(False)
                self._selected_region = ""
                return

            for name in names:
                b = FunButton(name, outline=True)
                b.setCheckable(True)
                b.setStyleSheet(
                    btn_style(outline=True)
                    + f" QPushButton:checked{{background:{PRIMARY_ACCENT}; color:white; border:none;}}"
                )
                b.clicked.connect(lambda _=False, n=name: self._select_region(n))
                self.region_buttons_layout.addWidget(b)
                self._region_btns[name] = b

            prev = getattr(self, "_selected_region", "")
            sel = prev if prev in names else names[0]
            self._select_region(sel)

            self.card_play.setEnabled(True)
            self.card_practice.setEnabled(True)

        except Exception:
            try:
                self.card_play.setEnabled(False)
                self.card_practice.setEnabled(False)
            except Exception:
                pass

    def _select_region(self, region: str):
        try:
            self._selected_region = region
            for name, b in getattr(self, "_region_btns", {}).items():
                try:
                    b.setChecked(name == region)
                except Exception:
                    pass
            self._apply_region_theme(region)
        except Exception:
            pass

    def _apply_region_theme(self, region: str):
        try:
            accent = accent_from_text(region)
            r, g, b = hex_to_rgb(accent)
            grad = (
                "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                f"stop:0 rgba({r},{g},{b},64), stop:0.5 #141a3a, stop:1 #1c2452);"
            )

            self.setStyleSheet(BASE_STYLESHEET + "\nQMainWindow{" + grad + "}")
            if hasattr(self, "_input_card") and self._input_card is not None:
                self._input_card.setStyleSheet(
                    "#inputCard{" f"border-radius: 24px; {grad} border:1px solid rgba(255,255,255,0.08);" "}"
                )
        except Exception:
            pass

    # ---- Team candidates ----

    def _refresh_team_candidates(self):
        year = str(self._get_year_value())
        csv_path = year_csv_path(year)
        target_group = (self._get_group_value() or "").strip()

        candidates = []
        seen = set()
        if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
            rows = []
            try:
                with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
                    rows = list(_csv.DictReader(f))
            except Exception:
                try:
                    with open(csv_path, "r", newline="", encoding="utf-8") as f:
                        rows = list(_csv.DictReader(f))
                except Exception:
                    rows = []

            for row in reversed(rows):
                g = (row.get("group") or "").strip()
                t = (row.get("team") or "").strip()
                if not t or not g:
                    continue
                if g != target_group:
                    continue
                if t in seen:
                    continue
                seen.add(t)
                candidates.append(t)

        cur_text = self.team_combo.currentText().strip()
        self.team_combo.blockSignals(True)
        self.team_combo.clear()
        if candidates:
            self.team_combo.addItems(candidates)
        if cur_text:
            self.team_combo.setEditText(cur_text)
        self.team_combo.blockSignals(False)

    def _on_group_changed(self):
        try:
            current_group = self.group_combo.currentText().strip()
            if current_group:
                settings = load_settings()
                settings["group_value"] = current_group
                save_settings(settings)
                self._settings = settings
            self._refresh_team_candidates()
        except Exception:
            pass

    # ---- Getters ----

    def _get_group_value(self) -> str:
        if hasattr(self, 'group_combo') and self.group_combo is not None:
            return self.group_combo.currentText().strip()
        st = load_settings()
        gv = str(st.get("group_value", "")).strip()
        if not gv:
            return "A" if (st.get("group_format", "AZ") == "AZ") else "1"
        return gv

    def _get_year_value(self) -> int:
        try:
            st = load_settings()
            return int(st.get("year", fiscal_year_default()))
        except Exception:
            return fiscal_year_default()

    def _get_region_set(self, region: str) -> Dict[str, Any]:
        self._settings = load_settings()
        reg = (self._settings or {}).get("regions", {}).get(region)
        return reg if isinstance(reg, dict) else {}

    def _normalize_rois(self, s: str) -> str:
        s = (s or "").replace("、", ",")
        parts = [p.strip() for p in s.split(",") if p.strip()]
        return ",".join(parts)

    # ---- Play / Practice ----

    def _validate_play_required(self) -> bool:
        st = load_settings()

        year = str(st.get("year", "")).strip()
        if not year:
            QMessageBox.warning(self, "入力不足", "年度が未設定です。設定から設定してください。")
            return False

        group = str(st.get("group_value", "")).strip()
        if not group:
            QMessageBox.warning(self, "入力不足", "班（グループ）が未設定です。設定から設定してください。")
            return False

        team = (self.team_combo.currentText() or "").strip()
        if not team:
            QMessageBox.warning(self, "入力不足", "チーム名を入力してください。")
            try:
                self.team_combo.setFocus()
                self.team_combo.lineEdit().setFocus()
            except Exception:
                pass
            return False

        pid = (self.id_edit.text() or "").strip()
        if not pid:
            QMessageBox.warning(self, "入力不足", "ID（学籍/参加者番号）を入力してください。")
            try:
                self.id_edit.setFocus()
            except Exception:
                pass
            return False

        return True

    def _confirm_and_launch(self, mode: str = "play"):
        try:
            if mode != "play":
                self._launch(mode)
                return
            ans = QMessageBox.question(
                self, "プレイ開始", "プレイ開始しますか？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if ans == QMessageBox.Yes:
                self._launch("play")
        except Exception as e:
            QMessageBox.critical(self, "開始できません", f"{e}")

    def _launch(self, mode: str):
        """コンツーリングアプリをインプロセスで起動"""
        try:
            if mode not in ("play", "practice", "tutorial"):
                raise ValueError("内部エラー: mode は 'play' / 'practice' / 'tutorial' のいずれかです。")

            if mode == "play" and not self._validate_play_required():
                return

            self._settings = load_settings()

            region = getattr(self, "_selected_region", "") or next(
                iter((self._settings.get("regions") or {}).keys()), ""
            )
            reg = self._get_region_set(region)
            rois = self._normalize_rois(reg.get("rois", ""))
            time_sec = int(reg.get("time_min", 10)) * 60
            ct = resolve_path(reg.get("ct", ""))
            gt_label = resolve_path(reg.get("gt_label", ""))
            outdir = resolve_path(reg.get("outdir", ""))

            if not ct:
                raise ValueError("設定で CT NIfTI が未指定です。設定から指定してください。")
            if not os.path.exists(ct):
                raise FileNotFoundError(f"CTファイルが見つかりません: {ct}")

            if mode == "play":
                if not gt_label:
                    raise ValueError("Play モードでは正解ラベル NIfTI が必要です。設定から指定してください。")
                if not os.path.exists(gt_label):
                    raise FileNotFoundError(f"正解ラベルファイルが見つかりません: {gt_label}")

            if mode == "tutorial":
                time_sec = 0
                rois = "チュートリアル"

            if mode == "practice":
                time_sec = 0

            participant = self.id_edit.text().strip()
            team = self.team_combo.currentText().strip()
            year = str(self._get_year_value())
            group = self._get_group_value()

            session_base = _dt.datetime.now().strftime("%Y-%m-%d-%H%M")
            tag = "Play" if mode == "play" else ("Tutorial" if mode == "tutorial" else "Practice")
            session_full = f"{session_base}-{region}-{tag}"

            group_outdir = os.path.join(outdir, f"Group_{group}") if (outdir and mode == "play") else outdir

            # Play のみ：年度CSVへ事前記録
            if mode == "play":
                self._last_play_year = year
                self._last_play_session = session_full
                ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._write_year_csv(year, {
                    "timestamp": ts, "year": year, "group": group, "team": team,
                    "participant": participant, "session": session_full, "region": region,
                    "mode": mode, "rois": rois, "ct": make_relative_path(ct),
                    "gt_label": make_relative_path(gt_label),
                    "result_dir": make_relative_path(group_outdir),
                })

            roi_list = [s.strip() for s in rois.split(",")] if rois and mode != "practice" else None

            game_cfg = GameConfig(
                enabled=True,
                ct_path=ct,
                roi_names=roi_list,
                time_limit_sec=time_sec,
                out_dir=group_outdir if mode == "play" else None,
                participant=participant,
                team=team,
                session_id=session_full,
                gt_label_path=gt_label if gt_label and os.path.exists(gt_label) else None,
                tutorial_mode=(mode in ("tutorial", "practice")),
            )

            from app.contouring.tf_contouring import SimpleNiftiContouringApp

            self._contouring_window = SimpleNiftiContouringApp()
            self._contouring_window.apply_game_config(game_cfg)
            setattr(self._contouring_window, "_auto_score", False)

            self.hide()
            self._contouring_window.show()
            self._contouring_window.start_game_if_needed()
            self._contouring_window.window_closing.connect(self._on_contouring_closed)

        except (ValueError, FileNotFoundError) as e:
            QMessageBox.warning(self, "起動できません", str(e))
        except Exception as e:
            QMessageBox.critical(self, "起動エラー", f"予期しないエラーが発生しました。\n{e}")

    def _on_contouring_closed(self):
        """コンツーリングウィンドウが閉じられたときの処理"""
        try:
            self._refresh_team_candidates()

            if hasattr(self, "id_edit") and self.id_edit is not None:
                self.id_edit.clear()

            self.show()
            self.raise_()
            self.activateWindow()

            # 中断フラグが立っている場合はスコアリングをスキップし、CSV行を削除
            if self._contouring_window is not None and getattr(self._contouring_window, "_game_aborted", False):
                year = getattr(self, "_last_play_year", None)
                session = getattr(self, "_last_play_session", None)
                if year and session:
                    self._remove_year_csv_row(year, session)
                return

            # スコアリングアプリをインプロセスで起動
            if self._contouring_window is not None:
                json_path = getattr(self._contouring_window, "_last_export_json", None)
                if json_path and os.path.exists(json_path):
                    self._start_scoring_inprocess(json_path)

        except Exception as e:
            print(f"例外が発生しました: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._contouring_window = None

    # ---- GT エディタ（設定画面から委譲） ----

    def _launch_gt_editor(self, config, settings_dlg):
        """設定画面から委譲されたGTエディタを起動（play/practiceと同じ遷移パターン）"""
        try:
            from app.contouring.tf_contouring import SimpleNiftiContouringApp

            self._gt_editor_window = SimpleNiftiContouringApp()
            self._gt_editor_window.apply_game_config(config)
            self._pending_settings_dlg = settings_dlg

            self.hide()
            self._gt_editor_window.show()
            self._gt_editor_window.start_game_if_needed()
            self._gt_editor_window.window_closing.connect(self._on_gt_editor_closed)
        except Exception as e:
            settings_dlg.show()
            QMessageBox.critical(self, "エラー", f"正解データエディタの起動に失敗しました:\n{e}")

    def _on_gt_editor_closed(self):
        """GTエディタが閉じられた — 設定画面に戻す"""
        dlg = getattr(self, '_pending_settings_dlg', None)
        editor = getattr(self, '_gt_editor_window', None)

        # 保存されたGTパスを設定画面に反映
        if dlg and editor:
            saved = getattr(editor, '_gt_saved_path', None)
            if saved:
                from app.common.paths import make_relative_path
                dlg.gt_edit.setText(make_relative_path(saved))

        self._gt_editor_window = None
        self._pending_settings_dlg = None

        # ハブを表示してから設定ダイアログを前面に出す
        self.show()
        if dlg:
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

    def _start_scoring_inprocess(self, json_path: str):
        """ScoringMainWindow をインプロセスで起動"""
        try:
            from app.scoring.scoring_window import ScoringMainWindow

            self._scoring_window = ScoringMainWindow(json_path)
            self._scoring_window.show()
        except Exception as e:
            print(f"スコアリング起動失敗: {e}")

    def _write_year_csv(self, year: str, row: dict):
        try:
            path = year_csv_path(year)
            fieldnames = [
                "timestamp", "year", "group", "team", "participant",
                "session", "region", "mode", "rois", "ct", "gt_label", "result_dir",
            ]
            exists_and_nonempty = os.path.exists(path) and os.path.getsize(path) > 0

            with open(path, "a", newline="", encoding="utf-8-sig") as f:
                writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                if not exists_and_nonempty:
                    writer.writeheader()

                sanitized = {}
                for k in fieldnames:
                    val = row.get(k, "")
                    sanitized[k] = "" if val is None else str(val)
                writer.writerow(sanitized)

        except Exception as e:
            try:
                QMessageBox.warning(self, "CSV保存エラー", f"年度CSVへの保存に失敗しました。\n{e}")
            except Exception:
                pass

    def _remove_year_csv_row(self, year: str, session: str):
        """年度CSVから指定セッションの行を除外して書き戻す。"""
        try:
            path = year_csv_path(year)
            if not os.path.exists(path):
                return
            with open(path, "r", newline="", encoding="utf-8-sig") as f:
                reader = _csv.DictReader(f)
                fieldnames = reader.fieldnames
                rows = [row for row in reader if row.get("session") != session]
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
        except Exception as e:
            print(f"CSV行削除エラー: {e}")

    # ---- Leaderboard ----

    def _open_leaderboard(self):
        try:
            from app.leaderboard.leaderboard_window import LeaderboardWindow

            group = self._get_group_value()
            self._leaderboard_window = LeaderboardWindow(group=group)
            self._leaderboard_window.destroyed.connect(self._on_child_closed)
            self.hide()
            self._leaderboard_window.show()
        except Exception as e:
            QMessageBox.critical(self, "起動エラー", f"ランキング画面の起動に失敗しました。\n{e}")

    # ---- Review ----

    def _open_review(self):
        try:
            from app.review.review_window import ReviewMainWindow

            root = get_project_root()
            records_dir = os.path.join(root, "records")
            group = self._get_group_value()
            self._review_window = ReviewMainWindow(records_dir, group=group)
            self._review_window.destroyed.connect(self._on_child_closed)
            self.hide()
            self._review_window.show()
        except Exception as e:
            QMessageBox.critical(self, "起動エラー", f"レビュー画面の起動に失敗しました。\n{e}")

    def _on_child_closed(self):
        """子ウィンドウが閉じられたときにハブを再表示"""
        self.show()
        self.raise_()
        self.activateWindow()

    # ---- File organization (first-time) ----

    def _organize_existing_files_once(self):
        settings = load_settings()
        if not settings.get("files_organized", False):
            self._organize_existing_files()
            settings["files_organized"] = True
            save_settings(settings)
            self._settings = settings

    def _organize_existing_files(self):
        try:
            root_dir = get_project_root()
            records_dir = os.path.join(root_dir, "records")

            if not os.path.exists(records_dir):
                return

            csv_dir = os.path.join(records_dir, "csv")
            os.makedirs(csv_dir, exist_ok=True)

            for filename in os.listdir(records_dir):
                if filename.endswith('.csv'):
                    old_path = os.path.join(records_dir, filename)
                    new_path = os.path.join(csv_dir, filename)
                    if os.path.isfile(old_path) and not os.path.exists(new_path):
                        shutil.move(old_path, new_path)

        except Exception as e:
            print(f"ファイル整理エラー: {e}")
