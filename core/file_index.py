"""Index uploaded files for Q&A using local Ollama."""

from __future__ import annotations

import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from core.ollama_text import ollama_complete
from core.voice_input import transcribe_file

_AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
_TEXT = {".txt", ".md", ".csv", ".json", ".log", ".py", ".js", ".html"}


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages[:30]:
            parts.append(page.extract_text() or "")
        return "\n".join(parts).strip()
    except Exception:
        pass
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages[:30]).strip()
    except Exception:
        return ""


def _read_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        return " ".join(
            t.text or "" for t in root.findall(".//w:t", ns) if t.text
        ).strip()
    except Exception:
        return ""


def _read_audio(path: Path) -> str:
    wav = tempfile.mktemp(suffix=".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-ar", "16000", "-ac", "1", wav],
            check=False,
            capture_output=True,
            timeout=120,
        )
        if Path(wav).exists() and Path(wav).stat().st_size > 1000:
            return transcribe_file(wav, min_bytes=1000) or ""
    except Exception:
        pass
    finally:
        Path(wav).unlink(missing_ok=True)
    return ""


def extract_text(path: Path, max_chars: int = 12000) -> str:
    ext = path.suffix.lower()
    if ext in _TEXT:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    if ext == ".pdf":
        return _read_pdf(path)[:max_chars]
    if ext in (".docx", ".doc"):
        return _read_docx(path)[:max_chars]
    if ext in _AUDIO:
        return _read_audio(path)[:max_chars]
    return path.read_text(encoding="utf-8", errors="ignore")[:2000]


def index_file(path: Path) -> dict:
    text = extract_text(path)
    name = path.name
    if not text.strip():
        summary = f"File '{name}' uploaded but no readable text was extracted."
        return {"name": name, "path": str(path), "summary": summary, "text": ""}

    preview = text[:6000]
    summary = ollama_complete(
        f"File: {name}\n\nContent preview:\n{preview}\n\n"
        "In 2-3 concise sentences, describe what this file contains and its main topics."
    )
    return {
        "name": name,
        "path": str(path),
        "summary": summary.strip(),
        "text": preview,
    }
