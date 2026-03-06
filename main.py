# -*- coding: utf-8 -*-
"""PyInstaller エントリポイント"""
import sys
import os

os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

from app.__main__ import main

main()
