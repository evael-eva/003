# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 — 比赛初盘筛选工具 (macOS)
使用方法: pyinstaller --clean 比赛初盘筛选工具.spec
"""

import os
SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
block_cipher = None

a = Analysis(
    [os.path.join(SPEC_DIR, '比赛初盘筛选工具.py')],
    pathex=[SPEC_DIR],
    binaries=[],
    datas=[
        (os.path.join(SPEC_DIR, 'proxy_config.json'), '.'),
    ],
    hiddenimports=[
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'DrissionPage',
        'DrissionPage._pages.chromium_page',
        'DrissionPage._configs.chromium_options',
        'DrissionPage._units.driver',
        'DrissionPage._units.setter',
        'DrissionPage._units.cookies',
        'DrissionPage._units.rect',
        'DrissionPage._elements.chromium_element',
        'DrissionPage._elements.session_element',
        'DrissionPage._funcs',
        'requests',
        'urllib3',
        'charset_normalizer',
        'certifi',
        'idna',
        'bs4',
        'bs4.builder',
        '_htmlparser',
        'html.parser',
        'json',
        'threading',
        'concurrent.futures',
        'multiprocessing',
        'encodings.gb2312',
        'encodings.gbk',
        'encodings.utf_8',
        'encodings.iso8859_1',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'PIL', 'cv2', 'tkinter',
        'jupyter', 'IPython', 'notebook',
        'winsound', 'winreg', 'win32api', 'win32con',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='比赛初盘筛选工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='比赛初盘筛选工具',
)

app = BUNDLE(
    coll,
    name='比赛初盘筛选工具.app',
    bundle_identifier='com.evael.matchfilter',
    version='1.0.0',
    info_plist={
        'CFBundleName': '比赛初盘筛选工具',
        'CFBundleDisplayName': '比赛初盘筛选工具',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
    },
)
