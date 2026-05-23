"""
src/utils/paths.py — caminhos centralizados para o TTS Converter standalone.
"""
from __future__ import annotations
from pathlib import Path
import sys
import os


def get_app_root() -> Path:
    """Raiz do projeto (pasta que contém main.py)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # Sobe de src/utils/ até a raiz
    return Path(__file__).resolve().parent.parent.parent


def src_dir() -> Path:
    return get_app_root() / "src"


def models_dir() -> Path:
    if getattr(sys, "frozen", False):
        return get_app_root() / "models"
    return src_dir() / "models"


def supertonic_dir() -> Path:
    return models_dir() / "tts" / "supertonic"


def kokoro_dir() -> Path:
    return models_dir() / "tts" / "kokoro"

def resource_path(relative: str) -> Path:
    """Resolve um caminho dentro do bundle (_MEIPASS) ou do projeto em dev."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative
    return get_app_root() / relative

# ---------------------------------------------------------------------------
# RVC — o rvc_env fica em um caminho configurável pelo usuário.
# Por padrão procura em <app_root>/rvc_env, mas pode ser sobrescrito
# via variável de ambiente TTS_RVC_ENV_DIR ou pelo settings.
# ---------------------------------------------------------------------------

def rvc_env_dir() -> Path:
    """Diretório do rvc_env (configurável)."""
    env_override = os.environ.get("TTS_RVC_ENV_DIR", "")
    if env_override:
        return Path(env_override)
    # fallback: lê do settings se disponível
    try:
        from src.config.settings import settings
        p = settings.get("rvc_env_path", "")
        if p:
            return Path(p)
    except Exception:
        pass
    return get_app_root() / "rvc_env"


def rvc_python_path() -> Path:
    base = rvc_env_dir()
    win = base / "Scripts" / "python.exe"
    if win.exists():
        return win
    return base / "bin" / "python"


def rvc_worker_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "rvc_worker_py" / "rvc_worker.py"
    return get_app_root() / "rvc_worker.py"


def rvc_models_dir() -> Path:
    return models_dir() / "rvc"