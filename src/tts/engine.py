import asyncio
import io
import os
import threading
import time
import wave

import numpy as np
import sounddevice as sd

from src.utils.paths import supertonic_dir

os.environ.setdefault("HF_HOME", str(supertonic_dir() / ".cache" / "huggingface"))

from kokoro_onnx import Kokoro
from supertonic import TTS
from supertonic.config import AVAILABLE_LANGUAGES
from src.tts.rvc import RVCConverter
from src.tts.styles import get_style_params

# ===========================================================================
# 🔥 Torch 2.6+ — patch feito UMA VEZ no nível de módulo
# ===========================================================================
import torch  # noqa: E402

try:
    torch.serialization.add_safe_globals([getattr])
except Exception:
    pass

if not hasattr(torch.load, "_patched_by_agentlena"):
    _original_torch_load = torch.load

    def _patched_torch_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return _original_torch_load(*args, **kwargs)

    _patched_torch_load._patched_by_agentlena = True  # type: ignore[attr-defined]
    torch.load = _patched_torch_load  # type: ignore[assignment]


# ===========================================================================


class SupertonicTTSEngine:
    def __init__(
        self,
        voice_name: str = "F5",
        lang: str = "pt",
        model: str = "supertonic-3",
        speed: float = 1.05,
        total_steps: int = 10,
        intra_threads: int | None = None,
        inter_threads: int | None = None,
        warmup: bool = True,
        rvc: "RVCConverter | None" = None,
    ):
        print("🔊 Carregando Supertonic TTS...")
        start = time.perf_counter()

        self.tts = TTS(
            model=model,
            auto_download=True,
            intra_op_num_threads=intra_threads,
            inter_op_num_threads=inter_threads,
        )

        if lang not in AVAILABLE_LANGUAGES:
            raise ValueError(
                f"Idioma inválido: {lang}. Disponíveis: {AVAILABLE_LANGUAGES}"
            )

        self.lang = lang
        self.voice_name = voice_name
        self.voice_style = self.tts.get_voice_style(voice_name)

        self._voice_cache = {voice_name: self.voice_style}

        self.sample_rate = self.tts.sample_rate

        self._base_speed = speed
        self._base_total_steps = total_steps

        self.speed = speed
        self.total_steps = total_steps

        self._lock = threading.Lock()

        elapsed = time.perf_counter() - start
        print(
            f"✅ Supertonic carregado em {elapsed:.2f}s | "
            f"🎙️ Voice={voice_name} | 🌎 Lang={lang}"
        )

        if warmup:
            print("🔥 Warm-up Supertonic...")
            try:
                self.tts.synthesize(
                    "teste",
                    voice_style=self.voice_style,
                    total_steps=self.total_steps,
                    speed=self.speed,
                    lang=self.lang,
                )
                print("✅ Warm-up concluído")
            except Exception as e:
                print(f"⚠️ Warm-up falhou: {e}")
        self.rvc = rvc

    def set_voice(self, voice_name: str):
        if voice_name not in self._voice_cache:
            self._voice_cache[voice_name] = self.tts.get_voice_style(voice_name)

        self.voice_style = self._voice_cache[voice_name]

    def speak(self, text: str) -> float:
        if not text.strip():
            return 0.0

        with self._lock:
            return self._synthesize_and_play(text, self._base_speed, self._base_total_steps)

    def speak_with_style(self, text: str, style: str) -> float:
        if not text.strip():
            return 0.0

        params = get_style_params(style)
        speed       = params["speed"]
        total_steps = params["total_steps"]

        with self._lock:
            return self._synthesize_and_play(text, speed, total_steps)

    def _synthesize_and_play(self, text: str, speed: float, total_steps: int) -> float:
        """Síntese + playback com parâmetros explícitos. Deve ser chamado com _lock adquirido."""
        start = time.perf_counter()
        wav, _ = self.tts.synthesize(
            text,
            voice_style=self.voice_style,
            total_steps=total_steps,
            speed=speed,
            lang=self.lang,
        )
        wav = wav.flatten().astype(np.float32)
        sr = self.sample_rate
        if self.rvc is not None:
            try:
                wav, sr = self.rvc.convert(wav, sr)
            except Exception as e:
                print(f"⚠️ RVC falhou, usando áudio original: {e}")
        with sd.OutputStream(samplerate=sr, channels=1, dtype="float32") as stream:
            stream.write(wav.reshape(-1, 1))
        return time.perf_counter() - start

    def synthesize_pcm(self, text: str, style: str = "neutral") -> tuple[bytes, int]:
        """
        Sintetiza e retorna (pcm_int16_bytes, sample_rate) SEM encapsular em WAV.

        Preferir este método quando o caller vai concatenar vários chunks antes
        de montar o WAV final (ex.: _synthesize_tagged_bytes em inference.py),
        eliminando o ciclo encode→decode→encode de WAV intermediário.
        """
        params      = get_style_params(style)
        speed       = params["speed"]
        total_steps = params["total_steps"]
        with self._lock:
            wav, _ = self.tts.synthesize(
                text,
                voice_style=self.voice_style,
                total_steps=total_steps,
                speed=speed,
                lang=self.lang,
            )
            wav = wav.flatten().astype(np.float32)
            sr = self.sample_rate
            if self.rvc is not None:
                try:
                    wav, sr = self.rvc.convert(wav, sr)
                except Exception as e:
                    print(f"⚠️ RVC falhou: {e}")
            pcm = (wav * 32767).clip(-32768, 32767).astype(np.int16)
            return pcm.tobytes(), sr

    def synthesize_bytes(self, text: str, style: str = "neutral") -> bytes:
        """Sintetiza e retorna WAV bytes completo (single-chunk)."""
        pcm, sr = self.synthesize_pcm(text, style)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm)
        return buf.getvalue()


