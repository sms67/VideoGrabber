# -*- coding: utf-8 -*-
"""Persistent settings stored as JSON in %APPDATA%/VideoGrabber/settings.json."""
import json
import os

APP_NAME = "VideoGrabber"


def _default_dir() -> str:
    dl = os.path.join(os.path.expanduser("~"), "Downloads")
    base = dl if os.path.isdir(dl) else os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


DEFAULTS = {
    "lang": "fa",                # "fa" | "en"
    "download_dir": _default_dir(),
    "max_parallel": 2,           # simultaneous downloads (1..5)
    "cookies_browser": "",       # "" | "chrome" | "firefox" | "edge" | ...
    "playlist_quality": "best",  # best | 2160 | 1440 | 1080 | 720 | 480 | 360 | mp3
    "proxy_mode": "smart",       # "smart" | "direct" | "proxy"
    "proxy_url": "",             # e.g. socks5://127.0.0.1:10808
}


def config_path() -> str:
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME, "settings.json")


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if k in DEFAULTS:
                cfg[k] = v
    except Exception:
        pass
    return cfg


def save(cfg: dict) -> None:
    try:
        path = config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
