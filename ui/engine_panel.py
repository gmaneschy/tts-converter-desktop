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
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QStandardItem, QFont


# ---------------------------------------------------------------------------
# Dados canônicos
# ---------------------------------------------------------------------------

# Kokoro: todas as vozes agrupadas por idioma.
# Formato: (label_grupo, lang_code, [(voice_id, display_label), ...])
_KOKORO_LANGS: list[tuple[str, str]] = [
    ("pt-br", "🇧🇷 Brazilian Portuguese"),
    ("en-us", "🇺🇸 American English"),
    ("en-gb", "🇬🇧 British English"),
    ("ja", "🇯🇵 Japanese"),
    ("zh", "🇨🇳 Mandarin Chinese"),
    ("es", "🇪🇸 Spanish"),
    ("fr-fr", "🇫🇷 French"),
    ("hi", "🇮🇳 Hindi"),
    ("it", "🇮🇹 Italian"),
]

# Apenas as vozes estáticas (Chinês foi removido para ser carregado dinamicamente)
_KOKORO_STATIC_VOICES: dict[str, list[tuple[str, str]]] = {
    "pt-br": [
        ("pf_dora",  "pf_dora  🚺"),
        ("pm_alex",  "pm_alex  🚹"),
        ("pm_santa", "pm_santa 🚹"),
    ],
    "en-us": [
        ("af_heart",   "af_heart   🚺❤️"), ("af_alloy",   "af_alloy   🚺"),
        ("af_aoede",   "af_aoede   🚺"),   ("af_bella",   "af_bella   🚺🔥"),
        ("af_jessica", "af_jessica 🚺"),   ("af_kore",    "af_kore    🚺"),
        ("af_nicole",  "af_nicole  🚺🎧"), ("af_nova",    "af_nova    🚺"),
        ("af_river",   "af_river   🚺"),   ("af_sarah",   "af_sarah   🚺"),
        ("af_sky",     "af_sky     🚺"),   ("am_adam",    "am_adam    🚹"),
        ("am_echo",    "am_echo    🚹"),   ("am_eric",    "am_eric    🚹"),
        ("am_fenrir",  "am_fenrir  🚹"),   ("am_liam",    "am_liam    🚹"),
        ("am_michael", "am_michael 🚹"),   ("am_onyx",    "am_onyx    🚹"),
        ("am_puck",    "am_puck    🚹"),   ("am_santa",   "am_santa   🚹"),
    ],
    "en-gb": [
        ("bf_alice",    "bf_alice    🚺"), ("bf_emma",     "bf_emma     🚺"),
        ("bf_isabella", "bf_isabella 🚺"), ("bf_lily",     "bf_lily     🚺"),
        ("bm_daniel",   "bm_daniel   🚹"), ("bm_fable",    "bm_fable    🚹"),
        ("bm_george",   "bm_george   🚹"), ("bm_lewis",    "bm_lewis    🚹"),
    ],
    "ja": [
        ("jf_alpha",     "jf_alpha     🚺"), ("jf_gongitsune","jf_gongitsune 🚺"),
        ("jf_nezumi",    "jf_nezumi    🚺"), ("jf_tebukuro",  "jf_tebukuro  🚺"),
        ("jm_kumo",      "jm_kumo      🚹"),
    ],
    "es": [
        ("ef_dora",  "ef_dora  🚺"), ("em_alex",  "em_alex  🚹"), ("em_santa", "em_santa 🚹"),
    ],
    "fr-fr": [("ff_siwis", "ff_siwis 🚺")],
    "hi": [
        ("hf_alpha", "hf_alpha 🚺"), ("hf_beta",  "hf_beta  🚺"),
        ("hm_omega", "hm_omega 🚹"), ("hm_psi",   "hm_psi   🚹"),
    ],
    "it": [
        ("if_sara",   "if_sara   🚺"), ("im_nicola", "im_nicola 🚹"),
    ],
}
# Lista de todas as vozes encontradas no arquivo oficial unificado v1.1-zh
_KOKORO_ZH_VOICES: list[tuple[str, str]] = [
    # Vozes Híbridas / Especiais
    ("af_maple", "af_maple 🚺 🇺🇸/🇨🇳"),
    ("af_sol", "af_sol   🚺 🇺🇸/🇨🇳"),
    ("bf_vale", "bf_vale  🚺 🇬🇧/🇨🇳"),

    # Vozes Femininas (zf_*)
    ("zf_001", "zf_001 🚺 🇨🇳"),
    ("zf_002", "zf_002 🚺 🇨🇳"),
    ("zf_003", "zf_003 🚺 🇨🇳"),
    ("zf_004", "zf_004 🚺 🇨🇳"),
    ("zf_005", "zf_005 🚺 🇨🇳"),
    ("zf_006", "zf_006 🚺 🇨🇳"),
    ("zf_007", "zf_007 🚺 🇨🇳"),
    ("zf_008", "zf_008 🚺 🇨🇳"),
    ("zf_017", "zf_017 🚺 🇨🇳"),
    ("zf_018", "zf_018 🚺 🇨🇳"),
    ("zf_019", "zf_019 🚺 🇨🇳"),
    ("zf_021", "zf_021 🚺 🇨🇳"),
    ("zf_022", "zf_022 🚺 🇨🇳"),
    ("zf_023", "zf_023 🚺 🇨🇳"),
    ("zf_024", "zf_024 🚺 🇨🇳"),
    ("zf_026", "zf_026 🚺 🇨🇳"),
    ("zf_027", "zf_027 🚺 🇨🇳"),
    ("zf_028", "zf_028 🚺 🇨🇳"),
    ("zf_032", "zf_032 🚺 🇨🇳"),
    ("zf_036", "zf_036 🚺 🇨🇳"),
    ("zf_038", "zf_038 🚺 🇨🇳"),
    ("zf_039", "zf_039 🚺 🇨🇳"),
    ("zf_040", "zf_040 🚺 🇨🇳"),
    ("zf_042", "zf_042 🚺 🇨🇳"),
    ("zf_043", "zf_043 🚺 🇨🇳"),
    ("zf_044", "zf_044 🚺 🇨🇳"),
    ("zf_046", "zf_046 🚺 🇨🇳"),
    ("zf_047", "zf_047 🚺 🇨🇳"),
    ("zf_048", "zf_048 🚺 🇨🇳"),
    ("zf_049", "zf_049 🚺 🇨🇳"),
    ("zf_051", "zf_051 🚺 🇨🇳"),
    ("zf_059", "zf_059 🚺 🇨🇳"),
    ("zf_060", "zf_060 🚺 🇨🇳"),
    ("zf_067", "zf_067 🚺 🇨🇳"),
    ("zf_070", "zf_070 🚺 🇨🇳"),
    ("zf_071", "zf_071 🚺 🇨🇳"),
    ("zf_072", "zf_072 🚺 🇨🇳"),
    ("zf_073", "zf_073 🚺 🇨🇳"),
    ("zf_074", "zf_074 🚺 🇨🇳"),
    ("zf_075", "zf_075 🚺 🇨🇳"),
    ("zf_076", "zf_076 🚺 🇨🇳"),
    ("zf_077", "zf_077 🚺 🇨🇳"),
    ("zf_078", "zf_078 🚺 🇨🇳"),
    ("zf_079", "zf_079 🚺 🇨🇳"),
    ("zf_083", "zf_083 🚺 🇨🇳"),
    ("zf_084", "zf_084 🚺 🇨🇳"),
    ("zf_085", "zf_085 🚺 🇨🇳"),
    ("zf_086", "zf_086 🚺 🇨🇳"),
    ("zf_087", "zf_087 🚺 🇨🇳"),
    ("zf_088", "zf_088 🚺 🇨🇳"),
    ("zf_090", "zf_090 🚺 🇨🇳"),
    ("zf_092", "zf_092 🚺 🇨🇳"),
    ("zf_093", "zf_093 🚺 🇨🇳"),
    ("zf_094", "zf_094 🚺 🇨🇳"),
    ("zf_099", "zf_099 🚺 🇨🇳"),

    # Vozes Masculinas (zm_*)
    ("zm_009", "zm_009 🚹 🇨🇳"),
    ("zm_010", "zm_010 🚹 🇨🇳"),
    ("zm_011", "zm_011 🚹 🇨🇳"),
    ("zm_012", "zm_012 🚹 🇨🇳"),
    ("zm_013", "zm_013 🚹 🇨🇳"),
    ("zm_014", "zm_014 🚹 🇨🇳"),
    ("zm_015", "zm_015 🚹 🇨🇳"),
    ("zm_016", "zm_016 🚹 🇨🇳"),
    ("zm_020", "zm_020 🚹 🇨🇳"),
    ("zm_025", "zm_025 🚹 🇨🇳"),
    ("zm_029", "zm_029 🚹 🇨🇳"),
    ("zm_030", "zm_030 🚹 🇨🇳"),
    ("zm_031", "zm_031 🚹 🇨🇳"),
    ("zm_033", "zm_033 🚹 🇨🇳"),
    ("zm_034", "zm_034 🚹 🇨🇳"),
    ("zm_035", "zm_035 🚹 🇨🇳"),
    ("zm_037", "zm_037 🚹 🇨🇳"),
    ("zm_041", "zm_041 🚹 🇨🇳"),
    ("zm_045", "zm_045 🚹 🇨🇳"),
    ("zm_050", "zm_050 🚹 🇨🇳"),
    ("zm_052", "zm_052 🚹 🇨🇳"),
    ("zm_053", "zm_053 🚹 🇨🇳"),
    ("zm_054", "zm_054 🚹 🇨🇳"),
    ("zm_055", "zm_055 🚹 🇨🇳"),
    ("zm_056", "zm_056 🚹 🇨🇳"),
    ("zm_057", "zm_057 🚹 🇨🇳"),
    ("zm_058", "zm_058 🚹 🇨🇳"),
    ("zm_061", "zm_061 🚹 🇨🇳"),
    ("zm_062", "zm_062 🚹 🇨🇳"),
    ("zm_063", "zm_063 🚹 🇨🇳"),
    ("zm_064", "zm_064 🚹 🇨🇳"),
    ("zm_065", "zm_065 🚹 🇨🇳"),
    ("zm_066", "zm_066 🚹 🇨🇳"),
    ("zm_068", "zm_068 🚹 🇨🇳"),
    ("zm_069", "zm_069 🚹 🇨🇳"),
    ("zm_080", "zm_080 🚹 🇨🇳"),
    ("zm_081", "zm_081 🚹 🇨🇳"),
    ("zm_082", "zm_082 🚹 🇨🇳"),
    ("zm_089", "zm_089 🚹 🇨🇳"),
    ("zm_091", "zm_091 🚹 🇨🇳"),
    ("zm_095", "zm_095 🚹 🇨🇳"),
    ("zm_096", "zm_096 🚹 🇨🇳"),
    ("zm_097", "zm_097 🚹 🇨🇳"),
    ("zm_098", "zm_098 🚹 🇨🇳"),
    ("zm_100", "zm_100 🚹 🇨🇳"),
]

