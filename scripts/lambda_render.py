#!/usr/bin/env python3
"""
scripts/lambda_render.py — the pipeline's Lambda render path.

    python3 scripts/lambda_render.py --props props.json --out video.mp4 --site-name my-project

Steps:
  1. npx remotion bundle  -> local static site (includes public/ assets)
  2. upload site          -> s3://<bucket>/sites/<site-name>/  (vendored boto3, proxy-native)
  3. launch               -> scripts/lambda_launch.mjs (proxy-aware Node)
  4. poll progress.json   -> until done / fatal / timeout
  5. download out.mp4     -> --out

Chunking rule (verified 2026-09-27 on a 3:47 1080p video: 4m46s):
  The AWS account allows 10 concurrent Lambdas. When framesPerLambda is
  set, Remotion launches ALL chunks at once, so chunks must stay <= 9.
  Each chunk must also finish inside the 900s Lambda timeout.
  -> framesPerLambda = ceil(totalFrames/9) clamped to [500, 1500];
     if that still yields > 9 chunks (very long video), fall back to
     concurrency=9 alone and let Remotion queue them.
  NOTE: Remotion rejects setting both framesPerLambda and concurrency.
"""
import argparse
import concurrent.futures
import json
import mimetypes
import os
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
# vendored deps (survives system python resets)
sys.path.insert(0, os.path.join(PROJECT_DIR, ".deps"))

MAX_CONCURRENT_CHUNKS = 9   # account limit is 10; keep one slot of headroom
MIN_FPL, MAX_FPL = 500, 1500

CONTENT_TYPES = {
    ".html": "text/html",
    ".js": "application/javascript",
    ".map": "application/json",
    ".css": "text/css",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}


def log(msg):
    print(f"[lambda] {msg}", flush=True)


def build_site(site_dir):
    log("building site bundle (npx remotion bundle) ...")
    subprocess.run(
        ["npx", "remotion", "bundle", "src/index.ts",
         "--out-dir", site_dir, "--quiet"],
        cwd=PROJECT_DIR, check=True, timeout=1200,
    )
    n = sum(len(files) for _, _, files in os.walk(site_dir))
    log(f"site built: {n} files")


def upload_site(site_dir, bucket, site_name):
    import boto3
    s3 = boto3.client("s3", region_name="us-east-1")
    prefix = f"sites/{site_name}/"
    jobs = []
    for root, _, files in os.walk(site_dir):
        for f in files:
            local = os.path.join(root, f)
            rel = os.path.relpath(local, site_dir).replace(os.sep, "/")
            ext = os.path.splitext(f)[1].lower()
            ctype = CONTENT_TYPES.get(ext) or mimetypes.guess_type(f)[0] \
                or "binary/octet-stream"
            jobs.append((local, prefix + rel, ctype))

    def put(job):
        local, key, ctype = job
        import boto3 as b3
        c = b3.client("s3", region_name="us-east-1")
        c.upload_file(local, bucket, key,
                      ExtraArgs={"ContentType": ctype})

    log(f"uploading {len(jobs)} site files to s3://{bucket}/{prefix} ...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(put, jobs))
    log("site upload complete")
    return f"https://{bucket}.s3.us-east-1.amazonaws.com/{prefix}index.html"


def find_fresh_render(s3, bucket, max_age_min=5):
    """Newest render whose progress.json was written within max_age_min."""
    from datetime import datetime, timezone
    r = s3.list_objects_v2(Bucket=bucket, Prefix="renders/", Delimiter="/")
    now = datetime.now(timezone.utc)
    best, best_age = None, None
    for p in r.get("CommonPrefixes", []):
        rid = p["Prefix"].split("/")[1]
        try:
            o = s3.head_object(Bucket=bucket,
                               Key=f"renders/{rid}/progress.json")
            age = (now - o["LastModified"]).total_seconds() / 60
            if age < max_age_min and (best_age is None or age < best_age):
                best, best_age = rid, age
        except Exception:
            pass
    return best


def launch(props_path, serve_url, region, function_name,
           frames_per_lambda, concurrency, bucket):
    import boto3
    s3 = boto3.client("s3", region_name=region)
    env = dict(os.environ)
    env["NODE_OPTIONS"] = \
        f"--require {os.path.join(PROJECT_DIR, 'proxy-preload.cjs')}"
    cmd = ["node",
           os.path.join(SCRIPT_DIR, "lambda_launch.mjs"),
           "--props", props_path,
           "--serve-url", serve_url,
           "--region", region,
           "--function-name", function_name]
    if frames_per_lambda:
        cmd += ["--frames-per-lambda", str(frames_per_lambda)]
    elif concurrency:
        cmd += ["--concurrency", str(concurrency)]

    for attempt in range(1, 4):
        out = subprocess.run(cmd, cwd=PROJECT_DIR, env=env,
                             capture_output=True, text=True, timeout=300)
        info = {}
        for line in out.stdout.splitlines():
            for key in ("RENDERID:", "BUCKET:", "START_TS:"):
                if line.startswith(key):
                    info[key.rstrip(":").lower()] = line[len(key):].strip()
        if "renderid" in info:
            log(f"launched render {info['renderid']}")
            return info
        # Egress-proxy flake: the invoke often succeeded server-side
        # (HTTP 200) while the response was lost. Adopt the fresh render
        # instead of launching a duplicate.
        log(f"launch attempt {attempt} lost its response; checking S3 "
            f"for a fresh render ...")
        time.sleep(30)
        fresh = find_fresh_render(s3, bucket)
        if fresh:
            log(f"adopted render {fresh} (started server-side)")
            return {"renderid": fresh, "bucket": bucket,
                    "start_ts": str(int(time.time()))}
        log("no fresh render found; retrying launch")
    raise RuntimeError("launch failed 3x with no recoverable render")


def render_finished(s3, bucket, render_id):
    """out.mp4 exists -> the render is done (progress.json's `done` flag
    is unreliable; the file's presence is the real signal)."""
    try:
        s3.head_object(Bucket=bucket, Key=f"renders/{render_id}/out.mp4")
        return True
    except Exception:
        return False


def poll(s3, bucket, render_id, timeout_min):
    key = f"renders/{render_id}/progress.json"
    deadline = time.time() + timeout_min * 60
    last = 0
    while time.time() < deadline:
        if render_finished(s3, bucket, render_id):
            r = s3.get_object(Bucket=bucket, Key=key)
            return json.loads(r["Body"].read())
        try:
            r = s3.get_object(Bucket=bucket, Key=key)
            p = json.loads(r["Body"].read())
        except Exception as e:
            log(f"progress read failed ({e}); retrying")
            time.sleep(15)
            continue
        fatal = [e for e in p.get("errors", []) if e.get("isFatal")]
        if fatal:
            raise RuntimeError("render fatal: " +
                               fatal[0].get("message", "?")[:300])
        if p.get("done") or render_finished(s3, bucket, render_id):
            return p
        if time.time() - last > 60:
            log(f"{p.get('framesRendered', 0)} frames rendered, "
                f"{p.get('lambdasInvoked', 0)} lambdas invoked")
            last = time.time()
        time.sleep(15)
    raise TimeoutError(f"render {render_id} not done after {timeout_min} min")


def download_output(s3, bucket, render_id, out_path):
    key = f"renders/{render_id}/out.mp4"
    out_path = os.path.abspath(out_path)
    # NEVER resume onto a stale file: a previous render's complete output
    # at out_path plus a Range-appended tail = a frankenfile that plays as
    # the OLD video (hit 2026-09-27: 312MB stale + 306MB new object).
    # Delete first; curl -C - then only resumes this render's own partial.
    if os.path.exists(out_path):
        log(f"removing stale {out_path} before download")
        os.remove(out_path)
    # boto3 first; on proxy flakiness fall back to resumable curl
    # via a presigned URL.
    for attempt in range(1, 4):
        try:
            s3.download_file(bucket, key, out_path)
            log("downloaded via boto3")
            return
        except Exception as e:
            log(f"boto3 download attempt {attempt} failed ({e}); "
                f"trying resumable curl")
        try:
            url = s3.generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": key},
                ExpiresIn=3600)
            r = subprocess.run(
                ["curl", "-sL", "-C", "-", "--retry", "2",
                 "-o", out_path, url],
                timeout=1800)
            if r.returncode == 0 and os.path.getsize(out_path) > 0:
                log("downloaded via curl (resumed)")
                return
        except Exception as e:
            log(f"curl download attempt {attempt} failed ({e})")
        time.sleep(20)
    raise RuntimeError("output download failed after retries")


