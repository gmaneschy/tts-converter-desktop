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


def _misaki_phonemize(text: str, lang_code: str) -> tuple[str, bool]:
    """
    zh/ja → misaki G2P (is_phonemes=True).
    Demais → kokoro_onnx.Tokenizer.phonemize (is_phonemes=True).
    Fallback de emergência: (text, False).
    """
    global _G2P_CACHE

    # ── zh ────────────────────────────────────────────────────────────────
    if lang_code == "z":
        try:
            with _G2P_CACHE_LOCK:
                if "zh" not in _G2P_CACHE:
                    from misaki.zh import ZHG2P
                    _G2P_CACHE["zh"] = ZHG2P()
                g2p = _G2P_CACHE["zh"]
            phonemes = _extract_phonemes(g2p(text))
            if phonemes:
                return phonemes, True
            print("⚠️ misaki[zh] retornou vazio → fallback texto bruto")
        except Exception as e:
            print(f"⚠️ misaki[zh] falhou → fallback texto bruto: {e}")
        return text, False

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
                return phonemes, True
            print("⚠️ misaki[ja] retornou vazio → fallback texto bruto")
        except Exception as e:
            print(f"⚠️ misaki[ja] falhou → fallback texto bruto: {e}")
        return text, False

    # ── todos os demais → kokoro_onnx.Tokenizer ───────────────────────────
    tokenizer_lang = _KOKORO_TOKENIZER_LANG.get(lang_code)
    if not tokenizer_lang:
        print(f"⚠️ lang_code '{lang_code}' sem mapeamento → fallback texto bruto")
        return text, False

    try:
        with _G2P_CACHE_LOCK:
            if "tokenizer" not in _G2P_CACHE:
                from kokoro_onnx import Tokenizer
                _G2P_CACHE["tokenizer"] = Tokenizer()
            tokenizer = _G2P_CACHE["tokenizer"]
        phonemes = tokenizer.phonemize(text, tokenizer_lang)
        if phonemes and phonemes.strip():
            return phonemes, True
        print(f"⚠️ Tokenizer lang={tokenizer_lang} retornou vazio → fallback texto bruto")
    except Exception as e:
        print(f"⚠️ Tokenizer lang={tokenizer_lang} falhou → fallback texto bruto: {e}")
    return text, False

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
    ):
        print("🔊 Carregando Kokoro TTS (ONNX Multivozes)...")
        start = time.perf_counter()

        self.kokoro = Kokoro(
            model_path=model_path,
            voices_path=voices_path,
        )

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
            _warmup_text, _warmup_is_phonemes = _misaki_phonemize("teste", self.lang)
            self.kokoro.create(
                _warmup_text,
                voice=self.voice,
                speed=self.speed,
                lang=self.lang,
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

        O produtor envia chunks do kokoro.create_stream() para a fila;
        o consumidor (thread de áudio) abre o OutputStream e escreve cada
        chunk assim que chega, reduzindo a latência percebida: o playback
        começa após o primeiro chunk, enquanto os demais ainda estão sendo
        sintetizados.

        Sentinela: None encerrar a fila sinaliza EOF ao consumidor.

        Se RVC estiver ativo, ele é aplicado por chunk (streaming) ou no
        áudio completo dependendo do que o converter suportar; aqui optamos
        por aplicar no array final (concatenado pelo consumidor) para manter
        consistência de pitch — isso é aceitável porque RVC já é o gargalo.
        """
        text, is_phonemes = _misaki_phonemize(text, lang)
        if not text or not text.strip():
            print("⚠️ _misaki_phonemize retornou texto vazio — abortando síntese")
            return

        queue: asyncio.Queue = asyncio.Queue(maxsize=4)

        # ── Produtor ─────────────────────────────────────────────────────
        async def _producer():
            try:
                async for chunk, sample_rate in self.kokoro.create_stream(
                    text,
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
            # Espera o primeiro chunk antes de abrir o OutputStream para
            # evitar latência de abertura de device sem áudio disponível.
            first = await queue.get()
            if first is None:
                return

            # Se RVC está ativo, acumulamos para processar em bloco (RVC
            # precisa de contexto contíguo para pitch tracking correto).
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

            # Sem RVC: abre stream e escreve cada chunk imediatamente.
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

        text, is_phonemes = _misaki_phonemize(text, lang)
        if not text or not text.strip():
            print("⚠️ _misaki_phonemize retornou texto vazio — retornando sem áudio")
            return chunks, sr

        async for chunk, sample_rate in self.kokoro.create_stream(
                text,
                voice=voice,
                speed=speed,
                lang=lang,
                is_phonemes=is_phonemes,
        ):
            chunks.append(np.asarray(chunk, dtype=np.float32).flatten())
            sr = sample_rate
        return chunks, sr