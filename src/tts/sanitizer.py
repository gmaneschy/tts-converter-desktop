import re
import unicodedata
from enum import Flag, auto
from typing import Optional
#from src.config.language import LanguageContext

# Import antecipado para evitar overhead de lookup a cada chamada de
# strip_rp_markup.  O try/except aqui é executado UMA vez no carregamento
# do módulo; _is_rp_paren_content fica None se supertonic_expression não
# estiver disponível (e.g. ambiente de testes sem a dependência).
try:
    from src.tts.supertonic_expression import _is_rp_paren_content as _is_rp_paren_content
except ImportError:
    _is_rp_paren_content = None  # type: ignore[assignment]

# ===============================
# 🔧 SUBSTITUIÇÕES SEMÂNTICAS — PT
# ===============================
SYMBOL_MAP_PT = {
    "¥": " iene ",      "$": " dólar ",     "€": " euro ",
    "£": " libra ",     "₹": " rúpia ",     "₩": " won ",
    "₽": " rublo ",     "₿": " bitcoin ",   "%": " por cento ",
    "‰": " por mil ",   "≈": " aproximadamente ",
    "≠": " diferente de ",  "≤": " menor ou igual a ",
    "≥": " maior ou igual a ", "±": " mais ou menos ",
    "×": " vezes ",     "÷": " dividido por ",
    "^": " elevado a ", "@": " arroba ",
    "&": " e ",         "+": " mais ",      "=": " igual a ",
}

# ===============================
# 🔧 SUBSTITUIÇÕES SEMÂNTICAS — EN
# ===============================
SYMBOL_MAP_EN = {
    "¥": " yen ",       "$": " dollar ",    "€": " euro ",
    "£": " pound ",     "₹": " rupee ",     "₩": " won ",
    "₽": " ruble ",     "₿": " bitcoin ",   "%": " percent ",
    "‰": " per mille ", "≈": " approximately ",
    "≠": " different from ", "≤": " less than or equal to ",
    "≥": " greater than or equal to ", "±": " plus or minus ",
    "×": " times ",     "÷": " divided by ",
    "^": " to the power of ", "@": " at ",
    "&": " and ",       "+": " plus ",      "=": " equals ",
}

# ===============================
# 📐 PADRÕES DE UNIDADES — PT
# ===============================
UNIT_PATTERNS_PT = {
    r"(\d+(?:[.,]\d+)?)\s*km/h\b":     r"\1 quilômetros por hora",
    r"(\d+(?:[.,]\d+)?)\s*m/s\b":      r"\1 metros por segundo",
    r"(\d+(?:[.,]\d+)?)\s*mph\b":      r"\1 milhas por hora",
    r"(\d+(?:[.,]\d+)?)\s*°C\b":       r"\1 graus Celsius",
    r"(\d+(?:[.,]\d+)?)\s*°F\b":       r"\1 graus Fahrenheit",
    r"(\d+(?:[.,]\d+)?)\s*K\b":        r"\1 kelvin",
    r"(\d+(?:[.,]\d+)?)\s*°\b":        r"\1 graus",
    r"(\d+(?:[.,]\d+)?)\s*km\b":       r"\1 quilômetros",
    r"(\d+(?:[.,]\d+)?)\s*cm\b":       r"\1 centímetros",
    r"(\d+(?:[.,]\d+)?)\s*mm\b":       r"\1 milímetros",
    r"(\d+(?:[.,]\d+)?)\s*mi\b":       r"\1 milhas",
    r"(\d+(?:[.,]\d+)?)\s*m\b":        r"\1 metros",
    r"(\d+(?:[.,]\d+)?)\s*ms\b":       r"\1 milissegundos",
    r"(\d+(?:[.,]\d+)?)\s*s\b":        r"\1 segundos",
    r"(\d+(?:[.,]\d+)?)\s*min\b":      r"\1 minutos",
    r"(\d+(?:[.,]\d+)?)\s*h(?:rs)?\b": r"\1 horas",
    r"(\d+(?:[.,]\d+)?)\s*kg\b":       r"\1 quilogramas",
    r"(\d+(?:[.,]\d+)?)\s*mg\b":       r"\1 miligramas",
    r"(\d+(?:[.,]\d+)?)\s*g\b":        r"\1 gramas",
    r"(\d+(?:[.,]\d+)?)\s*ml\b":       r"\1 mililitros",
    r"(\d+(?:[.,]\d+)?)\s*l\b":        r"\1 litros",
    r"(\d+(?:[.,]\d+)?)\s*GB\b":       r"\1 gigabytes",
    r"(\d+(?:[.,]\d+)?)\s*MB\b":       r"\1 megabytes",
    r"(\d+(?:[.,]\d+)?)\s*KB\b":       r"\1 kilobytes",
    r"(\d+(?:[.,]\d+)?)\s*GHz\b":      r"\1 gigahertz",
    r"(\d+(?:[.,]\d+)?)\s*MHz\b":      r"\1 megahertz",
    r"(\d+(?:[.,]\d+)?)\s*Hz\b":       r"\1 hertz",
}

