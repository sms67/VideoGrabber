# -*- coding: utf-8 -*-
"""Small helpers: human-readable sizes, ffmpeg detection, yt-dlp format selectors."""
import os
import shutil
import sys


def human_size(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    if n <= 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def human_speed(n) -> str:
    return human_size(n) + "/s" if n else "—"


def human_eta(s) -> str:
    if s is None or s < 0:
        return "—"
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def human_duration(s) -> str:
    return human_eta(s) if s else "—"


def find_ffmpeg() -> str | None:
    """Locate ffmpeg: next to EXE/script first, then PATH."""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    bases = []
    if getattr(sys, "frozen", False):
        bases.append(os.path.dirname(sys.executable))
    try:
        bases.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    except Exception:
        pass
    for b in bases:
        p = os.path.join(b, exe)
        if os.path.isfile(p):
            return p
    return shutil.which("ffmpeg")


def format_selector(quality) -> str:
    """Build a yt-dlp format selector from a quality key."""
    if quality == "mp3":
        return "bestaudio/best"
    if quality in (None, "", "best"):
        return "bestvideo*+bestaudio/best"
    try:
        h = int(quality)
    except (TypeError, ValueError):
        return "bestvideo*+bestaudio/best"
    return f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"


def quality_label(key, lang: str) -> str:
    """Short human label for a quality key."""
    if key == "mp3":
        return "MP3"
    if key in (None, "", "best"):
        from .i18n import tr
        return tr(lang, "q_best_short")
    return f"{key}p"


def available_qualities(info: dict) -> list:
    """Extract video qualities (height + approx size) from yt-dlp info dict."""
    fmts = info.get("formats") or []
    best_audio = 0
    for f in fmts:
        if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none"):
            sz = f.get("filesize") or f.get("filesize_approx") or 0
            best_audio = max(best_audio, sz or 0)

    heights = {}
    for f in fmts:
        h = f.get("height")
        if not h or f.get("vcodec") in (None, "none"):
            continue
        sz = f.get("filesize") or f.get("filesize_approx") or 0
        cur = heights.get(h)
        if cur is None or (sz or 0) >= cur[0]:
            heights[h] = (sz or 0, f.get("fps") or 0)

    out = []
    for h in sorted(heights, reverse=True):
        sz, fps = heights[h]
        total = sz + best_audio if best_audio else sz
        label = f"{h}p" + (f" {int(fps)}fps" if fps and fps >= 48 else "")
        out.append({"key": str(h), "label": label, "size": total or None})
    return out
