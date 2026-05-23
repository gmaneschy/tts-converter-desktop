"""
ui/style_panel.py — seleção de estilo TTS.
Lê os estilos disponíveis do módulo src/tts/styles.py.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QLabel, QComboBox, QVBoxLayout, QHBoxLayout,
)


# Estilos embutidos como fallback caso styles.py não esteja acessível ainda
_FALLBACK_STYLES = [
    "neutral", "happy", "sad", "angry", "fearful",
    "surprised", "disgusted", "excited", "calm",
    "whisper", "shouting",
]


def _load_styles() -> list[str]:
    try:
        from src.tts.styles import STYLE_PARAMS
        return sorted(STYLE_PARAMS.keys())
    except Exception:
        return _FALLBACK_STYLES


class StylePanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        title = QLabel("ESTILO")
        title.setObjectName("section_title")
        lay.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel("Estilo prosódico:")
        lbl.setMinimumWidth(110)
        row.addWidget(lbl)

        self.combo = QComboBox()
        for s in _load_styles():
            self.combo.addItem(s)
        row.addWidget(self.combo, 1)
        lay.addLayout(row)

    @property
    def style(self) -> str:
        return self.combo.currentText()

    def set_style(self, s: str):
        idx = self.combo.findText(s)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)