def main():
    ap = argparse.ArgumentParser(description="Render via Remotion Lambda")
    ap.add_argument("--props", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--site-name", required=True,
                    help="S3 site prefix: sites/<site-name>/")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--bucket",
                    default="remotionlambda-useast1-r5lxcie5hs")
    ap.add_argument("--function-name",
                    default="remotion-render-4-0-527-mem3008mb-disk10240mb-900sec")
    ap.add_argument("--timeout-min", type=int, default=60)
    args = ap.parse_args()

    import boto3
    s3 = boto3.client("s3", region_name=args.region)

    with open(args.props, encoding="utf-8") as fh:
        props = json.load(fh)
    total_frames = sum(s.get("durationInFrames", 0)
                       for s in props.get("segments", []))
    if not total_frames:
        sys.exit("error: no segments/frames in props")

    # chunking: keep chunks <= 9 (account limit 10, all launch at once)
    fpl = min(MAX_FPL, max(MIN_FPL, -(-total_frames // MAX_CONCURRENT_CHUNKS)))
    chunks = -(-total_frames // fpl)
    if chunks > MAX_CONCURRENT_CHUNKS:
        fpl, conc = None, MAX_CONCURRENT_CHUNKS
        log(f"{total_frames} frames -> long video: concurrency=9 queue mode")
    else:
        conc = None
        log(f"{total_frames} frames -> {chunks} chunks x {fpl} frames")

    site_dir = os.path.join(PROJECT_DIR, "tmp", f"site-{args.site_name}")
    build_site(site_dir)
    serve_url = upload_site(site_dir, args.bucket, args.site_name)

    info = launch(os.path.abspath(args.props), serve_url, args.region,
                  args.function_name, fpl, conc, args.bucket)
    render_id, bucket = info["renderid"], info["bucket"]
    start_ts = int(info.get("start_ts", time.time()))

    final = poll(s3, bucket, render_id, args.timeout_min)
    download_output(s3, bucket, render_id, args.out)

    elapsed = time.time() - start_ts
    mins, secs = divmod(int(elapsed), 60)
    log(f"DONE in {mins}m {secs:02d}s -> {os.path.abspath(args.out)} "
        f"({os.path.getsize(os.path.abspath(args.out))} bytes)")


if __name__ == "__main__":
    main()
