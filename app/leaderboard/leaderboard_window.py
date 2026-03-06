# -*- coding: utf-8 -*-
"""リーダーボードメインウィンドウ（3段階アニメーション付き）"""

import os
import json
import random
import datetime as dt
from typing import Tuple

from PySide6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QRect, QTimer, QEvent,
)
from PySide6.QtGui import QAction, QStandardItemModel, QStandardItem, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QTableView, QHeaderView, QFrame,
    QDialog, QMessageBox, QGraphicsOpacityEffect, QStackedWidget, QToolButton,
    QInputDialog,
)

from app.common.config_manager import get_config_manager
from app.common.settings import fiscal_year_default
from app.common.widgets import SpringButton
from app.common.styles import (
    BASE_STYLESHEET, PRIMARY_ACCENT, SECONDARY_ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_LABEL,
    DARK_SURFACE, DARK_SURFACE_ALT,
    PODIUM_GOLD, PODIUM_SILVER, PODIUM_BRONZE,
    PODIUM_GOLD_BG, PODIUM_SILVER_BG, PODIUM_BRONZE_BG,
)

from .data_utils import (
    discover_record_files, load_and_merge, write_merged_csv,
    pick_latest_per_person, ensure_overall_pt,
)

SETTINGS_FILE = "leaderboard_settings.json"