# ===============================
# 📐 PADRÕES DE UNIDADES — EN
# ===============================
UNIT_PATTERNS_EN = {
    r"(\d+(?:[.,]\d+)?)\s*km/h\b":     r"\1 kilometers per hour",
    r"(\d+(?:[.,]\d+)?)\s*m/s\b":      r"\1 meters per second",
    r"(\d+(?:[.,]\d+)?)\s*mph\b":      r"\1 miles per hour",
    r"(\d+(?:[.,]\d+)?)\s*°C\b":       r"\1 degrees Celsius",
    r"(\d+(?:[.,]\d+)?)\s*°F\b":       r"\1 degrees Fahrenheit",
    r"(\d+(?:[.,]\d+)?)\s*K\b":        r"\1 kelvin",
    r"(\d+(?:[.,]\d+)?)\s*°\b":        r"\1 degrees",
    r"(\d+(?:[.,]\d+)?)\s*km\b":       r"\1 kilometers",
    r"(\d+(?:[.,]\d+)?)\s*cm\b":       r"\1 centimeters",
    r"(\d+(?:[.,]\d+)?)\s*mm\b":       r"\1 millimeters",
    r"(\d+(?:[.,]\d+)?)\s*mi\b":       r"\1 miles",
    r"(\d+(?:[.,]\d+)?)\s*m\b":        r"\1 meters",
    r"(\d+(?:[.,]\d+)?)\s*ms\b":       r"\1 milliseconds",
    r"(\d+(?:[.,]\d+)?)\s*s\b":        r"\1 seconds",
    r"(\d+(?:[.,]\d+)?)\s*min\b":      r"\1 minutes",
    r"(\d+(?:[.,]\d+)?)\s*h(?:rs)?\b": r"\1 hours",
    r"(\d+(?:[.,]\d+)?)\s*kg\b":       r"\1 kilograms",
    r"(\d+(?:[.,]\d+)?)\s*mg\b":       r"\1 milligrams",
    r"(\d+(?:[.,]\d+)?)\s*g\b":        r"\1 grams",
    r"(\d+(?:[.,]\d+)?)\s*ml\b":       r"\1 milliliters",
    r"(\d+(?:[.,]\d+)?)\s*l\b":        r"\1 liters",
    r"(\d+(?:[.,]\d+)?)\s*GB\b":       r"\1 gigabytes",
    r"(\d+(?:[.,]\d+)?)\s*MB\b":       r"\1 megabytes",
    r"(\d+(?:[.,]\d+)?)\s*KB\b":       r"\1 kilobytes",
    r"(\d+(?:[.,]\d+)?)\s*GHz\b":      r"\1 gigahertz",
    r"(\d+(?:[.,]\d+)?)\s*MHz\b":      r"\1 megahertz",
    r"(\d+(?:[.,]\d+)?)\s*Hz\b":       r"\1 hertz",
}


# ===============================
# 📐 PADRÕES DE UNIDADES — compilados uma vez no nível de módulo
# ===============================
# As strings brutas (UNIT_PATTERNS_PT/EN) permanecem públicas para inspeção;
# as versões compiladas (_UNIT_RE_PT/_UNIT_RE_EN) são usadas internamente.
_UNIT_RE_PT: list[tuple[re.Pattern, str]] = [
    (re.compile(p, re.IGNORECASE), r) for p, r in UNIT_PATTERNS_PT.items()
]
_UNIT_RE_EN: list[tuple[re.Pattern, str]] = [
    (re.compile(p, re.IGNORECASE), r) for p, r in UNIT_PATTERNS_EN.items()
]

# ===============================
# 🇧🇷 DICIONÁRIO DE CORREÇÃO FONÉTICA PT-BR — Supertonic (espeak-ng)
# ===============================
# O espeak-ng para pt-br comete erros sistemáticos que degradam a qualidade
# do Supertonic TTS. Este dicionário corrige as categorias mais impactantes
# via substituição ortográfica ANTES de enviar o texto ao engine.
#
# PRINCÍPIO DE APLICAÇÃO:
#   1. Apenas palavras inteiras (word boundary \b) — nunca substrings.
#   2. Case-insensitive com restauração de caixa no resultado.
#   3. Aplicado APÓS sanitize_for_tts (texto já limpo) e ANTES do engine.
#   4. Cobre os 7 casos de falha documentados do espeak-ng pt-br:
#
# CASO 1 — Ditongos nasais oxítonos (ão, ões, ãe)
#   espeak erra a tonicidade: "não" → /naw/ em vez de /nɐ̃w̃/
#   Fix: grafia alternativa que força leitura correta
#
# CASO 2 — Palavras funcionais com vogal átona final
#   PT-BR reduz /e/ final átono → /i/ e /o/ átono → /u/
#   espeak não aplica essa redução, gerando prosódia "europeia"
#
# CASO 3 — Ditongos decrescentes em sílabas átonas
#   "também" → espeak lê /tãˈbẽ/ em vez de /tãˈbẽj/
#
# CASO 4 — Clíticos e contrações
#   "dele", "numa", "nessa" → espeak trata como duas sílabas abertas
#
# CASO 5 — Verbos de uso muito frequente com irregularidades vocálicas
#
# CASO 6 — Nasais em posição final de sílaba
#   "bem", "tem", "vem" → espeak não nasaliza corretamente
#
# CASO 7 — Dígrafos e encontros consonantais específicos do PT-BR
# -----------------------------------------------------------------------
# FORMATO: { "palavra_original": "grafia_alternativa_que_espeak_lê_bem" }
# A grafia alternativa é FONÉTICA, não ortográfica correta.
# -----------------------------------------------------------------------

