#!/usr/bin/env python3
"""Fetch a satellite map image for a map-callout overlay.

Geocodes the place name via Nominatim (free, no key), then pulls a
satellite image with a red pin from the Mapbox Static Images API
(MAPBOX_TOKEN in the project .env, chmod 600). Falls back to Esri World
Imagery tiles (free, no key) if Mapbox is unavailable.

Usage:
    python3 scripts/fetch_map.py "Hammelburg, Germany" --out maps/hammelburg.png
    python3 scripts/fetch_map.py "Hammelburg, Germany" --out maps/hammelburg.png --zoom 13 --no-pin

Called by render.py during asset prep for every overlay of type map-callout.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

SR = None  # (no audio here)


def load_dotenv():
    """Project-root .env, stdlib-only (no dependency). Env vars win."""
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(os.path.dirname(here), ".env"),
                 os.path.join(here, ".env")):
        if os.path.exists(cand):
            with open(cand) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(),
                                              v.strip().strip('"').strip("'"))
            break


def http_get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def geocode(place):
    """Nominatim: place name -> (lat, lon). Free, needs a user-agent."""
    q = urllib.parse.quote(place)
    url = ("https://nominatim.openstreetmap.org/search?format=json&limit=1&q="
           + q)
    raw = http_get(url, {"User-Agent": "history-video-pipeline/1.0"})
    hits = json.loads(raw)
    if not hits:
        raise RuntimeError(f"geocode: no result for {place!r}")
    return float(hits[0]["lat"]), float(hits[0]["lon"])


def fetch_mapbox(lat, lon, out, zoom, width, height, pin):
    token = os.environ.get("MAPBOX_TOKEN", "")
    if not token:
        raise RuntimeError("MAPBOX_TOKEN not set")
    overlay = f"pin-l+ff0000({lon},{lat})" if pin else "0"
    url = (
        "https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/"
        f"{overlay}/{lon},{lat},{zoom},0/{width}x{height}"
        f"?access_token={token}&attribution=false&logo=false"
    )
    img = http_get(url)
    if not (img.startswith(b"\x89PNG") or img.startswith(b"\xff\xd8\xff")):
        raise RuntimeError(f"mapbox: unexpected response ({img[:60]!r})")
    with open(out, "wb") as f:
        f.write(img)


def fetch_esri(lat, lon, out, zoom, width, height):
    """Fallback: stitch Esri World_Imagery tiles (free, no key)."""
    import math
    n = 2 ** zoom
    cx = (lon + 180.0) / 360.0 * n
    cy = (1.0 - math.log(math.tan(math.radians(lat))
                         + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    tx, ty = int(cx), int(cy)
    tiles_x = (width + 255) // 256
    tiles_y = (height + 255) // 256
    x0 = tx - tiles_x // 2
    y0 = ty - tiles_y // 2
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("esri fallback needs Pillow (pip install pillow)")
    canvas = Image.new("RGB", (tiles_x * 256, tiles_y * 256))
    for dx in range(tiles_x):
        for dy in range(tiles_y):
            url = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                   f"World_Imagery/MapServer/tile/{zoom}/{y0 + dy}/{x0 + dx}")
            raw = http_get(url, {"User-Agent": "history-video-pipeline/1.0"})
            import io
            tile = Image.open(io.BytesIO(raw)).convert("RGB")
            canvas.paste(tile, (dx * 256, dy * 256))
            time.sleep(0.15)
    # crop to center at the requested size, draw a red pin dot
    px = int((cx - x0) * 256)
    py = int((cy - y0) * 256)
    canvas = canvas.crop((px - width // 2, py - height // 2,
                          px + width // 2, py + height // 2))
    if True:  # pin marker
        from PIL import ImageDraw
        d = ImageDraw.Draw(canvas)
        r = max(14, width // 90)
        d.ellipse([width // 2 - r, height // 2 - r,
                   width // 2 + r, height // 2 + r], fill=(226, 58, 46))
    canvas.save(out, "PNG")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("place", help='place name, e.g. "Hammelburg, Germany"')
    ap.add_argument("--out", required=True, help="output PNG path")
    ap.add_argument("--zoom", type=int, default=12)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--no-pin", action="store_true",
                    help="skip the pin marker")
    ap.add_argument("--latlon", default=None,
                    help="skip geocoding: 'lat,lon'")
    args = ap.parse_args()

    load_dotenv()
    if args.latlon:
        lat, lon = (float(x) for x in args.latlon.split(","))
    else:
        lat, lon = geocode(args.place)
        time.sleep(1)  # Nominatim usage policy

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    try:
        fetch_mapbox(lat, lon, args.out, args.zoom, args.width, args.height,
                     pin=not args.no_pin)
        print(f"mapbox: {args.place} -> {args.out} ({lat:.4f},{lon:.4f})")
    except Exception as e:
        print(f"mapbox failed ({e}), falling back to Esri tiles",
              file=sys.stderr)
        fetch_esri(lat, lon, args.out, args.zoom, args.width, args.height)
        print(f"esri: {args.place} -> {args.out} ({lat:.4f},{lon:.4f})")


if __name__ == "__main__":
    main()
