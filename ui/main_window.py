"""
ui/main_window.py — janela principal do TTS Converter.

Layout:
  ┌─────────────────────────────────────────┐
  │  [TextPanel]          [EnginePanel]     │
  │  [StylePanel]         [RVCPanel]        │
  │  [AudioControls ─ span full width]      │
  └─────────────────────────────────────────┘

O loader é (re)criado a cada síntese se os parâmetros mudaram,
para evitar manter um engine pesado em RAM permanentemente enquanto
o usuário ainda está configurando. Uma vez carregado, é reutilizado
enquanto os parâmetros não mudam.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QLabel, QStatusBar, QPushButton,
    QFrame,
)

from ui.text_panel     import TextPanel
from ui.style_panel    import StylePanel
from ui.engine_panel   import EnginePanel
from ui.rvc_panel      import RVCPanel
from ui.audio_controls import AudioControls
from ui.worker         import SynthesisWorker
from src.config.settings import settings


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TTS Converter")
        self.setMinimumSize(960, 680)

        self._loader   = None   # loader TTS ativo
        self._loader_key: tuple | None = None  # chave de cache — evita reload desnecessário
        self._worker: SynthesisWorker | None = None
        self._last_wav: bytes | None = None

        self._build_ui()
        self._load_settings()

    # ------------------------------------------------------------------
    # UI

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)

        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(14, 14, 14, 14)
        root_lay.setSpacing(10)

        # ── header ───────────────────────────────────────────────────
        header = QHBoxLayout()
        lbl_title = QLabel("TTS CONVERTER")
        lbl_title.setStyleSheet(
            "font-size:18px; font-weight:bold; letter-spacing:4px; "
            "color:#c8922a; font-family:'JetBrains Mono','Consolas',monospace;"
        )
        self._lbl_engine_badge = QLabel()
        self._lbl_engine_badge.setStyleSheet(
            "font-size:10px; color:#6e6a62; letter-spacing:2px; "
            "font-family:'JetBrains Mono','Consolas',monospace;"
        )
        self._btn_synth = QPushButton("⚡  SINTETIZAR")
        self._btn_synth.setObjectName("btn_primary")
        self._btn_synth.setMinimumWidth(160)
        self._btn_synth.clicked.connect(self._on_synthesize)

        header.addWidget(lbl_title)
        header.addWidget(self._lbl_engine_badge)
        header.addStretch()
        header.addWidget(self._btn_synth)
        root_lay.addLayout(header)

        # ── divider ──────────────────────────────────────────────────
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color:#2e2e2e;")
        root_lay.addWidget(div)

        # ── main area (left | right) ──────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)

        # Left column
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(10)

        self.text_panel  = TextPanel()
        self.style_panel = StylePanel()
        left_lay.addWidget(self.text_panel, 3)
        left_lay.addWidget(self.style_panel)
        left_lay.addStretch()
        splitter.addWidget(left)

        # Right column
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(10)

        self.engine_panel = EnginePanel()
        self.rvc_panel    = RVCPanel()
        right_lay.addWidget(self.engine_panel)
        right_lay.addWidget(self.rvc_panel)
        right_lay.addStretch()
        splitter.addWidget(right)

        splitter.setSizes([560, 400])
        root_lay.addWidget(splitter, 1)

        # ── audio controls (full width) ───────────────────────────────
        self.audio_ctrl = AudioControls()
        root_lay.addWidget(self.audio_ctrl)

        # ── status bar ────────────────────────────────────────────────
        sb = QStatusBar()
        sb.setStyleSheet("color:#6e6a62; font-size:11px;")
        self.setStatusBar(sb)
        self._status_bar = sb

        # Connections
        self.engine_panel.engine_changed.connect(self._on_engine_changed)
        self.audio_ctrl.regenerate_requested.connect(self._on_synthesize)

    # ------------------------------------------------------------------
    # Settings persistence

    def _load_settings(self):
        # Engine
        eng = settings.get("engine", "kokoro")
        self.engine_panel.set_engine(eng)

        # Engine params
        kokoro_p = {
            "voice": settings.get("kokoro_voice", "pf_dora"),
            "lang":  settings.get("kokoro_lang",  "pt-br"),
            "speed": settings.get("kokoro_speed",  1.0),
        }
        suptonic_p = {
            "voice":       settings.get("supertonic_voice",       "F5"),
            "lang":        settings.get("supertonic_lang",        "pt"),
            "speed":       settings.get("supertonic_speed",       1.05),
            "total_steps": settings.get("supertonic_total_steps", 10),
        }
        self.engine_panel.set_engine_params("kokoro",    kokoro_p)
        self.engine_panel.set_engine_params("supertonic", suptonic_p)

        # Style
        self.style_panel.set_style(settings.get("last_style", "neutral"))

        # RVC
        rvc_p = {
            "enabled":      settings.get("rvc_enabled",    False),
            "rvc_env_path": settings.get("rvc_env_path",   ""),
            "model_path":   settings.get("rvc_model_path", ""),
            "index_path":   settings.get("rvc_index_path", "") or None,
            "pitch_shift":  settings.get("rvc_pitch_shift", 0),
            "f0_method":    settings.get("rvc_f0_method",   "rmvpe+"),
            "index_rate":   settings.get("rvc_index_rate",  0.66),
            "protect":      settings.get("rvc_protect",     0.33),
            "only_cpu":     settings.get("rvc_only_cpu",    False),
        }
        self.rvc_panel.set_params(rvc_p)
        self._update_engine_badge()

    def _save_settings(self):
        eng = self.engine_panel.engine
        settings.set("engine", eng)

        p = self.engine_panel.get_engine_params()
        if eng == "kokoro":
            settings.set("kokoro_voice", p.get("voice", "pf_dora"))
            settings.set("kokoro_lang",  p.get("lang",  "pt-br"))
            settings.set("kokoro_speed", p.get("speed",  1.0))
        elif eng == "supertonic":
            settings.set("supertonic_voice",       p.get("voice",       "F5"))
            settings.set("supertonic_lang",        p.get("lang",        "pt"))
            settings.set("supertonic_speed",       p.get("speed",       1.05))
            settings.set("supertonic_total_steps", p.get("total_steps", 10))

        settings.set("last_style", self.style_panel.style)

        rvc_p = self.rvc_panel.get_params()
        settings.set("rvc_enabled",    rvc_p["enabled"])
        settings.set("rvc_env_path",   rvc_p["rvc_env_path"])
        settings.set("rvc_model_path", rvc_p["model_path"])
        settings.set("rvc_index_path", rvc_p["index_path"] or "")
        settings.set("rvc_pitch_shift", rvc_p["pitch_shift"])
        settings.set("rvc_f0_method",  rvc_p["f0_method"])
        settings.set("rvc_index_rate", rvc_p["index_rate"])
        settings.set("rvc_protect",    rvc_p["protect"])
        settings.set("rvc_only_cpu",   rvc_p["only_cpu"])

        settings.save()

    # ------------------------------------------------------------------
    # Engine

    def _on_engine_changed(self, name: str):
        # Invalida o loader em cache para forçar recriação
        self._loader     = None
        self._loader_key = None
        self._update_engine_badge()

    def _update_engine_badge(self):
        labels = {"kokoro": "KOKORO ONNX", "supertonic": "SUPERTONIC"}
        self._lbl_engine_badge.setText(labels.get(self.engine_panel.engine, ""))

    def _make_loader_key(self) -> tuple:
        """Chave que identifica unicamente a configuração atual do loader."""
        eng = self.engine_panel.engine
        p   = self.engine_panel.get_engine_params()
        rvc = self.rvc_panel.get_params()
        # Constrói tupla determinística
        rvc_key = (
            rvc["enabled"], rvc.get("rvc_env_path",""),
            rvc["model_path"], rvc["index_path"],
            rvc["pitch_shift"], rvc["f0_method"],
            rvc["index_rate"], rvc["protect"], rvc["only_cpu"],
        )
        return (eng, tuple(sorted(p.items())), rvc_key)

    def _build_loader(self):
        """Constrói o loader TTS com os parâmetros atuais da UI."""
        from src.tts.loader import (
            KokoroTTSLoader, SupertonicTTSLoader,
        )

        eng = self.engine_panel.engine
        p   = self.engine_panel.get_engine_params()
        rvc_p = self.rvc_panel.get_params()

        # ── RVC ──────────────────────────────────────────────────────
        rvc = None
        if rvc_p["enabled"] and rvc_p["model_path"]:
            # Aplica o rvc_env_path informado pelo usuário ao env do OS
            if rvc_p.get("rvc_env_path"):
                os.environ["TTS_RVC_ENV_DIR"] = rvc_p["rvc_env_path"]

            from src.tts.rvc import RVCConverter
            if RVCConverter.is_available():
                try:
                    rvc = RVCConverter(
                        model_path  = rvc_p["model_path"],
                        index_path  = rvc_p["index_path"],
                        pitch_shift = rvc_p["pitch_shift"],
                        f0_method   = rvc_p["f0_method"],
                        index_rate  = rvc_p["index_rate"],
                        protect     = rvc_p["protect"],
                        only_cpu    = rvc_p["only_cpu"],
                    )
                except Exception as e:
                    self._status_bar.showMessage(f"⚠️ RVC não carregado: {e}", 6000)
            else:
                self._status_bar.showMessage(
                    "⚠️ rvc_env não encontrado no caminho configurado.", 6000
                )

        # ── Engine ───────────────────────────────────────────────────
        if eng == "kokoro":
            loader = KokoroTTSLoader(
                voice       = p.get("voice", "pf_dora"),
                lang        = p.get("lang",  "pt-br"),
                speed       = float(p.get("speed", 1.0)),
                rvc         = rvc,
            )
        elif eng == "supertonic":
            loader = SupertonicTTSLoader(
                voice_name  = p.get("voice", "F5"),
                lang        = p.get("lang",  "pt"),
                rvc         = rvc,
            )
        else:
            raise ValueError(f"Engine desconhecido: {eng}")

        return loader

    # ------------------------------------------------------------------
    # Synthesis

    def _on_synthesize(self):
        text = self.text_panel.text.strip()
        if not text:
            self._status_bar.showMessage("⚠️ Texto vazio.", 3000)
            return

        if self._worker and self._worker.isRunning():
            self._status_bar.showMessage("⚠️ Síntese em andamento…", 2000)
            return

        self._save_settings()
        self.audio_ctrl.set_synthesizing(True)
        self._btn_synth.setEnabled(False)

        # Reload do loader somente se os parâmetros mudaram
        new_key = self._make_loader_key()
        if self._loader is None or new_key != self._loader_key:
            try:
                self._loader     = self._build_loader()
                self._loader_key = new_key
            except Exception as e:
                self.audio_ctrl.show_error(str(e))
                self._btn_synth.setEnabled(True)
                return

        style = self.style_panel.style

        self._worker = SynthesisWorker(self._loader, text, style, parent=self)
        self._worker.finished.connect(self._on_synth_done)
        self._worker.error.connect(self._on_synth_error)
        self._worker.start()

    def _on_synth_done(self, wav_bytes: bytes):
        self._last_wav = wav_bytes
        self.audio_ctrl.load_audio(wav_bytes)
        self._btn_synth.setEnabled(True)
        self._status_bar.showMessage("✅ Síntese concluída.", 4000)

    def _on_synth_error(self, msg: str):
        self.audio_ctrl.show_error(msg)
        self._btn_synth.setEnabled(True)
        self._status_bar.showMessage(f"❌ {msg}", 8000)

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self._save_settings()
        # Encerra o worker RVC se ativo
        if self._loader is not None:
            try:
                # Qualquer loader pode ter um engine com rvc
                engine = getattr(self._loader, "engine", None)
                rvc = getattr(engine, "rvc", None) if engine else None
                if rvc:
                    rvc.shutdown()
            except Exception:
                pass
        super().closeEvent(event)