_PT_BR_ESPEAK_FIXES: dict[str, str] = {
    # ── CASO 1: Ditongos nasais oxítonos ─────────────────────────────────
    # "ão" final tônico — espeak lê /ao/ sem nasalização
    "não":           "nãum",
    "são":           "sãum",
    "então":         "entãum",
    "também":        "tambẽi",
    "irmão":         "irmãum",
    "mão":           "mãum",
    "mãos":          "mãums",
    "pão":           "pãum",
    "pães":          "pãiNs",
    "chão":          "shãum",
    "razão":         "razãum",
    "coração":       "corasãum",
    "atenção":       "atensãum",
    "intenção":      "intensãum",
    "menção":        "mensãum",
    "situação":      "situasãum",
    "condição":      "condisãum",
    "emoção":        "emosãum",
    "nação":         "nasãum",
    "ação":          "asãum",
    "questão":       "questãum",
    "ocasião":       "ocasiãum",
    "previsão":      "previZãum",
    "televisão":     "televisiZãum",
    "mansão":        "mansãum",
    "missão":        "misãum",
    "canção":        "cansãum",
    "paixão":        "paixãum",
    "traição":       "traisãum",
    "feição":        "feisãum",
    "audição":       "audisãum",
    "descrição":     "descriSãum",
    "ligação":       "ligasãum",
    "relação":       "relasãum",
    "solução":       "solusãum",
    "função":        "funsãum",
    "opinião":       "opiniãum",
    "reunião":       "reunjãum",
    "informação":    "informasãum",
    "comunicação":   "comunicasãum",
    "proteção":      "protesãum",
    "conexão":       "conesãum",
    "expressão":     "espresãum",
    "versão":        "versãum",
    "decisão":       "decisãum",
    "divisão":       "divisãum",
    "visão":         "visãum",
    "oração":        "orasãum",
    "vocação":       "vocasãum",
    "ilusão":        "ilusãum",
    "conclusão":     "conclusãum",
    "inclusão":      "inclusãum",
    "precisão":      "precisãum",
    "tensão":        "tensãum",
    "extensão":      "estensãum",
    "lição":         "lisãum",
    "porção":        "porsãum",
    "direção":       "diresãum",
    "posição":       "posisãum",
    "percepção":     "persepsãum",
    "exceção":       "esetsãum",
    # plurais
    "questões":      "questõiNs",
    "ações":         "asõiNs",
    "nações":        "nasõiNs",
    "emoções":       "emosõiNs",
    "condições":     "condisõiNs",
    "situações":     "situasõiNs",
    "funções":       "funsõiNs",
    "opiniões":      "opiniõiNs",
    "reuniões":      "reunjõiNs",
    "informações":   "informasõiNs",
    "versões":       "versõiNs",
    "decisões":      "decisõiNs",
    "razões":        "razõiNs",
    "direções":      "diresõiNs",
    "posições":      "posisõiNs",

    # "ã" final átono (paroxítona) — espeak abre demais
    "manhã":         "manhã",
    "amanhã":        "amanhã",
    "irmã":          "irmã",
    "já":            "zhá",      # /ʒ/ — espeak às vezes usa /j/

    # ── CASO 2: Vogais átonas finais (redução PT-BR) ─────────────────────
    # /e/ átono final → /i/ — espeak mantém /e/ aberto
    "me":            "mi",
    "te":            "ti",
    "se":            "si",
    "de":            "di",
    "que":           "qui",
    "ele":           "éli",
    "ela":           "éla",
    "esse":          "éssi",
    "este":          "ésti",
    "entre":         "êntri",
    "sobre":         "sóbri",
    "sempre":        "sêmpri",
    "possível":      "possívew",
    "difícil":       "difísiw",
    "fácil":         "fásiw",
    "útil":          "útiw",
    "gentil":        "zhentiw",
    "sutil":         "sutiw",
    "infantil":      "infantiw",
    "juvenil":       "zhuveniw",
    "funil":         "funiw",
    # clíticos pronominais
    "lhe":           "lyi",
    "lhes":          "lyis",
    "nos":           "nus",
    "vos":           "vus",
    # advérbios em -mente (espeak não aplica redução da vogal átona final)
    "realmente":     "reawmêntchi",
    "totalmente":    "totawmêntchi",
    "finalmente":    "finawmêntchi",
    "simplesmente":  "simplesmêntchi",
    "certamente":    "sertamêntchi",
    "diretamente":   "diretamêntchi",
    "exatamente":    "ezatamêntchi",
    "completamente": "completamêntchi",
    "provavelmente": "provavewmêntchi",
    "naturalmente":  "naturawmêntchi",
    "geralmente":    "zherawmêntchi",   # também cobre o /g/ palatal do CASO 7
    # adjetivos/particípios em -nte frequentes em diálogo
    "importante":    "importântchi",
    "suficiente":    "suficiêntchi",
    "diferente":     "diferêntchi",
    "seguinte":      "seguíntchi",
    "recente":       "resêntchi",
    "presente":      "prezêntchi",
    "ausente":       "auzêntchi",
    "urgente":       "urzhêntchi",
    "evidente":      "evidêntchi",
    "inocente":      "inosêntchi",

    # /o/ átono final → /u/ — espeak mantém /o/ semiaberto
    "pelo":          "pélu",
    "isso":          "íssu",
    "disso":         "díssu",
    "nisso":         "níssu",
    "disto":         "dístu",
    "isto":          "ístu",
    "aquilo":        "aquílu",
    "muito":         "múitu",
    "outro":         "óutru",
    "pouco":         "póuku",
    "nosso":         "nóssu",
    "vosso":         "vóssu",

    # ── CASO 3: Ditongos decrescentes ─────────────────────────────────────
    "bem":           "bẽi",
    "tem":           "tẽi",
    "vem":           "vẽi",
    "quem":          "kẽi",
    "sem":           "sẽi",
    "ninguém":       "ninguẽi",
    "alguém":        "alguẽi",
    "além":          "alẽi",
    "armazém":       "armazẽi",
    "convém":        "convẽi",
    "refém":         "refẽi",
    "tens":          "tẽis",
    "vens":          "vẽis",
    "bens":          "bẽis",

    # ── CASO 4: Clíticos, contrações e preposições compostas ──────────────
    "dele":          "déli",
    "dela":          "déla",
    "deles":         "délis",
    "delas":         "délas",
    "nele":          "néli",
    "nela":          "néla",
    "neles":         "nélis",
    "nelas":         "nélas",
    "pela":          "péla",
    "pelos":         "pélu s",
    "pelas":         "péla s",
    "numa":          "núma",
    "num":           "núm",
    "nuns":          "núns",
    "numas":         "númas",
    "nessa":         "néssa",
    "nesse":         "néssi",
    "nisto":         "nístu",
    "desse":         "déssi",
    "dessa":         "déssa",
    "daquele":       "dakéli",
    "daquela":       "dakéla",
    "àquele":        "akéli",
    "àquela":        "akéla",
    "daí":           "daí",
    "aí":            "aí",
    "ali":           "alí",
    "aqui":          "aquí",
    "até":           "até",
    "após":          "apóz",
    "dali":          "dalí",
    "daqui":         "dakí",
    "contigo":       "contígu",
    "comigo":        "comígu",
    "consigo":       "consígu",

    # ── CASO 5: Verbos de alta frequência com irregularidades ─────────────
    "é":             "é",
    "está":          "istá",
    "estão":         "istãum",
    "estou":         "istôu",
    "estamos":       "istâmus",
    "estavam":       "istávãum",
    "estava":        "istáva",
    "sou":           "sôu",
    "somos":         "sômus",
    "há":            "á",
    "haja":          "ázhia",
    "houve":         "ôuvi",
    "houveram":      "ouvérãum",
    "havia":         "avía",
    "teria":         "tería",
    "seria":         "séria",
    "podia":         "podjia",
    "dizia":         "dizia",
    "ouvia":         "ouvía",
    "vivia":         "vivía",
    "daria":         "daría",
    "faria":         "faría",
    "iria":          "iría",
    "tenho":         "têniu",
    "tenha":         "tênia",
    "venho":         "vêniu",
    "venha":         "vênia",
    "venham":        "vêniãum",
    "ponho":         "pôniu",
    "ponha":         "pônia",
    "faço":          "fásu",
    "faça":          "fása",
    "passo":         "pásu",
    "posso":         "pósu",
    "quero":         "kéru",
    "queira":        "kéira",
    "queiram":       "kéirãum",
    "saiba":         "sáiba",
    "saibam":        "sáibãum",
    "sei":           "séi",
    "foi":           "fói",
    "vou":           "vôu",
    "vai":           "vái",
    "vão":           "vãum",
    "veio":          "véiu",
    "trouxe":        "trôushi",
    "trouxeram":     "trôushérãum",
    "disse":         "díssi",
    "disseram":      "disérãum",
    "fez":           "fêz",
    "fizeram":       "fizérãum",
    "pôs":           "pôz",
    "puseram":       "puzérãum",
    # subjuntivo/imperativo de alta frequência em diálogo
    "seja":          "sézhia",
    "sejam":         "sézhiãum",
    "esteja":        "istézhia",
    "estejam":       "istézhiãum",

    # ── CASO 6: Nasais internas e finais problemáticas ────────────────────
    "com":           "cõm",
    "bom":           "bõm",
    "tom":           "tõm",
    "som":           "sõm",
    "dom":           "dõm",
    "rim":           "rĩm",
    "sim":           "sĩm",
    "assim":         "assĩm",
    "jardim":        "zhardĩm",
    "atum":          "atũm",
    "algum":         "algũm",
    "alguma":        "algũma",
    "nenhum":        "neniũm",
    "nenhuma":       "neniũma",
    "jejum":         "zhezhũm",
    "fórum":         "fórũm",

    # ── CASO 7: Dígrafos e fricativas específicas do PT-BR ────────────────
    # /ʒ/ — espeak às vezes usa /dʒ/ ou /j/ para "g" + vogal frontal
    "hoje":          "ôzhi",
    "gente":         "zhêntchi",
    "gênio":         "zhêniu",
    "geral":         "zherâw",
    "girar":         "zhirár",
    "geração":       "zherasãum",
    "viagem":        "viázhẽi",
    "coragem":       "corázhẽi",
    "garagem":       "garázhẽi",
    "mensagem":      "mensázhẽi",
    "imagem":        "imázhẽi",
    "personagem":    "personázhẽi",
    "linguagem":     "linguázhẽi",

    # /tʃ/ e /dʒ/ — assimilação de /t/ e /d/ antes de /i/ (PT-BR culto)
    "dia":           "djia",
    "dias":          "djias",
    "tinha":         "tchinha",
    "tio":           "tchiu",
    "tia":           "tchia",
    "tias":          "tchias",
    "tios":          "tchius",
    "tipo":          "tchipu",
    "time":          "tchimi",
    "atitude":       "atichudi",
    "latitude":      "latichudi",

    # /lh/ (lateral palatal) — espeak não palataliza sistematicamente
    "filho":         "fílyu",
    "filha":         "fílya",
    "milho":         "mílyu",
    "galho":         "gályu",
    "palha":         "pálya",
    "talho":         "tályu",
    "velho":         "vélyu",
    "velha":         "vélya",
    "brilho":        "brílyu",
    "julho":         "zhúlyu",
    "melhor":        "melyôr",
    "melhorar":      "melyorár",
    "escolha":       "eskólya",
    "escolher":      "eskolyêr",
    "olho":          "ólyu",
    "olhos":         "ólyus",
    "olhar":         "olyár",
    "molhar":        "molyár",
    "colher":        "colyêr",
    "ilha":          "ílya",
    "ilhas":         "ílyas",
    "trilha":        "trílya",
    "trilhar":       "trilyár",
    "espelho":       "espélyu",
    "joelho":        "zhoélyu",
    "telhado":       "telyádu",
    "agulha":        "agúlya",
    "orgulho":       "orgúlyu",
    "vermelho":      "vermélyu",
    "coelho":        "coélyu",
    "rolha":         "rólya",
    "batalha":       "batalya",
    "medalha":       "medalya",
    "toalha":        "toalya",
    "folha":         "fólya",
    "folhas":        "fólyas",
    "bolha":         "bólya",

    # /nh/ (nasal palatal) — espeak às vezes não palataliza
    "trabalhar":     "trabalyár",
    "mulher":        "mulyêr",
    "sonho":         "sôniu",
    "sonhos":        "sônius",
    "sonhar":        "soniár",
    "banho":         "bâniu",
    "banhos":        "bânius",
    "ganha":         "gânia",
    "ganhar":        "ganiár",
    "rainha":        "raínia",
    "linha":         "línia",
    "linhas":        "línias",
    "minha":         "mínia",
    "vinha":         "vínia",
    "cunha":         "cúnia",
    "pinho":         "píniu",
    "ninho":         "níniu",
    "tamanho":       "tamâniu",
    "companhia":     "companiía",
    "fazer":         "fazêr",
    "falar":         "falár",
    "elho":          "élyu",
    "castorp":       "cástor-p",
    "llm":           "éle éle émi",
    "tts":           "tê tê ésse",
    "apis":          "apeís",
    "ocr":           "ô cê érri",
    "vrm":           "vê érri émi",
    "2d":            "dois dê",
    "live2d":        "láivi dois dê",
}

