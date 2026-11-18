#!/usr/bin/env python3
"""Build the v8.0.2 current-release PDF from its Markdown source.

Markdown -> HTML (markdown-it-py) -> PDF (LibreOffice headless).
The Markdown file (docs/TRUSTLINE_V8.0.2_CURRENT_RELEASE_REPORT.md) is
the source of truth; the HTML is a build intermediate written to the
system temp dir, and the PDF is written beside the Markdown source.
If the two ever disagree, the Markdown governs and the PDF must be
regenerated with this script.

Requires: markdown-it-py (in the v7.3.1 dev venv) and LibreOffice
(`soffice`). Run from anywhere:

  <venv>/bin/python scripts/build-current-release-report.py
  pdfinfo docs/TRUSTLINE_V8.0.2_CURRENT_RELEASE_REPORT.pdf
  pdftotext docs/TRUSTLINE_V8.0.2_CURRENT_RELEASE_REPORT.pdf - | head
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "docs/TRUSTLINE_V8.0.2_CURRENT_RELEASE_REPORT.md"
PDF = ROOT / "docs/TRUSTLINE_V8.0.2_CURRENT_RELEASE_REPORT.pdf"

CSS = """
@page { size: A4; margin: 2cm; }
body { font-family: "DejaVu Sans", sans-serif; font-size: 11pt; line-height: 1.45; color: #111; }
h1 { font-size: 18pt; border-bottom: 2px solid #111; padding-bottom: 6px; }
h2 { font-size: 14pt; margin-top: 1.4em; border-bottom: 1px solid #999; padding-bottom: 3px; }
h3 { font-size: 12pt; margin-top: 1.1em; }
table { border-collapse: collapse; margin: 0.6em 0; font-size: 10pt; }
th, td { border: 1px solid #666; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #eee; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 9.5pt; background: #f2f2f2; padding: 0 2px; }
pre { background: #f2f2f2; padding: 8px; font-size: 9.5pt; overflow-wrap: break-word; white-space: pre-wrap; }
pre code { background: none; padding: 0; }
blockquote { border-left: 3px solid #666; margin-left: 0; padding-left: 12px; color: #222; }
"""

md = MarkdownIt("commonmark").enable("table")
body = md.render(MD.read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory() as tmp:
    html = Path(tmp) / "TRUSTLINE_V8.0.2_CURRENT_RELEASE_REPORT.html"
    html.write_text(
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">\n"
        "<title>IdentityForge — Current-Release Report: Operation Trustline v8.0.2</title>\n"
        f"<style>{CSS}</style></head><body>\n{body}</body></html>\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(PDF.parent), str(html)],
        capture_output=True, text=True, timeout=180,
    )
    print(r.stdout.strip())
    if r.stderr.strip():
        print(r.stderr.strip(), file=sys.stderr)
    if r.returncode != 0:
        sys.exit(f"soffice failed rc={r.returncode}")
print(f"PDF written: {PDF} ({PDF.stat().st_size} bytes)")
