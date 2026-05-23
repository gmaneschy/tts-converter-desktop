"""
src/tts/rvc.py
"""
from __future__ import annotations

import select
import struct
import subprocess
import sys
import threading

import numpy as np
from src.utils.paths import (
    get_app_root,
    rvc_models_dir,
    rvc_python_path,
    rvc_worker_path,
)

# select() não funciona com pipes no Windows — usamos threads com timeout nesse caso.
_USE_SELECT = sys.platform != "win32"


class RVCConverter:
    def __init__(
        self,
        model_path: str,
        index_path: str | None = None,
        pitch_shift: int = 0,
        f0_method: str = "rmvpe+",
        index_rate: float = 0.66,
        protect: float = 0.33,
        only_cpu: bool = False,
        recv_timeout: float = 120.0,
    ):
        """
        Parameters
        ----------
        recv_timeout : float
            Tempo máximo (segundos) para aguardar uma resposta do worker por frame.
            120s cobre o warm-up eager do modelo pesado (model.pth + rmvpe.pt) na CPU.
            Após o warm-up, conversões reais levam 6–15s; o timeout continua válido
            para detectar travamentos genuínos.
        """
        # Tanto em desenvolvimento quanto em build compilada, o worker é
        # chamado como: rvc_python rvc_worker.py [args]
        # Em frozen, o rvc_env fica ao lado do Castorp.exe (copiado manualmente
        # após o build) e o rvc_worker.py fica em _internal/rvc_worker_py/.
        python = rvc_python_path()
        if not python.exists():
            raise FileNotFoundError(
                f"Python do rvc_env não encontrado em {python}.\n"
                "Em desenvolvimento: execute scripts/setup_rvc_env.py\n"
                "Em produção: copie o rvc_env para ao lado do Castorp.exe"
            )

        worker = rvc_worker_path()
        if not worker.exists():
            raise FileNotFoundError(f"rvc_worker.py não encontrado em {worker}.")

        self._cmd = [str(python), str(worker)]

        # Argumentos do worker
        self._cmd += [
            "--model", model_path,
            "--pitch", str(pitch_shift),
            "--f0",    f0_method,
            "--index-rate", str(index_rate),
            "--protect",    str(protect),
        ]

        # --index só é passado quando preenchido — string vazia confunde o argparse
        if index_path and index_path.strip():
            self._cmd += ["--index", index_path]

        if only_cpu:
            self._cmd.append("--only-cpu")

        # Informa o diretório dos modelos base (hubert, rmvpe) sempre que existir,
        # pois o worker pode não herdar o CWD correto (especialmente em builds).
        models_dir = rvc_models_dir()
        if models_dir.exists():
            self._cmd += ["--models-dir", str(models_dir)]

        self._recv_timeout = recv_timeout
        print(f"[RVC] cmd: {self._cmd}", flush=True)
        self._proc: subprocess.Popen | None = None
        self._stderr_thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._start_worker()

    # ------------------------------------------------------------------
    def _drain_stderr(self):
        """
        Thread dedicada a consumir o stderr do worker continuamente.
        Sem isso o pipe de stderr enche, o worker bloqueia ao escrever,
        e o processo pai trava esperando resposta no stdout (deadlock).

        Sinais de pronto (em ordem de preferência):
          1. "Warm-up RVC concluído"  — modelo totalmente carregado e aquecido
          2. "Warm-up RVC falhou"     — warm-up deu erro mas worker ainda funciona
          3. "Modelo carregado"       — fallback para versões antigas do worker
        """
        for raw in self._proc.stderr:
            line = raw.decode("utf-8", errors="replace").rstrip()
            print(f"[RVC] {line}", flush=True)
            if (
                "Warm-up RVC concluído" in line
                or "Warm-up RVC falhou"  in line
                or "Modelo carregado"    in line
            ):
                self._ready.set()

    def _start_worker(self):
        print("🎤 Iniciando RVC worker...", flush=True)
        self._ready.clear()

        _flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        self._proc = subprocess.Popen(
            self._cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_flags,
        )

        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, daemon=True
        )
        self._stderr_thread.start()

        # Registra shutdown como handler atexit para garantir que o subprocess
        # seja encerrado mesmo que __del__ não seja chamado (ex.: referências
        # circulares ou shutdown do interpretador com módulos já descarregados).
        import atexit as _atexit
        _atexit.register(self.shutdown)

        # Warm-up na CPU pode demorar 120–180s na primeira execução
        # (model.pth + rmvpe.pt carregados juntos sem GPU).
        if not self._ready.wait(timeout=180):
            if self._proc.poll() is not None:
                raise RuntimeError("RVC worker encerrou durante startup.")
            raise TimeoutError("RVC worker não respondeu em 180s.")

        print("✅ RVC worker pronto.", flush=True)

    # ------------------------------------------------------------------
    def _send_frame(self, data: bytes):
        self._proc.stdin.write(struct.pack(">I", len(data)))
        self._proc.stdin.write(data)
        self._proc.stdin.flush()

    def _read_exact(self, n: int, timeout: float) -> bytes | None:
        """
        Lê exatamente n bytes do stdout do worker dentro do prazo (deadline).

        Uma única chamada a stdout.read(n) não garante n bytes em pipes —
        o kernel pode entregar menos fragmentos. O loop acumula até completar
        ou detectar EOF/timeout, evitando corrupção silenciosa do payload.
        O timeout é tratado como deadline absoluto: cada iteração desconta o
        tempo já consumido, independentemente do número de fragmentos recebidos.
        """
        import time as _time

        buf = bytearray()
        deadline = _time.monotonic() + timeout

        if _USE_SELECT:
            fd = self._proc.stdout.fileno()
            while len(buf) < n:
                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"RVC worker não respondeu em {timeout}s "
                        "(travamento durante inferência?)."
                    )
                ready, _, _ = select.select([fd], [], [], remaining)
                if not ready:
                    raise TimeoutError(
                        f"RVC worker não respondeu em {timeout}s "
                        "(travamento durante inferência?)."
                    )
                chunk = self._proc.stdout.read(n - len(buf))
                if not chunk:
                    return None  # EOF inesperado
                buf += chunk
        else:
            while len(buf) < n:
                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"RVC worker não respondeu em {timeout}s "
                        "(travamento durante inferência?)."
                    )
                result: list[bytes] = []
                exc: list[Exception] = []

                def _read(want=n - len(buf)):
                    try:
                        result.append(self._proc.stdout.read(want))
                    except Exception as e:
                        exc.append(e)

                t = threading.Thread(target=_read, daemon=True)
                t.start()
                t.join(remaining)
                if t.is_alive():
                    raise TimeoutError(
                        f"RVC worker não respondeu em {timeout}s "
                        "(travamento durante inferência?)."
                    )
                if exc:
                    raise exc[0]
                chunk = result[0] if result else b""
                if not chunk:
                    return None  # EOF inesperado
                buf += chunk

        return bytes(buf)

    def _recv_frame(self) -> bytes | None:
        header = self._read_exact(4, self._recv_timeout)
        if header is None or len(header) < 4:
            return None
        size = struct.unpack(">I", header)[0]
        if size == 0:
            return None
        return self._read_exact(size, self._recv_timeout)

    def is_alive(self) -> bool:
        """Retorna True se o worker ainda está em execução."""
        return self._proc is not None and self._proc.poll() is None

    # ------------------------------------------------------------------
    def convert(self, wav: np.ndarray, sample_rate: int) -> tuple[np.ndarray, int]:
        if not self.is_alive():
            # Worker morreu (crash, OOM, kill externo). Tenta reiniciar uma vez
            # antes de propagar o erro, para que o engine não fique em estado
            # permanentemente inválido sem possibilidade de recuperação.
            print("⚠️ RVC worker encerrado inesperadamente — tentando reiniciar...", flush=True)
            try:
                self.restart()
                print("✅ RVC worker reiniciado com sucesso.", flush=True)
            except Exception as restart_exc:
                raise RuntimeError(
                    f"RVC worker encerrado e não foi possível reiniciar: {restart_exc}"
                ) from restart_exc

        payload = struct.pack(">i", sample_rate) + wav.astype(np.float32).tobytes()
        self._send_frame(payload)

        response = self._recv_frame()
        if response is None:
            raise RuntimeError("RVC worker retornou erro ou fechou.")

        out_sr  = struct.unpack(">i", response[:4])[0]
        out_wav = np.frombuffer(response[4:], dtype=np.int16).astype(np.float32)
        out_wav *= (1.0 / 32768.0)

        return out_wav, out_sr

    # ------------------------------------------------------------------
    def restart(self):
        if not hasattr(self, "_cmd"):
            raise RuntimeError(
                "RVCConverter não foi inicializado corretamente — "
                "não é possível reiniciar."
            )
        self.shutdown()
        self._start_worker()

    def shutdown(self):
        if not hasattr(self, "_proc"):
            return
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write(struct.pack(">I", 0))
                self._proc.stdin.flush()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            print("🔇 RVC worker encerrado.")

    def __del__(self):
        # __del__ é não-confiável em shutdown do interpretador (módulos podem
        # já ter sido descarregados). O atexit registrado em _start_worker()
        # é o mecanismo primário de cleanup; este é apenas um fallback secundário
        # para coleta de lixo durante execução normal.
        try:
            if hasattr(self, "_proc"):
                self.shutdown()
        except Exception:
            pass

    @staticmethod
    def is_available() -> bool:
        return rvc_python_path().exists() and rvc_worker_path().exists()