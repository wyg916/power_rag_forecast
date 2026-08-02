from __future__ import annotations

import hashlib
import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


ALLOWED_CONVERSIONS = {"wps": "docx", "doc": "docx", "ofd": "pdf"}
SHELL_EXECUTABLES = {"bash", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "sh"}


class ConversionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConversionRequest:
    source_path: Path
    source_format: str
    staging_root: Path
    timeout_seconds: int = 300


@dataclass(frozen=True)
class ConverterSpec:
    name: str
    executable: str
    fixed_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConverterApprovalPolicy:
    approved_specs: tuple[ConverterSpec, ...]

    def allows(self, spec: ConverterSpec) -> bool:
        identity = (spec.name, _normalized_executable(spec.executable), spec.fixed_args)
        return any(
            identity == (approved.name, _normalized_executable(approved.executable), approved.fixed_args)
            for approved in self.approved_specs
        )


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    timed_out: bool = False


@dataclass(frozen=True)
class ConversionArtifact:
    source_sha256: str
    input_copy: Path
    output_path: Path
    output_format: str
    output_sha256: str
    converter_name: str


class ConversionRunner(Protocol):
    def run(self, argv: tuple[str, ...], *, timeout_seconds: int, cwd: Path) -> ProcessResult: ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _normalized_executable(value: str) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ConversionError("converter_executable_must_be_absolute")
    return os.path.normcase(os.path.normpath(str(path.resolve())))


def _validate_spec(spec: ConverterSpec) -> None:
    if not spec.name or not spec.executable:
        raise ConversionError("converter_spec_incomplete")
    if any(mark in spec.executable for mark in ("\0", "\n", "\r")):
        raise ConversionError("converter_argv_invalid")
    _normalized_executable(spec.executable)
    if Path(spec.executable).name.lower() in SHELL_EXECUTABLES:
        raise ConversionError("shell_executable_forbidden")
    if any(not isinstance(arg, str) or "\0" in arg or "\n" in arg or "\r" in arg for arg in spec.fixed_args):
        raise ConversionError("converter_argv_invalid")


def _validate_output(path: Path, output_format: str) -> None:
    if output_format == "pdf":
        with path.open("rb") as handle:
            header = handle.read(8)
            handle.seek(max(0, path.stat().st_size - 1024))
            trailer = handle.read(1024)
        if not header.startswith(b"%PDF-") or b"%%EOF" not in trailer:
            raise ConversionError("converted_output_format_invalid")
        return
    if output_format == "docx":
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
        except (OSError, zipfile.BadZipFile) as exc:
            raise ConversionError("converted_output_format_invalid") from exc
        if not {"[Content_Types].xml", "word/document.xml"} <= names:
            raise ConversionError("converted_output_format_invalid")
        return
    raise ConversionError("converted_output_format_forbidden")


def convert_document(
    request: ConversionRequest,
    spec: ConverterSpec,
    runner: ConversionRunner,
    approval_policy: ConverterApprovalPolicy,
) -> ConversionArtifact:
    source_format = request.source_format.lower().lstrip(".")
    output_format = ALLOWED_CONVERSIONS.get(source_format)
    if output_format is None:
        raise ConversionError("conversion_format_forbidden")
    source = request.source_path.resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != f".{source_format}":
        raise ConversionError("conversion_source_format_mismatch")
    if isinstance(request.timeout_seconds, bool) or not 1 <= request.timeout_seconds <= 1800:
        raise ConversionError("conversion_timeout_invalid")
    _validate_spec(spec)
    if not approval_policy.allows(spec):
        raise ConversionError("converter_spec_not_approved")

    staging_root = request.staging_root.resolve()
    input_root = (staging_root / "inputs").resolve()
    output_root = (staging_root / "outputs").resolve()
    if not _within(input_root, staging_root) or not _within(output_root, staging_root):
        raise ConversionError("conversion_staging_escape")
    input_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    source_hash = sha256_file(source)
    staged_input = (input_root / f"{source_hash}.{source_format}").resolve()
    output_path = (output_root / f"{source_hash}.{output_format}").resolve()
    if not _within(staged_input, staging_root) or not _within(output_path, staging_root):
        raise ConversionError("conversion_staging_escape")
    if staged_input.exists() or output_path.exists():
        raise ConversionError("conversion_output_exists")
    with source.open("rb") as source_handle, staged_input.open("xb") as staged_handle:
        for block in iter(lambda: source_handle.read(1024 * 1024), b""):
            staged_handle.write(block)
    if sha256_file(staged_input) != source_hash:
        raise ConversionError("conversion_input_copy_hash_mismatch")
    try:
        os.chmod(staged_input, stat.S_IREAD)
    except OSError as exc:
        raise ConversionError("conversion_input_readonly_failed") from exc

    argv = (_normalized_executable(spec.executable), *spec.fixed_args, str(staged_input), str(output_path))
    if not isinstance(argv, tuple):
        raise ConversionError("converter_argv_must_be_array")
    try:
        result = runner.run(argv, timeout_seconds=request.timeout_seconds, cwd=staging_root)
    except TimeoutError as exc:
        raise ConversionError("conversion_timeout") from exc
    if result.timed_out:
        raise ConversionError("conversion_timeout")
    if result.exit_code != 0:
        raise ConversionError(f"conversion_exit_nonzero:{result.exit_code}")
    try:
        inputs_unchanged = sha256_file(source) == source_hash and sha256_file(staged_input) == source_hash
    except OSError as exc:
        raise ConversionError("conversion_input_modified") from exc
    if not inputs_unchanged:
        raise ConversionError("conversion_input_modified")
    if not output_path.is_file() or not _within(output_path.resolve(), staging_root):
        raise ConversionError("conversion_output_missing_or_escaped")
    _validate_output(output_path, output_format)
    output_hash = sha256_file(output_path)
    if not output_hash:
        raise ConversionError("conversion_output_hash_missing")
    return ConversionArtifact(source_hash, staged_input, output_path, output_format, output_hash, spec.name)
