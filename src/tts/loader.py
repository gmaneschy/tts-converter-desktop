from typing import Optional
from src.config.settings import settings as config
from src.tts.engine import KokoroTTSEngine, SupertonicTTSEngine
from src.tts.rvc import RVCConverter
from src.utils.paths import kokoro_dir

# NOTA: sanitize_for_tts foi removido do import — a sanitização é responsabilidade
# exclusiva de inference.py, que possui o LanguageContext e as flags de feature
# (rp_strip, etc.) necessárias para um sanitize correto. Os loaders recebem texto
# já sanitizado e apenas delegam ao engine.


def _rvc_config_snapshot() -> dict:
    """Lê as chaves de configuração do RVC e retorna um dict comparável."""
    return {
        "enabled":     config.get("tts", "rvc.enabled", False),
        "model_path":  config.get("tts", "rvc.model_path", "").strip(),
        "index_path":  config.get("tts", "rvc.index_path", None) or None,
        "pitch_shift": config.get("tts", "rvc.pitch_shift", 0),
        "f0_method":   config.get("tts", "rvc.f0_method", "rmvpe+"),
        "only_cpu":    config.get("tts", "rvc.only_cpu", False),
    }


def _build_rvc(
    previous: "RVCConverter | None" = None,
    previous_snapshot: "dict | None" = None,
) -> "tuple[RVCConverter | None, dict]":
    """
    Constrói (ou reusa) um RVCConverter.

    Se a configuração atual for idêntica à do snapshot anterior E já existe
    um RVC carregado, retorna o mesmo objeto sem recriar o modelo — evitando
    o custo de load em reloads onde apenas o engine TTS muda.

    Retorna (rvc_instance, snapshot_atual).
    """
    snapshot = _rvc_config_snapshot()

    if not snapshot["enabled"]:
        return None, snapshot

    if previous is not None and snapshot == previous_snapshot:
        # Configuração inalterada — reaproveitamos o objeto já carregado.
        return previous, snapshot

    # Configuração nova ou RVC nunca foi carregado.
    model_path = snapshot["model_path"]
    if not model_path:
        print("⚠️ RVC habilitado mas rvc.model_path está vazio — ignorando.")
        return None, snapshot

    if not RVCConverter.is_available():
        print("⚠️ rvc_env não encontrado — RVC desativado.")
        return None, snapshot

    try:
        rvc = RVCConverter(
            model_path  = model_path,
            index_path  = snapshot["index_path"],
            pitch_shift = snapshot["pitch_shift"],
            f0_method   = snapshot["f0_method"],
            only_cpu    = snapshot["only_cpu"],
        )
        return rvc, snapshot
    except Exception as e:
        print(f"❌ Falha ao carregar RVC: {e} — TTS continuará sem conversão.")
        return None, snapshot


class SupertonicTTSLoader:
    """
    Loader simples (stateless).
    Cada instância representa uma configuração ativa de TTS.

    Não executa sanitização — o texto recebido já foi sanitizado por inference.py
    com o LanguageContext e as flags de feature corretas.

    A validação de texto vazio é responsabilidade do engine; os loaders apenas
    delegam, evitando a duplicação de guards.

    Registra o engine criado no singleton global (engine.set_supertonic_singleton)
    para que o _OnboardingTTS possa reusar a instância já carregada e evitar
    o crash 0xC0000005 causado por dois modelos ONNX Runtime ativos no Windows.
    """

    def __init__(
        self,
        voice_name: str = "F5",
        lang: str = "pt",
        rvc: "RVCConverter | None" = None,
        _engine: "SupertonicTTSEngine | None" = None,  # permite injetar engine externo
    ):
        from src.tts.engine import set_supertonic_singleton
        if _engine is not None:
            self.engine = _engine
        else:
            self.engine = SupertonicTTSEngine(voice_name=voice_name, lang=lang, rvc=rvc)
        # Registra no singleton para que consumidores secundários (ex.: onboarding)
        # possam reusar este engine sem criar uma segunda instância ONNX.
        set_supertonic_singleton(self.engine)

    def speak(self, text: str) -> float:
        return self.engine.speak(text)

    def speak_with_style(self, text: str, style: str) -> float:
        return self.engine.speak_with_style(text, style)

    def synthesize_bytes(self, text: str, style: str = "neutral") -> bytes:
        return self.engine.synthesize_bytes(text, style)


class KokoroTTSLoader:
    """
    Não executa sanitização — o texto recebido já foi sanitizado por inference.py
    com o LanguageContext e as flags de feature corretas.
    """

    def __init__(
            self,
            model_path: Optional[str] = None,
            voices_path: Optional[str] = None,
            voice: str = "pf_dora",
            lang: str = "pt-br",
            speed: float = 1.0,
            sample_rate: int = 24000,
            rvc: "RVCConverter | None" = None,
    ):
        _kokoro_dir = kokoro_dir()
        resolved_model = model_path or str(_kokoro_dir / "kokoro-v0_19.onnx")
        resolved_voices = voices_path or str(_kokoro_dir / "voices-v1.0.bin")

        self.engine = KokoroTTSEngine(
            model_path=resolved_model,
            voices_path=resolved_voices,
            voice=voice,
            lang=lang,
            speed=speed,
            sample_rate=sample_rate,
            rvc=rvc,
        )

    def set_voice_and_lang(self, voice: str, lang: str) -> None:
        """
        Atualiza voz e lang no engine sem recriar a instância.
        Deve ser chamado sempre que a voz for trocada nas configurações
        (ex.: em reload_tts ou quando o dialog de configurações salvar).
        """
        self.engine.set_voice_and_lang(voice, lang)

    def speak(self, text: str) -> float:
        return self.engine.speak(text)

    def speak_with_style(self, text: str, style: str) -> float:
        """Fala o texto aplicando os parâmetros prosódicos do estilo."""
        return self.engine.speak_with_style(text, style)

    def synthesize_bytes(self, text: str, style: str = "neutral") -> bytes:
        return self.engine.synthesize_bytes(text, style)