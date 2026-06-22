"""
ui/audio_controls.py — waveform mini-visualizador, player inline e botões de ação.
"""
from __future__ import annotations
import io
import wave
import threading

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QProgressBar, QWidget, QFileDialog,
    QSizePolicy,
)

try:
    import sounddevice as sd
    _SD_AVAILABLE = True
except ImportError:
    _SD_AVAILABLE = False


class _WaveformWidget(QWidget):
    """Mini visualizador de forma de onda (estático, baseado no WAV carregado)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(50)
        self.setMaximumHeight(70)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._samples: np.ndarray | None = None
        self._accent   = QColor("#c8922a")
        self._accent_lo = QColor("#7a5418")
        self._bg       = QColor("#171717")
        self._playhead = 0.0   # 0.0 – 1.0

    def load_wav(self, wav_bytes: bytes):
        try:
            buf = io.BytesIO(wav_bytes)
            with wave.open(buf) as wf:
                n = wf.getnframes()
                raw = wf.readframes(n)
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            # Downsample para display
            target = 400
            if len(arr) > target:
                factor = len(arr) // target
                arr = arr[:factor * target].reshape(-1, factor).max(axis=1)
            self._samples = arr
        except Exception:
            self._samples = None
        self._playhead = 0.0
        self.update()

    def set_playhead(self, frac: float):
        self._playhead = max(0.0, min(1.0, frac))
        self.update()

    def clear(self):
        self._samples = None
        self._playhead = 0.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid = h // 2

        p.fillRect(0, 0, w, h, self._bg)

        if self._samples is None or len(self._samples) == 0:
            # Linha de referência vazia
            p.setPen(QPen(self._accent_lo, 1))
            p.drawLine(0, mid, w, mid)
            return

        n = len(self._samples)
        # Largura de cada barra em ponto flutuante: a soma das n barras
        # preenche exatamente "w" pixels. Antes, bar_w era inteiro
        # (w // n) e o avanço de x parava antes da borda direita
        # sempre que w não fosse múltiplo de n — a onda ficava
        # "encolhida" enquanto a linha de playhead (px = frac * w) ia
        # até o fim real do widget. Resultado: a barrinha de progresso
        # destacava a onda já tocada fora do ritmo do áudio.
        bar_w = w / n

        for i in range(n):
            amp = abs(float(self._samples[i]))
            bar_h = int(amp * mid * 0.9)
            frac = i / n
            color = self._accent if frac <= self._playhead else self._accent_lo
            x_center = int((i + 0.5) * bar_w)
            pen_w = max(1, round(bar_w))
            p.setPen(QPen(color, pen_w))
            p.drawLine(x_center, mid - bar_h, x_center, mid + bar_h)

        # playhead line
        if self._playhead > 0:
            px = int(self._playhead * w)
            p.setPen(QPen(QColor("#e0a83a"), 1))
            p.drawLine(px, 0, px, h)


class AudioControls(QFrame):
    """
    Controles de áudio: waveform, play, regenerar, download.

    Signals
    -------
    regenerate_requested — usuário clicou em "Gerar novamente"
    """
    regenerate_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self._wav_bytes: bytes | None = None
        self._play_thread: threading.Thread | None = None
        self._playing = False
        self._playhead_timer = QTimer(self)
        self._playhead_timer.setInterval(50)
        self._playhead_timer.timeout.connect(self._update_playhead)
        self._play_start_time: float = 0.0
        self._wav_duration: float = 0.0
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        title = QLabel("ÁUDIO")
        title.setObjectName("section_title")
        lay.addWidget(title)

        self._waveform = _WaveformWidget()
        lay.addWidget(self._waveform)

        # Status / duração
        self._status = QLabel("—")
        self._status.setObjectName("status_label")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._status)

        # Progress bar (síntese)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate
        self._progress.setFixedHeight(4)
        self._progress.setVisible(False)
        lay.addWidget(self._progress)

        # Botões
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_play = QPushButton("▶  PLAY")
        self._btn_play.setObjectName("btn_primary")
        self._btn_play.setEnabled(False)
        self._btn_play.clicked.connect(self._on_play)
        btn_row.addWidget(self._btn_play)

        self._btn_regen = QPushButton("↺  GERAR NOVAMENTE")
        self._btn_regen.clicked.connect(self.regenerate_requested)
        btn_row.addWidget(self._btn_regen)

        self._btn_save = QPushButton("⬇  SALVAR WAV")
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_save)

        lay.addLayout(btn_row)

    # ------------------------------------------------------------------
    def set_synthesizing(self, active: bool):
        """Mostra/esconde a barra de progresso indeterminada durante síntese."""
        self._progress.setVisible(active)
        self._btn_regen.setEnabled(not active)
        if active:
            self._status.setText("Sintetizando…")

    def load_audio(self, wav_bytes: bytes):
        self._wav_bytes = wav_bytes
        self._waveform.load_wav(wav_bytes)
        self._wav_duration = self._get_duration(wav_bytes)
        self._status.setText(f"Pronto  ·  {self._wav_duration:.2f}s")
        self._progress.setVisible(False)
        self._btn_play.setEnabled(True)
        self._btn_save.setEnabled(True)

    def show_error(self, msg: str):
        self._progress.setVisible(False)
        self._status.setText(f"Erro: {msg}")
        self._btn_regen.setEnabled(True)

    # ------------------------------------------------------------------
    @staticmethod
    def _get_duration(wav_bytes: bytes) -> float:
        try:
            buf = io.BytesIO(wav_bytes)
            with wave.open(buf) as wf:
                return wf.getnframes() / wf.getframerate()
        except Exception:
            return 0.0

    def _on_play(self):
        if not _SD_AVAILABLE or not self._wav_bytes:
            return
        if self._playing:
            # stop
            try:
                sd.stop()
            except Exception:
                pass
            self._stop_playback()
            return

        buf = io.BytesIO(self._wav_bytes)
        try:
            with wave.open(buf) as wf:
                n  = wf.getnframes()
                sr = wf.getframerate()
                raw = wf.readframes(n)
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        except Exception as e:
            self._status.setText(f"Erro ao ler áudio: {e}")
            return

        self._playing = True
        self._btn_play.setText("■  PARAR")
        import time
        self._play_start_time = time.monotonic()
        self._playhead_timer.start()

        def _play():
            try:
                sd.play(arr, samplerate=sr)
                sd.wait()
            except Exception:
                pass
            finally:
                self._stop_playback_safe()

        self._play_thread = threading.Thread(target=_play, daemon=True)
        self._play_thread.start()

    def _stop_playback_safe(self):
        # chamado de thread — post para o main thread via QTimer
        QTimer.singleShot(0, self._stop_playback)

    def _stop_playback(self):
        self._playing = False
        self._playhead_timer.stop()
        self._waveform.set_playhead(0.0)
        self._btn_play.setText("▶  PLAY")
        self._status.setText(f"Pronto  ·  {self._wav_duration:.2f}s")

    def _update_playhead(self):
        import time
        elapsed = time.monotonic() - self._play_start_time
        if self._wav_duration > 0:
            frac = elapsed / self._wav_duration
            self._waveform.set_playhead(frac)
            self._status.setText(f"{min(elapsed, self._wav_duration):.1f}s / {self._wav_duration:.1f}s")
            if frac >= 1.0:
                self._stop_playback()

    def _on_save(self):
        if not self._wav_bytes:
            return
        from src.config.settings import settings
        last_dir = settings.get("last_save_dir", "")
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar áudio WAV", last_dir, "WAV (*.wav)"
        )
        if not path:
            return
        if not path.endswith(".wav"):
            path += ".wav"
        try:
            from pathlib import Path
            Path(path).write_bytes(self._wav_bytes)
            from pathlib import Path as P
            settings.set("last_save_dir", str(P(path).parent))
            settings.save()
            self._status.setText(f"Salvo em {path}")
        except Exception as e:
            self._status.setText(f"Erro ao salvar: {e}")