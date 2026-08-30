from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import BenchmarkConfig
from .models import BenchmarkTask, BenchmarkTier, ModelSpec
from .resources import WindowsJobLimit


@dataclass(frozen=True)
class LocalGeneration:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    model_load_time_ms: int | None
    inference_time_ms: int | None
    wall_time_ms: int
    metadata: dict[str, Any]


class OllamaLocalClient:
    """A proxy-free, loopback-only Ollama protocol adapter."""

    def __init__(self, config: BenchmarkConfig) -> None:
        config.validate()
        self.config = config
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def version(self) -> str:
        payload = self._request("GET", "/api/version")
        return str(payload.get("version") or "unknown")

    def tags(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/tags")
        models = payload.get("models")
        return [dict(item) for item in models] if isinstance(models, list) else []

    def model_spec(self, tier: BenchmarkTier, model: str) -> ModelSpec:
        show = self._request("POST", "/api/show", {"model": model})
        tags = self.tags()
        matching = next(
            (
                item
                for item in tags
                if item.get("name") == model
                or item.get("model") == model
                or str(item.get("name", "")).startswith(f"{model}:")
            ),
            None,
        )
        if matching is None:
            raise RuntimeError(f"Ollama did not report a manifest for {model}")
        raw_details = show.get("details")
        details: dict[str, Any] = dict(raw_details) if isinstance(raw_details, dict) else {}
        parameter_billions = _parse_parameter_billions(str(details.get("parameter_size") or ""))
        size = _optional_int(matching.get("size"))
        digest = _normalize_sha256_digest(str(matching.get("digest") or ""))
        spec = ModelSpec(
            tier=tier,
            provider="ollama",
            model=model,
            parameter_billions=parameter_billions,
            digest=digest,
            quantization=str(details.get("quantization_level") or "") or None,
            size_bytes=size,
            predicted_memory_bytes=int(size * 1.25) if size is not None else None,
        )
        spec.validate()
        return spec

    def count_prompt_tokens(self, model: str, task: BenchmarkTask) -> int:
        prompt = build_generation_prompt(task)
        payload = self._request(
            "POST",
            "/api/generate",
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                # Preparation measures every frozen prompt with the same FAST model.
                # Keep it resident for the batch instead of reloading it 542 times;
                # DedicatedOllamaServer.stop() still releases it at phase completion.
                "keep_alive": "30m",
                "options": {
                    "temperature": 0,
                    "seed": self.config.seed,
                    "num_predict": 0,
                    "num_ctx": self.config.context_window,
                    "num_thread": 1,
                },
            },
            timeout=self.config.generation_timeout_seconds,
        )
        count = payload.get("prompt_eval_count")
        if not isinstance(count, int) or count < 0:
            raise RuntimeError(f"Ollama did not return prompt_eval_count for {task.identity()}")
        return count

    def generate(self, model: str, task: BenchmarkTask) -> LocalGeneration:
        started = time.perf_counter()
        payload = self._request(
            "POST",
            "/api/generate",
            {
                "model": model,
                "prompt": build_generation_prompt(task),
                "stream": False,
                "keep_alive": "5m",
                "options": {
                    "temperature": 0,
                    "top_p": 1,
                    "seed": self.config.seed,
                    "num_predict": self.config.max_output_tokens,
                    "num_ctx": self.config.context_window,
                    "num_thread": 1,
                },
            },
            timeout=self.config.generation_timeout_seconds,
        )
        wall_ms = int((time.perf_counter() - started) * 1000)
        input_tokens = _optional_int(payload.get("prompt_eval_count"))
        output_tokens = _optional_int(payload.get("eval_count"))
        total_tokens = (
            input_tokens + output_tokens
            if input_tokens is not None and output_tokens is not None
            else None
        )
        return LocalGeneration(
            text=str(payload.get("response") or ""),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model_load_time_ms=_nanoseconds_to_ms(payload.get("load_duration")),
            inference_time_ms=_nanoseconds_to_ms(payload.get("eval_duration")),
            wall_time_ms=wall_ms,
            metadata={
                "done": payload.get("done"),
                "done_reason": payload.get("done_reason"),
                "prompt_eval_duration_ms": _nanoseconds_to_ms(payload.get("prompt_eval_duration")),
                "total_duration_ms": _nanoseconds_to_ms(payload.get("total_duration")),
            },
        )

    def unload(self, model: str) -> None:
        self._request(
            "POST",
            "/api/generate",
            {"model": model, "prompt": "", "stream": False, "keep_alive": 0},
            timeout=60,
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: int = 30,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.config.ollama_url.rstrip("/") + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"local Ollama request failed at {path}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError(f"local Ollama response at {path} was not an object")
        if parsed.get("error"):
            raise RuntimeError(f"local Ollama error at {path}: {parsed['error']}")
        return parsed


class DedicatedOllamaServer:
    """Launch a benchmark-owned Ollama server and optionally assign it to a Job Object."""

    def __init__(
        self,
        config: BenchmarkConfig,
        log_path: Path,
        *,
        job: WindowsJobLimit | None = None,
    ) -> None:
        self.config = config
        self.log_path = log_path
        self.job = job
        self.process: subprocess.Popen[bytes] | None = None
        self._log_stream: Any = None

    def start(self) -> OllamaLocalClient:
        if self.process is not None:
            raise RuntimeError("dedicated Ollama server already started")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_stream = self.log_path.open("ab")
        environment = os.environ.copy()
        environment.update(
            {
                "OLLAMA_HOST": self.config.ollama_url.removeprefix("http://"),
                "OLLAMA_NUM_PARALLEL": "1",
                "OLLAMA_MAX_LOADED_MODELS": "1",
                "OLLAMA_NO_CLOUD": "1",
                "HTTP_PROXY": "",
                "HTTPS_PROXY": "",
                "ALL_PROXY": "",
                "NO_PROXY": "127.0.0.1,localhost,::1",
            }
        )
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        self.process = subprocess.Popen(
            [self.config.ollama_executable, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=self._log_stream,
            stderr=subprocess.STDOUT,
            env=environment,
            creationflags=creationflags,
        )
        if self.job is not None:
            self.job.assign_pid(self.process.pid)
        client = OllamaLocalClient(self.config)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"dedicated Ollama server exited with code {self.process.returncode}"
                )
            try:
                client.version()
                return client
            except RuntimeError:
                time.sleep(0.25)
        raise RuntimeError("dedicated Ollama server did not become ready within 45 seconds")

    def pull(self, model: str) -> None:
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("dedicated Ollama server is not running")
        environment = os.environ.copy()
        environment.update(
            {
                "OLLAMA_HOST": self.config.ollama_url.removeprefix("http://"),
                "OLLAMA_NO_CLOUD": "1",
                "HTTP_PROXY": environment.get("HTTP_PROXY", ""),
                "HTTPS_PROXY": environment.get("HTTPS_PROXY", ""),
                "NO_PROXY": "127.0.0.1,localhost,::1",
            }
        )
        completed = subprocess.run(
            [self.config.ollama_executable, "pull", model],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=7200,
            check=False,
            env=environment,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown error").strip()
            raise RuntimeError(f"failed to pull local model {model}: {detail[:1000]}")

    def stop(self) -> None:
        process = self.process
        self.process = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        if self._log_stream is not None:
            self._log_stream.close()
            self._log_stream = None

    def __enter__(self) -> DedicatedOllamaServer:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()


def _normalize_sha256_digest(value: str) -> str:
    digest = value.strip().casefold()
    if re.fullmatch(r"[0-9a-f]{64}", digest):
        return f"sha256:{digest}"
    if re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        return digest
    raise RuntimeError("Ollama model manifest did not contain a valid SHA-256 digest")


def build_system_prompt(task: BenchmarkTask) -> str:
    if task.benchmark == "humaneval":
        format_rule = (
            "Return only the Python completion that follows the supplied function stub. "
            "Do not repeat the stub and do not use Markdown fences."
        )
    else:
        format_rule = (
            "Return only a complete Python solution defining the requested function. "
            "Do not use Markdown fences or explanatory prose."
        )
    return (
        "You are solving a public Python coding benchmark task. Hidden tests and reference "
        "solutions are unavailable.\n"
        f"{format_rule}\n\n"
    )


def build_generation_prompt(task: BenchmarkTask) -> str:
    """Build the frozen prompt; escalation deliberately does not add feedback."""

    return f"{build_system_prompt(task)}TASK:\n{task.prompt}\n"


def normalize_solution(task: BenchmarkTask, response: str) -> tuple[str, tuple[str, ...]]:
    text = response.strip()
    notes: list[str] = []
    fenced = re.match(r"^```(?:python)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
        notes.append("removed-markdown-fence")
    if task.benchmark == "humaneval":
        if text.startswith(task.prompt.strip()) or re.match(
            rf"^(?:async\s+)?def\s+{re.escape(task.entry_point)}\s*\(", text
        ):
            solution = text
            notes.append("used-full-function-response")
        else:
            solution = task.prompt + text
            notes.append("appended-completion-to-prompt")
    else:
        solution = text
    return solution, tuple(notes)


def _parse_parameter_billions(value: str) -> float:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([BM])\s*", value, re.IGNORECASE)
    if match is None:
        raise RuntimeError(f"cannot parse Ollama parameter size: {value!r}")
    number = float(match.group(1))
    return number if match.group(2).upper() == "B" else number / 1000.0


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and value >= 0 else None


def _nanoseconds_to_ms(value: Any) -> int | None:
    return int(float(value) / 1_000_000) if isinstance(value, int | float) and value >= 0 else None
