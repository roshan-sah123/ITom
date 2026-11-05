import subprocess
from pathlib import Path

import pytest

from app.services import attachment_preview as preview


@pytest.mark.parametrize("name,data,mime", [
    ("reference.pdf", b"%PDF-1.7\npreview", "application/pdf"),
    ("notes.txt", b"Operational notes", "text/plain"),
    ("diagram.png", b"\x89PNG\r\n\x1a\nbytes", "image/png"),
])
def test_native_preview_preserves_bytes(name, data, mime):
    result, result_type = preview.preview_attachment(name, data)
    assert result == data
    assert result_type == mime


@pytest.mark.parametrize("name", ["payload.exe", "unknown", "page.html", "image.svg", "archive.zip"])
def test_unsupported_preview_is_explicit_and_never_converts(name, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unsupported files must not reach the converter")
    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(preview.PreviewError, match="Preview unavailable") as error:
        preview.preview_attachment(name, b"opaque bytes")
    assert error.value.status_code == 415


def test_office_conversion_is_bounded_private_and_cleans_up(monkeypatch, tmp_path):
    converter = tmp_path / "soffice.com"
    converter.touch()
    monkeypatch.setattr(preview.settings, "DOCUMENT_PREVIEW_CONVERTER", str(converter))
    paths = []

    def convert(command, **kwargs):
        assert kwargs["timeout"] == 45
        assert kwargs["shell"] is False
        assert "--headless" in command
        assert any(value.startswith("-env:UserInstallation=file:") for value in command)
        source = Path(command[-1])
        assert source.name == "document.xlsx"
        assert source.read_bytes() == b"original workbook"
        profile = source.parent / "profile" / "user" / "registrymodifications.xcu"
        assert "MacroSecurityLevel" in profile.read_text()
        assert "UpdateDocMode" in profile.read_text()
        output = Path(command[command.index("--outdir") + 1])
        (output / "document.pdf").write_bytes(b"%PDF-1.7\nconverted")
        paths.append(source.parent)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", convert)
    result, mime = preview.preview_attachment("employee workbook.xlsx", b"original workbook")
    assert result == b"%PDF-1.7\nconverted"
    assert mime == "application/pdf"
    assert all(not path.exists() for path in paths)


def test_missing_converter_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setattr(preview.settings, "DOCUMENT_PREVIEW_CONVERTER", str(tmp_path / "missing.exe"))
    with pytest.raises(preview.PreviewError) as error:
        preview.preview_attachment("guide.docx", b"original")
    assert error.value.status_code == 503


@pytest.mark.parametrize("failure,status", [
    (subprocess.TimeoutExpired("converter", 45), 504),
    (subprocess.CalledProcessError(1, "converter"), 422),
    (OSError("private diagnostic"), 503),
])
def test_conversion_failures_have_safe_messages(monkeypatch, tmp_path, failure, status):
    converter = tmp_path / "soffice.com"
    converter.touch()
    monkeypatch.setattr(preview.settings, "DOCUMENT_PREVIEW_CONVERTER", str(converter))

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(preview.PreviewError) as error:
        preview.preview_attachment("guide.docx", b"opaque content")
    assert error.value.status_code == status
    assert "private diagnostic" not in str(error.value)
