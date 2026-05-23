# src/tts/styles.py
#
# Parâmetros de estilo para os engines Supertonic e Kokoro.
#
# ─── O QUE CADA ENGINE EXPÕE DE FATO ────────────────────────────────────────
#
#   Supertonic.synthesize()
#     speed        float   multiplicador de velocidade de fala
#     total_steps  int     qualidade/textura da síntese (3–10)
#                          valores mais altos = mais nítido, sem efeito prosódico
#
#   Kokoro.create() / create_stream()
#     speed        float   multiplicador de velocidade de fala
#     voice        str     nome da voz — a principal alavanca de variação no Kokoro
#
# ─── O QUE NÃO EXISTE NESSAS LIBS ───────────────────────────────────────────
#
#   length_scale, noise_scale, noise_w  →  são parâmetros internos do Vits/ONNX
#   que as APIs públicas do Supertonic e do Kokoro-ONNX não expõem.
#   pitch direto                        →  idem; não há controle de pitch externo.
#
# ─── ESTRATÉGIA DE VARIAÇÃO EXPRESSIVA ──────────────────────────────────────
#
#   1. speed      — funciona nos dois engines, efeito imediato e perceptível
#   2. total_steps (Supertonic) — influencia textura; aumentar 1–2 steps em
#      estilos "neutral" / "casual" deixa a fala ligeiramente mais clara
#   3. voice swap (Kokoro) — a forma mais eficaz de variação: cada estilo pode
#      apontar para uma voz diferente do pacote instalado.
#      Deixamos None como padrão; o loader usa a voz configurada no config.
#
# ─── FORMATO ─────────────────────────────────────────────────────────────────
#
#   STYLE_PARAMS = {
#       "<style>": {
#           # ── Comuns ──────────────────────────────────────────────────
#           "speed":                    float,        # multiplicador (0.75–1.3)
#           "total_steps":              int,          # Supertonic: 3–10
#           # ── Kokoro only ─────────────────────────────────────────────
#           "kokoro_voice":             str | None,   # None = usa voz padrão do config
#       }
#   }
#
# ─── DICA DE CALIBRAÇÃO ──────────────────────────────────────────────────────
#
#   Execute  python -m src.tts.calibrate  (script a criar) para ouvir cada
#   estilo em sequência e ajustar os valores sem reiniciar o agente.
#
# ─────────────────────────────────────────────────────────────────────────────

from typing import TypedDict


class StyleParams(TypedDict, total=False):
    # ── Comuns ──────────────────────────────────────────────────────────────
    speed: float
    total_steps: int

    # ── Kokoro only ──────────────────────────────────────────────────────────
    kokoro_voice: "str | None"  # None = usa voz padrão do config

# ---------------------------------------------------------------------------
# Tabela principal
# ---------------------------------------------------------------------------
# Referência de speed:
#   0.75 → muito lento / pesado
#   0.85 → lento / pensativo
#   0.92 → levemente pausado
#   1.00 → neutro
#   1.08 → levemente animado
#   1.15 → animado
#   1.25 → acelerado / excitado
#
# Referência de total_steps (Supertonic):
#   5 → padrão / rápido
#   6 → ligeiramente mais nítido
#   8 → mais limpo, perceptível em frases longas
#
# Ordem: neutro → positivos → ambíguos → negativos crescentes
# ---------------------------------------------------------------------------

STYLE_PARAMS: dict[str, StyleParams] = {

    # ── Neutro ────────────────────────────────────────────────────────────
    "neutral": {
        "speed":                      1.0,
        "total_steps":                10,
        "kokoro_voice":               None,
    },

    # ── Casual ────────────────────────────────────────────────────────────
    "casual": {
        "speed":                      1.08,
        "total_steps":                10,
        "kokoro_voice":               None,
    },

    # ── Curioso ───────────────────────────────────────────────────────────
    "curious": {
        "speed":                      1.13,
        "total_steps":                10,
        "kokoro_voice":               None,
    },

    # ── Feliz ─────────────────────────────────────────────────────────────
    "happy": {
        "speed":                      1.15,
        "total_steps":                10,
        "kokoro_voice":               None,
    },

    # ── Fofo ──────────────────────────────────────────────────────────────
    "cute": {
        "speed":                      1.05,
        "total_steps":                10,
        "kokoro_voice":               None,
    },

    # ── Gentil ────────────────────────────────────────────────────────────
    "gentle": {
        "speed":                      0.95,
        "total_steps":                10,
        "kokoro_voice":               None,
    },

    # ── Tímido ────────────────────────────────────────────────────────────
    "shy": {
        "speed":                      0.98,
        "total_steps":                10,
        "kokoro_voice":               None,
    },

    # ── Entediado ─────────────────────────────────────────────────────────
    "bored": {
        "speed":                      0.90,
        "total_steps":                10,
        "kokoro_voice":               None,
    },

    # ── Triste ────────────────────────────────────────────────────────────
    "sad": {
        "speed":                      0.90,
        "total_steps":                10,
        "kokoro_voice":               None,
    },

    # ── Irritado ─────────────────────────────────────────────────────────
    "angry": {
        "speed":                      1.10,
        "total_steps":                10,
        "kokoro_voice":               None,
    },
}

# ---------------------------------------------------------------------------
# Fallback global — usado quando o estilo não está na tabela
# ---------------------------------------------------------------------------
_FALLBACK: StyleParams = {
    "speed":                      1.0,
    "total_steps":                10,
    "kokoro_voice":               None,
}


def get_style_params(style: str) -> StyleParams:
    """
    Retorna os parâmetros de TTS para um estilo.
    Se o estilo não existir na tabela, retorna o fallback neutro.
    """
    return STYLE_PARAMS.get(style, _FALLBACK)