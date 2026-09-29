"""Word-clock: measure real word timings from narration audio.

Caption phrases used to be timed by a spoken-length estimate (character
counts, digit expansion, punctuation pauses). That drifts. This module runs
the segment's silence-trimmed MP3 through faster-whisper with word
timestamps, then aligns the transcribed words to the segment's exact script
text with difflib. The renderer times each caption phrase on the actual
spoken words, and falls back to the estimate when alignment confidence is
low.

Nothing here touches the script text or the audio — timing only.
"""

import difflib
import os
import re
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".deps")
)

_MODEL = None
MODEL_NAME = "tiny"  # fast on CPU, fine for clean TTS English


def _sanitize_proxy_env():
    """Drop IPv6 literals from no_proxy.

    The vendored httpx (via huggingface-hub) crashes parsing bracketed IPv6
    entries like [::1] in NO_PROXY ("Invalid port: ':1]'"), which kills the
    model download. IPv6 loopbacks are irrelevant for downloading models,
    so they are dropped; everything else is kept.
    """
    for key in ("no_proxy", "NO_PROXY"):
        val = os.environ.get(key, "")
        keep = [p.strip() for p in val.split(",") if p.strip() and ":" not in p]
        os.environ[key] = ",".join(keep)


def _load_model():
    global _MODEL
    if _MODEL is None:
        _sanitize_proxy_env()
        from faster_whisper import WhisperModel

        _MODEL = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
    return _MODEL


_WORD_RE = re.compile(r"[^\w']+", re.UNICODE)


def _norm(word):
    """Lowercase, strip punctuation (keep apostrophes): for alignment only."""
    return _WORD_RE.sub("", word.lower())


def get_word_timings(audio_path, text, min_confidence=0.5):
    """Return [(start_sec, end_sec)] per script word, or None on low confidence.

    Times are relative to the audio file's start (render.py passes the
    silence-trimmed MP3, so frame 0 of the scene is ~the first word).
    """
    script_words = text.split()
    if not script_words:
        return None

    model = _load_model()
    whisper_segments, _info = model.transcribe(audio_path, word_timestamps=True)

    hyp = []  # (normalized_word, start, end)
    for wseg in whisper_segments:
        for w in wseg.words or []:
            n = _norm(w.word)
            if n:
                hyp.append((n, float(w.start), float(w.end)))
    if not hyp:
        return None

    ref = [_norm(w) for w in script_words]
    sm = difflib.SequenceMatcher(
        a=ref, b=[h[0] for h in hyp], autojunk=False
    )

    times = [None] * len(script_words)
    matched = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            continue  # replaced/inserted/deleted words get interpolated below
        n = i2 - i1
        # "equal" blocks always have n == m; keep the guard for safety
        if n == j2 - j1:
            for k in range(n):
                times[i1 + k] = (hyp[j1 + k][1], hyp[j1 + k][2])
        else:
            t0, t1 = hyp[j1][1], hyp[j2 - 1][2]
            for k in range(n):
                times[i1 + k] = (
                    t0 + (t1 - t0) * k / n,
                    t0 + (t1 - t0) * (k + 1) / n,
                )
        matched += n

    if matched / len(script_words) < min_confidence:
        return None

    # Fill unmatched words by linear interpolation between anchored words.
    result = list(times)
    anchored = [(i, t) for i, t in enumerate(times) if t is not None]
    if not anchored:
        return None

    first_i, (first_s, _first_e) = anchored[0]
    if first_i > 0:
        step = first_s / first_i
        for k in range(first_i):
            result[k] = (step * k, step * (k + 1))

    for (i0, (_s0, e0)), (i1, (s1, _e1)) in zip(anchored, anchored[1:]):
        gap = i1 - i0 - 1
        if gap > 0:
            for k in range(1, gap + 1):
                a = e0 + (s1 - e0) * (k - 1) / gap
                b = e0 + (s1 - e0) * k / gap
                result[i0 + k] = (a, b)

    last_i, (_last_s, last_e) = anchored[-1]
    audio_end = hyp[-1][2]
    n_trail = len(result) - 1 - last_i
    if n_trail > 0:
        step = max(0.0, audio_end - last_e) / n_trail
        for k in range(n_trail):
            result[last_i + 1 + k] = (
                last_e + step * k,
                last_e + step * (k + 1),
            )

    return [(max(0.0, float(s)), max(0.0, float(e))) for s, e in result]


if __name__ == "__main__":
    # smoke test: python3 scripts/wordclock.py <audio.mp3> "<text>"
    audio, text = sys.argv[1], sys.argv[2]
    timings = get_word_timings(audio, text)
    if timings is None:
        print("word-clock: no confident alignment (fallback to estimation)")
        sys.exit(1)
    for w, (s, e) in zip(text.split(), timings):
        print(f"{s:7.2f}-{e:7.2f}  {w}")
