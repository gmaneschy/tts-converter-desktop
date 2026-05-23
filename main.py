"""
main.py — entry point do TTS Converter.

Uso:
    python main.py

Dependências de sistema:
    PySide6, sounddevice, numpy
    (+ dependências de cada engine TTS conforme selecionado)
"""
from __future__ import annotations
import sys
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Garante que a raiz do projeto está no sys.path para imports absolutos
# do tipo "src.tts.engine", "ui.main_window", etc.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# HF_HOME — evita que o Supertonic grave no home global do usuário
# ---------------------------------------------------------------------------
_HF_CACHE = _ROOT / "src" / "models" / "tts" / "supertonic" / ".cache" / "huggingface"
os.environ.setdefault("HF_HOME", str(_HF_CACHE))

# ---------------------------------------------------------------------------
# UTF-8 em stdout/stderr (evita UnicodeEncodeError com emojis no Windows)
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Qt imports — somente após configurar env vars
# ---------------------------------------------------------------------------
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QFont
from src.utils.paths import resource_path
from PySide6.QtGui import QIcon

import ui.theme as theme
from ui.main_window import MainWindow


def main():
    # High-DPI
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(resource_path("assets/hr.ico"))))
    app.setApplicationName("TTS Converter")
    app.setOrganizationName("tts_converter")

    # Aplica tema
    theme.apply(app)

    # Fonte padrão
    font = QFont("JetBrains Mono", 11)
    font.setStyleHint(QFont.StyleHint.Monospace)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()