# Supertonic: 31 idiomas suportados + 10 vozes genéricas (F1-F5, M1-M5)
_SUPERTONIC_VOICES: list[str] = ["F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5"]

_SUPERTONIC_LANGS: list[tuple[str, str]] = [
    ("ar", "Arabic"),
    ("bg", "Bulgarian"),
    ("cs", "Czech"),
    ("da", "Danish"),
    ("de", "German"),
    ("el", "Greek"),
    ("en", "English"),
    ("es", "Spanish"),
    ("et", "Estonian"),
    ("fi", "Finnish"),
    ("fr", "French"),
    ("hi", "Hindi"),
    ("hr", "Croatian"),
    ("hu", "Hungarian"),
    ("id", "Indonesian"),
    ("it", "Italian"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("lt", "Lithuanian"),
    ("lv", "Latvian"),
    ("nl", "Dutch"),
    ("pl", "Polish"),
    ("pt", "Portuguese"),
    ("ro", "Romanian"),
    ("ru", "Russian"),
    ("sk", "Slovak"),
    ("sl", "Slovenian"),
    ("sv", "Swedish"),
    ("tr", "Turkish"),
    ("uk", "Ukrainian"),
    ("vi", "Vietnamese"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _add_separator(combo: QComboBox, text: str) -> None:
    """Insere um item não-selecionável como separador/cabeçalho de grupo."""
    model = combo.model()
    item = QStandardItem(f"── {text} ──")
    bold = QFont()
    bold.setBold(True)
    item.setFont(bold)
    item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
    model.appendRow(item)


# ---------------------------------------------------------------------------
# Widgets de parâmetros por engine
# ---------------------------------------------------------------------------

class _KokoroParams(QWidget):
    """
    Parâmetros do Kokoro ONNX.

    O combo de voz é preenchido dinamicamente de acordo com o idioma selecionado.
    Para o idioma Chinês (zh), os arquivos .bin são lidos em tempo de execução
    do diretório do modelo.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # Combo de Idioma
        self.lang_combo = QComboBox()
        self.lang_combo.setMaxVisibleItems(15)
        for code, name in _KOKORO_LANGS:
            self.lang_combo.addItem(name, userData=code)
        lay.addLayout(_row("Idioma:", self.lang_combo))

        # Combo de Voz (Vazio inicialmente, preenchido via sinal)
        self.voice_combo = QComboBox()
        self.voice_combo.setMaxVisibleItems(20)
        lay.addLayout(_row("Voz:", self.voice_combo))

        # Spinner de Velocidade
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 3.0)
        self.speed_spin.setSingleStep(0.05)
        self.speed_spin.setValue(1.0)
        lay.addLayout(_row("Velocidade:", self.speed_spin))

        # Conectar sinal de mudança de idioma e disparar a primeira vez
        self.lang_combo.currentIndexChanged.connect(self._update_voices)
        self._update_voices()

    def _update_voices(self) -> None:
        """Preenche as vozes com base no idioma atual. Usa mapeamento para o arquivo unificado zh."""
        self.voice_combo.clear()
        lang = self.lang_combo.currentData()

        if lang == "zh":
            # Em vez de ler a pasta física antiga com glob(*.bin),
            # popula diretamente usando os IDs presentes no arquivo unificado
            for voice_id, display in _KOKORO_ZH_VOICES:
                self.voice_combo.addItem(display, userData=voice_id)
        else:
            # Busca do dict estático padrão para os outros idiomas
            voices = _KOKORO_STATIC_VOICES.get(lang, [])
            for voice_id, display in voices:
                self.voice_combo.addItem(display, userData=voice_id)

    def get_params(self) -> dict:
        return {
            "lang": self.lang_combo.currentData() or "pt-br",
            "voice": self.voice_combo.currentData() or "",
            "speed": self.speed_spin.value(),
        }

    def set_params(self, p: dict) -> None:
        # 1. Definir o idioma primeiro para disparar o _update_voices e popular as vozes
        target_lang = p.get("lang", "pt-br")
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == target_lang:
                self.lang_combo.setCurrentIndex(i)
                break

        # 2. Com a lista correta já populada, selecionar a voz
        target_voice = p.get("voice", "pf_dora")
        for i in range(self.voice_combo.count()):
            if self.voice_combo.itemData(i) == target_voice:
                self.voice_combo.setCurrentIndex(i)
                break

        self.speed_spin.setValue(float(p.get("speed", 1.0)))


class _SupertonicParams(QWidget):
    """Parâmetros do Supertonic 3 — 10 vozes genéricas, 31 idiomas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.voice_combo = QComboBox()
        for v in _SUPERTONIC_VOICES:
            self.voice_combo.addItem(v)
        lay.addLayout(_row("Voz:", self.voice_combo))

        self.lang_combo = QComboBox()
        self.lang_combo.setMaxVisibleItems(20)
        for code, name in _SUPERTONIC_LANGS:
            self.lang_combo.addItem(f"{code}  –  {name}", userData=code)
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

        # Default: Portuguese
        self._set_lang("pt")

    def _set_lang(self, code: str) -> None:
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == code:
                self.lang_combo.setCurrentIndex(i)
                return

    def get_params(self) -> dict:
        return {
            "voice":       self.voice_combo.currentText(),
            "lang":        self.lang_combo.currentData() or "pt",
            "speed":       self.speed_spin.value(),
            "total_steps": self.steps_spin.value(),
        }

    def set_params(self, p: dict) -> None:
        idx = self.voice_combo.findText(p.get("voice", "F5"))
        if idx >= 0:
            self.voice_combo.setCurrentIndex(idx)
        self._set_lang(p.get("lang", "pt"))
        self.speed_spin.setValue(float(p.get("speed", 1.05)))
        self.steps_spin.setValue(int(p.get("total_steps", 10)))


# ---------------------------------------------------------------------------
# Painel principal
# ---------------------------------------------------------------------------

class EnginePanel(QFrame):
    engine_changed = Signal(str)   # emitido quando o usuário troca de engine

    _ENGINE_NAMES  = ["kokoro", "supertonic"]
    _ENGINE_LABELS = {
        "kokoro":     "Kokoro ONNX",
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

        self._stack      = QStackedWidget()
        self._kokoro_w   = _KokoroParams()
        self._supertonic_w = _SupertonicParams()
        self._stack.addWidget(self._kokoro_w)       # index 0
        self._stack.addWidget(self._supertonic_w)   # index 1
        lay.addWidget(self._stack)

        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)

    def _on_engine_changed(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self.engine_changed.emit(self._ENGINE_NAMES[idx])

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

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
            "kokoro":     self._kokoro_w,
            "supertonic": self._supertonic_w,
        }
        w = mapping.get(name)
        if w:
            w.set_params(params)