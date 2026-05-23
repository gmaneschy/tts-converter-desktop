# -*- mode: python ; coding: utf-8 -*-
"""
tts_converter.spec
==================
Spec para o TTS Converter — subprojeto isolado do Castorp.
Empacota apenas os engines Supertonic e Kokoro-ONNX + UI PySide6.

Estrutura de saída esperada em dist/tts_converter/TTSConverter/:

  TTSConverter.exe
  _internal/
      ...dlls, pyc, etc...
  config/                    ← YAMLs editáveis (copiados ao lado do .exe)
  models/
      tts/
          supertonic/        ← pesos Supertonic
          kokoro/            ← modelo ONNX + voices

Após o build:
  - Copie ou crie config/ ao lado do .exe conforme necessário.
  - Os modelos TTS devem estar em models/tts/ (mesmo esquema do Castorp).
"""

from PyInstaller.utils.hooks import collect_data_files, collect_all

block_cipher = None

# ---------------------------------------------------------------------------
# collect_all — pacotes com DLLs + dados + hiddenimports
# ---------------------------------------------------------------------------

# onnxruntime: providers nativos (CUDA, DirectML, CPU)
_onnx_datas,       _onnx_bins,       _onnx_hidden       = collect_all("onnxruntime")

# torch (CPU): kernels e libs — exigido pelo Supertonic
_torch_datas,      _torch_bins,      _torch_hidden      = collect_all("torch")

# kokoro_onnx: config.json, vocab e dados de runtime
_kokoro_datas,     _kokoro_bins,     _kokoro_hidden     = collect_all("kokoro_onnx")

# misaki: dados linguísticos usados pelo Kokoro
_misaki_datas,     _misaki_bins,     _misaki_hidden     = collect_all("misaki")

# supertonic: dados do pacote
_supertonic_datas, _supertonic_bins, _supertonic_hidden = collect_all("supertonic")

# scipy: dependência interna do Supertonic/torch
_scipy_datas,      _scipy_bins,      _scipy_hidden      = collect_all("scipy")

# espeakng: backend fonético do misaki/kokoro
_espeak_datas,     _espeak_bins,     _espeak_hidden     = collect_all("espeakng_loader")

# ---------------------------------------------------------------------------
# collect_data_files — pacotes apenas com dados (sem DLLs extras)
# Cadeia: kokoro_onnx → phonemizer → segments → csvw → language_tags
# ---------------------------------------------------------------------------

_phonemizer_datas  = collect_data_files("phonemizer")
_segments_datas    = collect_data_files("segments")
_csvw_datas        = collect_data_files("csvw")
_lang_tags_datas   = collect_data_files("language_tags")
_sounddevice_datas = collect_data_files("sounddevice")
_json5_datas       = collect_data_files("json5")

# ---------------------------------------------------------------------------
# Agrega datas
# ---------------------------------------------------------------------------

datas = []

datas += _onnx_datas
datas += _torch_datas
datas += _kokoro_datas
datas += _misaki_datas
datas += _supertonic_datas
datas += _scipy_datas
datas += _espeak_datas

datas += _phonemizer_datas
datas += _segments_datas
datas += _csvw_datas
datas += _lang_tags_datas
datas += _sounddevice_datas
datas += _json5_datas

# Ícone da aplicação (também referenciado na janela em runtime)
datas += [
    ("src/assets/hr.ico", "assets"),
]

# rvc_worker.py — bundled em _internal/rvc_worker_py/
# O rvc_env (python + dependências) é copiado separadamente ao lado do .exe.
datas += [
    ("rvc_worker.py", "rvc_worker_py"),
]

# ---------------------------------------------------------------------------
# Agrega binaries
# ---------------------------------------------------------------------------

binaries = []
binaries += _onnx_bins
binaries += _torch_bins
binaries += _kokoro_bins
binaries += _misaki_bins
binaries += _supertonic_bins
binaries += _scipy_bins
binaries += _espeak_bins

# ---------------------------------------------------------------------------
# hiddenimports
# ---------------------------------------------------------------------------

hiddenimports = []

hiddenimports += _onnx_hidden
hiddenimports += _torch_hidden
hiddenimports += _kokoro_hidden
hiddenimports += _misaki_hidden
hiddenimports += _supertonic_hidden
hiddenimports += _scipy_hidden
hiddenimports += _espeak_hidden

hiddenimports += [
    # Cadeia kokoro → phonemizer → segments → csvw → language_tags
    "phonemizer",
    "phonemizer.backend",
    "phonemizer.backend.espeak",
    "phonemizer.backend.segments",
    "segments",
    "csvw",
    "language_tags",
    # Áudio
    "sounddevice",
    "pyaudio",
    # Misc
    "yaml",
    "dotenv",
    "psutil",
    "requests",
    "json5",
    "pkg_resources.py2_warn",
]

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    name="TTSConverter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="src/assets/hr.ico",
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# ---------------------------------------------------------------------------
# Trees externas — ficam fora de _internal/, ao lado do .exe
# ---------------------------------------------------------------------------

models_tree = Tree("src/models", prefix="models", excludes=["*.pyc"])

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    models_tree,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TTSConverter",
)
