"""Builds self-contained report.html and slides.html from docs/*_src.html.

Every <img src="img/..."> is inlined as a base64 data URI so the files open anywhere,
even when emailed. Missing screenshots render as a labelled placeholder box.
Usage:  python scripts/build_docs.py
"""
import base64
import mimetypes
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def inline(html: str) -> str:
    def repl(m):
        path = DOCS / m.group(2)
        if not path.exists():
            name = m.group(2)
            return (f'<div class="ph">Screenshot pending: {name}</div>')
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        data = base64.b64encode(path.read_bytes()).decode()
        return f'<img{m.group(1)}src="data:{mime};base64,{data}"{m.group(3)}>'
    return re.sub(r'<img([^>]*?)src="(img/[^"]+)"([^>]*)>', repl, html)


def main():
    for name in ("report", "slides"):
        src = DOCS / f"{name}_src.html"
        if src.exists():
            (ROOT / f"{name}.html").write_text(inline(src.read_text(encoding="utf-8")), encoding="utf-8")
            print("built", f"{name}.html")


if __name__ == "__main__":
    main()