# Pré-compila os padrões do dicionário PT-BR em UMA ÚNICA regex de alternação
# com callback — substitui o loop de ~150 chamadas a pattern.sub() por uma
# passagem única sobre o texto.
#
# Estratégia:
#   1. Deduplica _PT_BR_ESPEAK_FIXES (o dict-literal tinha entradas repetidas
#      que geravam padrões compilados redundantes).
#   2. Ordena por comprimento decrescente para que matches mais longos
#      (ex.: "estavam") sejam testados antes dos mais curtos ("está").
#   3. Compila a alternação (\b(palavra1|palavra2|...)\b, IGNORECASE).
#   4. O callback _pt_br_fix_sub faz lookup O(1) no dict e restaura a caixa
#      original quando a substituição é uma grafia fonética pura (sem acento
#      já imposto pelo dicionário).

_PT_BR_ESPEAK_FIXES_DEDUPED: dict[str, str] = dict(_PT_BR_ESPEAK_FIXES)

_PT_BR_ALT_RE: re.Pattern = re.compile(
    r"\b(" +
    "|".join(
        re.escape(w)
        for w in sorted(_PT_BR_ESPEAK_FIXES_DEDUPED, key=len, reverse=True)
    ) +
    r")\b",
    re.IGNORECASE,
)


