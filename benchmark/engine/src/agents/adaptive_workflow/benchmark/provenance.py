from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import tempfile
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import BenchmarkTask

HUMANEVAL_COMMIT = "6d43fb980f9fee3c892a914eda09951f772ad10d"
MBPP_COMMIT = "f46ca8374b4cddef97ca4208ad986049d74d296a"
EVALPLUS_VERSION = "v0.3.1"
HUMANEVAL_PLUS_VERSION = "v0.1.10"
MBPP_PLUS_VERSION = "v0.2.0"


@dataclass(frozen=True)
class SourceDefinition:
    benchmark: str
    source: str
    version: str
    license: str
    artifact_url: str
    artifact_filename: str
    license_url: str
    license_filename: str
    expected_tasks: int | None = None
    derived_from: tuple[str, ...] = ()


@dataclass(frozen=True)
class FrozenSource:
    benchmark: str
    source: str
    version: str
    license: str
    license_file: str
    artifact_file: str
    artifact_sha256: str
    artifact_size: int
    license_sha256: str
    retrieved_at: str
    derived_from: tuple[str, ...]


SOURCES: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        benchmark="HumanEval",
        source="https://github.com/openai/human-eval",
        version=HUMANEVAL_COMMIT,
        license="MIT (repository-level license; no separate dataset license asserted)",
        artifact_url=(
            "https://raw.githubusercontent.com/openai/human-eval/"
            f"{HUMANEVAL_COMMIT}/data/HumanEval.jsonl.gz"
        ),
        artifact_filename="HumanEval.jsonl.gz",
        license_url=(
            f"https://raw.githubusercontent.com/openai/human-eval/{HUMANEVAL_COMMIT}/LICENSE"
        ),
        license_filename="HumanEval-MIT.txt",
        expected_tasks=164,
    ),
    SourceDefinition(
        benchmark="MBPP",
        source="https://github.com/google-research/google-research/tree/master/mbpp",
        version=MBPP_COMMIT,
        license="CC BY 4.0 International (dataset); Apache-2.0 (repository source)",
        artifact_url=(
            "https://raw.githubusercontent.com/google-research/google-research/"
            f"{MBPP_COMMIT}/mbpp/sanitized-mbpp.json"
        ),
        artifact_filename="sanitized-mbpp.json",
        license_url="https://creativecommons.org/licenses/by/4.0/legalcode.txt",
        license_filename="MBPP-CC-BY-4.0.txt",
    ),
    SourceDefinition(
        benchmark="EvalPlus",
        source="https://github.com/evalplus/evalplus",
        version=EVALPLUS_VERSION,
        license="Apache-2.0",
        artifact_url=(
            f"https://github.com/evalplus/evalplus/archive/refs/tags/{EVALPLUS_VERSION}.tar.gz"
        ),
        artifact_filename=f"evalplus-{EVALPLUS_VERSION}.tar.gz",
        license_url=(
            f"https://raw.githubusercontent.com/evalplus/evalplus/{EVALPLUS_VERSION}/LICENSE"
        ),
        license_filename="EvalPlus-Apache-2.0.txt",
    ),
    SourceDefinition(
        benchmark="HumanEval+",
        source="https://github.com/evalplus/humanevalplus_release",
        version=HUMANEVAL_PLUS_VERSION,
        license="Apache-2.0 with upstream HumanEval MIT obligations retained",
        artifact_url=(
            "https://github.com/evalplus/humanevalplus_release/releases/download/"
            f"{HUMANEVAL_PLUS_VERSION}/HumanEvalPlus.jsonl.gz"
        ),
        artifact_filename="HumanEvalPlus.jsonl.gz",
        license_url=(
            f"https://raw.githubusercontent.com/evalplus/evalplus/{EVALPLUS_VERSION}/LICENSE"
        ),
        license_filename="HumanEvalPlus-Apache-2.0.txt",
        expected_tasks=164,
        derived_from=("HumanEval", "EvalPlus"),
    ),
    SourceDefinition(
        benchmark="MBPP+",
        source="https://github.com/evalplus/mbppplus_release",
        version=MBPP_PLUS_VERSION,
        license="Apache-2.0 with upstream MBPP CC BY 4.0 obligations retained",
        artifact_url=(
            "https://github.com/evalplus/mbppplus_release/releases/download/"
            f"{MBPP_PLUS_VERSION}/MbppPlus.jsonl.gz"
        ),
        artifact_filename="MbppPlus.jsonl.gz",
        license_url=(
            f"https://raw.githubusercontent.com/evalplus/evalplus/{EVALPLUS_VERSION}/LICENSE"
        ),
        license_filename="MBPPPlus-Apache-2.0.txt",
        expected_tasks=378,
        derived_from=("MBPP", "EvalPlus"),
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_sources(cache_directory: Path) -> tuple[FrozenSource, ...]:
    data_directory = cache_directory / "datasets"
    licenses_directory = cache_directory / "licenses"
    data_directory.mkdir(parents=True, exist_ok=True)
    licenses_directory.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.now(UTC).isoformat()
    frozen: list[FrozenSource] = []
    for definition in SOURCES:
        artifact = data_directory / definition.artifact_filename
        license_path = licenses_directory / definition.license_filename
        _download_if_missing(definition.artifact_url, artifact)
        _download_if_missing(definition.license_url, license_path)
        if definition.expected_tasks is not None and definition.artifact_filename.endswith(
            ".jsonl.gz"
        ):
            actual_count = sum(1 for _ in _read_gzip_jsonl(artifact))
            if actual_count != definition.expected_tasks:
                raise RuntimeError(
                    f"{definition.benchmark} task count mismatch: "
                    f"expected {definition.expected_tasks}, found {actual_count}"
                )
        frozen.append(
            FrozenSource(
                benchmark=definition.benchmark,
                source=definition.source,
                version=definition.version,
                license=definition.license,
                license_file=str(license_path),
                artifact_file=str(artifact),
                artifact_sha256=sha256_file(artifact),
                artifact_size=artifact.stat().st_size,
                license_sha256=sha256_file(license_path),
                retrieved_at=retrieved_at,
                derived_from=definition.derived_from,
            )
        )
    manifest_path = cache_directory / "benchmark_sources.json"
    manifest_path.write_text(
        json.dumps([asdict(item) for item in frozen], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return tuple(frozen)


def load_primary_tasks(
    sources: tuple[FrozenSource, ...],
    *,
    reference_input_tokens: dict[str, int] | None = None,
) -> tuple[BenchmarkTask, ...]:
    by_name = {source.benchmark: source for source in sources}
    tasks: list[BenchmarkTask] = []
    for benchmark, short_name in (("HumanEval+", "humaneval"), ("MBPP+", "mbpp")):
        source = by_name[benchmark]
        for row in _read_gzip_jsonl(Path(source.artifact_file)):
            task_id = str(row.get("task_id") or "")
            prompt = str(row.get("prompt") or "")
            entry_point = str(row.get("entry_point") or "")
            if not task_id or not prompt or not entry_point:
                raise RuntimeError(f"invalid {benchmark} task record")
            identity = f"{short_name}:{task_id}"
            tasks.append(
                BenchmarkTask(
                    benchmark=short_name,
                    benchmark_version=source.version,
                    task_id=task_id,
                    prompt=prompt,
                    entry_point=entry_point,
                    reference_input_tokens=(reference_input_tokens or {}).get(identity, 0),
                    source_sha256=source.artifact_sha256,
                )
            )
    expected = 164 + 378
    if len(tasks) != expected:
        raise RuntimeError(
            f"primary EvalPlus task count mismatch: expected {expected}, found {len(tasks)}"
        )
    identities = {task.identity() for task in tasks}
    if len(identities) != len(tasks):
        raise RuntimeError("duplicate task identity in primary benchmark")
    return tuple(tasks)


def _read_gzip_jsonl(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"invalid JSON at {path.name}:{line_number}") from exc


def _download_if_missing(url: str, target: Path) -> None:
    if target.is_file() and target.stat().st_size > 0:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Adaptive-Workflow-Benchmark/0.19.4"},
    )
    temporary: Path | None = None
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with tempfile.NamedTemporaryFile(
                prefix=f".{target.name}.", suffix=".download", dir=target.parent, delete=False
            ) as stream:
                temporary = Path(stream.name)
                shutil.copyfileobj(response, stream)
        if temporary.stat().st_size == 0:
            raise RuntimeError(f"downloaded empty artifact from {url}")
        temporary.replace(target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def frozen_sources_from_json(path: Path) -> tuple[FrozenSource, ...]:
    values: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    sources = tuple(
        FrozenSource(
            **{
                **value,
                "derived_from": tuple(value.get("derived_from", ())),
            }
        )
        for value in values
    )
    validate_frozen_sources(sources)
    return sources


def validate_frozen_sources(sources: tuple[FrozenSource, ...]) -> None:
    definitions = {definition.benchmark: definition for definition in SOURCES}
    if {source.benchmark for source in sources} != set(definitions):
        raise RuntimeError("frozen benchmark source set is incomplete or unexpected")
    for source in sources:
        definition = definitions[source.benchmark]
        if (
            source.source != definition.source
            or source.version != definition.version
            or source.license != definition.license
        ):
            raise RuntimeError(f"frozen benchmark provenance changed: {source.benchmark}")
        artifact = Path(source.artifact_file)
        license_path = Path(source.license_file)
        if not artifact.is_file() or sha256_file(artifact) != source.artifact_sha256:
            raise RuntimeError(f"frozen benchmark artifact hash mismatch: {source.benchmark}")
        if not license_path.is_file() or sha256_file(license_path) != source.license_sha256:
            raise RuntimeError(f"frozen benchmark license hash mismatch: {source.benchmark}")
        if artifact.stat().st_size != source.artifact_size:
            raise RuntimeError(f"frozen benchmark artifact size mismatch: {source.benchmark}")
