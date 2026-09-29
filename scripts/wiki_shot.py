#!/usr/bin/env python3
"""Screenshot a Wikipedia article with a phrase highlighted.

Fetches the article text LIVE from the Wikipedia API (real article text,
never generated or paraphrased), finds the paragraph containing the
highlight phrase, builds a clean Wikipedia-styled HTML page with the
phrase wrapped in <mark>, and screenshots it with headless Chromium.

Usage:
    python3 scripts/wiki_shot.py --article "Battle of Arracourt" \
        --highlight "Panther tanks" --out public/wiki/wiki_00.png
    python3 scripts/wiki_shot.py --article "Battle of Arracourt" \
        --highlight "Panther tanks" --out public/wiki/wiki_00.png --width 1280

Called by render.py during asset prep for every overlay of type wiki-quote.

Env notes:
- Python's urllib HTTPS is broken through this box's transparent egress
  proxy (TypeError inside chunked encoding), so the API fetch goes through
  curl, which is proxy-native.
- IPv6 literals are stripped from no_proxy/NO_PROXY first (copied from
  scripts/wordclock.py::_sanitize_proxy_env) for tools that misparse them.
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

UA = "history-video-pipeline/1.0"
API = "https://en.wikipedia.org/w/api.php"


def _sanitize_proxy_env():
    """Drop IPv6 literals from no_proxy (see wordclock.py)."""
    for key in ("no_proxy", "NO_PROXY"):
        val = os.environ.get(key, "")
        keep = [p.strip() for p in val.split(",") if p.strip() and ":" not in p]
        os.environ[key] = ",".join(keep)


def api_get(params):
    """Wikipedia API via curl (urllib HTTPS is broken behind this proxy)."""
    url = API + "?" + urllib.parse.urlencode(params)
    out = subprocess.run(
        ["curl", "-s", "-m", "30", "-A", UA, url],
        check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def fetch_article(title):
    """-> (canonical_title, [paragraphs]) or raises."""
    data = api_get({
        "action": "query", "prop": "extracts", "explaintext": "1",
        "titles": title, "format": "json", "redirects": "1",
    })
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        if page.get("missing"):
            raise RuntimeError(f"Wikipedia article not found: {title!r}")
        canon = page.get("title", title)
        extract = page.get("extract", "") or ""
        paras = []
        for chunk in extract.split("\n\n"):
            # drop "== Section ==" header lines, keep the prose
            lines = [ln for ln in chunk.split("\n")
                     if not re.match(r"^\s*==.*==\s*$", ln)]
            text = "\n".join(lines).strip()
            if text:
                paras.append(text)
        if not paras:
            raise RuntimeError(f"Wikipedia article has no text: {canon!r}")
        return canon, paras
    raise RuntimeError(f"Wikipedia article not found: {title!r}")


def mark_paragraph(para, highlight):
    """HTML-escape the paragraph, wrapping every highlight hit in <mark>."""
    parts, last = [], 0
    for m in re.finditer(re.escape(highlight), para, re.IGNORECASE):
        parts.append(html.escape(para[last:m.start()]))
        parts.append(f"<mark>{html.escape(m.group(0))}</mark>")
        last = m.end()
    parts.append(html.escape(para[last:]))
    return "".join(parts)


PAGE_CSS = """
body { background: #f8f9fa; margin: 0; padding: 0; }
.page {
  background: #ffffff; max-width: 940px; margin: 56px auto;
  padding: 54px 62px 46px; border: 1px solid #a2a9b1;
  box-shadow: 0 2px 10px rgba(0,0,0,0.08);
}
.kicker {
  font-family: -apple-system, 'Segoe UI', Roboto, sans-serif;
  font-size: 14px; letter-spacing: 5px; color: #72777d;
  text-transform: uppercase; margin-bottom: 6px;
}
h1 {
  font-family: 'Linux Libertine', Georgia, 'Times New Roman', serif;
  font-size: 46px; font-weight: 400; color: #000;
  border-bottom: 1px solid #a2a9b1; padding-bottom: 12px;
  margin: 0 0 28px;
}
p {
  font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, sans-serif;
  font-size: 21px; line-height: 1.7; color: #202122; margin: 0 0 18px;
}
mark { background: #ffe600; color: inherit; padding: 0 3px; border-radius: 2px; }
.foot {
  margin-top: 34px; font-family: -apple-system, 'Segoe UI', Roboto, sans-serif;
  font-size: 14px; color: #72777d;
}
"""


def build_html(title, para_html):
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>{html.escape(title)} - Wikipedia</title>
<style>{PAGE_CSS}</style></head>
<body><div class="page">
<div class="kicker">Wikipedia &middot; The Free Encyclopedia</div>
<h1>{html.escape(title)}</h1>
<p>{para_html}</p>
<div class="foot">From Wikipedia, the free encyclopedia</div>
</div></body></html>
"""


def find_chromium():
    for name in ("chromium", "chromium-browser", "google-chrome",
                 "google-chrome-stable"):
        p = shutil.which(name)
        if p:
            return p
    home = os.path.expanduser("~")
    for cand in (
            os.path.join(home, ".cache/ms-playwright/chromium-1243/"
                         "chrome-linux/chrome"),
            os.path.join(home, ".cache/ms-playwright/"
                         "chromium_headless_shell-1243/chrome-linux/"
                         "headless_shell")):
        if os.path.exists(cand):
            return cand
    return None


def screenshot(html_path, out, width, height=900):
    chrome = find_chromium()
    if not chrome:
        raise RuntimeError("no Chromium found (checked PATH + "
                           "ms-playwright cache)")
    headless = ("--headless" if os.path.basename(chrome) == "headless_shell"
                else "--headless=new")
    cmd = [chrome, headless, "--disable-gpu", "--no-sandbox",
           "--hide-scrollbars", f"--screenshot={out}",
           f"--window-size={width},{height}", f"file://{html_path}"]
    subprocess.run(cmd, check=True, capture_output=True, text=True,
                   timeout=120)
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        raise RuntimeError("chromium produced no screenshot")
    return chrome


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--article", required=True,
                    help='Wikipedia article title, e.g. "Battle of Arracourt"')
    ap.add_argument("--highlight", required=True,
                    help="exact phrase to highlight (must appear in article)")
    ap.add_argument("--out", required=True, help="output PNG path")
    ap.add_argument("--width", type=int, default=1280)
    args = ap.parse_args()

    _sanitize_proxy_env()
    title, paras = fetch_article(args.article)
    hl = args.highlight.strip()
    para = next((p for p in paras if hl.lower() in p.lower()), None)
    if para is None:
        raise RuntimeError(
            f"highlight phrase {hl!r} not found in article {title!r}")

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html",
                                     delete=False) as fh:
        fh.write(build_html(title, mark_paragraph(para, hl)))
        html_path = fh.name
    try:
        chrome = screenshot(html_path, out, args.width)
    finally:
        os.unlink(html_path)
    print(f"wiki: {title} -> {args.out} (chromium: {chrome})",
          file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"error: {e}")