def _pt_br_fix_sub(m: re.Match) -> str:
    return _PT_BR_ESPEAK_FIXES_DEDUPED[m.group(1).lower()]


def apply_pt_br_phoneme_fixes(text: str) -> str:
    """
    Aplica correções fonéticas PT-BR para motores que usam espeak-ng
    como backend de fonemização (Supertonic).

    Implementação: substituição em passagem única via regex de alternação,
    em vez do loop anterior de ~150 chamadas a pattern.sub().

    Deve ser chamada APÓS sanitize_for_tts() e ANTES de enviar o texto
    ao engine. Para o Kokoro, esta função é desnecessária quando o
    XphoneBR está instalado — o G2P Transformer já produz IPA correto.

    As substituições usam grafia alternativa que o espeak-ng interpreta
    corretamente, preservando a prosódia natural do PT-BR:
      • Ditongos nasais oxítonos (não, então, também)
      • Vogais átonas finais (/e/→/i/, /o/→/u/)
      • Assimilações /t/→/tʃ/ e /d/→/dʒ/ antes de /i/
      • Lateral palatal /lh/ → /j/ (pronúncia carioca/paulistana)
      • Nasais em coda silábica
    """
    return _PT_BR_ALT_RE.sub(_pt_br_fix_sub, text)


# ===============================
# 🌐 SUPORTE A SCRIPTS POR ENGINE
# ===============================
class ScriptSupport(Flag):
    LATIN      = auto()
    CJK        = auto()
    CYRILLIC   = auto()
    ARABIC     = auto()
    DEVANAGARI = auto()
    HANGUL     = auto()
    THAI       = auto()
    HEBREW     = auto()

# Ranges Unicode por script (exceto Latin, que é sempre base)
_SCRIPT_RANGES: dict[ScriptSupport, str] = {
    ScriptSupport.CJK:        r"\u4E00-\u9FFF\u3040-\u30FF\u31F0-\u31FF\u3400-\u4DBF\uF900-\uFAFF",
    ScriptSupport.CYRILLIC:   r"\u0400-\u04FF",
    ScriptSupport.ARABIC:     r"\u0600-\u06FF",
    ScriptSupport.DEVANAGARI: r"\u0900-\u097F",
    ScriptSupport.HANGUL:     r"\uAC00-\uD7AF\u1100-\u11FF",
    ScriptSupport.THAI:       r"\u0E00-\u0E7F",
    ScriptSupport.HEBREW:     r"\u0590-\u05FF",
}

