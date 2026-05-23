"""
supertonic_expression.py
────────────────────────────────────────────────────────────────────────
Módulo de expression tags para Supertonic 3.

Responsabilidade única: dada uma frase já sanitizada pelo pipeline
principal (sanitize_for_tts), detectar intenção emocional a partir de
marcações de RP/pensamento do LLM (*laughs*, *sighs deeply*, etc.) e
injetar as expression tags na posição e quantidade que o modelo
processa corretamente — baseado nos testes empíricos de 2026-05-16.

NÃO faz split de parágrafo — esse passo pertence ao caller (inference.py
ou similar), que deve chamar split_into_sentences() antes de processar
cada frase individualmente.

────────────────────────────────────────────────────────────────────────
COMPORTAMENTO VERIFICADO (testes empíricos, voz F1, 2026-05-16)
────────────────────────────────────────────────────────────────────────

Tag       | Posição  | Repetições | Resultado          | Padrão final
──────────┼──────────┼────────────┼────────────────────┼──────────────────────────────
<laugh>   | fim      | ×3         | MELHOR**           | texto <laugh> <laugh> <laugh>
<breath>  | início   | ×3         | MELHOR**           | <breath> <breath> <breath> texto
<sad>     | ambos    | ×3         | MELHOR***          | <sad>×3 texto <sad>×3
<cough>   | início   | ×3         | MELHOR (parcial)   | <cough> <cough> <cough> texto

Descartadas (falham ou comportamento imprevisível em todas posições):
  angry, throatclear, yawn, surprise, sigh, scream

Razão do padrão N+1 tags:
  O modelo consome UMA tag como sinal prosódico e vocaliza as excedentes
  como texto. Com ×3, consome uma e vocaliza duas — mas o fenômeno só
  ocorre em posições sem ancoragem semântica (fim sem texto seguinte,
  início sem contexto prévio). A combinação posição+repetição correta
  elimina a vocalização.

────────────────────────────────────────────────────────────────────────
FLUXO DE USO
────────────────────────────────────────────────────────────────────────

  # Em inference.py (ou equivalente), após sanitize_for_tts():
  from src.tts.supertonic_expression import tag_sentence

  sentences = split_into_sentences(sanitized_paragraph)
  for sentence in sentences:
      tagged = tag_sentence(sentence, rp_hint=extract_rp_hint(raw_sentence))
      loader.speak(tagged)

  # Versão simplificada (sem hint externo — detecta no próprio texto):
  tagged = tag_sentence(sentence)
  loader.speak(tagged)

────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import NamedTuple


# ═══════════════════════════════════════════════════════════════════════
# 1. CATÁLOGO DE TAGS USÁVEIS
# ═══════════════════════════════════════════════════════════════════════

class TagPlacement(Enum):
    """Posição onde as tags devem ser injetadas na frase."""
    START = auto()   # <tag>×N texto
    END   = auto()   # texto <tag>×N
    BOTH  = auto()   # <tag>×N texto <tag>×N


@dataclass(frozen=True)
class TagSpec:
    """Especificação completa de uma expression tag verificada empiricamente."""
    name:      str           # nome da tag, ex.: "laugh"
    placement: TagPlacement
    repeat:    int           # quantas tags inserir em cada posição


# Catálogo derivado dos testes empíricos.
# Ordem importa para a resolução de conflitos (maior prioridade primeiro).
_USABLE_TAGS: dict[str, TagSpec] = {
    "laugh":  TagSpec("laugh",  TagPlacement.END,   3),
    "breath": TagSpec("breath", TagPlacement.START,  3),
    "sad":    TagSpec("sad",    TagPlacement.BOTH,   3),
    "cough":  TagSpec("cough",  TagPlacement.START,  3),
}

# Tags conhecidas mas descartadas — usadas apenas para suprimir detecção
# e evitar que sejam passadas ao modelo acidentalmente.
_UNSUPPORTED_TAGS: frozenset[str] = frozenset(
    {"angry", "throatclear", "yawn", "surprise", "sigh", "scream"}
)

ALL_KNOWN_TAGS: frozenset[str] = frozenset(_USABLE_TAGS) | _UNSUPPORTED_TAGS


# ═══════════════════════════════════════════════════════════════════════
# 2. TABELA DE CORRESPONDÊNCIA: termos de RP → tag
# ═══════════════════════════════════════════════════════════════════════
# Estrutura: { tag_name: [lista de padrões regex (case-insensitive)] }
# A lista é avaliada em ordem; o primeiro match encerra a busca.
#
# Critério de inclusão:
#   - Verbos/substantivos de ação vocal que um LLM de RP tipicamente usa
#   - Apenas quando mapeiam para uma tag empiricamente confiável
#   - Termos ambíguos (ex.: "sighs" → <sigh> descartada) são omitidos
#     intencionalmente para não injetar tags que falham
#
_RP_TERM_MAP: dict[str, list[str]] = {
    # ── laugh ──────────────────────────────────────────────────────────
    "laugh": [
        r"\blaugh(?:s|ing|ed|ter)?\b",
        r"\bchuckle?s?\b",
        r"\bgiggles?\b",
        r"\bsnickers?\b",
        r"\bsniggers?\b",                           # rir às escondidas
        r"\btitters?\b",                             # risinho reprimido
        r"\bsnorts?\b",
        r"\bcackles?\b",
        r"\blets?\s+out\s+a\s+laugh\b",
        r"\bbursts?\s+(?:out\s+)?laughing\b",
        r"\bgrin(?:s|ning|ned)?\b",                 # sorriso aberto/vocalizado
        r"\bheh\b",
        r"\bhaha\b",
        r"\bha\s+ha\b",
        r"\bheehee\b",
        # ── PT-BR ───────────────────────────────────────────────────────
        r"\bri\b",                                   # "ri" — presente PT
        r"\brir\b",                                  # infinitivo PT
        r"\brisada\b",                               # "uma risada"
        r"\bgargalha(?:da)?s?\b",                    # gargalhada / gargalha
        r"\bgargalha(?:r|ndo)\b",                    # gargalhar / gargalhando
        r"\bchora\s+de\s+rir\b",                     # "chora de rir"
        r"\bdá\s+uma\s+risada\b",                    # "dá uma risada"
        r"\bsolta\s+uma\s+risada\b",                 # "solta uma risada"
        r"\bri\s+(?:baixinho|levemente|suavemente|sozinho|discretamente)\b",
        # ── Risos literais fora de marcação de RP ───────────────────────
        # Detectados diretamente no texto sanitizado (ex.: "hahaha que engraçado").
        # Padrão: repetição de sílabas de riso com pelo menos 2 repetições,
        # para não capturar interjections curtas legítimas como "ah" ou "oh".
        r"\b(?:ha){2,}\b",          # haha, hahaha, hahahaha…
        r"\b(?:he){2,}\b",          # hehe, hehehe…
        r"\b(?:hi){2,}\b",          # hihi, hihihi…
        r"\b(?:ho){2,}\b",          # hoho, hohohó…
        r"\bah?(?:ah?){2,}\b",      # ahaah, ahahah, ahaha… (variantes com 'a')
        r"\bkk+\b",                 # kk, kkk, kkkk… (riso informal PT-BR)
        r"\brs+\b",                 # rs, rss, rsrs… (riso informal PT-BR)
        r"\brsrs(?:rs)*\b",         # rsrs, rsrsrs…
        r"\blol\b",                 # lol (EN)
        r"\blmao\b",                # lmao (EN)
    ],

    # ── breath ─────────────────────────────────────────────────────────
    "breath": [
        r"\bexhales?\b",
        r"\binhales?\b",
        r"\bbreath(?:es|ing)?\b",
        r"\btakes?\s+a\s+(?:deep\s+)?breath\b",
        r"\bbreath(?:ing)?\s+(?:deeply|hard|heavily|slowly|shakily)\b",
        r"\bgasps?\b",
        r"\bpants?\b",
        r"\bpanting\b",
        r"\bwheezes?\b",
        r"\bwheezing\b",
        r"\bshudders?\b",                            # tremor respiratório
        r"\bsighs?\b",                               # suspiro → redirecionado para breath
        r"\bsighing\b",
        # ── PT-BR ───────────────────────────────────────────────────────
        r"\bsuspira(?:r|ndo)?\b",                    # suspirar / suspirando
        r"\bsuspiro\b",
        r"\bsolta\s+um\s+suspiro\b",
        r"\bofega(?:r|ndo)?\b",                      # ofegar / ofegando
        r"\bofego\b",
        r"\brespira\s+(?:fundo|devagar|fundo\s+e\s+devagar)\b",
        r"\bperde\s+o\s+fôlego\b",
        r"\bfôlego\b",
        r"\bsoluça(?:r|ndo)?\b",                     # soluçar — fronteiriço com sad
        r"\bsoluço\b",
        r"\btreme(?:ndo)?\b",                        # tremor de voz/respiração
        r"\btremi\b",
    ],

    # ── sad ────────────────────────────────────────────────────────────
    "sad": [
        r"\bcries?\b",
        r"\bcrying\b",
        r"\bcried\b",
        r"\bsobs?\b",
        r"\bsobbing\b",
        r"\bwhimpers?\b",
        r"\bwhimpering\b",
        r"\bsniffles?\b",
        r"\bsniffling\b",
        r"\bweeps?\b",
        r"\bweeping\b",
        r"\btears?\s+up\b",
        r"\bvoice\s+(?:breaks?|cracks?|trembles?)\b",
        r"\bon\s+the\s+verge\s+of\s+tears\b",
        r"\bholding\s+back\s+tears\b",
        r"\bteary[- ]eyed\b",
        r"\blaments?\b",                             # EN: laments
        r"\bquavering\b",                            # EN: voz trêmula
        r"\bbroken[- ]voice[d]?\b",                  # EN
        r"\bcracking\s+voice\b",                     # EN
        # ── PT-BR ───────────────────────────────────────────────────────
        r"\bchora(?:r|ndo)?\b",                      # chorar / chorando
        r"\bchoro\b",                                # "em choro"
        r"\blamenta(?:r|ndo)?\b",                    # lamentar
        r"\blamúria\b",
        r"\bpranteia(?:r|ndo)?\b",                   # pranteiar
        r"\bchora\s+(?:baixinho|em\s+silêncio|sem\s+parar)\b",
        r"\bengole\s+(?:em\s+seco|o\s+choro)\b",     # "engole o choro"
        r"\bperde\s+a\s+voz\b",
        r"\bvoz\s+embargada\b",
        r"\bdesaba(?:ndo)?\b",                       # "desaba em choro"
        r"\bdesabou\b",
    ],

    # ── cough ──────────────────────────────────────────────────────────
    "cough": [
        r"\bcoughs?\b",
        r"\bcoughing\b",
        r"\bclears?\s+(?:her\s+|his\s+|their\s+)?throat\b",
        r"\bhacks?\b",                               # tosse seca
        r"\bchokes?\b",                              # EN: engasga com algo
        r"\bsplutters?\b",                           # EN: tosse com saliva
        r"\bsputters?\b",                            # EN
        # ── PT-BR ───────────────────────────────────────────────────────
        r"\btosse\b",                                # "dá uma tosse"
        r"\btossir\b",                               # infinitivo
        r"\btossindo\b",                             # gerúndio
        r"\bdá\s+uma\s+tosse\b",
        r"\bpigarreia(?:r|ndo)?\b",                  # pigarrear
        r"\bpigarreio\b",
        r"\bengasga(?:r|ndo)?\b",                    # engasgar
        r"\bengasgo\b",
    ],
}

# Pré-compila todos os padrões para performance.
_COMPILED_RP_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    tag: [re.compile(p, re.IGNORECASE) for p in patterns]
    for tag, patterns in _RP_TERM_MAP.items()
}

# ── Riso literal fora de marcação ───────────────────────────────────────────
# Regex que captura tokens de riso digitados diretamente no corpo do texto
# (ex.: "hahaha que engraçado", "kkk não acredito").
# Esses tokens não vivem dentro de *...* nem (...), portanto extract_rp_hint()
# não os captura — mas detect_tag_from_hint() os detecta via _RP_TERM_MAP.
# A regex abaixo é usada exclusivamente por strip_inline_laugh_tokens() para
# REMOVER o token do texto antes de síntese, evitando que o engine tente
# vocalizá-lo literalmente (o que soaria estranho ou incorreto).
#
# Inclui variantes PT-BR (kk, kkk, rs, rsrs) e EN (lol, lmao).
# Não inclui "heh" isolado pois pode ser interjection neutra ("heh, interesting").
_INLINE_LAUGH_RE = re.compile(
    r"(?:"
    r"\b(?:ha){2,}\b"           # haha, hahaha...
    r"|\b(?:he){2,}\b"          # hehe, hehehe...
    r"|\b(?:hi){2,}\b"          # hihi, hihihi...
    r"|\b(?:ho){2,}\b"          # hoho, hohohó...
    r"|\bah?(?:ah?){2,}\b"      # ahaha, ahahah...
    r"|\bkk+\b"                 # kk, kkk...
    r"|\brs+\b"                 # rs, rss...
    r"|\brsrs(?:rs)*\b"         # rsrs, rsrsrs...
    r"|\blol\b"                 # lol
    r"|\blmao\b"                # lmao
    r")",
    re.IGNORECASE,
)


def strip_inline_laugh_tokens(text: str) -> str:
    """
    Remove tokens de riso literal do texto sanitizado, substituindo-os
    por uma vírgula de pausa (, ,) para preservar o ritmo da fala.

    Deve ser chamado APÓS sanitize_for_tts() e ANTES de tag_sentence() /
    process_paragraph(), de modo que o texto enviado ao engine não contenha
    tokens ininteligíveis como "hahaha" ou "kkkk", mas a prosódia de pausa
    seja mantida no ponto onde o riso ocorreu.

    O hint de RP para injeção de <laugh> é extraído do texto bruto pelo
    caller (inference.py) ANTES desta chamada — portanto a remoção do token
    aqui não impede a detecção da tag.

    Exemplos:
        "hahaha que engraçado!"       -> ", , que engraçado!"
        "Não acredito kkkk sério?"    -> "Não acredito , , sério?"
        "lol isso foi inesperado"     -> ", , isso foi inesperado"
        "Texto normal sem risos."     -> "Texto normal sem risos."  (no-op)
    """
    if not text:
        return text

    # Fast-path: evita regex quando não há candidatos óbvios.
    _markers = ("ha", "he", "hi", "ho", "ah", "kk", "rs", "lol", "lmao")
    if not any(m in text.lower() for m in _markers):
        return text

    # Substitui cada token por ", ," e depois normaliza espaços redundantes.
    result = _INLINE_LAUGH_RE.sub(", ,", text)
    # Colapsa múltiplos ", ," consecutivos (caso de "hahaha kkkk").
    result = re.sub(r"(?:,\s*,\s*){2,}", ", , ", result)
    # Normaliza espaços.
    result = re.sub(r"\s{2,}", " ", result).strip()
    return result


# ═══════════════════════════════════════════════════════════════════════
# 3. DETECÇÃO DE HINT DE RP
# ═══════════════════════════════════════════════════════════════════════

# Regex que captura o conteúdo interno de marcações de RP comuns:
#   *texto*  **texto**  _texto_  (( texto ))  [[ texto ]]  ~texto~  (texto)
#
# NOTA sobre parênteses simples (grupo 6):
#   (texto) é ambíguo — pode ser ação de RP "(ri levemente)" ou informação
#   legítima "(ver seção 3)", "(1984)". A heurística aplicada em
#   extract_rp_hint filtra pelo conteúdo: só são considerados blocos (...)
#   cujo interior contém ao menos uma palavra de ação/emoção do _RP_TERM_MAP
#   OU que correspondam ao padrão geral de ação narrativa (verbo no presente
#   ou gerúndio + complemento curto, sem numerais isolados).
#   Parênteses com apenas números, siglas ou referências são descartados.
_RP_BLOCK_RE = re.compile(
    r"\*{1,3}([^*\n]+?)\*{1,3}"      # *...*  **...**  ***...***
    r"|_{1,2}([^_\n]+?)_{1,2}"       # _..._  __...__
    r"|\(\(\s*(.+?)\s*\)\)"          # (( ... ))
    r"|\[\[\s*(.+?)\s*]]"            # [[ ... ]]
    r"|~{1,2}([^~\n]+?)~{1,2}"       # ~...~  ~~...~~
    r"|\(([^()\n]{2,80})\)",         # ( ... ) — parêntese simples, ≤80 chars
    re.IGNORECASE | re.DOTALL,
)

# Heurística para distinguir parênteses de RP de parênteses informativos.
# Um bloco (...) é considerado RP se:
#   1. Contém palavra do _RP_TERM_MAP (verificado em extract_rp_hint), OU
#   2. Começa com letra, não contém numeral, não usa palavras de referência,
#      e tem ao menos 2 palavras (indicativo de frase de ação narrativa).
# Casos como "(1984)", "(ver seção 3)", "(API)", "(p. 42)" são rejeitados.
_PAREN_RP_RE = re.compile(
    r"^[a-záàâãéèêíïóôõöúçñA-Z]"   # começa com letra (não número/símbolo)
    r"(?!.*\b\d{4}\b)"              # não contém ano de 4 dígitos isolado
    r"(?!^\s*[A-Z]{2,}\s*$)",       # não é só sigla em maiúsculas
    re.IGNORECASE,
)

# Palavras que tipicamente introduzem referências, não ações de RP.
_PAREN_REF_WORDS: frozenset[str] = frozenset([
    "ver", "veja", "vide", "veja-se", "cf", "see", "cf.", "p", "pp",
    "pág", "página", "seção", "section", "cap", "capítulo", "chapter",
    "fig", "figura", "figure", "tab", "tabela", "table", "nota", "note",
    "apud", "ibid", "op", "cit", "ed", "vol", "n", "nr", "num",
    "tradução", "translation", "grifo", "emphasis", "itálico", "negrito",
    "sic", "idem",
])


def _is_rp_paren_content(content: str) -> bool:
    """
    Retorna True se o conteúdo de um parêntese simples parece ser uma
    ação/emoção de RP em vez de informação textual.

    Critérios (qualquer um satisfatório):
      1. Contém ao menos uma palavra dos padrões do _RP_TERM_MAP.
      2. Começa com letra, ≥2 palavras, sem:
           - numerais de qualquer tipo (\d+)
           - palavras de referência (_PAREN_REF_WORDS)
           - sigla isolada (≥3 caps)

    Exemplos aceitos : "ri levemente", "takes a deep breath", "tosse"
    Exemplos rejeitados: "1984", "API", "ver seção 3", "15 min", "p. 42"
    """
    content = content.strip()

    # Critério 1 — match direto com qualquer padrão do _RP_TERM_MAP
    for patterns in _COMPILED_RP_PATTERNS.values():
        for p in patterns:
            if p.search(content):
                return True

    # Critério 2 — heurística estrutural
    words = content.split()
    if len(words) < 2:
        return False

    # Rejeita se contiver qualquer numeral
    if re.search(r"\d", content):
        return False

    # Rejeita se a primeira palavra for palavra de referência
    first_lower = words[0].rstrip(".,;:").lower()
    if first_lower in _PAREN_REF_WORDS:
        return False

    # Rejeita se qualquer palavra for sigla ≥3 caps
    if any(w.isupper() and len(w) >= 3 for w in words):
        return False

    # Rejeita se a primeira palavra for só maiúsculas isolada (sigla)
    if words[0].isupper() and len(words[0]) >= 2:
        return False

    # Verifica padrão estrutural: começa com letra, sem ano
    if _PAREN_RP_RE.match(content):
        return True

    return False


def extract_rp_hint(raw_text: str) -> str | None:
    """
    Extrai o conteúdo de marcações de RP/pensamento do texto bruto
    (ANTES de sanitize_for_tts) e retorna a string concatenada de
    todos os blocos encontrados.

    Retorna None se não houver nenhum bloco de RP.

    Marcadores reconhecidos (em ordem de prioridade):
      *...*  **...**  ***...***   — ação/emoção de RP (asterisco)
      _..._  __...__              — ênfase/ação
      (( ... ))                  — bloco de RP explícito
      [[ ... ]]                  — bloco de RP explícito
      ~...~  ~~...~~              — emoção/tom
      ( ... )                    — parêntese simples: apenas aceito se o
                                   conteúdo parecer ação/emoção de RP
                                   (heurística via _is_rp_paren_content)

    Exemplos:
        "*She laughs softly.*  I'm fine, really."
        → "She laughs softly."

        "Sure! (grins mischievously) Let's go."
        → "grins mischievously"

        "Published in (1984) by Orwell."
        → None  ← parêntese informativo, descartado
    """
    fragments = []
    for m in _RP_BLOCK_RE.finditer(raw_text):
        groups = m.groups()
        # Grupos 0–4: marcadores não-ambíguos (* _ (( [[ ~)
        # Grupo 5: parêntese simples — requer heurística
        content = None
        for i, g in enumerate(groups):
            if g is not None:
                if i == 5:  # grupo do parêntese simples
                    if _is_rp_paren_content(g):
                        content = g.strip()
                else:
                    content = g.strip()
                break
        if content:
            fragments.append(content)
    return " ".join(fragments) if fragments else None


def detect_tag_from_hint(hint: str) -> str | None:
    """
    Dado um hint de RP (string com descrição de ação/emoção),
    retorna o nome da tag usável mais relevante, ou None.

    Avalia as tags na ordem do catálogo (laugh > breath > sad > cough).
    """
    for tag_name in _USABLE_TAGS:
        for pattern in _COMPILED_RP_PATTERNS[tag_name]:
            if pattern.search(hint):
                return tag_name
    return None



# ═══════════════════════════════════════════════════════════════════════
# 4. CONSTRUÇÃO DO TEXTO COM TAGS
# ═══════════════════════════════════════════════════════════════════════

def _build_tag_block(tag_name: str, n: int) -> str:
    """Retorna uma string com N repetições da tag, separadas por espaço."""
    t = f"<{tag_name}>"
    return " ".join([t] * n)


def apply_expression_tag(sentence: str, tag_name: str) -> str:
    """
    Aplica a expression tag na posição e repetição corretas para a tag
    dada, de acordo com o catálogo empírico.

    Args:
        sentence:  Frase sanitizada (sem marcação de RP).
        tag_name:  Nome da tag a aplicar (ex.: "laugh").

    Returns:
        Frase com tags injetadas, ou a frase original se a tag não for
        reconhecida ou não estiver no catálogo usável.
    """
    spec = _USABLE_TAGS.get(tag_name)
    if spec is None:
        return sentence  # tag desconhecida ou descartada — não injeta

    sentence = sentence.strip()
    block = _build_tag_block(spec.name, spec.repeat)

    if spec.placement == TagPlacement.END:
        return f"{sentence} {block}"
    elif spec.placement == TagPlacement.START:
        return f"{block} {sentence}"
    else:  # BOTH
        return f"{block} {sentence} {block}"


# ═══════════════════════════════════════════════════════════════════════
# 5. API PÚBLICA PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════

def tag_sentence(
    sentence: str,
    rp_hint: str | None = None,
    *,
    force_tag: str | None = None,
) -> str:
    """
    Ponto de entrada principal. Dado o texto de uma frase (já sanitizado
    por sanitize_for_tts), detecta a intenção emocional e injeta a
    expression tag correta para o Supertonic 3.

    Args:
        sentence:   Frase sanitizada e pronta para síntese.
        rp_hint:    Conteúdo extraído de marcações de RP do texto bruto
                    (resultado de extract_rp_hint()). Se None, a detecção
                    é feita sobre a própria frase.
        force_tag:  Força uma tag específica, ignorando a detecção
                    automática. Útil para chamadas programáticas com
                    contexto externo (ex.: config de avatar).

    Returns:
        Frase com expression tags injetadas, ou a frase original se
        nenhuma tag for detectada ou aplicável.

    Exemplos:
        >>> tag_sentence("I can't believe it.", rp_hint="laughs softly")
        "I can't believe it. <laugh> <laugh> <laugh>"

        >>> tag_sentence("I finally made it.", rp_hint="exhales with relief")
        "<breath> <breath> <breath> I finally made it."

        >>> tag_sentence("I never thought it would end.", rp_hint="crying")
        "<sad> <sad> <sad> I never thought it would end. <sad> <sad> <sad>"

        >>> tag_sentence("This room is so dusty.", rp_hint="coughs")
        "<cough> <cough> <cough> This room is so dusty."

        >>> tag_sentence("Everything is fine.", rp_hint="sighs")
        "Everything is fine."  # <sigh> descartada — sem injeção
    """
    if not sentence.strip():
        return sentence

    if force_tag is not None:
        return apply_expression_tag(sentence, force_tag)

    # Tenta detectar pelo hint externo primeiro (mais confiável)
    source = rp_hint if rp_hint is not None else sentence
    tag_name = detect_tag_from_hint(source)

    if tag_name is None:
        return sentence  # nenhuma expressão detectada

    return apply_expression_tag(sentence, tag_name)


# ═══════════════════════════════════════════════════════════════════════
# 6. UTILITÁRIO: SPLIT DE SENTENÇAS
# ═══════════════════════════════════════════════════════════════════════

# Regex de split: quebra em '.', '!', '?' seguidos de espaço+maiúscula
# ou fim de string. Preserva a pontuação na sentença anterior.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ú\"])")


def split_into_sentences(text: str) -> list[str]:
    """
    Divide um parágrafo em frases individuais para síntese separada.

    Usa split por pontuação terminal (. ! ?) como heurística simples.
    Para textos em inglês/português sem abreviações problemáticas, isso
    é suficiente para o fluxo de RP.

    Se NLTK estiver disponível no ambiente e o caller preferir maior
    precisão, pode substituir esta função por uma chamada a
    nltk.sent_tokenize — este módulo não depende de NLTK para não
    adicionar overhead em ambientes sem o recurso baixado.

    Returns:
        Lista de frases não-vazias, mantendo a pontuação original.
    """
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


# ═══════════════════════════════════════════════════════════════════════
# 7. UTILITÁRIO: PIPELINE COMPLETO (parágrafo → frases tagueadas)
# ═══════════════════════════════════════════════════════════════════════

class TaggedSentence(NamedTuple):
    """Resultado de process_paragraph para uma frase individual."""
    original:  str          # frase sanitizada, sem tags
    tagged:    str          # frase com expression tags (ou igual a original)
    tag_used:  str | None   # nome da tag aplicada, ou None


def process_paragraph(
    sanitized_paragraph: str,
    raw_paragraph: str | None = None,
) -> list[TaggedSentence]:
    """
    Pipeline completo: recebe um parágrafo sanitizado, divide em frases
    e aplica expression tags individualmente.

    Args:
        sanitized_paragraph:  Saída de sanitize_for_tts().
        raw_paragraph:        Texto bruto original (antes de sanitize),
                              usado para extrair hints de RP com maior
                              precisão. Se None, a detecção é feita sobre
                              o texto sanitizado.

    Returns:
        Lista de TaggedSentence — uma por frase detectada.

    Exemplo de uso em inference.py:

        raw = llm_response          # texto bruto do LLM
        sanitized = sanitize_for_tts(raw, ctx=ctx, ...)
        results = process_paragraph(sanitized, raw_paragraph=raw)
        for ts in results:
            loader.speak(ts.tagged)
    """
    sentences = split_into_sentences(sanitized_paragraph)

    # Se temos o raw, extrai um hint global para o parágrafo inteiro.
    # Heurística: o hint é atribuído apenas à primeira frase que não
    # tenha detecção própria — evita que um único bloco de RP contamine
    # todas as frases do parágrafo.
    global_hint: str | None = None
    if raw_paragraph is not None:
        global_hint = extract_rp_hint(raw_paragraph)

    results: list[TaggedSentence] = []
    hint_consumed = False

    for sentence in sentences:
        # 1. Tenta detecção local (hint embutido na própria frase)
        local_hint = extract_rp_hint(sentence)
        tag_name = detect_tag_from_hint(local_hint) if local_hint else None

        # 2. Se não achou localmente, usa o hint global (apenas uma vez)
        if tag_name is None and global_hint and not hint_consumed:
            tag_name = detect_tag_from_hint(global_hint)
            if tag_name is not None:
                hint_consumed = True

        # 3. Aplica a tag ou retorna a frase sem alteração
        tagged = apply_expression_tag(sentence, tag_name) if tag_name else sentence
        results.append(TaggedSentence(original=sentence, tagged=tagged, tag_used=tag_name))

    return results


# ═══════════════════════════════════════════════════════════════════════
# 8. NOTAS DE INTEGRAÇÃO
# ═══════════════════════════════════════════════════════════════════════
# • Este módulo deve ser chamado APÓS sanitize_for_tts(), nunca antes,
#   pois o texto limpo é requisito para a detecção correta de padrões.
#
# • sanitizer.py já protege <laugh>, <breath>, <sad> e <cough> via
#   _protect_expression_tags / _restore_expression_tags, garantindo que
#   tags injetadas programaticamente antes de sanitize_for_tts sobrevivam
#   ao pipeline.
#
# • hint_consumed em process_paragraph:
#   O hint global é atribuído à PRIMEIRA frase sem detecção local própria.
#   Se a primeira frase já tiver uma tag detectada localmente, o hint vai
#   para a segunda, e assim por diante. Isso é intencional: um único bloco
#   de RP no início do parágrafo não deve contaminar todas as frases
#   subsequentes — apenas a mais próxima que ainda não tenha expressão.
# ═══════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════
# SELF-TEST (python supertonic_expression.py)
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    _cases = [
        # (raw, sanitized, expected_tag)
        ("*She laughs softly.* I can't believe it.", "I can't believe it.", "laugh"),
        ("*exhales with relief*", "I finally made it.", "breath"),
        ("*crying* I never thought it would end like this.", "I never thought it would end like this.", "sad"),
        ("*coughs* This room is so dusty.", "This room is so dusty.", "cough"),
        ("*sighs deeply*", "Another meeting added to my calendar.", None),     # sigh descartada
        ("*screams*", "Watch out, behind you!", None),                          # scream descartada
        (None, "She snickers and looks away.", "laugh"),                        # detecção no sanitized
        (None, "He exhales and closes his eyes.", "breath"),
        (None, "Everything is fine.", None),                                    # sem tag
        # ── Risos literais fora de marcação ──────────────────────────────
        (None, "hahaha que engraçado!", "laugh"),                               # haha inline
        (None, "Não acredito kkkk sério?", "laugh"),                            # kkk PT-BR
        (None, "rsrs isso foi inesperado", "laugh"),                             # rsrs PT-BR
        (None, "lol I can't believe that", "laugh"),                             # lol EN
        (None, "hehehe adorei!", "laugh"),                                       # hehe
    ]

    print("=" * 72)
    print("SELF-TEST — supertonic_expression.py")
    print("=" * 72)
    passed = failed = 0
    for raw, sanitized, expected in _cases:
        hint = extract_rp_hint(raw) if raw else None
        result = tag_sentence(sanitized, rp_hint=hint)
        detected = detect_tag_from_hint(hint or sanitized)
        ok = detected == expected
        status = "✅" if ok else "❌"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"  {status}  expected={expected!r:10}  got={detected!r:10}  →  {result}")

    print()
    print(f"  {passed}/{passed+failed} passed")
    print("=" * 72)

    print()
    print("STRIP_INLINE_LAUGH_TOKENS:")
    print("-" * 72)
    _strip_cases = [
        ("hahaha que engraçado!",       ", , que engraçado!"),
        ("Não acredito kkkk sério?",     "Não acredito , , sério?"),
        ("lol isso foi inesperado",      ", , isso foi inesperado"),
        ("hehehe adorei!",               ", , adorei!"),
        ("rsrs não acredito rsrs",       ", , não acredito , ,"),
        ("Texto normal sem risos.",      "Texto normal sem risos."),
        ("hahaha kkkk demais!",          ", , demais!"),    # dois tokens colapsam
    ]
    strip_passed = strip_failed = 0
    for inp, expected in _strip_cases:
        got = strip_inline_laugh_tokens(inp)
        ok = got == expected
        status = "✅" if ok else "❌"
        if ok:
            strip_passed += 1
        else:
            strip_failed += 1
        print(f"  {status}  {inp!r:40} -> {got!r}")
        if not ok:
            print(f"       expected: {expected!r}")
    print(f"  {strip_passed}/{strip_passed+strip_failed} passed")
    print()
    print("PROCESS_PARAGRAPH demo:")
    print("-" * 72)
    raw_demo = (
        "*She laughs softly and shakes her head.*\n"
        "I really can't believe you said that.\n"
        "But honestly? It was kind of funny."
    )
    from src.tts.sanitizer import sanitize_for_tts  # type: ignore
    try:
        from src.config.language import LanguageContext  # type: ignore
        ctx = LanguageContext.from_string("en")
        sanitized_demo = sanitize_for_tts(raw_demo, ctx=ctx)
    except ImportError:
        # fallback se rodado fora do projeto
        sanitized_demo = re.sub(r"\*[^*]+\*", "", raw_demo).strip()
        sanitized_demo = re.sub(r"\s+", " ", sanitized_demo)

    print(f"  RAW:\n    {raw_demo!r}")
    print(f"  SANITIZED:\n    {sanitized_demo!r}")
    print()
    tagged_results = process_paragraph(sanitized_demo, raw_paragraph=raw_demo)
    for ts in tagged_results:
        print(f"  [{ts.tag_used or 'none':8}]  {ts.tagged}")
    print("=" * 72)