# ---------------------------------------------------------------------------
# Singleton de SupertonicTTSEngine
#
# Garante que apenas UMA instância do modelo Supertonic (ONNX/PyTorch) exista
# no processo. Tanto o AgentWorker quanto o _OnboardingTTS devem usar estas
# funções para obter/registrar o engine, evitando o crash 0xC0000005 causado
# por dois modelos ONNX Runtime ativos simultaneamente no Windows.
# ---------------------------------------------------------------------------

_supertonic_singleton: "SupertonicTTSEngine | None" = None
_supertonic_singleton_lock = threading.Lock()


def get_supertonic_singleton() -> "SupertonicTTSEngine | None":
    """Retorna o singleton de SupertonicTTSEngine, ou None se ainda não criado."""
    return _supertonic_singleton


def set_supertonic_singleton(engine: "SupertonicTTSEngine | None") -> None:
    """
    Registra (ou limpa) o singleton de SupertonicTTSEngine.

    Deve ser chamado pelo AgentWorker imediatamente após criar/destruir o engine.
    Thread-safe: usa _supertonic_singleton_lock internamente.
    """
    global _supertonic_singleton
    with _supertonic_singleton_lock:
        _supertonic_singleton = engine


def get_or_create_supertonic_singleton(
    voice_name: str = "F4",
    lang: str = "pt",
    **kwargs,
) -> "SupertonicTTSEngine":
    """
    Retorna o singleton existente ou cria um novo se ainda não houver um.

    Parâmetros de construção (voice_name, lang, **kwargs) só são usados quando
    um novo engine precisa ser criado; se o singleton já existe, os parâmetros
    são ignorados e o engine em uso é retornado sem modificação.

    Thread-safe.
    """
    global _supertonic_singleton
    with _supertonic_singleton_lock:
        if _supertonic_singleton is None:
            _supertonic_singleton = SupertonicTTSEngine(
                voice_name=voice_name,
                lang=lang,
                **kwargs,
            )
        return _supertonic_singleton


# ===========================================================================
_KOKORO_LANG_CODES: dict[str, str] = {
    "pt-br": "p",
    "en-us": "a",
    "en-gb": "b",
    "es":    "e",
    "fr-fr": "f",
    "ja":    "j",
    "zh":    "z",
    "ko":    "k",
    "hi":    "h",
    "it":    "i",
}

