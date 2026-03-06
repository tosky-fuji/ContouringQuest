# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Contouring Quest (onedir mode)"""

import os
import glob
import sys
from PyInstaller.utils.hooks import (
    collect_submodules, collect_data_files, collect_dynamic_libs,
)

block_cipher = None

# サブモジュール自動収集
pyside6_imports = collect_submodules('PySide6')
scipy_imports = collect_submodules('scipy')
skimage_imports = collect_submodules('skimage')
nibabel_imports = collect_submodules('nibabel')

# DLL / .pyd 自動収集
scipy_binaries = collect_dynamic_libs('scipy')
skimage_binaries = collect_dynamic_libs('skimage')
numpy_binaries = collect_dynamic_libs('numpy')

# conda 環境の MKL / BLAS / OpenMP DLL を収集
# scipy._ufuncs が実行時にこれらを動的ロードするため必須
conda_prefix = os.path.dirname(sys.executable)
conda_lib_bin = os.path.join(conda_prefix, 'Library', 'bin')
mkl_binaries = []
if os.path.isdir(conda_lib_bin):
    for pattern in ['mkl_*.dll', 'libiomp5md.dll', 'libblas.dll',
                    'libcblas.dll', 'liblapack.dll']:
        for dll_path in glob.glob(os.path.join(conda_lib_bin, pattern)):
            mkl_binaries.append((dll_path, '.'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=scipy_binaries + skimage_binaries + numpy_binaries + mkl_binaries,
    datas=[
        ('nifti', 'nifti'),
        ('LICENSES', 'LICENSES'),
        ('NOTICES', 'NOTICES'),
    ],
    hiddenimports=[
        'shiboken6',
    ] + pyside6_imports + scipy_imports + skimage_imports + nibabel_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'tkinter',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ContoringQuest',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join('ビルド関係', 'icon', 'app_icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ContoringQuest',
)
