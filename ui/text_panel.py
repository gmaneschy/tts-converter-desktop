"""
ui/text_panel.py — área de texto e contador de caracteres.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QLabel, QPlainTextEdit, QVBoxLayout, QHBoxLayout,
)


class TextPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("TEXTO")
        title.setObjectName("section_title")
        self._char_count = QLabel("0 chars")
        self._char_count.setObjectName("status_label")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._char_count)
        lay.addLayout(header)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(
            "Digite ou cole o texto a ser sintetizado…"
        )
        self.text_edit.setMinimumHeight(140)
        self.text_edit.textChanged.connect(self._update_count)
        lay.addWidget(self.text_edit)

    def _update_count(self):
        n = len(self.text_edit.toPlainText())
        self._char_count.setText(f"{n} chars")

    @property
    def text(self) -> str:
        return self.text_edit.toPlainText()

    def set_text(self, t: str):
        self.text_edit.setPlainText(t)