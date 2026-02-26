# -*- coding: utf-8 -*-
"""リーダーボード設定ダイアログ（パスワード保護）"""

from typing import Tuple

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QDialogButtonBox, QFileDialog,
)

from app.common.styles import BASE_STYLESHEET, btn_style


class SettingsDialog(QDialog):
    def __init__(self, records_dir: str, year: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("設定（パスワード: kochi）")
        self.resize(560, 160)
        self.setStyleSheet(BASE_STYLESHEET)
        self._records_dir = records_dir
        self._year = year

        layout = QVBoxLayout(self)

        # records
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("records フォルダ:"))
        self.dir_edit = QLineEdit(records_dir)
        row1.addWidget(self.dir_edit, 1)
        btn_browse = QPushButton("選択")
        btn_browse.setStyleSheet(btn_style(outline=True))
        btn_browse.clicked.connect(self._choose_dir)
        row1.addWidget(btn_browse)
        layout.addLayout(row1)

        # 年度
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("年度:"))
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2000, 2100)
        self.year_spin.setValue(year)
        row2.addWidget(self.year_spin)
        layout.addLayout(row2)

        # ボタン
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "records フォルダを選択", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    @property
    def result(self) -> Tuple[str, int]:
        return self.dir_edit.text().strip(), int(self.year_spin.value())
