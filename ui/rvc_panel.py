"""
ui/rvc_panel.py — configuração do RVC, incluindo path do rvc_env.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QLabel, QCheckBox, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QDoubleSpinBox, QSpinBox,
    QComboBox, QFileDialog, QWidget,
)
from PySide6.QtCore import Signal


def _row(label: str, widget, min_label=130) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(8)
    lbl = QLabel(label)
    lbl.setMinimumWidth(min_label)
    lay.addWidget(lbl)
    lay.addWidget(widget, 1)
    return lay


def _file_row(label: str, line_edit: QLineEdit, btn: QPushButton, min_label=130) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(6)
    lbl = QLabel(label)
    lbl.setMinimumWidth(min_label)
    lay.addWidget(lbl)
    lay.addWidget(line_edit, 1)
    lay.addWidget(btn)
    return lay


class RVCPanel(QFrame):
    rvc_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("RVC")
        title.setObjectName("section_title")
        self.enabled_cb = QCheckBox("Habilitado")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.enabled_cb)
        lay.addLayout(header)

        # Container que é habilitado/desabilitado junto com o checkbox
        self._container = QWidget()
        clay = QVBoxLayout(self._container)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(6)

        # ── rvc_env path ──────────────────────────────────────────
        self.env_edit = QLineEdit()
        self.env_edit.setPlaceholderText("Caminho para o diretório rvc_env …")
        env_btn = QPushButton("…")
        env_btn.setFixedWidth(32)
        env_btn.clicked.connect(self._browse_env)
        clay.addLayout(_file_row("rvc_env dir:", self.env_edit, env_btn))

        # ── model path ────────────────────────────────────────────
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("Caminho para o .pth do modelo …")
        model_btn = QPushButton("…")
        model_btn.setFixedWidth(32)
        model_btn.clicked.connect(lambda: self._browse_file(self.model_edit, "Modelo (*.pth *.pt)"))
        clay.addLayout(_file_row("Modelo (.pth):", self.model_edit, model_btn))

        # ── index path ────────────────────────────────────────────
        self.index_edit = QLineEdit()
        self.index_edit.setPlaceholderText("Caminho para o .index (opcional) …")
        index_btn = QPushButton("…")
        index_btn.setFixedWidth(32)
        index_btn.clicked.connect(lambda: self._browse_file(self.index_edit, "Index (*.index)"))
        clay.addLayout(_file_row("Index (.index):", self.index_edit, index_btn))

        # ── pitch shift ───────────────────────────────────────────
        self.pitch_spin = QSpinBox()
        self.pitch_spin.setRange(-24, 24)
        self.pitch_spin.setValue(0)
        self.pitch_spin.setSuffix(" st")
        clay.addLayout(_row("Pitch shift:", self.pitch_spin))

        # ── F0 method ─────────────────────────────────────────────
        self.f0_combo = QComboBox()
        for m in ["rmvpe+", "rmvpe", "pm", "harvest", "dio", "crepe", "crepe-tiny"]:
            self.f0_combo.addItem(m)
        clay.addLayout(_row("Método F0:", self.f0_combo))

        # ── index rate ────────────────────────────────────────────
        self.index_rate_spin = QDoubleSpinBox()
        self.index_rate_spin.setRange(0.0, 1.0)
        self.index_rate_spin.setSingleStep(0.05)
        self.index_rate_spin.setValue(0.66)
        clay.addLayout(_row("Index rate:", self.index_rate_spin))

        # ── protect ───────────────────────────────────────────────
        self.protect_spin = QDoubleSpinBox()
        self.protect_spin.setRange(0.0, 0.5)
        self.protect_spin.setSingleStep(0.01)
        self.protect_spin.setValue(0.33)
        clay.addLayout(_row("Protect:", self.protect_spin))

        # ── only cpu ─────────────────────────────────────────────
        self.cpu_cb = QCheckBox("Forçar CPU (only_cpu)")
        clay.addWidget(self.cpu_cb)

        lay.addWidget(self._container)

        # Lógica enabled/disabled
        self.enabled_cb.toggled.connect(self._on_toggle)
        self._container.setEnabled(False)
        self.enabled_cb.toggled.connect(self.rvc_toggled)

    def _on_toggle(self, checked: bool):
        self._container.setEnabled(checked)

    def _browse_env(self):
        path = QFileDialog.getExistingDirectory(self, "Selecionar diretório rvc_env")
        if path:
            self.env_edit.setText(path)

    def _browse_file(self, edit: QLineEdit, filter_str: str):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar arquivo", "", filter_str)
        if path:
            edit.setText(path)

    def get_params(self) -> dict:
        return {
            "enabled":     self.enabled_cb.isChecked(),
            "rvc_env_path": self.env_edit.text().strip(),
            "model_path":  self.model_edit.text().strip(),
            "index_path":  self.index_edit.text().strip() or None,
            "pitch_shift": self.pitch_spin.value(),
            "f0_method":   self.f0_combo.currentText(),
            "index_rate":  self.index_rate_spin.value(),
            "protect":     self.protect_spin.value(),
            "only_cpu":    self.cpu_cb.isChecked(),
        }

    def set_params(self, p: dict):
        self.enabled_cb.setChecked(bool(p.get("enabled", False)))
        self.env_edit.setText(p.get("rvc_env_path", ""))
        self.model_edit.setText(p.get("model_path", ""))
        self.index_edit.setText(p.get("index_path") or "")
        self.pitch_spin.setValue(int(p.get("pitch_shift", 0)))
        idx = self.f0_combo.findText(p.get("f0_method", "rmvpe+"))
        if idx >= 0:
            self.f0_combo.setCurrentIndex(idx)
        self.index_rate_spin.setValue(float(p.get("index_rate", 0.66)))
        self.protect_spin.setValue(float(p.get("protect", 0.33)))
        self.cpu_cb.setChecked(bool(p.get("only_cpu", False)))