# Capability declarada por engine:lang
# Baseado em VOICES.md — Kokoro usa misaki[zh] e misaki[ja] como G2P nativo,
# sem fallback espeak, portanto CJK é suportado nativamente.
ENGINE_SCRIPT_SUPPORT: dict[str, ScriptSupport] = {
    # Kokoro — idiomas com G2P Latin apenas
    "kokoro:pt-br":  ScriptSupport.LATIN,
    "kokoro:en-us":  ScriptSupport.LATIN,
    "kokoro:en-gb":  ScriptSupport.LATIN,
    "kokoro:es":     ScriptSupport.LATIN,
    "kokoro:fr-fr":  ScriptSupport.LATIN,
    # Kokoro — idiomas com G2P nativo não-Latin (misaki[ja], misaki[zh])
    "kokoro:ja":     ScriptSupport.LATIN | ScriptSupport.CJK,
    "kokoro:zh":     ScriptSupport.LATIN | ScriptSupport.CJK,
    # Kokoro — outros idiomas com script próprio
    "kokoro:ko":     ScriptSupport.LATIN | ScriptSupport.HANGUL,
    "kokoro:hi":     ScriptSupport.LATIN | ScriptSupport.DEVANAGARI,
    # Supertonic — indexado por lang (multilíngue desde supertonic-3 atualizado)
    # Idiomas Latin-only
    "supertonic:en": ScriptSupport.LATIN,
    "supertonic:es": ScriptSupport.LATIN,
    "supertonic:pt": ScriptSupport.LATIN,
    "supertonic:fr": ScriptSupport.LATIN,
    "supertonic:de": ScriptSupport.LATIN,
    "supertonic:it": ScriptSupport.LATIN,
    "supertonic:nl": ScriptSupport.LATIN,
    "supertonic:pl": ScriptSupport.LATIN,
    "supertonic:ro": ScriptSupport.LATIN,
    "supertonic:cs": ScriptSupport.LATIN,
    "supertonic:sk": ScriptSupport.LATIN,
    "supertonic:sl": ScriptSupport.LATIN,
    "supertonic:hr": ScriptSupport.LATIN,
    "supertonic:hu": ScriptSupport.LATIN,
    "supertonic:da": ScriptSupport.LATIN,
    "supertonic:sv": ScriptSupport.LATIN,
    "supertonic:fi": ScriptSupport.LATIN,
    "supertonic:et": ScriptSupport.LATIN,
    "supertonic:lv": ScriptSupport.LATIN,
    "supertonic:lt": ScriptSupport.LATIN,
    "supertonic:id": ScriptSupport.LATIN,
    "supertonic:vi": ScriptSupport.LATIN,
    "supertonic:tr": ScriptSupport.LATIN,
    "supertonic:el": ScriptSupport.LATIN,   # Grego — usa LATIN como base de romanização
    # Idiomas com script próprio além do Latin
    "supertonic:ru": ScriptSupport.LATIN | ScriptSupport.CYRILLIC,
    "supertonic:uk": ScriptSupport.LATIN | ScriptSupport.CYRILLIC,
    "supertonic:bg": ScriptSupport.LATIN | ScriptSupport.CYRILLIC,
    "supertonic:ar": ScriptSupport.LATIN | ScriptSupport.ARABIC,
    "supertonic:hi": ScriptSupport.LATIN | ScriptSupport.DEVANAGARI,
    "supertonic:ko": ScriptSupport.LATIN | ScriptSupport.HANGUL,
    "supertonic:ja": ScriptSupport.LATIN | ScriptSupport.CJK,
    # StyleTTS2 — apenas Latin
    "styletts2":     ScriptSupport.LATIN,
}


def resolve_script_support(engine: str, lang: str | None = None) -> ScriptSupport:
    """
    Resolve ScriptSupport para um engine/lang.

    Para Supertonic e Kokoro, o lang é obrigatório para resolução correta —
    ambos indexam por "engine:lang". Para StyleTTS2, lang é ignorado.
    Fallback: LATIN apenas.
    """
    key = f"{engine}:{lang}" if lang else engine
    return ENGINE_SCRIPT_SUPPORT.get(key, ScriptSupport.LATIN)


