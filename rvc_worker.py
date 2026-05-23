"""
rvc_worker.py  —  roda DENTRO do rvc_env, NÃO do projeto principal.
Localização: raiz do projeto (AgentLena/rvc_worker.py)

API usada: infer_rvc_python.BaseLoader  →  generate_from_cache(audio_data=(array, sr))

Protocolo stdin/stdout (framing binário):
  → header 4 bytes big-endian = tamanho do payload
  → payload = bytes de um array float32 + 4 bytes de sample_rate (int32 big-endian)
  ← header 4 bytes big-endian = tamanho da resposta  (0 = erro)
  ← payload = bytes de array int16 + 4 bytes de sample_rate (int32 big-endian)

Encerramento: enviar header com tamanho 0.
"""

import argparse
import struct
import sys
from pathlib import Path

import numpy as np


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model",         required=True,  help="Caminho para o .pth")
    p.add_argument("--index",         default="",     help="Caminho para o .index (opcional)")
    p.add_argument("--pitch",         type=int,   default=0,    help="Pitch shift em semitons")
    p.add_argument("--f0",            default="rmvpe+",         help="Método F0")
    p.add_argument("--index-rate",    type=float, default=0.66, help="Influência do index")
    p.add_argument("--filter-radius", type=int,   default=3)
    p.add_argument("--envelope-ratio",type=float, default=0.25)
    p.add_argument("--protect",       type=float, default=0.33)
    p.add_argument("--only-cpu",      action="store_true")
    p.add_argument(
        "--models-dir",
        default="",
        help=(
            "Diretório que contém hubert_base.pt e rmvpe.pt. "
            "Passado pelo rvc.py em builds compiladas para apontar "
            "para models/rvc/ ao lado do Castorp.exe."
        ),
    )
    return p.parse_args()


def _patch_fairseq():
    """
    Corrige bug de compatibilidade entre fairseq==0.12.2 e Python 3.11+.
    dataclasses não permite campos mutáveis como default sem default_factory.

    Erros nos blocos são logados em vez de ignorados silenciosamente para
    facilitar diagnóstico sem custo de performance.
    """
    import dataclasses

    try:
        import fairseq.dataclass.configs as _cfg
        for _field in dataclasses.fields(_cfg.CommonConfig):
            if isinstance(_field.default, (dict, list)):
                object.__setattr__(
                    _field, "default",
                    dataclasses.field(default_factory=type(_field.default))
                )
    except Exception as e:
        print(
            f"[rvc_worker] aviso: patch fairseq (bloco 1) falhou — {e}",
            file=sys.stderr, flush=True,
        )

    try:
        import fairseq.dataclass.configs
        import omegaconf
        original = fairseq.dataclass.configs.CommonConfig

        if hasattr(original, "__dataclass_fields__"):
            for name, f in original.__dataclass_fields__.items():
                if f.default is dataclasses.MISSING:
                    continue
                if isinstance(f.default, omegaconf.DictConfig):
                    f.default = dataclasses.MISSING
                    f.default_factory = dict
                elif isinstance(f.default, (dict, list)):
                    factory = type(f.default)
                    f.default = dataclasses.MISSING
                    f.default_factory = factory
    except Exception as e:
        print(
            f"[rvc_worker] aviso: patch fairseq (bloco 2) falhou — {e}",
            file=sys.stderr, flush=True,
        )


