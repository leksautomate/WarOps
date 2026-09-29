#!/usr/bin/env python3
"""Pinterest image fetcher for the history-video pipeline.

Method (verified 2026-09-29): Pinterest's search page is bot-walled from
datacenter IPs, but pin PAGES are SEO-friendly and served to curl.
Pin discovery happens via web search (site:pinterest.com) — done by the
agent at production time. This script takes pin URLs, fetches each pin
page with curl, extracts the full-res pinimg.com image URL, and
downloads it. No API key, no browser needed.

Usage:
    python3 pinterest_images.py --pins pins.txt --out ./pinterest_imgs
    python3 pinterest_images.py --pin https://www.pinterest.com/pin/123/ --out ./x
"""
import re
import subprocess
import argparse
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def curl(url, out_path=None, max_time=40):
    cmd = ["curl", "-sL", "--max-time", str(max_time), "-A", UA, url]
    if out_path:
        cmd += ["-o", str(out_path)]
        r = subprocess.run(cmd, capture_output=True)
        return r.returncode == 0 and out_path.exists()
    r = subprocess.run(cmd, capture_output=True)
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""


def pin_image_url(pin_url):
    """Fetch a pin page and return the best pinimg.com image URL."""
    html = curl(pin_url)
    if not html or len(html) < 50000:
        return None
    # Prefer the embedded 736x/originals image; og:image is often present too.
    urls = re.findall(r"https://i\.pinimg\.com/[^\s\"'\\]+", html)
    # Filter out tiny UI assets / emoticons: keep photo-ish ones.
    photo = [u for u in urls if "/60x60/" not in u and "emoticon" not in u]
    if not photo:
        return None
    # Prefer originals > 736x > 564x.
    def rank(u):
        if "/originals/" in u:
            return 0
        m = re.search(r"/(\d+)x/", u)
        return -int(m.group(1)) if m else 99
    best = sorted(set(photo), key=rank)[0]
    # Upgrade 736x/564x to originals when possible.
    best = re.sub(r"pinimg\.com/\d+x/", "pinimg.com/originals/", best)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pins", help="text file with one pin URL per line")
    ap.add_argument("--pin", action="append", default=[],
                    help="single pin URL (repeatable)")
    ap.add_argument("--num", type=int, default=8)
    ap.add_argument("--out", default="pinterest_imgs")
    args = ap.parse_args()

    pins = list(args.pin)
    if args.pins:
        pins += [l.strip() for l in Path(args.pins).read_text().splitlines()
                 if l.strip().startswith("http")]
    # De-dupe, keep order.
    pins = list(dict.fromkeys(pins))[:args.num * 2]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, pin in enumerate(pins):
        if len(saved) >= args.num:
            break
        try:
            img = pin_image_url(pin)
            if not img:
                print(f"[{i}] no image found: {pin}")
                continue
            ext = ".png" if img.endswith(".png") else ".jpg"
            dest = out / f"pin_{i}{ext}"
            if curl(img, dest) and dest.stat().st_size > 20000:
                print(f"[{i}] saved {dest} "
                      f"({dest.stat().st_size // 1024}KB)\n     {pin}")
                saved.append(str(dest))
            else:
                if dest.exists():
                    dest.unlink()
                print(f"[{i}] download failed: {img[:80]}")
        except Exception as e:
            print(f"[{i}] error: {type(e).__name__}")
    print(f"DONE: {len(saved)} images in {out}")


if __name__ == "__main__":
    main()
