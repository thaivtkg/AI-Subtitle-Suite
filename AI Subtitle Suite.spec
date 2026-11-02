# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

project_root = os.path.abspath(SPECPATH)

# 1. Thu thập data files & dynamic libs từ các thư viện AI và lõi dịch
datas = []
datas += collect_data_files('faster_whisper')
datas += collect_data_files('ctranslate2')
datas += collect_data_files('huggingface_hub')
datas += collect_data_files('tokenizers')
datas += collect_data_files('llama_cpp')

# Đóng gói giao diện QML của CAT Studio
qml_dir = os.path.join(project_root, 'ui', 'qml_translation')
if os.path.exists(qml_dir):
    datas.append((qml_dir, os.path.join('ui', 'qml_translation')))

# Đóng gói FFmpeg và Resources theo đúng Contract của RuntimePaths
ffmpeg_dir = os.path.join(project_root, 'resources', 'ffmpeg')
if not os.path.exists(ffmpeg_dir):
    ffmpeg_dir = os.path.join(project_root, 'ffmpeg')
resources_dir = os.path.join(project_root, 'resources')

if os.path.exists(ffmpeg_dir):
    datas.append((ffmpeg_dir, 'ffmpeg'))
if os.path.exists(resources_dir):
    datas.append((resources_dir, 'resources'))

binaries = []
binaries += collect_dynamic_libs('ctranslate2')
binaries += collect_dynamic_libs('llama_cpp')

# Loại trừ Poppler ICU xung đột nếu có
_poppler_icu_names = {'icuuc.dll', 'icudt78.dll'}
_poppler_bin_marker = os.path.normcase(
    os.path.join('native', 'poppler', 'library', 'bin')
)

def _exclude_conflicting_poppler_icu(entries):
    filtered = []
    for entry in entries:
        destination, source, *metadata = entry
        source_path = os.path.normcase(os.path.normpath(str(source)))
        source_name = os.path.basename(source_path)
        if (
            source_name in _poppler_icu_names
            and _poppler_bin_marker in source_path
        ):
            continue
        filtered.append((destination, source, *metadata))
    return type(entries)(filtered)

# 2. Hidden imports để tránh lỗi thiếu module ngầm của PySide6, PyTorch, AI và nội bộ
hiddenimports = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'PySide6.QtQuick',
    'PySide6.QtQuickWidgets',
    'PySide6.QtQml',
    'PySide6.QtQuickControls2',
    'faster_whisper',
    'ctranslate2',
    'llama_cpp',
    'huggingface_hub',
    'tokenizers',
    'torch',
    'torchaudio',
    'psutil',
    'sqlite3',
    'unittest.mock',
    # Modules nội bộ của dự án
    'core',
    'core.translation',
    'core.subtitle_generation',
    'player',
    'ui',
    'workers',
]
hiddenimports += collect_submodules('faster_whisper')
hiddenimports += collect_submodules('ctranslate2')
hiddenimports += collect_submodules('llama_cpp')

# 3. Phân tích mã nguồn
a = Analysis(
    [os.path.join(project_root, 'main.py')],
    pathex=[project_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'pytest', 'IPython', 'notebook', 'curl_cffi'],
    noarchive=False,
    optimize=0,
)
a.binaries = _exclude_conflicting_poppler_icu(a.binaries)

pyz = PYZ(a.pure)

icon_file = os.path.join(project_root, 'resources', 'app_icon.ico')
if not os.path.exists(icon_file):
    icon_file = os.path.join(project_root, 'app_icon.ico')

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AI Subtitle Suite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file if os.path.exists(icon_file) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='AI Subtitle Suite',
)
