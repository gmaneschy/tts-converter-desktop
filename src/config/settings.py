"""
src/config/settings.py — configurações persistidas em JSON.
"""
from __future__ import annotations
import json
from pathlib import Path

_SETTINGS_FILE = Path(__file__).resolve().parent.parent.parent / "settings.json"

_DEFAULTS: dict = {
    # Paths
    "rvc_env_path": "",
    # Engine ativo
    "engine": "kokoro",           # "kokoro" | "supertonic"
    # Kokoro
    "kokoro_voice": "pf_dora",
    "kokoro_lang": "pt-br",
    "kokoro_speed": 1.0,
    # Supertonic
    "supertonic_voice": "F5",
    "supertonic_lang": "pt",
    "supertonic_speed": 1.05,
    "supertonic_total_steps": 10,
    # RVC
    "rvc_enabled": False,
    "rvc_model_path": "",
    "rvc_index_path": "",
    "rvc_pitch_shift": 0,
    "rvc_f0_method": "rmvpe+",
    "rvc_index_rate": 0.66,
    "rvc_protect": 0.33,
    "rvc_only_cpu": False,
    # Último estilo usado
    "last_style": "neutral",
    # Último diretório de download
    "last_save_dir": "",
}


class Settings:
    def __init__(self):
        self._data: dict = dict(_DEFAULTS)
        self._load()

    def _load(self):
        if _SETTINGS_FILE.exists():
            try:
                with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except Exception as e:
                print(f"⚠️ Não foi possível carregar settings: {e}")

    def save(self):
        try:
            _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Não foi possível salvar settings: {e}")

    def get(self, key: str, default=None):
        return self._data.get(key, _DEFAULTS.get(key, default))

    def set(self, key: str, value):
        self._data[key] = value

    def update(self, d: dict):
        self._data.update(d)

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value


settings = Settings()