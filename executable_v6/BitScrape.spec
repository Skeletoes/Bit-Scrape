# -*- mode: python ; coding: utf-8 -*-


from PyInstaller.utils.hooks import collect_data_files

invisible_core_datas = collect_data_files('invisible_core')
invisible_playwright_datas = collect_data_files('invisible_playwright')

a = Analysis(
    ['backend.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('.env', '.'),
    ] + invisible_core_datas + invisible_playwright_datas,
    hiddenimports=[
        'webview.platforms.edgechromium',
        'invisible_playwright',
        'invisible_playwright.cli',
        'invisible_core',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BitScrape',
    debug=False,
    console=False,
    icon='static/images/BitScrapeLogo.ico',
    onefile=True,
)
