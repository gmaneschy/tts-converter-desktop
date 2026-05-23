"""
ui/engine_panel.py — seleção de engine TTS e parâmetros específicos de cada engine.
Usa QStackedWidget para mostrar apenas os controles do engine ativo.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QLabel, QComboBox, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QWidget, QDoubleSpinBox, QSpinBox,
    QLineEdit, QPushButton,
)
from PySide6.QtCore import Signal


def _row(label: str, widget, min_label=110) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(8)
    lbl = QLabel(label)
    lbl.setMinimumWidth(min_label)
    lay.addWidget(lbl)
    lay.addWidget(widget, 1)
    return lay


def _file_row(label: str, line_edit: QLineEdit, btn: QPushButton, min_label=110) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(6)
    lbl = QLabel(label)
    lbl.setMinimumWidth(min_label)
    lay.addWidget(lbl)
    lay.addWidget(line_edit, 1)
    lay.addWidget(btn)
    return lay


class _KokoroParams(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.voice_combo = QComboBox()
        # Vozes comuns do kokoro — o loader não expõe lista, então usamos as conhecidas
        for v in ["pf_dora", "af_heart", "af_bella", "af_nicole", "am_adam",
                  "am_michael", "bf_emma", "bf_isabella", "bm_george", "bm_lewis"]:
            self.voice_combo.addItem(v)
        lay.addLayout(_row("Voz:", self.voice_combo))

        self.lang_combo = QComboBox()
        for l in ["pt-br", "en-us", "en-gb", "es", "fr-fr", "ja", "zh", "ko", "hi", "it"]:
            self.lang_combo.addItem(l)
        lay.addLayout(_row("Idioma:", self.lang_combo))

        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 3.0)
        self.speed_spin.setSingleStep(0.05)
        self.speed_spin.setValue(1.0)
        lay.addLayout(_row("Velocidade:", self.speed_spin))

    def get_params(self) -> dict:
        return {
            "voice": self.voice_combo.currentText(),
            "lang": self.lang_combo.currentText(),
            "speed": self.speed_spin.value(),
        }

    def set_params(self, p: dict):
        idx = self.voice_combo.findText(p.get("voice", "pf_dora"))
        if idx >= 0:
            self.voice_combo.setCurrentIndex(idx)
        idx = self.lang_combo.findText(p.get("lang", "pt-br"))
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.speed_spin.setValue(float(p.get("speed", 1.0)))


class _SupertonicParams(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.voice_combo = QComboBox()
        for v in ["F5", "F4", "F3", "F2", "F1", "M5", "M4", "M3", "M2", "M1"]:
            self.voice_combo.addItem(v)
        lay.addLayout(_row("Voz:", self.voice_combo))

        self.lang_combo = QComboBox()
        for l in ["pt", "en", "es", "fr", "de", "it", "ja", "zh"]:
            self.lang_combo.addItem(l)
        lay.addLayout(_row("Idioma:", self.lang_combo))

        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 3.0)
        self.speed_spin.setSingleStep(0.05)
        self.speed_spin.setValue(1.05)
        lay.addLayout(_row("Velocidade:", self.speed_spin))

        self.steps_spin = QSpinBox()
        self.steps_spin.setRange(1, 50)
        self.steps_spin.setValue(10)
        lay.addLayout(_row("Total steps:", self.steps_spin))

    def get_params(self) -> dict:
        return {
            "voice": self.voice_combo.currentText(),
            "lang": self.lang_combo.currentText(),
            "speed": self.speed_spin.value(),
            "total_steps": self.steps_spin.value(),
        }

    def set_params(self, p: dict):
        idx = self.voice_combo.findText(p.get("voice", "F5"))
        if idx >= 0:
            self.voice_combo.setCurrentIndex(idx)
        idx = self.lang_combo.findText(p.get("lang", "pt"))
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.speed_spin.setValue(float(p.get("speed", 1.05)))
        self.steps_spin.setValue(int(p.get("total_steps", 10)))


class EnginePanel(QFrame):
    engine_changed = Signal(str)   # emitido quando o usuário troca de engine

    _ENGINE_NAMES = ["kokoro", "supertonic"]
    _ENGINE_LABELS = {
        "kokoro":    "Kokoro ONNX",
        "supertonic": "Supertonic",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        title = QLabel("ENGINE")
        title.setObjectName("section_title")
        lay.addWidget(title)

        # Engine selector
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        lbl = QLabel("Engine:")
        lbl.setMinimumWidth(70)
        self.engine_combo = QComboBox()
        for key in self._ENGINE_NAMES:
            self.engine_combo.addItem(self._ENGINE_LABELS[key], key)
        sel_row.addWidget(lbl)
        sel_row.addWidget(self.engine_combo, 1)
        lay.addLayout(sel_row)

        # Stacked params
        self._stack = QStackedWidget()
        self._kokoro_w     = _KokoroParams()
        self._supertonic_w = _SupertonicParams()
        self._stack.addWidget(self._kokoro_w)      # index 0
        self._stack.addWidget(self._supertonic_w)  # index 1
        lay.addWidget(self._stack)

        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)

    def _on_engine_changed(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self.engine_changed.emit(self._ENGINE_NAMES[idx])

    @property
    def engine(self) -> str:
        return self.engine_combo.currentData()

    def set_engine(self, name: str):
        idx = self._ENGINE_NAMES.index(name) if name in self._ENGINE_NAMES else 0
        self.engine_combo.setCurrentIndex(idx)

    def get_engine_params(self) -> dict:
        idx = self.engine_combo.currentIndex()
        return [self._kokoro_w, self._supertonic_w][idx].get_params()

    def set_engine_params(self, name: str, params: dict):
        mapping = {
            "kokoro": self._kokoro_w,
            "supertonic": self._supertonic_w,
        }
        w = mapping.get(name)
        if w:
            w.set_params(params)