class LeaderboardWindow(QMainWindow):
    def __init__(self, group: str = ""):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("CQ Leaderboard")
        self.setMinimumSize(1000, 760)

        # ハブから渡された班（空なら設定から取得）
        self._fixed_group = group.strip().upper() if group else ""

        # 統一設定マネージャーを初期化
        self.config_manager = get_config_manager()

        # 設定のロード（無ければデフォルト）
        self.records_dir, self.year = self._load_settings()

        self._build_ui()

    # ---- 設定 I/O ----

    def _load_settings(self) -> Tuple[str, int]:
        from app.common.paths import get_project_root
        root_dir = get_project_root()
        app_dir = os.path.join(root_dir, "app")

        def root_records_abs() -> str:
            return os.path.abspath(os.path.join(root_dir, "records"))

        default_year = fiscal_year_default()
        default_records = root_records_abs()

        # config_manager があれば拾う（後で正規化）
        # ただし file_paths.records_dir が明示的に設定されている場合のみ使用
        cm_path = ""
        if hasattr(self, 'config_manager') and self.config_manager:
            try:
                file_paths = self.config_manager.config.get('file_paths', {})
                if 'records_dir' in file_paths:
                    cm_path = str(self.config_manager.get_file_path('records_dir'))
            except Exception:
                cm_path = ""

        # 相対や app/records を "必ず" dist/records に寄せる正規化
        def _normalize(candidate: str) -> str:
            if not candidate:
                return default_records
            s = candidate.strip()

            # 相対指定 'records' / './records' / '.\records' は dist/records 扱い
            if s.lower() in ("records", "./records", ".\\records"):
                return default_records

            # 変数展開 → 絶対化
            cand_abs = os.path.abspath(os.path.expanduser(os.path.expandvars(s)))

            app_records_abs = os.path.abspath(os.path.join(app_dir, "records"))
            # app/records を指していたら dist/records にリライト
            if os.path.normcase(cand_abs) == os.path.normcase(app_records_abs):
                return default_records

            return cand_abs

        # 設定ファイル（プロジェクトルート直下）
        settings_path = os.path.join(root_dir, SETTINGS_FILE)

        if os.path.isfile(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                rec = _normalize(cfg.get("records_dir") or cm_path or default_records)
                yr = int(cfg.get("year") or default_year)
            except Exception:
                rec = _normalize(cm_path or default_records)
                yr = default_year
        else:
            rec = _normalize(cm_path or default_records)
            yr = default_year

        return rec, yr

    def _save_settings(self):
        from app.common.paths import get_project_root
        root_dir = get_project_root()
        app_dir = os.path.join(root_dir, "app")

        def root_records_abs() -> str:
            return os.path.abspath(os.path.join(root_dir, "records"))

        def _normalize_out(p: str) -> str:
            if not p:
                return root_records_abs()
            s = p.strip()
            if s.lower() in ("records", "./records", ".\\records"):
                return root_records_abs()
            cand_abs = os.path.abspath(os.path.expanduser(os.path.expandvars(s)))
            app_records_abs = os.path.abspath(os.path.join(app_dir, "records"))
            if os.path.normcase(cand_abs) == os.path.normcase(app_records_abs):
                return root_records_abs()
            return cand_abs

        settings_path = os.path.join(root_dir, SETTINGS_FILE)
        cfg = {"records_dir": _normalize_out(self.records_dir), "year": int(self.year)}
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---- UI 構築 ----

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(10)

        # ===== 帯ヘッダー =====
        title = QLabel("🎮  CQ LEADERBOARD — RESULT SHOW  🎉")
        title.setAlignment(Qt.AlignCenter)
        title.setFixedHeight(64)
        title.setStyleSheet(f"""
            QLabel {{
                font-size: 22px; font-weight: 900; color: #ffffff;
                padding: 6px 12px; border-radius: 16px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                   stop:0 {PRIMARY_ACCENT}, stop:1 {SECONDARY_ACCENT});
            }}
        """)
        root.addWidget(title)

        # ===== 初期ヒーロー（丸い集計ボタン＋班セレクト） =====
        self.hero = QWidget()
        hero_lay = QVBoxLayout(self.hero)
        hero_lay.setContentsMargins(0, 6, 0, 16)
        hero_lay.setSpacing(14)
        hero_lay.setAlignment(Qt.AlignHCenter)

        group_row = QHBoxLayout()
        group_row.setAlignment(Qt.AlignHCenter)
        self.hero_group_label = QLabel("班")
        self.hero_group_label.setStyleSheet(f"font-size:16px; color:{TEXT_LABEL}; padding-right:6px;")
        if self._fixed_group:
            # ハブから班指定済み → 固定ラベル表示（変更不可）
            self.group_combo = QComboBox()
            self.group_combo.addItem(self._fixed_group)
            self.group_combo.setEnabled(False)
            self.group_combo.setStyleSheet(f"""
                QComboBox {{ font-size:18px; padding:6px 10px; min-width:80px;
                            border:1px solid rgba(255,255,255,0.12); border-radius:10px;
                            background: rgba(255,255,255,0.06); color:{TEXT_PRIMARY}; }}
            """)
        else:
            self.group_combo = QComboBox()
            self.group_combo.addItems(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
            self.group_combo.setStyleSheet(f"""
                QComboBox {{ font-size:18px; padding:6px 10px; min-width:80px;
                            border:1px solid rgba(255,255,255,0.12); border-radius:10px;
                            background: rgba(255,255,255,0.06); color:{TEXT_PRIMARY}; }}
                QComboBox::drop-down {{ width:24px; }}
                QComboBox QAbstractItemView {{ background:#1e244c; color:white; }}
            """)
        group_row.addWidget(self.hero_group_label)
        group_row.addWidget(self.group_combo)
        hero_lay.addLayout(group_row)

        # 丸い巨大"集計開始"ボタン（中央）
        self.btn_run = SpringButton("集計開始")
        self.btn_run.clicked.connect(self._on_run_clicked)
        self.btn_run.setCursor(Qt.PointingHandCursor)
        diameter = 220
        self.btn_run.setMinimumSize(diameter, diameter)
        self.btn_run.setMaximumSize(diameter, diameter)
        self.btn_run.setStyleSheet(f"""
            QPushButton {{
                font-size: 30px; font-weight: 900; letter-spacing: 1px;
                color: #ffffff;
                border-radius: {diameter // 2}px;
                border: 5px solid {PRIMARY_ACCENT};
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #3a3f8a, stop:1 {PRIMARY_ACCENT});
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #4a4f9a, stop:1 #8C73FF);
                border-color: #9B85FF;
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #2b2f66, stop:1 #6A55E6);
                border-color: #5E35B1;
            }}
        """)
        self.btn_run.installEventFilter(self)  # hover ふわっと
        hero_lay.addWidget(self.btn_run, 0, Qt.AlignHCenter)
        root.addWidget(self.hero)

        # ===== トップツール行（集計後に表示） =====
        tools = QWidget()
        tools_lay = QHBoxLayout(tools)
        tools_lay.setContentsMargins(0, 0, 0, 0)
        tools_lay.setSpacing(8)

        self.group_label = QLabel("班: -")
        self.group_label.setVisible(False)
        self.group_label.setStyleSheet(
            f"font-size:16px; padding:6px 10px; border-radius:10px; "
            f"background: rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.12); color:{TEXT_PRIMARY};"
        )
        tools_lay.addWidget(self.group_label)
        tools_lay.addStretch(1)

        self.btn_reveal = QPushButton("🎲 ① 全班を発表（ガチャ！）")
        self.btn_reveal.setEnabled(False)
        self.btn_reveal.setVisible(False)
        self.btn_reveal.clicked.connect(self._reveal_next_stage)
        self.btn_reveal.setStyleSheet(f"""
            QPushButton {{
                font-size:16px; font-weight:800; padding:8px 16px;
                border-radius:12px; color:white;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #2b2f66, stop:1 {PRIMARY_ACCENT});
                border:1px solid {PRIMARY_ACCENT};
            }}
            QPushButton:disabled {{ color:{TEXT_MUTED}; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.08); }}
        """)
        tools_lay.addWidget(self.btn_reveal)

        root.addWidget(tools)

        # ===== ナビ（①全班 / ②個人 / ③チーム） =====
        self.stage_titles = ["① 全班", "② 個人", "③ チーム"]
        self.nav_bar = QWidget()
        nav = QHBoxLayout(self.nav_bar)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(8)
        nav.addStretch(1)
        self.nav_buttons = []
        for i, label in enumerate(self.stage_titles):
            b = QToolButton()
            b.setText(label)
            b.setCheckable(True)
            b.setEnabled(False)
            b.clicked.connect(lambda _=False, idx=i: self._on_nav_stage_clicked(idx))
            b.setStyleSheet(f"""
                QToolButton {{
                    font-size:16px; font-weight:800; padding:8px 16px;
                    border-radius:16px; border:2px solid rgba(255,255,255,0.15); color:{TEXT_SECONDARY};
                    background: rgba(255,255,255,0.04);
                }}
                QToolButton:checked {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                        stop:0 #2b2f66, stop:1 {PRIMARY_ACCENT});
                    border-color:{PRIMARY_ACCENT}; color:white;
                }}
                QToolButton:disabled {{
                    color:{TEXT_MUTED}; border-color:rgba(255,255,255,0.06); background:rgba(255,255,255,0.02);
                }}
            """)
            self.nav_buttons.append(b)
            nav.addWidget(b)
            if i < 2:
                sep = QLabel("›")
                sep.setStyleSheet(f"font-size:20px; color:{TEXT_MUTED}; font-weight:900;")
                nav.addWidget(sep)
        nav.addStretch(1)
        self.nav_bar.setVisible(False)
        root.addWidget(self.nav_bar)

        # ===== ステージ表示 =====
        self.stage_stack = QStackedWidget()
        self.stage_stack.setStyleSheet(
            "QStackedWidget { background: rgba(255,255,255,0.04); border-radius:16px; border:1px solid rgba(255,255,255,0.08); }"
        )

        # --- ① 全班 ---
        self.page_group = QWidget()
        lay_g = QVBoxLayout(self.page_group)
        lay_g.setContentsMargins(18, 14, 18, 18)
        lay_g.setSpacing(8)
        self.title_group = self._make_stage_title("🌐 全班比較（班平均）ランキング")
        lay_g.addWidget(self.title_group)
        self.lbl_group_rank = QLabel("対象班の順位: -")
        self.lbl_group_rank.setAlignment(Qt.AlignCenter)
        self.lbl_group_rank.setStyleSheet(f"font-size:16px; color:{SECONDARY_ACCENT};")
        lay_g.addWidget(self.lbl_group_rank)
        self.tbl_group = QTableView()
        lay_g.addWidget(self.tbl_group, 1)
        self.stage_stack.addWidget(self.page_group)

        # --- ② 個人 ---
        self.page_person = QWidget()
        lay_p = QVBoxLayout(self.page_person)
        lay_p.setContentsMargins(18, 14, 18, 18)
        lay_p.setSpacing(8)
        self.title_person = self._make_stage_title("🏆 個人総合ランキング")
        lay_p.addWidget(self.title_person)
        self.lbl_person_info = QLabel("✨ overall_score_pt による個人総合スコア ✨")
        self.lbl_person_info.setAlignment(Qt.AlignCenter)
        self.lbl_person_info.setStyleSheet(f"font-size:16px; color:{SECONDARY_ACCENT};")
        lay_p.addWidget(self.lbl_person_info)
        self.tbl_person = QTableView()
        lay_p.addWidget(self.tbl_person, 1)
        self.stage_stack.addWidget(self.page_person)

        # --- ③ チーム ---
        self.page_team = QWidget()
        lay_t = QVBoxLayout(self.page_team)
        lay_t.setContentsMargins(18, 14, 18, 18)
        lay_t.setSpacing(8)
        self.title_team = self._make_stage_title("🛡 チーム総合ランキング")
        lay_t.addWidget(self.title_team)
        self.tbl_team = QTableView()
        lay_t.addWidget(self.tbl_team, 1)
        self.stage_stack.addWidget(self.page_team)

        root.addWidget(self.stage_stack, 1)
        self.stage_stack.hide()

        # ===== ステータス =====
        bottom = QHBoxLayout()
        root.addLayout(bottom)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"font-size:12px; color:{TEXT_MUTED}; padding: 4px;")
        bottom.addWidget(self.status_label, 1)

        self.setCentralWidget(central)

        # メニュー
        refresh_act = QAction("再読込", self)
        refresh_act.triggered.connect(self._run_aggregate_with_ui_switch)
        self.menuBar().addAction(refresh_act)

        # ===== テーマ & テーブル装飾 =====
        self._apply_global_theme()
        self._style_tables([self.tbl_group, self.tbl_person, self.tbl_team])

        # ステート
        self.current_stage = -1
        self.max_revealed_stage = -1
        self._anims = []

    # ---- 集計と表示（CSV自動結合を含む） ----

    def _run_aggregate(self):
        records_dir = self.records_dir
        year = int(self.year)
        group = self.group_combo.currentText().strip().upper()

        if not os.path.isdir(records_dir):
            QMessageBox.warning(self, "エラー", f"records フォルダが存在しません:\n{records_dir}")
            return

        files = discover_record_files(records_dir, year)
        if not files:
            QMessageBox.warning(self, "情報", f"{year} 年の CSV が見つかりません。")
            return

        rows = load_and_merge(files, year)
        if not rows:
            QMessageBox.warning(self, "情報", f"{year} 年のデータがありません。")
            return

        # 自動結合保存（csvサブフォルダに保存）
        csv_dir = os.path.join(records_dir, "csv")
        os.makedirs(csv_dir, exist_ok=True)
        merged_path = os.path.join(csv_dir, f"CQ_{year}_merged.csv")
        merged_ok = write_merged_csv(rows, merged_path)

        # 最新 per person
        latest_rows = pick_latest_per_person(rows)

        # ---- ステージの並びは ①全班 → ②個人 → ③チーム ----
        self._fill_group_table(latest_rows, group)    # ① 全班
        self._fill_person_table(latest_rows, group)   # ② 個人（team列なし）
        self._fill_team_table(latest_rows, group)     # ③ チーム（members列なし）

        msg = f"読込 {len(files)} ファイル / 行 {len(rows)}（最新化 {len(latest_rows)} 人）"
        if merged_ok:
            msg += f" ｜ 結合保存: {os.path.basename(merged_path)}"
        self.status_label.setText(msg)

        # ===== 初期は隠していた UI を解放（ステージ画面へ） =====
        self.group_combo.setVisible(False)
        self.btn_run.setVisible(False)
        self.group_label.setText(f"班: {group}")
        self.group_label.setVisible(True)

        self.nav_bar.setVisible(True)

        # ナビは使える（未開放段はクリックで"めくる"挙動）
        self._reset_presentation()

        # 最初の表示だけは自動で①（全班）へ
        QTimer.singleShot(600, self._reveal_next_stage)

    def _fill_person_table(self, latest_rows, group: str):
        """個人総合のランキング（降順）。上位3人のみ表示。1〜3位に色付け。"""
        group_rows = [
            r for r in latest_rows
            if (r.get("group", "") or "").strip().upper() == group
        ]

        entrants = []
        for r in group_rows:
            pt = ensure_overall_pt(r)  # 0-100
            participant = (r.get("participant") or "").strip()
            if not participant:
                continue
            entrants.append({
                "participant": participant,
                "overall_pt": f"{pt:.1f}",
            })

        # 降順 → rank 1 が先頭
        entrants.sort(key=lambda x: float(x["overall_pt"]), reverse=True)

        # 上位3人のみに制限
        top_entrants = entrants[:3]

        # データを保存（後でアニメーション表示）
        self._person_data = top_entrants

        # 初期状態：空のモデルを作成（演出で後から埋める）
        model = QStandardItemModel(len(top_entrants), 3)
        model.setHorizontalHeaderLabels(["rank", "participant", "overall_pt"])

        for r in range(len(top_entrants)):
            for c in range(3):
                it = QStandardItem("")
                it.setEditable(False)
                model.setItem(r, c, it)

        self.tbl_person.setModel(model)
        self.tbl_person.setSortingEnabled(False)
        self.tbl_person.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_person.verticalHeader().setVisible(False)

    def _fill_team_table(self, latest_rows, group: str):
        """チーム平均（overall_score_pt）のランキング（降順）。1〜3位に色付け。"""
        team_scores = {}
        for r in latest_rows:
            if (r.get("group", "") or "").strip().upper() != group:
                continue
            pt = ensure_overall_pt(r)
            team = (r.get("team") or "").strip()
            if not team:
                continue
            team_scores.setdefault(team, []).append(pt)

        rows = []
        for team, vals in team_scores.items():
            avg = sum(vals) / max(1, len(vals))
            rows.append({"team": team, "avg_overall_pt": avg})

        rows.sort(key=lambda x: x["avg_overall_pt"], reverse=True)

        model = QStandardItemModel(len(rows), 3)
        model.setHorizontalHeaderLabels(["rank", "team", "avg_overall_pt"])

        podium_bg = [
            QColor(255, 215, 0, 45),
            QColor(192, 192, 192, 35),
            QColor(205, 127, 50, 35),
        ]
        podium_fg = [
            QColor(PODIUM_GOLD),
            QColor(PODIUM_SILVER),
            QColor(PODIUM_BRONZE),
        ]
        for i, row in enumerate(rows):
            items = [
                QStandardItem(str(i + 1)),
                QStandardItem(row["team"]),
                QStandardItem(f"{row['avg_overall_pt']:.1f}"),
            ]
            for it in items:
                it.setEditable(False)
                f = QFont("", 12)
                if i < 3:
                    f.setBold(True)
                it.setFont(f)

            if i < 3:
                for it in items:
                    it.setForeground(QBrush(podium_fg[i]))
                    it.setBackground(QBrush(podium_bg[i]))
                if i == 0:
                    items[1].setText(f"👑 {row['team']}")

            for c, it in enumerate(items):
                model.setItem(i, c, it)

        self.tbl_team.setModel(model)
        self.tbl_team.setSortingEnabled(False)
        self.tbl_team.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_team.verticalHeader().setVisible(False)

    def _fill_group_table(self, latest_rows, target_group: str):
        """全班比較（overall 平均）のランキング。1〜3位に色付け＋対象班を強調表示。"""
        grp_scores = {}
        for r in latest_rows:
            g = (r.get("group") or "").strip().upper()
            if not g:
                continue
            grp_scores.setdefault(g, []).append(ensure_overall_pt(r))

        rows = []
        for g, vals in grp_scores.items():
            avg = sum(vals) / max(1, len(vals))
            rows.append({"group": g, "members": len(vals), "avg_overall_pt": avg})

        # 降順（1位を上）
        rows.sort(key=lambda x: x["avg_overall_pt"], reverse=True)

        model = QStandardItemModel(len(rows), 4)
        model.setHorizontalHeaderLabels(["rank", "group", "members", "avg_overall_pt"])

        podium_bg = [
            QColor(255, 215, 0, 45),
            QColor(192, 192, 192, 35),
            QColor(205, 127, 50, 35),
        ]
        podium_fg = [
            QColor(PODIUM_GOLD),
            QColor(PODIUM_SILVER),
            QColor(PODIUM_BRONZE),
        ]
        highlight_bg = QColor(124, 92, 255, 50)  # PRIMARY_ACCENT 半透明
        highlight_fg = QColor("#b8a0ff")
        tgt = (target_group or "").upper()
        tgt_rank_text = "対象班の順位: -"

        for i, row in enumerate(rows):
            items = [
                QStandardItem(str(i + 1)),
                QStandardItem(row["group"]),
                QStandardItem(str(row["members"])),
                QStandardItem(f"{row['avg_overall_pt']:.1f}"),
            ]
            for it in items:
                it.setEditable(False)
                f = QFont("", 12)
                if i < 3:
                    f.setBold(True)
                it.setFont(f)

            # トップ3の色
            if i < 3:
                for it in items:
                    it.setForeground(QBrush(podium_fg[i]))
                    it.setBackground(QBrush(podium_bg[i]))
                if i == 0:
                    items[1].setText(f"🥇 {row['group']}")

            # 対象班の強調（上書き）
            if row["group"] == tgt:
                for it in items:
                    it.setBackground(QBrush(highlight_bg))
                    it.setForeground(QBrush(highlight_fg))
                    ff = it.font()
                    ff.setBold(True)
                    it.setFont(ff)
                items[1].setText(f"👑 {row['group']}")
                tgt_rank_text = (
                    f"対象班の順位: {i + 1} 位"
                    f"（平均 {row['avg_overall_pt']:.1f} pt / {row['members']} 人）"
                )

            for c, it in enumerate(items):
                model.setItem(i, c, it)

        self.tbl_group.setModel(model)
        self.tbl_group.setSortingEnabled(False)
        self.tbl_group.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_group.verticalHeader().setVisible(False)
        self.lbl_group_rank.setText(tgt_rank_text)

    # ====== プレゼン（ガチャ演出＆ナビ） ======

    def _reset_presentation(self):
        """集計直後の初期化。"""
        self.current_stage = -1
        self.max_revealed_stage = -1
        self.stage_stack.hide()
        self.btn_reveal.setText("🎲 ① 全班を発表（ガチャ！）")
        for b in self.nav_buttons:
            b.setChecked(False)
            b.setEnabled(True)

    def _reveal_next_stage(self):
        """ガチャボタンで ①→②→③ と順送り。"""
        try:
            if hasattr(self, "btn_reveal") and self.btn_reveal.isVisible():
                self._animate_button_pop(self.btn_reveal)
        except Exception:
            pass
        next_idx = min(self.current_stage + 1, 2)
        self._reveal_stage(next_idx, animate=True)

    def _reveal_stage(self, index: int, animate: bool = True):
        """指定ステージを"めくる"。"""
        index = max(0, min(2, int(index)))
        if not self.stage_stack.isVisible():
            self.stage_stack.show()

        prev = self.current_stage

        if index > self.max_revealed_stage:
            self.max_revealed_stage = index

        self.current_stage = index
        try:
            self.stage_stack.setCurrentIndex(index)
        except Exception:
            pass

        if animate:
            self._animate_transition(prev, index)

        self._update_stage_nav()

        # ② 個人ランキングの場合は演出を開始
        if index == 1 and animate:
            QTimer.singleShot(600, self._start_person_reveal_animation)

        # 次のボタン文言をタイトル込みで更新
        if self.max_revealed_stage < 2:
            nxt = self.max_revealed_stage + 1
            self.btn_reveal.setText(f"🎲 {self.stage_titles[nxt]} を発表（ガチャ！）")
        else:
            self.btn_reveal.setText("🔁 もう一度（最初から）")

    def _reveal_to_stage(self, target_index: int):
        """ナビ ①②③ から未開放の段へ飛ぶ場合、中継を静かに開放してから表示。"""
        target_index = max(0, min(2, int(target_index)))
        for i in range(self.max_revealed_stage + 1, target_index):
            self._reveal_stage(i, animate=False)
        self._reveal_stage(target_index, animate=True)

    def _update_stage_nav(self):
        """ナビのチェック状態を現在ステージに合わせる。"""
        for i, b in enumerate(self.nav_buttons):
            b.setChecked(i == self.current_stage)

    def _on_nav_stage_clicked(self, index: int):
        """中央ナビをクリックしたらその段を表示。"""
        if index > self.max_revealed_stage:
            self._reveal_to_stage(index)
        else:
            if not self.stage_stack.isVisible():
                self.stage_stack.show()
            prev = self.current_stage
            self.current_stage = index
            self._show_stage(index)
            self._animate_transition(prev, index)
            self._update_stage_nav()

    def _show_stage(self, index: int):
        try:
            self.stage_stack.setCurrentIndex(index)
        except Exception:
            pass

    # ====== アニメーション ======

    def _animate_in(self, widget):
        """フェード＋軽いズームイン"""
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(650)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        r0 = widget.geometry()
        r_start = QRect(
            r0.x() + int(r0.width() * 0.01),
            r0.y() + int(r0.height() * 0.01),
            int(r0.width() * 0.98),
            int(r0.height() * 0.98),
        )
        anim2 = QPropertyAnimation(widget, b"geometry", widget)
        anim2.setDuration(650)
        anim2.setStartValue(r_start)
        anim2.setEndValue(r0)
        anim2.setEasingCurve(QEasingCurve.OutBack)

        if not hasattr(self, "_anims"):
            self._anims = []
        self._anims[:] = [anim, anim2]
        anim.start()
        anim2.start()

    def _animate_button_pop(self, btn):
        """ガチャボタンの"ポンッ"演出"""
        r0 = btn.geometry()
        scale = 1.06
        rw = int(r0.width() * scale)
        rh = int(r0.height() * scale)
        r_start = QRect(r0.center().x() - rw // 2, r0.center().y() - rh // 2, rw, rh)

        anim = QPropertyAnimation(btn, b"geometry", btn)
        anim.setDuration(220)
        anim.setStartValue(r_start)
        anim.setEndValue(r0)
        anim.setEasingCurve(QEasingCurve.OutBack)

        if not hasattr(self, "_anims"):
            self._anims = []
        self._anims.append(anim)
        anim.start()

    def _animate_transition(self, from_idx: int, to_idx: int):
        """ページ遷移の左右スライド＋フェード＋軽いズーム。"""
        w = self.stage_stack.currentWidget()
        if not w:
            return

        # フェード
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        fade = QPropertyAnimation(eff, b"opacity", w)
        fade.setDuration(500)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)

        # スライド（方向）
        final = w.geometry()
        dx = int(self.stage_stack.width() * 0.12) or 80
        dy = int(self.stage_stack.height() * 0.06) or 40

        if from_idx < 0:
            start = QRect(final.x(), final.y() + dy, final.width(), final.height())
        elif to_idx > from_idx:
            start = QRect(final.x() + dx, final.y(), final.width(), final.height())
        else:
            start = QRect(final.x() - dx, final.y(), final.width(), final.height())

        slide = QPropertyAnimation(w, b"geometry", w)
        slide.setDuration(500)
        slide.setStartValue(start)
        slide.setEndValue(final)
        slide.setEasingCurve(QEasingCurve.OutBack)

        self._anims = [fade, slide]
        fade.start()
        slide.start()

    def eventFilter(self, obj, event):
        """hoverモーション用。集計ボタンに乗ったら"ふわっと"浮かす。"""
        if obj is self.btn_run:
            if event.type() == QEvent.Enter:
                self._animate_button_hover(self.btn_run)
        return super().eventFilter(obj, event)

    def _on_run_clicked(self):
        """ガチャ風の押下演出 → 集計実行 → 初期画面を閉じて結果UIへ"""
        btn = self.btn_run
        btn.setEnabled(False)

        def after_wrapper():
            self._run_aggregate()
            if hasattr(self, "hero"):
                self.hero.hide()
            if hasattr(self, "hero_group_label"):
                self.hero_group_label.hide()
            if hasattr(self, "group_combo"):
                self.group_combo.hide()
            self._hide_restart_button_if_exists()
            QTimer.singleShot(200, lambda: btn.setEnabled(True))

        self._play_gacha_press(btn, after=after_wrapper)

    def _animate_button_hover(self, btn):
        """マウスオン時の"ふわっと浮いてバウンド"モーション"""
        r0 = btn.geometry()
        up = QRect(r0.x(), r0.y() - 6, r0.width(), r0.height())

        a1 = QPropertyAnimation(btn, b"geometry", btn)
        a1.setDuration(220)
        a1.setStartValue(r0)
        a1.setEndValue(up)
        a1.setEasingCurve(QEasingCurve.OutCubic)

        a2 = QPropertyAnimation(btn, b"geometry", btn)
        a2.setDuration(440)
        a2.setStartValue(up)
        a2.setEndValue(r0)
        a2.setEasingCurve(QEasingCurve.OutBounce)

        self._anims = [a1, a2]
        a1.finished.connect(a2.start)
        a1.start()

    def _play_gacha_press(self, btn, after):
        """
        "ガチャ！"押下演出：
          1) ぱっと大きく → 2) きゅっと戻る（バネ感）
          3) フラッシュ（不透明度）
          完了後に after() を実行
        """
        from PySide6.QtWidgets import QGraphicsDropShadowEffect as _QGDSE

        r0 = btn.geometry()
        scale = 1.12
        rw = int(r0.width() * scale)
        rh = int(r0.height() * scale)
        r_big = QRect(r0.center().x() - rw // 2, r0.center().y() - rh // 2, rw, rh)

        a1 = QPropertyAnimation(btn, b"geometry", btn)
        a1.setDuration(160)
        a1.setStartValue(r0)
        a1.setEndValue(r_big)
        a1.setEasingCurve(QEasingCurve.OutCubic)

        a2 = QPropertyAnimation(btn, b"geometry", btn)
        a2.setDuration(240)
        a2.setStartValue(r_big)
        a2.setEndValue(r0)
        a2.setEasingCurve(QEasingCurve.InOutBack)

        # ---- フラッシュ用エフェクト（影を一時停止） ----
        if isinstance(btn, SpringButton):
            btn._suspend_shadow = True
        eff = QGraphicsOpacityEffect(btn)
        btn.setGraphicsEffect(eff)
        f1 = QPropertyAnimation(eff, b"opacity", btn)
        f1.setDuration(150)
        f1.setStartValue(1.0)
        f1.setEndValue(0.40)
        f2 = QPropertyAnimation(eff, b"opacity", btn)
        f2.setDuration(150)
        f2.setStartValue(0.40)
        f2.setEndValue(1.0)

        def _finish():
            btn.setGraphicsEffect(None)
            if isinstance(btn, SpringButton):
                btn._suspend_shadow = False
                btn._ensure_shadow()
                btn._apply_shadow()
            after()
            QTimer.singleShot(200, lambda: btn.setEnabled(True))

        self._anims = [a1, a2, f1, f2]
        a1.finished.connect(f1.start)
        f1.finished.connect(f2.start)
        f2.finished.connect(a2.start)
        a2.finished.connect(_finish)
        a1.start()

    def _make_stage_title(self, text: str) -> QLabel:
        """各ステージのタイトルを統一トーンで生成"""
        lab = QLabel(text)
        lab.setAlignment(Qt.AlignCenter)
        lab.setStyleSheet(f"""
            QLabel {{
                font-size: 24px; font-weight: 900; color: white;
                padding: 10px 14px; border-radius: 14px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                   stop:0 {PRIMARY_ACCENT}, stop:1 {SECONDARY_ACCENT});
                border:1px solid rgba(255,255,255,0.12);
            }}
        """)
        return lab

    def _style_tables(self, tables):
        """テーブルの見た目を統一"""
        for tbl in tables:
            tbl.setAlternatingRowColors(True)
            tbl.setStyleSheet(f"""
                QTableView {{
                    background:{DARK_SURFACE}; alternate-background-color:{DARK_SURFACE_ALT};
                    gridline-color:rgba(255,255,255,0.06); font-size:16px;
                    color:{TEXT_PRIMARY};
                    selection-background-color:rgba(124,92,255,0.35);
                    selection-color:white;
                    border:1px solid rgba(255,255,255,0.08); border-radius:8px;
                }}
                QHeaderView::section {{
                    background:#1a2050; color:{TEXT_SECONDARY}; font-size:14px; font-weight:700;
                    padding:6px; border:0; border-right:1px solid rgba(255,255,255,0.06);
                }}
            """)
            header = tbl.horizontalHeader()
            try:
                header.setStretchLastSection(True)
            except Exception:
                pass

    def _apply_global_theme(self):
        """アプリ全体のスタイルを統一"""
        self.setStyleSheet(BASE_STYLESHEET)

    def _run_aggregate_with_ui_switch(self):
        """メニューの再読込などから呼ぶときも、初期画面を閉じて結果UIに統一"""
        self._run_aggregate()
        if hasattr(self, "hero"):
            self.hero.hide()
        self._hide_restart_button_if_exists()

    def _hide_restart_button_if_exists(self):
        """①②③画面にある『もう一度』『最初から』などのボタンを強制的に非表示にする"""
        for w in self.findChildren(QPushButton):
            t = w.text()
            if t and ("もう一度" in t or "最初から" in t):
                w.hide()

    # ====== 個人ランキング演出 ======

    def _start_person_reveal_animation(self):
        """個人ランキングの演出付き表示"""
        if not hasattr(self, '_person_data') or not self._person_data:
            return

        self.title_person.setText("🎊 集計中...")

        self._person_reveal_dots = 0
        self._person_reveal_timer = QTimer(self)

        def update_dots():
            self._person_reveal_dots = (self._person_reveal_dots + 1) % 4
            dots = "." * self._person_reveal_dots
            self.title_person.setText(f"🎊 集計中{dots}")

        self._person_reveal_timer.timeout.connect(update_dots)
        self._person_reveal_timer.start(300)

        # 1.2秒後にドラムロール風の演出
        QTimer.singleShot(1200, lambda: self._person_drumroll())

        # 2.4秒後にタイトルを元に戻して結果発表
        QTimer.singleShot(2400, lambda: [
            self._person_reveal_timer.stop(),
            self.title_person.setText("🏆 個人総合ランキング - 結果発表！！"),
            self._flash_widget(self.title_person),
            self._reveal_person_rankings()
        ])

    def _person_drumroll(self):
        """ドラムロール風の演出"""
        for i in range(6):
            QTimer.singleShot(i * 80, lambda: self._shake_widget(self.tbl_person))

    def _shake_widget(self, widget):
        """ウィジェットを微振動させる"""
        original_pos = widget.geometry()
        offset_x = random.randint(-3, 3)
        offset_y = random.randint(-3, 3)

        shaken = QRect(
            original_pos.x() + offset_x,
            original_pos.y() + offset_y,
            original_pos.width(),
            original_pos.height()
        )
        widget.setGeometry(shaken)
        QTimer.singleShot(40, lambda: widget.setGeometry(original_pos))

    def _flash_widget(self, widget):
        """ウィジェットをフラッシュさせる"""
        original_style = widget.styleSheet()
        flash_style = (
            original_style
            + f"\nbackground: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f" stop:0 {PRIMARY_ACCENT}, stop:1 {SECONDARY_ACCENT});"
        )
        widget.setStyleSheet(flash_style)
        QTimer.singleShot(200, lambda: widget.setStyleSheet(original_style))

    def _reveal_person_rankings(self):
        """個人ランキングを順番に表示（3位→2位→1位の順）"""
        if not hasattr(self, '_person_data') or not self._person_data:
            return

        model = self.tbl_person.model()
        if not model:
            return

        podium = [
            QColor(255, 215, 0, 45),
            QColor(192, 192, 192, 35),
            QColor(205, 127, 50, 35),
        ]

        # 全行を一旦透明に
        for row in range(model.rowCount()):
            for col in range(model.columnCount()):
                item = model.item(row, col)
                if item:
                    item.setText("")

        # 3位から順に表示（逆順）
        reveal_order = [2, 1, 0]
        for i, rank_idx in enumerate(reveal_order):
            if rank_idx >= len(self._person_data):
                continue
            delay = i * 800
            QTimer.singleShot(delay, lambda r=rank_idx: self._reveal_person_rank(r, podium))

    def _reveal_person_rank(self, rank_idx: int, podium):
        """指定順位を演出付きで表示"""
        if rank_idx >= len(self._person_data):
            return

        model = self.tbl_person.model()
        if not model:
            return

        podium_fg = [
            QColor(PODIUM_GOLD),
            QColor(PODIUM_SILVER),
            QColor(PODIUM_BRONZE),
        ]

        e = self._person_data[rank_idx]

        items = [
            QStandardItem(str(rank_idx + 1)),
            QStandardItem(e["participant"]),
            QStandardItem(e["overall_pt"]),
        ]

        for it in items:
            it.setEditable(False)
            f = QFont("", 12)
            f.setBold(True)
            it.setFont(f)
            it.setForeground(QBrush(podium_fg[rank_idx]))
            it.setBackground(QBrush(podium[rank_idx]))

        if rank_idx == 0:
            items[1].setText(f"👑 {e['participant']}")

        for c, it in enumerate(items):
            model.setItem(rank_idx, c, it)

        QTimer.singleShot(0, lambda: self._highlight_row(rank_idx))

        if rank_idx == 0:
            QTimer.singleShot(100, lambda: self._celebrate_first_place())

    def _highlight_row(self, row_idx: int):
        """行を一瞬ハイライト"""
        model = self.tbl_person.model()
        if not model:
            return

        original_colors = []
        for col in range(model.columnCount()):
            item = model.item(row_idx, col)
            if item:
                original_colors.append(item.background())

        highlight_color = QBrush(QColor(124, 92, 255, 80))
        for col in range(model.columnCount()):
            item = model.item(row_idx, col)
            if item:
                item.setBackground(highlight_color)

        def restore_colors():
            for col in range(model.columnCount()):
                item = model.item(row_idx, col)
                if item and col < len(original_colors):
                    item.setBackground(original_colors[col])

        QTimer.singleShot(400, restore_colors)

    def _celebrate_first_place(self):
        """1位の特別演出（画面全体フラッシュ）"""
        central = self.centralWidget()
        if not central:
            return

        original_style = central.styleSheet()
        flash_style = f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a1040, stop:0.5 #2a1860, stop:1 #1a1040);
            }}
        """
        central.setStyleSheet(flash_style)
        QTimer.singleShot(250, lambda: central.setStyleSheet(original_style))
