"""
ui/worker.py — QThread worker para síntese TTS.
Emite sinais de progresso, resultado e erro sem bloquear a UI.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class SynthesisWorker(QThread):
    """
    Executa a síntese em thread separada.

    Signals
    -------
    finished(bytes)   — WAV bytes resultantes
    error(str)        — mensagem de erro
    """
    finished = Signal(bytes)
    error    = Signal(str)

    def __init__(self, loader, text: str, style: str, parent=None):
        super().__init__(parent)
        self._loader = loader
        self._text   = text
        self._style  = style

    def run(self):
        try:
            wav_bytes = self._loader.synthesize_bytes(self._text, self._style)
            self.finished.emit(wav_bytes)
        except Exception as e:
            self.error.emit(str(e))