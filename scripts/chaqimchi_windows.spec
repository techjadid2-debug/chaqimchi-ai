# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
import sys

block_cipher = None

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

added_data = [
    (os.path.join(BASE_DIR, 'cloud', 'static'), os.path.join('cloud', 'static')),
    (os.path.join(BASE_DIR, 'webapp', 'static'), os.path.join('webapp', 'static')),
    (os.path.join(BASE_DIR, 'config'), 'config'),
]

# Agar mavjud bo'lsa models papkasini ham qo'shamiz
models_dir = os.path.join(BASE_DIR, 'models')
if os.path.isdir(models_dir):
    added_data.append((models_dir, 'models'))

hidden_imports = [
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'fastapi',
    'starlette',
    'pydantic',
    'sqlite3',
    'cryptography',
    'cv2',
    'openvino',
    'chaqimchi_ai',
    'chaqimchi_ai.discovery',
    'chaqimchi_ai.events',
    'chaqimchi_ai.outbox',
    'chaqimchi_ai.retention',
    'chaqimchi_ai.retail.tracker',
    'chaqimchi_ai.retail.rules',
    'chaqimchi_ai.retail.lines',
    'cloud',
    'cloud.main',
    'cloud.store',
    'cloud.event_store',
    'cloud.alerts',
]

a = Analysis(
    [os.path.join(BASE_DIR, 'scripts', 'windows_entrypoint.py')],
    pathex=[BASE_DIR],
    binaries=[],
    datas=added_data,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pytest', 'unittest'],
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
    name='ChaqimchiAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Qora konsol oynasi chiqmaydi (GUI rejim)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ChaqimchiAI',
)
