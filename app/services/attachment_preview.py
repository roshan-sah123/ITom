"""Local, temporary Office conversion; originals are never modified."""

import logging
import subprocess
import tempfile
import threading
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("itom.previews")
_conversion_lock = threading.Lock()
_native_types = {
    ".pdf": "application/pdf", ".txt": "text/plain", ".csv": "text/plain",
    ".log": "text/plain", ".json": "text/plain", ".xml": "text/plain",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".mp4": "video/mp4",
    ".webm": "video/webm", ".mov": "video/quicktime",
}
_office_types = {".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods",
                 ".ppt", ".pptx", ".odp"}
_profile = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting">
<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>
<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>
</item>
<item oor:path="/org.openoffice.Office.Writer/Content/Update">
<prop oor:name="Link" oor:op="fuse"><value>false</value></prop>
</item>
<item oor:path="/org.openoffice.Office.Calc/Content/Update">
<prop oor:name="Link" oor:op="fuse"><value>2</value></prop>
</item>
<item oor:path="/org.openoffice.Office.Common/Load">
<prop oor:name="UpdateDocMode" oor:op="fuse"><value>0</value></prop>
</item>
</oor:items>"""


class PreviewError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def preview_attachment(name: str, data: bytes) -> tuple[bytes, str]:
    extension = Path(name).suffix.lower()
    if extension in _native_types:
        return data, _native_types[extension]
    if extension not in _office_types:
        raise PreviewError(415, "Preview unavailable for this file format.")
    executable = Path(settings.DOCUMENT_PREVIEW_CONVERTER) if settings.DOCUMENT_PREVIEW_CONVERTER else None
    if executable is None or not executable.is_file():
        logger.error("Office preview converter is not configured or available")
        raise PreviewError(503, "Office preview is unavailable: the local converter is not configured.")
    if not _conversion_lock.acquire(blocking=False):
        raise PreviewError(429, "Another Office preview is being prepared. Please retry shortly.")
    try:
        with tempfile.TemporaryDirectory(prefix="itom-preview-") as directory:
            root = Path(directory)
            source = root / ("document" + extension)
            source.write_bytes(data)
            user = root / "profile" / "user"
            user.mkdir(parents=True)
            (user / "registrymodifications.xcu").write_text(_profile, encoding="utf-8")
            output = root / "output"
            output.mkdir()
            subprocess.run(
                [str(executable), "-env:UserInstallation=" + (root / "profile").as_uri(),
                 "--headless", "--nologo", "--nodefault", "--norestore", "--nolockcheck",
                 "--convert-to", "pdf", "--outdir", str(output), str(source)],
                check=True, timeout=45, shell=False, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            result = output / "document.pdf"
            if not result.is_file() or not 0 < result.stat().st_size <= 30 * 1024 * 1024:
                logger.warning("Office preview produced no usable PDF")
                raise PreviewError(422, "Preview unavailable. The file may be encrypted, damaged, or too large to render.")
            converted = result.read_bytes()
            if not converted.startswith(b"%PDF-"):
                logger.error("Office preview converter produced a non-PDF result")
                raise PreviewError(422, "Preview unavailable: document conversion did not produce a readable PDF.")
            return converted, "application/pdf"
    except subprocess.TimeoutExpired as error:
        logger.warning("Office preview conversion timed out")
        raise PreviewError(504, "Preview preparation timed out. The document may be password-protected or too complex.") from error
    except subprocess.CalledProcessError as error:
        logger.warning("Office preview conversion failed exit_code=%s", error.returncode)
        raise PreviewError(422, "Preview unavailable. The document could not be converted.") from error
    except OSError as error:
        logger.exception("Local Office preview operation failed")
        raise PreviewError(503, "The local preview service is unavailable. Please retry.") from error
    finally:
        _conversion_lock.release()
