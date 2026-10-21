"""Takes report screenshots with headless Microsoft Edge (Windows) or Chrome.

The app must be running (python app.py). Usage:
  python scripts/screenshots.py applicant                # docs/img/01_applicant.png
  python scripts/screenshots.py tests                    # docs/img/07_tests.png (runs pytest)
  python scripts/screenshots.py run <run_id> <name> [h]  # replay a finished run, full page height h
"""
import html
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "docs" / "img"
BASE = "http://localhost:5000/"
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            shutil.which("google-chrome") or "", shutil.which("chromium") or ""]


def shoot(url: str, out: Path, width=1400, height=900):
    exe = next(b for b in BROWSERS if b and Path(b).exists())
    IMG.mkdir(parents=True, exist_ok=True)
    subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--window-size={width},{height}", "--virtual-time-budget=6000",
                    f"--screenshot={out}", url], check=True, timeout=90,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("saved", out)


def tests_page() -> Path:
    r = subprocess.run([sys.executable, "-m", "pytest", "-v", "--color=no", "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if "::" in l or "passed" in l or "failed" in l]
    body = "\n".join(html.escape(l.replace(str(ROOT), ".")) for l in lines)
    page = IMG / "_tests.html"
    page.write_text(f"""<html><body style="margin:0;background:#0c1a10;color:#cfe8cf;
      font:14px/1.5 Consolas,monospace;padding:18px"><div style="color:#9fc79f">$ python -m pytest -v</div>
      <pre style="margin:6px 0 0">{body}</pre></body></html>""", encoding="utf-8")
    return page


if __name__ == "__main__":
    what = sys.argv[1]
    if what == "applicant":
        shoot(BASE + "#maria_bronx", IMG / "01_applicant.png", height=640)
    elif what == "tests":
        shoot(tests_page().as_uri(), IMG / "07_tests.png", width=1100, height=560)
    elif what == "run":
        shoot(BASE + "#run=" + sys.argv[2], IMG / f"{sys.argv[3]}.png",
              height=int(sys.argv[4]) if len(sys.argv) > 4 else 2400)
    elif what == "crop":  # crop <src> <dst> x0 y0 x1 y1
        from PIL import Image
        Image.open(IMG / f"{sys.argv[2]}.png").crop(tuple(map(int, sys.argv[4:8]))).save(IMG / f"{sys.argv[3]}.png")
        print("saved", IMG / f"{sys.argv[3]}.png")