def load_converter(args):
    _patch_fairseq()

    # Se --models-dir foi fornecido, adiciona ao sys.path e configura
    # variáveis de ambiente que o infer_rvc_python usa para localizar
    # hubert_base.pt e rmvpe.pt.
    if args.models_dir:
        models_dir = Path(args.models_dir)
        hubert = models_dir / "hubert_base.pt"
        rmvpe  = models_dir / "rmvpe.pt"
        if hubert.exists():
            import os
            # infer_rvc_python respeita essas env vars para localizar os modelos base
            os.environ.setdefault("RVC_HUBERT_PATH", str(hubert))
            os.environ.setdefault("RVC_RMVPE_PATH",  str(rmvpe))
            print(
                f"[rvc_worker] modelos base: {hubert}, {rmvpe}",
                file=sys.stderr, flush=True,
            )
        else:
            print(
                f"[rvc_worker] aviso: --models-dir fornecido mas hubert_base.pt "
                f"não encontrado em {models_dir}",
                file=sys.stderr, flush=True,
            )

    from infer_rvc_python import BaseLoader

    converter = BaseLoader(only_cpu=args.only_cpu)
    converter.apply_conf(
        tag                          = "voice",
        file_model                   = args.model,
        pitch_algo                   = args.f0,
        pitch_lvl                    = args.pitch,
        file_index                   = args.index,
        index_influence              = args.index_rate,
        respiration_median_filtering = args.filter_radius,
        envelope_ratio               = args.envelope_ratio,
        consonant_breath_protection  = args.protect,
    )

    # Warm-up: força o carregamento imediato de model.pth e rmvpe.pt,
    # que o infer_rvc_python carrega de forma lazy na primeira conversão.
    # Sem isso, a primeira fala real tem +40s de overhead de I/O de modelo.
    print("🔥 Warm-up RVC (carregando pesos de forma antecipada)...",
          file=sys.stderr, flush=True)
    try:
        _silence = np.zeros(int(16000 * 0.1), dtype=np.float32)
        converter.generate_from_cache(
            audio_data=(_silence, 16000),
            tag="voice",
        )
        print("✅ Warm-up RVC concluído.", file=sys.stderr, flush=True)
    except Exception as _e:
        # Falha no warm-up não impede o worker de funcionar —
        # apenas a primeira conversão real vai ter o overhead.
        print(f"⚠️ Warm-up RVC falhou (inofensivo): {_e}",
              file=sys.stderr, flush=True)

    return converter


def recv_frame(stream) -> bytes | None:
    """Lê um frame do protocolo: 4 bytes de tamanho + payload."""
    header = stream.read(4)
    if len(header) < 4:
        return None
    size = struct.unpack(">I", header)[0]
    if size == 0:
        return None   # sinal de encerramento
    payload = stream.read(size)
    if len(payload) < size:
        return None
    return payload


def send_frame_parts(stream, sr: int, wav: np.ndarray):
    """
    Envia header + sample_rate + amostras em uma única chamada write,
    reduzindo syscalls e pressão no GC em loops de áudio.
    """
    wav_i16 = np.asarray(wav, dtype=np.int16)
    body_size = 4 + wav_i16.nbytes
    out = struct.pack(">Ii", body_size, sr) + wav_i16.tobytes()
    stream.write(out)
    stream.flush()


def send_error(stream):
    """Envia tamanho 0 como sinal de erro."""
    stream.write(struct.pack(">I", 0))
    stream.flush()


def decode_audio(payload: bytes) -> tuple[np.ndarray, int]:
    """Payload = int32 big-endian (sample_rate) + float32 array."""
    sr  = struct.unpack(">i", payload[:4])[0]
    wav = np.frombuffer(payload[4:], dtype=np.float32).copy()
    return wav, sr


def main():
    args = parse_args()

    print("🎤 RVC worker: carregando modelo...", file=sys.stderr, flush=True)
    try:
        converter = load_converter(args)
    except Exception as e:
        print(f"❌ Falha ao carregar modelo: {e}", file=sys.stderr, flush=True)
        sys.exit(1)

    print("✅ Modelo carregado. Aguardando áudio...", file=sys.stderr, flush=True)

    stdin  = sys.stdin.buffer
    stdout = sys.stdout.buffer

    while True:
        payload = recv_frame(stdin)
        if payload is None:
            break

        try:
            wav_in, sr_in = decode_audio(payload)

            out_wav, out_sr = converter.generate_from_cache(
                audio_data=(wav_in, sr_in),
                tag="voice",
            )

            send_frame_parts(stdout, out_sr, out_wav)

        except Exception as e:
            print(f"❌ Erro na conversão: {e}", file=sys.stderr, flush=True)
            send_error(stdout)


if __name__ == "__main__":
    main()