# lang_code de 1 char → lang completo para o Tokenizer do kokoro_onnx
_KOKORO_TOKENIZER_LANG: dict[str, str] = {
    "a": "en-us",
    "b": "en-gb",
    "p": "pt-br",
    "e": "es",
    "f": "fr-fr",
    "k": "ko",
    "h": "hi",
    "i": "it",
}

from typing import Any

_G2P_CACHE: dict[str, Any] = {}
_G2P_CACHE_LOCK = threading.Lock()


def _resolve_kokoro_lang(lang: str) -> str:
    resolved = _KOKORO_LANG_CODES.get(lang.lower(), lang)
    if len(resolved) != 1:
        print(f"⚠️ lang_code desconhecido: '{lang}' → fallback 'a' (en-us)")
        return "a"
    return resolved


def _extract_phonemes(result) -> str | None:
    phonemes = result[0] if isinstance(result, tuple) else result
    if not phonemes or not str(phonemes).strip():
        return None
    return str(phonemes)


_KOKORO_MAX_PHONEMES = 500  # limite real é 510; margem de 10 para segurança


def _split_phonemes(phonemes: str, max_len: int = _KOKORO_MAX_PHONEMES) -> list[str]:
    """
    Parte uma string de fonemas em chunks de até `max_len` caracteres,
    quebrando preferencialmente em espaços (fronteiras de sílaba/palavra).
    Retorna lista com 1+ chunks, nunca vazia.
    """
    if len(phonemes) <= max_len:
        return [phonemes]

    chunks: list[str] = []
    while len(phonemes) > max_len:
        cut = phonemes.rfind(" ", 0, max_len)
        if cut == -1:
            cut = max_len  # sem espaço: corte forçado
        chunks.append(phonemes[:cut])
        phonemes = phonemes[cut:].lstrip(" ")
    if phonemes:
        chunks.append(phonemes)
    return chunks


def _misaki_phonemize(text: str, lang_code: str) -> tuple[str, bool, str]:
    """
    zh/ja → misaki G2P (is_phonemes=True).
    Demais → kokoro_onnx.Tokenizer.phonemize (is_phonemes=True).
    Fallback de emergência: (text, False, "a").

    Retorna (text_ou_fonemas, is_phonemes, lang_efetivo).
    lang_efetivo pode diferir de lang_code quando o misaki falha e o caller
    precisa usar espeak — nesse caso retornamos "a" (en-us) em vez de "z"/"j"
    para evitar o erro "no support for lang z/j" no espeak interno do Kokoro.
    """
    global _G2P_CACHE

    # ── zh ────────────────────────────────────────────────────────────────
    # Correção: O chinês PRECISA ser pré-processado pelo misaki[zh]
    # para gerar os fonemas IPA corretos antes de ir para o ONNX.
    if lang_code == "z":
        try:
            with _G2P_CACHE_LOCK:
                if "zh" not in _G2P_CACHE:
                    from misaki.zh import ZHG2P
                    _G2P_CACHE["zh"] = ZHG2P()
                g2p = _G2P_CACHE["zh"]
            phonemes = _extract_phonemes(g2p(text))
            if phonemes:
                return phonemes, True, "z"
            print("⚠️ misaki[zh] retornou vazio → fallback texto bruto (lang=a)")
        except Exception as e:
            print(f"⚠️ misaki[zh] falhou → fallback texto bruto (lang=a): {e}")
        # Fallback: se falhar, lang "z" explode no espeak nativo, redirecionamos para "a"
        return text, False, "a"

    # ── ja ────────────────────────────────────────────────────────────────
    if lang_code == "j":
        try:
            with _G2P_CACHE_LOCK:
                if "ja" not in _G2P_CACHE:
                    from misaki.ja import JAG2P
                    _G2P_CACHE["ja"] = JAG2P()
                g2p = _G2P_CACHE["ja"]
            phonemes = _extract_phonemes(g2p(text))
            if phonemes:
                return phonemes, True, "j"
            print("⚠️ misaki[ja] retornou vazio → fallback texto bruto (lang=a)")
        except Exception as e:
            print(f"⚠️ misaki[ja] falhou → fallback texto bruto (lang=a): {e}")
        # Fallback: lang "j" não tem suporte no espeak interno → usar "a"
        return text, False, "a"

    # ── todos os demais → kokoro_onnx.Tokenizer ───────────────────────────
    tokenizer_lang = _KOKORO_TOKENIZER_LANG.get(lang_code)
    if not tokenizer_lang:
        print(f"⚠️ lang_code '{lang_code}' sem mapeamento → fallback texto bruto (lang=a)")
        return text, False, "a"

    try:
        with _G2P_CACHE_LOCK:
            if "tokenizer" not in _G2P_CACHE:
                from kokoro_onnx import Tokenizer
                _G2P_CACHE["tokenizer"] = Tokenizer()
            tokenizer = _G2P_CACHE["tokenizer"]
        phonemes = tokenizer.phonemize(text, tokenizer_lang)
        if phonemes and phonemes.strip():
            return phonemes, True, lang_code
        print(f"⚠️ Tokenizer lang={tokenizer_lang} retornou vazio → fallback texto bruto")
    except Exception as e:
        print(f"⚠️ Tokenizer lang={tokenizer_lang} falhou → fallback texto bruto: {e}")
    return text, False, lang_code