# ===============================
# 🎭 LIMPEZA DE MARCAÇÃO DE RP
# ===============================
def strip_rp_markup(text: str, destructive: bool = False) -> str:
    """
    Remove marcação de RP.

    destructive = False -> mantém conteúdo interno (lido como pausa)
    destructive = True  -> remove bloco inteiro

    Parênteses simples (texto):
      São ambíguos — podem ser ação de RP "(ri levemente)" ou informação
      legítima "(1984)". Apenas parênteses cujo conteúdo pareça uma ação
      de RP são tratados; os demais são preservados intactos.
      A detecção usa _is_rp_paren_content de supertonic_expression.py.
      Para não criar dependência circular, a heurística é replicada aqui
      como _paren_rp_sub() via importação lazy.
    """
    # Padrões não-ambíguos — tratamento idêntico ao anterior
    if destructive:
        text = re.sub(r"\(\(.*?\)\)", " ", text, flags=re.DOTALL)
        text = re.sub(r"\[\[.*?]]", " ", text, flags=re.DOTALL)
        text = re.sub(r"\*{1,3}[^*\n]+?\*{1,3}", " ", text)
        text = re.sub(r"_{1,2}[^_\n]+?_{1,2}", " ", text)
        text = re.sub(r"~{1,2}[^~\n]+?~{1,2}", " ", text)
    else:
        text = re.sub(r"\(\(\s*(.*?)\s*\)\)", r", , \1, , ", text, flags=re.DOTALL)
        text = re.sub(r"\[\[\s*(.*?)\s*]]", r", , \1, , ", text, flags=re.DOTALL)
        text = re.sub(r"\*{1,3}([^*\n]+?)\*{1,3}", r", , \1, , ", text)
        text = re.sub(r"_{1,2}([^_\n]+?)_{1,2}", r", , \1, , ", text)
        text = re.sub(r"~{1,2}([^~\n]+?)~{1,2}", r", , \1, , ", text)

    # Parênteses simples — heurística de conteúdo
    # _is_rp_paren_content é importado no nível de módulo (None se
    # supertonic_expression não estiver disponível).
    def _paren_sub(m: re.Match) -> str:
        content = m.group(1)
        if _is_rp_paren_content is None or not _is_rp_paren_content(content):
            return m.group(0)   # parêntese informativo — preserva intacto
        if destructive:
            return " "
        return f", , {content.strip()}, , "

    text = re.sub(r"\(([^()\n]{2,80})\)", _paren_sub, text)

    text = re.sub(r"^\s*>+\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"#(\w+)", r"\1", text)

    return text


def fix_single_letter_stutter(text: str) -> str:
    """
    Converte padrões como 'Y-yes' em uma disfluência natural para TTS.
    """
    filler = "uh… "
    pattern = r"\b([A-Za-zÀ-ÿ])-(\w+)"

    def replacer(match):
        letter = match.group(1)
        word   = match.group(2)
        if len(letter) == 1:
            return f"{filler}{word}"
        return match.group(0)

    return re.sub(pattern, replacer, text)


def apply_dramatic_pauses(text: str) -> str:
    """
    Aplica pausas dramáticas universais para TTS.

    Vírgula dupla (, ,) é usada como marcador de pausa longa:
    cada vírgula extra força um beat adicional no Kokoro/Supertonic
    sem exigir capitalização da palavra seguinte (ao contrário de ponto).
    """
    text = re.sub(r"\.{3,}", ", , ", text)
    text = re.sub(r"\s[—–]\s", ", , ", text)
    text = re.sub(r"\s-\s", ", , ", text)
    text = re.sub(r"-{2,}", ", , ", text)
    return text


# ===============================
# 🔤 STRIP POR SCRIPT SUPORTADO
# ===============================
# NOTA: O apóstrofo reto (U+0027) é declarado explicitamente como \x27
# fora do charset, para evitar ambiguidade com \' dentro de [...].
# Os codepoints curvos U+2018/2019/201C/201D são omitidos aqui porque
# o passo 4 já os normalizou para retos antes desta chamada.
# Símbolos especiais ($, ^, +, =, *) são tratados pelo SYMBOL_MAP_*
# antes deste passo e não precisam constar no charset de preservação.
_LATIN_BASE = (
    "a-zA-ZÀ-ÖØ-öø-ÿ0-9ªº"
    " .,;:!?()"
    "\x27"          # apóstrofo reto U+0027 — essencial para contrações (don't, i'm, i'll)
    "\""            # aspas duplas retas
    "\u2014\u2013"  # — (em dash) e – (en dash)
    "\\-_/\\\\…@#€%"
)

def strip_unsupported_scripts(text: str, support: ScriptSupport) -> str:
    """
    Remove caracteres de scripts não suportados pelo engine.
    Latin é sempre preservado como base.

    O apóstrofo reto (U+0027) é preservado explicitamente via \\x27
    no charset, garantindo que contrações como don't, i'm, i'll
    sobrevivam intactas após a normalização do passo 4.

    Símbolos como $, ^, +, =, & já foram substituídos semanticamente
    pelo SYMBOL_MAP antes desta chamada, portanto não precisam estar
    no charset de preservação.
    """
    allowed = _LATIN_BASE
    for script, ranges in _SCRIPT_RANGES.items():
        if script in support:
            allowed += ranges

    return re.sub(f"[^{allowed}]", " ", text)


# ===============================
# 🎙️ EXPRESSION TAGS — SUPERTONIC 3
# ===============================
# Tags de expressão suportadas nativamente pelo Supertonic 3.
# Referência: https://github.com/supertone-inc/supertonic-py
# Devem ser preservadas intactas através dos passos 3️⃣ (strip HTML)
# e 🔟 (strip_unsupported_scripts), que de outra forma as destruiriam.
# Estratégia: substituir por placeholder com null bytes (U+0000) antes
# do passo 3️⃣ e restaurar após o passo 🔟. Null bytes não ocorrem em
# texto normal, eliminando risco de colisão com conteúdo real.
_SUPERTONIC_EXPRESSION_TAGS: frozenset[str] = frozenset(["laugh", "breath", "sigh", "sad", "cough"])


def _protect_expression_tags(text: str) -> tuple[str, dict[str, str]]:
    """
    Substitui <laugh>, <breath> e <sigh> por placeholders imunes ao pipeline.

    Retorna (texto_com_placeholders, mapa_placeholder→tag_original).
    Apenas tags cujo nome (case-insensitive) esteja em
    _SUPERTONIC_EXPRESSION_TAGS são protegidas; qualquer outra tag HTML
    continua a ser removida normalmente pelo passo 3️⃣.
    """
    # Fast-path: evita alocação de dict e regex quando o texto não
    # contém '<' ou nenhuma das tags de expressão conhecidas.
    if "<" not in text or not any(t in text.lower() for t in _SUPERTONIC_EXPRESSION_TAGS):
        return text, {}

    placeholders: dict[str, str] = {}

    def replacer(match: re.Match) -> str:
        tag_name = match.group(1).lower()
        if tag_name in _SUPERTONIC_EXPRESSION_TAGS:
            canonical = f"<{tag_name}>"          # normaliza capitalização
            placeholder = f"\x00EXPR:{tag_name}\x00"
            placeholders[placeholder] = canonical
            return placeholder
        return match.group(0)                     # deixa outras tags intactas

    text = re.sub(r"<([A-Za-z]+)>", replacer, text)
    return text, placeholders


def _restore_expression_tags(text: str, placeholders: dict[str, str]) -> str:
    """
    Restaura os placeholders gerados por _protect_expression_tags
    para as tags originais canônicas (<laugh>, <breath>, <sigh>).
    """
    for placeholder, tag in placeholders.items():
        text = text.replace(placeholder, tag)
    return text


# ===============================
# 🧽 SANITIZER PRINCIPAL
# ===============================
def sanitize_for_tts(
    text: str,
    ctx: "Optional[LanguageContext]" = None,
    remove_rp_actions: bool = False,
    script_support: ScriptSupport = ScriptSupport.LATIN,
    apply_espeak_fixes: bool = False,
) -> str:
    """
    Sanitiza texto para síntese de voz (TTS).

    Args:
        text:               Texto bruto a sanitizar.
        ctx:                LanguageContext do sistema. Se None, usa PT como fallback.
        remove_rp_actions:  Se True, elimina ações de RP do TTS.
        script_support:     Scripts Unicode permitidos pelo engine ativo.
                            Resolver via resolve_script_support(engine, lang).
        apply_espeak_fixes: Se True, aplica o dicionário de correção fonética
                            PT-BR para engines que usam espeak-ng como backend
                            (Supertonic). Deve ser False para Kokoro com XphoneBR.
    """

    if not text:
        return ""

    is_en         = ctx.is_en if ctx is not None else False
    symbol_map    = SYMBOL_MAP_EN    if is_en else SYMBOL_MAP_PT
    unit_patterns = _UNIT_RE_EN      if is_en else _UNIT_RE_PT

    # 1️⃣ Remove marcação de RP
    text = strip_rp_markup(text, destructive=remove_rp_actions)

    # 2️⃣ Remove URLs antes da regex IPA — evita que segmentos de URL com
    # caracteres IPA sejam mutilados antes de serem descartados por completo.
    text = re.sub(r"https?://\S+", " ", text)

    # 2b️⃣ Remove IPA e colchetes fonéticos
    text = re.sub(r"\[[^]]*?]", " ", text)
    text = re.sub(r"/[ˈˌæɛɪɔʊʌəɑɜʃʒθðŋ][^/]{1,40}/", " ", text)

    # 2c️⃣ Protege expression tags do Supertonic 3 (<laugh>, <breath>, <sigh>)
    # antes que o passo 3️⃣ as remova junto com o HTML genérico.
    text, _expr_placeholders = _protect_expression_tags(text)

    # 3️⃣ Remove HTML/XML
    text = re.sub(r"<[^>]+>", " ", text)

    # 4️⃣ Normaliza apóstrofos e aspas curvos → retos (ANTES do NFKC e do misaki)
    # LLMs e editores usam ' (U+2019) e " (U+201C/D) por padrão.
    # Sem essa normalização, contrações como "don't" chegam ao misaki
    # como "don t" (palavra partida), causando fonemas completamente errados.
    text = text.replace("\u2018", "'").replace("\u2019", "'")   # ' '  → '
    text = text.replace("\u201C", '"').replace("\u201D", '"')   # " "  → "
    text = text.replace("\u02BC", "'")                          # ʼ modifier letter

    # 4b️⃣ Remove aspas usadas como delimitadores ao redor de tokens
    # Ex: 'sdxl', "house" — geradas por tool results e f-strings do sistema.
    # O misaki EN interpreta aspas ao redor de palavras como marcação prosódica,
    # alterando entonação e às vezes gerando fonemas errados.
    #
    # CORREÇÃO: a regex de aspas simples agora usa [^'\n] sem lookahead,
    # o que é seguro porque qualquer contração (don't, i'm, i'll) contém
    # um apóstrofo interno — isso impede o match do grupo inteiro, preservando
    # a contração. Tokens-delimitador genuínos ('sdxl', 'house') não têm
    # apóstrofo interno e são removidos corretamente.
    text = re.sub(r"(?<![A-Za-z])'([^'\n]{1,60})'(?![A-Za-z])", r"\1", text)
    # Aspas duplas: pausa longa antes e depois do conteúdo de fala direta.
    # Ex: She said "don't worry" → She said , , don't worry , ,
    text = re.sub(r'"([^"\n]{1,60})"', r", , \1, , ", text)

    # 5️⃣ Normalização Unicode
    text = unicodedata.normalize("NFKC", text)

    # 6️⃣ Corrige gagueira tipo "Y-yes"
    text = fix_single_letter_stutter(text)

    # 7️⃣ Aplica pausas dramáticas universais
    text = apply_dramatic_pauses(text)

    # 8️⃣ Substituições de unidades (padrões pré-compilados)
    for pattern, repl in unit_patterns:
        text = pattern.sub(repl, text)

    # 9️⃣ Substituição de símbolos semânticos
    # IMPORTANTE: deve ocorrer ANTES de strip_unsupported_scripts,
    # pois converte $, ^, +, = etc. em palavras que serão preservadas.
    for symbol, replacement in symbol_map.items():
        text = text.replace(symbol, replacement)

    # 🔟 Remove scripts não suportados pelo engine
    text = strip_unsupported_scripts(text, script_support)

    # 🔟+️⃣ Restaura expression tags após o strip de scripts.
    # Os placeholders contêm null bytes (U+0000), que strip_unsupported_scripts
    # remove junto com outros caracteres fora do _LATIN_BASE, portanto a
    # restauração precisa ocorrer aqui, não antes do passo 🔟.
    # Nota: se _expr_placeholders estiver vazio (nenhuma tag no texto),
    # esta chamada é no-op.
    text = _restore_expression_tags(text, _expr_placeholders)

    # 🔟+1️⃣ Correções fonéticas PT-BR para engines com espeak-ng (Supertonic).
    # Aplicado APÓS a restauração de tags e ANTES da normalização final para
    # que as substituições de palavra inteira não interfiram com placeholders.
    # Para Kokoro com XphoneBR instalado, este passo deve ser omitido
    # (apply_espeak_fixes=False, padrão) pois o G2P Transformer já lida
    # corretamente com a fonologia do PT-BR.
    if apply_espeak_fixes and not (ctx.is_en if ctx is not None else False):
        text = apply_pt_br_phoneme_fixes(text)

    # 1️⃣1️⃣ Remove emojis restantes
    text = re.sub(
        "[\U0001F300-\U0001FAFF]+",
        " ",
        text,
    )

    # 1️⃣2️⃣ Normaliza espaços
    text = re.sub(r"\s+", " ", text).strip()

    # 1️⃣3️⃣ Limpa vírgulas mal posicionadas geradas pelas injeções de pausa:
    # colapsa mais de 2 vírgulas consecutivas, remove espaço antes de vírgula,
    # remove vírgula após pontuação de frase, remove vírgula no início/fim.
    text = re.sub(r"\s+,", ",", text)                  # " ," → ","
    text = re.sub(r"(,\s*){3,}", ", , ", text)         # 3+ vírgulas → exatamente 2
    text = re.sub(r"([.!?])\s*,\s*,?", r"\1 ", text)  # ". ,," → ". "
    text = re.sub(r"^[,\s]+", "", text)                # vírgulas no início
    text = re.sub(r"[,\s]+$", "", text)                # vírgulas no fim

    return text