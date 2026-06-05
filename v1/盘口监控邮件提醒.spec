# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置文件 — 盘口监控与邮件提醒系统
使用方法: pyinstaller 盘口监控邮件提醒.spec
"""

import os
import sys

# 获取当前目录（.spec文件所在目录）
SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))

block_cipher = None

a = Analysis(
    [os.path.join(SPEC_DIR, '盘口监控邮件提醒.py')],
    pathex=[SPEC_DIR],
    binaries=[],
    datas=[
        # 邮件配置文件（打包后随程序一起发布）
        (os.path.join(SPEC_DIR, 'email_config.json'), '.'),
        # 数据文件目录（如果里面有需要打包的资源）
        # (os.path.join(SPEC_DIR, '数据文件'), '数据文件'),
    ],
    hiddenimports=[
        # PyQt5 相关
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        # DrissionPage 及其依赖（关键！必须显式声明）
        'DrissionPage',
        'DrissionPage._pages.chromium_page',
        'DrissionPage._configs.chromium_options',
        'DrissionPage._units.driver',
        'DrissionPage._units.setter',
        'DrissionPage._units.cookies',
        'DrissonPage._units.rect',  # 兼容新旧版本拼写
        'DrissionPage._units.rect',
        'DrissionPage._elements.chromium_element',
        'DrissionPage._elements.session_element',
        'DrissionPage._funcs',
        # requests + urllib3（requests 内部依赖链）
        'requests',
        'urllib3',
        'charset_normalizer',
        'certifi',
        'idna',
        # BeautifulSoup4
        'bs4',
        'bs4.builder',
        '_htmlparser',
        'html.parser',
        # 标准库中可能被动态引用的模块
        'winsound',
        'smtplib',
        'email',
        'email.mime',
        'email.mime.text',
        'email.header',
        'email.utils',
        'json',
        'threading',
        'concurrent.futures',
        'multiprocessing',
        # 编码相关（titan007 页面用 gb2312）
        'encodings.gb2312',
        'encodings.gbk',
        'encodings.utf_8',
        'encodings.iso8859_1',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大型库，减小包体积
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'tkinter',
        'jupyter',
        'IPython',
        'notebook',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='盘口监控邮件提醒',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # False = 不显示黑色命令行窗口（GUI程序）
    icon=None,              # 可替换为 .ico 图标路径，如: icon='app.ico'
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='盘口监控邮件提醒',
)