class KokoroTTSEngine:
    def __init__(
        self,
        model_path: str,
        voices_path: str,
        voice: str,
        lang: str,
        speed: float,
        sample_rate: int,
        rvc: "RVCConverter | None" = None,
        zh_model_path: str | None = None,
        zh_voices_path: str | None = None,
    ):
        print("🔊 Carregando Kokoro TTS (ONNX Multivozes)...")
        start = time.perf_counter()

        self.kokoro = Kokoro(
            model_path=model_path,
            voices_path=voices_path,
        )

        # Instância separada para o modelo chinês (Kokoro-82M-v1.1-zh-ONNX).
        # Usa diretório de vozes individuais (.bin por voz) em vez do voices-v1.0.bin.
        # Só é criada se os caminhos forem fornecidos.
        self.kokoro_zh: "Kokoro | None" = None
        self._zh_voices_dir: str | None = None

        if zh_model_path and zh_voices_path:
            try:
                print("🔊 Carregando Kokoro ZH (onnx-community/Kokoro-82M-v1.1-zh-ONNX)...")
                import os

                # Kokoro-ONNX tenta fazer open() no path. Se for diretório, dá PermissionError.
                # Portanto, injetamos o arquivo padrão (inglês) só pro init não quebrar.
                is_dir = os.path.isdir(zh_voices_path)
                safe_voices_path = voices_path if is_dir else zh_voices_path

                self.kokoro_zh = Kokoro(
                    model_path=zh_model_path,
                    voices_path=safe_voices_path,
                )


                print("✅ Kokoro ZH carregado")
            except Exception as e:
                print(f"⚠️ Falha ao carregar Kokoro ZH: {e} — síntese zh indisponível.")

        self.voice = voice
        self.lang = _resolve_kokoro_lang(lang)
        self.sample_rate = sample_rate

        self._base_speed = speed
        self._base_voice = voice
        self._base_lang  = self.lang   # lang resolvido — base para restore após speak_with_style

        self.speed = speed

        # Event loop dedicado em thread daemon — evita criar/destruir loop por síntese
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="KokoroEventLoop"
        )
        self._loop_thread.start()

        self._lock = threading.Lock()

        elapsed = time.perf_counter() - start
        print(f"✅ Kokoro carregado em {elapsed:.2f}s")
        print(f"🎙️ Voz: {voice} | 🌎 Lang: {lang}")

        print("🔥 Warm-up Kokoro...")
        try:
            # Fonemas IPA hardcoded por lang — curtos, sem passar pelo G2P,
            # garantindo que nunca ultrapassem o limite de 510 fonemas do Kokoro.
            _WARMUP_PHONEMES: dict[str, str] = {
                "j": "koɴnichiwa",
                "k": "annjʌŋhasejo",
                "h": "nəməste",
            }
            if self.lang == "z":
                if self.kokoro_zh is not None:
                    self._get_kokoro_for_lang("z", self.voice)
                    try:
                        # Correção: Pré-processa o texto chinês usando misaki[zh] para o warm-up
                        _warmup_text, _warmup_is_phonemes, _warmup_lang = _misaki_phonemize("你好", "z")
                        self.kokoro_zh.create(
                            _warmup_text,
                            voice=self.voice,
                            speed=self.speed,
                            lang=_warmup_lang,
                            is_phonemes=_warmup_is_phonemes,
                        )
                        print("✅ Warm-up Kokoro ZH concluído")
                    except Exception as e:
                        print(f"⚠️ Warm-up ZH falhou: {e}")
            elif self.lang in _WARMUP_PHONEMES:
                _warmup_text = _WARMUP_PHONEMES[self.lang]
                _warmup_is_phonemes = True
                _warmup_lang = self.lang
                self.kokoro.create(
                    _warmup_text,
                    voice=self.voice,
                    speed=self.speed,
                    lang=_warmup_lang,
                    is_phonemes=_warmup_is_phonemes,
                )
                print("✅ Warm-up concluído")
            else:
                _warmup_text, _warmup_is_phonemes, _warmup_lang = _misaki_phonemize("hello", self.lang)
                self.kokoro.create(
                    _warmup_text,
                    voice=self.voice,
                    speed=self.speed,
                    lang=_warmup_lang,
                    is_phonemes=_warmup_is_phonemes,
                )
                print("✅ Warm-up concluído")
        except Exception as e:
            print(f"⚠️ Warm-up falhou: {e}")
        self.rvc = rvc

    def speak(self, text: str) -> float:
        if not text.strip():
            return 0.0

        with self._lock:
            start = time.perf_counter()
            future = asyncio.run_coroutine_threadsafe(
                self._speak_streaming(text, self._base_speed, self._base_voice, self._base_lang),
                self._loop,
            )
            future.result()   # bloqueia até concluir; propaga exceções
            return time.perf_counter() - start

    async def _speak_streaming(self, text: str, speed: float, voice: str, lang: str):
        """
        Produtor-consumidor real via asyncio.Queue.
        """
        text, is_phonemes, lang = _misaki_phonemize(text, lang)
        if not text or not text.strip():
            print("⚠️ _misaki_phonemize retornou texto vazio — abortando síntese")
            return

        # Parte sequências de fonemas longas em sub-chunks para respeitar o
        # limite de 510 fonemas do Kokoro. Para texto bruto (is_phonemes=False)
        # o Kokoro já lida internamente, então aplicamos só quando is_phonemes=True.
        phoneme_chunks = _split_phonemes(text) if is_phonemes else [text]
        # Sub-particionamento de segurança para o chinês v1.1 (Evita sobrecarga e anomalias de áudio)
        if lang == "z" and is_phonemes:
            zh_optimized_chunks = []
            for chunk in phoneme_chunks:
                # Se o chunk de fonemas for muito longo, quebra preventivamente por espaços simples
                if len(chunk) > 200:
                    words = chunk.split(" ")
                    current_chunk = []
                    current_len = 0
                    for word in words:
                        if current_len + len(word) + 1 > 200:
                            zh_optimized_chunks.append(" ".join(current_chunk))
                            current_chunk = [word]
                            current_len = len(word)
                        else:
                            current_chunk.append(word)
                            current_len += len(word) + 1
                    if current_chunk:
                        zh_optimized_chunks.append(" ".join(current_chunk))
                else:
                    zh_optimized_chunks.append(chunk)
            phoneme_chunks = zh_optimized_chunks

        queue: asyncio.Queue = asyncio.Queue(maxsize=4)

        # ── Produtor ─────────────────────────────────────────────────────
        _kokoro_instance = self._get_kokoro_for_lang(lang, voice)

        async def _producer():
            try:
                for ph_chunk in phoneme_chunks:
                    async for chunk, sample_rate in _kokoro_instance.create_stream(
                        ph_chunk,
                        voice=voice,
                        speed=speed,
                        lang=lang,
                        is_phonemes=is_phonemes,
                    ):
                        await queue.put((np.asarray(chunk, dtype=np.float32).flatten(), sample_rate))
            except Exception as e:
                print(f"❌ Erro durante streaming TTS: {e}")
            finally:
                await queue.put(None)  # EOF

        # ── Consumidor ───────────────────────────────────────────────────
        async def _consumer():
            first = await queue.get()
            if first is None:
                return

            if self.rvc is not None:
                chunks = [first[0]]
                sr = first[1]
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    chunks.append(item[0])
                    sr = item[1]
                full_wav = np.concatenate(chunks)
                try:
                    full_wav, sr = self.rvc.convert(full_wav, sr)
                except Exception as e:
                    print(f"⚠️ RVC falhou, usando áudio original: {e}")
                with sd.OutputStream(samplerate=sr, channels=1, dtype="float32") as stream:
                    stream.write(full_wav.reshape(-1, 1))
                return

            sr = first[1]
            with sd.OutputStream(samplerate=sr, channels=1, dtype="float32") as stream:
                stream.write(first[0].reshape(-1, 1))
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    chunk_data, sr = item
                    stream.write(chunk_data.reshape(-1, 1))

        await asyncio.gather(_producer(), _consumer())

    def set_voice_and_lang(self, voice: str, lang: str) -> None:
        """
        Atualiza voz e lang em runtime (ex.: troca de voz sem reload do engine).
        Resolve o lang_code kokoro e atualiza as bases de restore.
        """
        self.voice      = voice
        self.lang       = _resolve_kokoro_lang(lang)
        self._base_voice = self.voice
        self._base_lang  = self.lang
        print(f"🎙️ Kokoro voz/lang atualizados: voice={voice} lang={self.lang}")

    def _get_kokoro_for_lang(self, lang: str, voice: str = "") -> "Kokoro":
        if lang == "z" and self.kokoro_zh is not None:
            # Se o dicionário de vozes do modelo chinês ainda não foi adaptado
            # e o arquivo consolidado de vozes existe:
            if not getattr(self, "_zh_voices_patched", False) and self._zh_voices_dir:
                import os
                if os.path.exists(self._zh_voices_dir) and os.path.isfile(self._zh_voices_dir):
                    try:
                        print(f"⚙️ Adaptando vozes do arquivo unificado ZH: {self._zh_voices_dir}")

                        # Força o recarregamento correto das vozes se o dicionário estiver vazio
                        if not self.kokoro_zh.voices:
                            # kokoro-onnx armazena as vozes internamente usando np.load ou estrutura similar
                            # Vamos garantir que ele leia do arquivo unificado
                            import numpy as np
                            # Se for um arquivo .bin unificado do kokoro-onnx, ele normalmente é um dicionário serializado (.npz)
                            try:
                                loaded_voices = np.load(self._zh_voices_dir, allow_pickle=True)
                                self.kokoro_zh.voices = dict(loaded_voices)
                            except Exception:
                                # Fallback seguro usando a API nativa se disponível
                                pass

                        # Se conseguiu popular o dicionário de vozes, aplica o hotfix de dimensões
                        if self.kokoro_zh.voices:
                            for name in list(self.kokoro_zh.voices.keys()):
                                v = self.kokoro_zh.voices[name]

                                # 1. Correção Crítica (512 -> 256): Fatiamento do vetor de estilo
                                if v.shape[-1] == 512:
                                    v = v[..., :256]

                                # 2. Padding vertical para evitar IndexError (linhas de 255 -> 511)
                                target_rows = 511
                                # Se a matriz for 2D, expande para 3D (target_rows, 1, 256)
                                if len(v.shape) == 2:
                                    matrix = v.reshape(-1, 256)
                                else:
                                    matrix = v.reshape(-1, 256)

                                if matrix.shape[0] < target_rows:
                                    padding_rows = target_rows - matrix.shape[0]
                                    last_row = matrix[-1:]
                                    padding = np.repeat(last_row, padding_rows, axis=0)
                                    matrix = np.vstack([matrix, padding])
                                elif matrix.shape[0] > target_rows:
                                    matrix = matrix[:target_rows]

                                # Salva de volta no formato 3D esperado pelo Kokoro-ONNX
                                self.kokoro_zh.voices[name] = matrix.reshape(target_rows, 1, 256)

                            self._zh_voices_patched = True
                            print("✅ Todas as vozes ZH unificadas foram adaptadas com sucesso para 256 dimensões.")
                    except Exception as patch_err:
                        print(f"⚠️ Erro ao aplicar patch no arquivo unificado ZH: {patch_err}")

            return self.kokoro_zh

        return self.kokoro

    def speak_with_style(self, text: str, style: str) -> float:
        if not text.strip():
            return 0.0

        params = get_style_params(style)
        speed = params["speed"]
        voice = params["kokoro_voice"] if params["kokoro_voice"] is not None else self._base_voice
        lang  = self._base_lang

        with self._lock:
            start = time.perf_counter()
            future = asyncio.run_coroutine_threadsafe(
                self._speak_streaming(text, speed, voice, lang),
                self._loop,
            )
            future.result()
            return time.perf_counter() - start

    def synthesize_bytes(self, text: str, style: str = "neutral") -> bytes:
        params = get_style_params(style)
        speed  = params["speed"]
        voice  = params["kokoro_voice"] if params["kokoro_voice"] is not None else self._base_voice
        lang   = self._base_lang

        with self._lock:
            future = asyncio.run_coroutine_threadsafe(
                self._collect_chunks_bytes(text, speed, voice, lang),
                self._loop,
            )
            chunks, final_sr = future.result()

        if not chunks:
            return b""
        wav = np.concatenate(chunks)
        sr  = final_sr
        if self.rvc is not None:
            try:
                wav, sr = self.rvc.convert(wav, sr)
            except Exception as e:
                print(f"⚠️ RVC falhou: {e}")
        pcm = (wav * 32767).clip(-32768, 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm.tobytes())
        return buf.getvalue()

    async def _collect_chunks_bytes(
        self, text: str, speed: float, voice: str, lang: str
    ) -> tuple[list, int]:
        chunks, sr = [], self.sample_rate

        text, is_phonemes, lang = _misaki_phonemize(text, lang)
        if not text or not text.strip():
            print("⚠️ _misaki_phonemize retornou texto vazio — retornando sem áudio")
            return chunks, sr

        phoneme_chunks = _split_phonemes(text) if is_phonemes else [text]
        # Sub-particionamento de segurança para o chinês v1.1 (Evita sobrecarga e anomalias de áudio)
        if lang == "z" and is_phonemes:
            zh_optimized_chunks = []
            for chunk in phoneme_chunks:
                # Se o chunk de fonemas for muito longo, quebra preventivamente por espaços simples
                if len(chunk) > 200:
                    words = chunk.split(" ")
                    current_chunk = []
                    current_len = 0
                    for word in words:
                        if current_len + len(word) + 1 > 200:
                            zh_optimized_chunks.append(" ".join(current_chunk))
                            current_chunk = [word]
                            current_len = len(word)
                        else:
                            current_chunk.append(word)
                            current_len += len(word) + 1
                    if current_chunk:
                        zh_optimized_chunks.append(" ".join(current_chunk))
                else:
                    zh_optimized_chunks.append(chunk)
            phoneme_chunks = zh_optimized_chunks

        _kokoro_instance = self._get_kokoro_for_lang(lang, voice)
        for ph_chunk in phoneme_chunks:
            async for chunk, sample_rate in _kokoro_instance.create_stream(
                    ph_chunk,
                    voice=voice,
                    speed=speed,
                    lang=lang,
                    is_phonemes=is_phonemes,
            ):
                chunks.append(np.asarray(chunk, dtype=np.float32).flatten())
                sr = sample_rate
        return chunks, sr