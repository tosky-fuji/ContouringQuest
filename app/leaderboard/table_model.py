# -*- coding: utf-8 -*-
"""テーブルモデル"""

from typing import List, Dict

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtWidgets import QTableView, QHeaderView


def _safe_str(x) -> str:
    return "" if x is None else str(x)


class DictTableModel(QAbstractTableModel):
    def __init__(self, rows: List[Dict[str, str]], headers: List[str], parent=None):
        super().__init__(parent)
        self.rows = rows
        self.headers = headers

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = index.row()
        c = index.column()
        if r >= len(self.rows) or c >= len(self.headers):
            return None
        if role == Qt.DisplayRole:
            return _safe_str(self.rows[r].get(self.headers[c], ""))
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.headers[section]
        return str(section + 1)


def make_table(view: QTableView, rows: List[Dict[str, str]], headers: List[str]):
    model = DictTableModel(rows, headers, view)
    proxy = QSortFilterProxyModel(view)
    proxy.setSourceModel(model)
    view.setModel(proxy)
    view.setSortingEnabled(True)
    h = view.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.Stretch)
    view.verticalHeader().setVisible(False)
