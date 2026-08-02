import hashlib
import os
import stat
import zipfile
from pathlib import Path

import pytest

from knowledge_pipeline.enterprise.controlled_conversion import (
    ConversionError,
    ConverterApprovalPolicy,
    ConversionRequest,
    ConverterSpec,
    ProcessResult,
    convert_document,
)


class FakeRunner:
    def __init__(self, behavior: str = "success") -> None:
        self.behavior = behavior
        self.argv = ()
        self.input_was_read_only = False

    def run(self, argv, *, timeout_seconds, cwd):
        self.argv = argv
        source, output = Path(argv[-2]), Path(argv[-1])
        self.input_was_read_only = not bool(stat.S_IMODE(source.stat().st_mode) & stat.S_IWUSR)
        if self.behavior == "raise_timeout":
            raise TimeoutError
        if self.behavior == "timeout":
            return ProcessResult(1, True)
        if self.behavior == "exit":
            return ProcessResult(7)
        if self.behavior == "mutate":
            os.chmod(source, stat.S_IWRITE | stat.S_IREAD)
            source.write_bytes(b"changed")
        if output.suffix == ".docx" and self.behavior != "bad_format":
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", "<document/>")
        elif output.suffix == ".pdf" and self.behavior != "bad_format":
            output.write_bytes(b"%PDF-1.7\nconverted\n%%EOF")
        else:
            output.write_bytes(b"not-the-declared-format")
        return ProcessResult(0)


def _approved(tmp_path: Path, fixed_args=("--headless",)):
    spec = ConverterSpec("approved-local-converter", str((tmp_path / "tools" / "converter.exe").resolve()), fixed_args)
    return spec, ConverterApprovalPolicy((spec,))


@pytest.mark.parametrize(("source_format", "target"), (("wps", "docx"), ("doc", "docx"), ("ofd", "pdf")))
def test_conversion_uses_read_only_staged_input_and_argv_array(tmp_path: Path, source_format: str, target: str) -> None:
    source = tmp_path / f"source.{source_format}"
    source.write_bytes(f"immutable-{source_format}".encode())
    staging = tmp_path / "staging"
    runner = FakeRunner()
    spec, policy = _approved(tmp_path)
    artifact = convert_document(
        ConversionRequest(source, source_format, staging, 30),
        spec,
        runner,
        policy,
    )
    assert isinstance(runner.argv, tuple)
    assert runner.argv[0] == os.path.normcase(os.path.normpath(str(Path(spec.executable).resolve())))
    assert runner.input_was_read_only
    assert artifact.output_format == target and staging.resolve() in artifact.output_path.resolve().parents
    assert artifact.source_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert artifact.output_sha256 == hashlib.sha256(artifact.output_path.read_bytes()).hexdigest()
    with pytest.raises(ConversionError, match="conversion_output_exists"):
        convert_document(
            ConversionRequest(source, source_format, staging, 30),
            spec,
            runner,
            policy,
        )


@pytest.mark.parametrize(
    ("behavior", "error"),
    (("raise_timeout", "conversion_timeout"), ("timeout", "conversion_timeout"), ("exit", "conversion_exit_nonzero"),
     ("bad_format", "converted_output_format_invalid"), ("mutate", "conversion_input_modified")),
)
def test_conversion_fail_closed_on_runner_and_output_failures(tmp_path: Path, behavior: str, error: str) -> None:
    source = tmp_path / "source.ofd"
    source.write_bytes(b"immutable")
    spec, policy = _approved(tmp_path, ())
    with pytest.raises(ConversionError, match=error):
        convert_document(
            ConversionRequest(source, "ofd", tmp_path / behavior, 10),
            spec,
            FakeRunner(behavior),
            policy,
        )


def test_conversion_rejects_unlisted_format_shell_and_suffix_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("data", encoding="utf-8")
    spec, policy = _approved(tmp_path, ())
    with pytest.raises(ConversionError, match="conversion_format_forbidden"):
        convert_document(ConversionRequest(source, "txt", tmp_path / "a"), spec, FakeRunner(), policy)
    with pytest.raises(ConversionError, match="conversion_source_format_mismatch"):
        convert_document(ConversionRequest(source, "doc", tmp_path / "b"), spec, FakeRunner(), policy)
    doc = tmp_path / "source.doc"
    doc.write_bytes(b"doc")
    shell = ConverterSpec("bad", str((tmp_path / "cmd.exe").resolve()))
    with pytest.raises(ConversionError, match="shell_executable_forbidden"):
        convert_document(ConversionRequest(doc, "doc", tmp_path / "c"), shell, FakeRunner(), ConverterApprovalPolicy((shell,)))


@pytest.mark.parametrize("drift", ("name", "executable", "args"))
def test_conversion_requires_exact_approved_spec(tmp_path: Path, drift: str) -> None:
    source = tmp_path / "source.doc"
    source.write_bytes(b"doc")
    approved, policy = _approved(tmp_path)
    changes = {
        "name": {"name": "unknown-converter"},
        "executable": {"executable": str((tmp_path / "tools" / "other.exe").resolve())},
        "args": {"fixed_args": ("--headless", "--drift")},
    }[drift]
    candidate = ConverterSpec(
        changes.get("name", approved.name),
        changes.get("executable", approved.executable),
        changes.get("fixed_args", approved.fixed_args),
    )
    with pytest.raises(ConversionError, match="converter_spec_not_approved"):
        convert_document(ConversionRequest(source, "doc", tmp_path / "staging"), candidate, FakeRunner(), policy)

    relative = ConverterSpec("relative", "converter.exe")
    with pytest.raises(ConversionError, match="converter_executable_must_be_absolute"):
        convert_document(
            ConversionRequest(source, "doc", tmp_path / "relative"),
            relative,
            FakeRunner(),
            ConverterApprovalPolicy((relative,)),
        )
