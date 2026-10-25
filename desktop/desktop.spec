# Build with: python -m desktop.build
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
work = root / 'build/desktop-package'
stage = work / 'source'
sys.path.insert(0, str(stage))
data = []
binaries = []
hidden = []
for package in ['videodl', 'fake_useragent', 'tldextract', 'pycountry', 'emoji', 'DrissionPage', 'DrissionGet', 'DrissionRecord', 'nodejs_wheel', 'nodejs_wheel_binaries', 'pyfreeproxy', 'freeproxy', 'puremagic']:
    hidden += collect_submodules(package)
    data += collect_data_files(package, excludes=['**/*.wvd', '**/__pycache__/**', '**/tests/**'])
    binaries += collect_dynamic_libs(package)
for package in ['videofetch', 'fake-useragent', 'pyfreeproxy', 'nodejs-wheel', 'nodejs-wheel-binaries', 'DrissionPage', 'DrissionGet', 'DrissionRecord', 'pywidevine', 'construct', 'puremagic']:
    data += copy_metadata(package)
data += [(str(root / 'desktop/assets/check.svg'), 'desktop/assets'), (str(root / 'desktop/upstream.json'), 'desktop'), (str(work / 'build-info.json'), 'desktop')]
tools = Path(os.environ['VIDEODL_BUILD_TOOLS'])
for path in tools.iterdir():
    if path.suffix.lower() in {'.exe', '.dll'} and (path.suffix.lower() != '.exe' or path.stem in {'ffmpeg', 'ffprobe'}):
        binaries.append((str(path), 'tools'))
hidden += ['desktop.worker', 'desktop.adapter', 'desktop.updates', 'Crypto', 'Cryptodome', 'curl_cffi', 'quickjs', 'lxml.etree']
for p in ['Crypto', 'Cryptodome']:
    hidden += collect_submodules(p, filter=lambda name: '.SelfTest' not in name)
    binaries += collect_dynamic_libs(p)
a = Analysis([str(root / 'desktop/entry.py')], pathex=[str(stage), str(root)], binaries=binaries, datas=data,
    hiddenimports=hidden, hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtPdf', 'PySide6.QtQml', 'PySide6.QtQuick', 'tkinter', 'pytest', 'numpy', 'IPython'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='VideoDL Desktop', icon=str(root / 'desktop/assets/app.ico'), debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    disable_windowed_traceback=False, target_arch=None, codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='VideoDL Desktop')
