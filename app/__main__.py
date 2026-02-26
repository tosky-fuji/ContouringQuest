# -*- coding: utf-8 -*-
"""Contour Quest エントリポイント: python -m app"""

import sys
import os

os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

try:
    from PySide6.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)
except Exception:
    pass

from PySide6.QtWidgets import QApplication

try:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
except Exception:
    pass

from app.hub.hub_window import HubWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    hub = HubWindow()
    hub.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        import nibabel
        import numpy
        from scipy.ndimage import binary_dilation
        print("必要なライブラリが確認できました")
        main()
    except ImportError as e:
        print(f"必要なライブラリがインストールされていません: {e}")
        print("以下のコマンドでインストールしてください:")
        print("pip install PySide6 nibabel numpy scipy")
