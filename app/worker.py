# -*- coding: utf-8 -*-
"""Background workers (QThread) wrapping yt-dlp: link analysis + downloads.

Worst-case / censorship-hardened behaviour:
* All proxy URLs go through utils.normalize_proxy() — 'socks5://' becomes
  'socks5h://' so DNS is resolved *through the proxy* (local DNS in censored
  networks is poisoned and breaks even a working proxy).
* IPv4 is forced ('socket_address_family') — broken IPv6 on some ISPs/VPNs
  causes "Network is unreachable".
* AnalyzeWorker: fast timeouts, auto-retry with no-check-certificate on TLS
  interception, auto-retry with alternative YouTube player clients on
  bot-check / player errors.
* DownloadWorker: self-healing retry ladder — SSL fix -> format fallback ->
  single-file fallback when ffmpeg is missing -> alternative YouTube clients.
"""
import os

import yt_dlp
from PyQt6.QtCore import QThread, pyqtSignal

from . import utils

BASE_IPV4 = {"socket_address_family": "ipv4"}

# Alternative YouTube player clients — help against "Sign in to confirm
# you're not a bot", age-walls and player errors without any cookies.
YT_ALT_ARGS = [
    {"youtube": {"player_client": ["tv", "web_safari"]}},
    {"youtube": {"player_client": ["ios", "tv_embedded"]}},
]

ALT_TRIGGERS = ("sign in to confirm", "not a bot", "unable to extract",
                "player response", "this video is unavailable",
                "precondition check failed", "age", "private video",
                "video unavailable", "confirm your age")


def _is_youtube(url: str) -> bool:
    u = (url or "").lower()
    return ("youtube.com" in u or "youtu.be" in u or "youtube-nocookie" in u)


class AnalyzeWorker(QThread):
    """Extract metadata for a URL (single video or flat playlist)."""
    done = pyqtSignal(object)     # info dict
    failed = pyqtSignal(str)      # error message

    def __init__(self, url: str, cookies_browser: str = "", proxy: str = "",
                 insecure: bool = False, parent=None):
        super().__init__(parent)
        self.url = (url or "").strip()
        self.cookies_browser = cookies_browser or ""
        self.proxy, _ = utils.normalize_proxy(proxy)
        self.insecure = insecure

    def run(self):
        base = {
            "quiet": True, "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",   # fast for playlists, full for single videos
            "socket_timeout": 15,            # fail fast so the fallback ladder can run
            "retries": 2, "extractor_retries": 1,
            "geo_bypass": True, **BASE_IPV4,
        }
        if self.proxy:
            base["proxy"] = self.proxy
        if self.insecure:
            base["nocheckcertificate"] = True
        if self.cookies_browser:
            base["cookiesfrombrowser"] = (self.cookies_browser,)

        attempts = [dict(base)]
        # self-healing plan built per failure type while running:
        #  1) plain  2) TLS fix  3) alt YouTube clients  4) TLS fix + alt clients
        err = None
        for i, opts in enumerate(attempts):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(self.url, download=False)
                if self.insecure or opts.get("nocheckcertificate"):
                    info = dict(info or {})
                    info["_vg_insecure"] = True
                self.done.emit(info or {})
                return
            except yt_dlp.utils.DownloadCancelled:
                return
            except Exception as e:
                err = _err_msg(e)
                low = err.lower()
                if "ssl" in low or "certificate" in low:
                    nxt = dict(base); nxt["nocheckcertificate"] = True
                    if nxt not in attempts:
                        attempts.append(nxt)
                if _is_youtube(self.url) and any(t in low for t in ALT_TRIGGERS):
                    for args in YT_ALT_ARGS:
                        nxt = dict(base); nxt["extractor_args"] = dict(args)
                        if "ssl" in low or "certificate" in low:
                            nxt["nocheckcertificate"] = True
                        if nxt not in attempts:
                            attempts.append(nxt)
                # stop growing the ladder after the second pass
                if i >= 2:
                    break
        self.failed.emit(err or "unknown error")


class ProxyDetectWorker(QThread):
    """Probe common local proxy ports of popular VPN clients (v2rayN, NekoRay,
    Clash, Oblivion/Warp, Hiddify, Tor, ...)."""
    done = pyqtSignal(list)       # list of working proxy URLs

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            self.done.emit(utils.detect_proxies())
        except Exception:
            self.done.emit([])


class DownloadWorker(QThread):
    """Download a single item; reports progress/ok/failed/canceled.

    Self-heals through a retry ladder (max 4 attempts total):
      SSL/cert error      -> nocheckcertificate
      format unavailable  -> plain 'best'
      ffmpeg/merge error  -> single-file format (no merging needed)
      network + YouTube   -> alternative player clients
    """
    progress = pyqtSignal(object)  # yt-dlp hook dict or {'status': 'postprocessing'}
    ok = pyqtSignal(str)           # final file path
    failed = pyqtSignal(str)
    canceled = pyqtSignal()
    attempt = pyqtSignal(int, int)  # attempt number, total possible

    MAX_ATTEMPTS = 4

    def __init__(self, url, quality, download_dir, cookies_browser="",
                 proxy="", insecure=False, parent=None):
        super().__init__(parent)
        self.url = url
        self.quality = quality if quality not in (None, "") else "best"
        self.download_dir = download_dir
        self.cookies_browser = cookies_browser or ""
        self.proxy, _ = utils.normalize_proxy(proxy)
        self.insecure = insecure
        self._cancel = False

    def cancel(self):
        self._cancel = True

    # ---------- hooks ----------
    def _progress_hook(self, d):
        if self._cancel:
            raise yt_dlp.utils.DownloadCancelled()
        self.progress.emit(d)

    def _pp_hook(self, d):
        if self._cancel:
            raise yt_dlp.utils.DownloadCancelled()
        if d.get("status") == "started":
            self.progress.emit({"status": "postprocessing",
                                "postprocessor": d.get("postprocessor", "")})

    # ---------- options ----------
    def _base_opts(self) -> dict:
        opts = {
            "outtmpl": os.path.join(self.download_dir, "%(title).100s [%(id)s].%(ext)s"),
            "format": utils.format_selector(self.quality),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "progress_hooks": [self._progress_hook],
            "postprocessor_hooks": [self._pp_hook],
            "retries": 10,
            "fragment_retries": 10,
            "extractor_retries": 2,
            "concurrent_fragment_downloads": 4,   # much faster on HLS/DASH streams
            "http_chunk_size": 10 * 1024 * 1024,  # small chunks survive flaky/blocked links
            "windowsfilenames": True,             # sanitize illegal Windows chars
            "socket_timeout": 30,
            "geo_bypass": True,
            **BASE_IPV4,
        }
        if self.proxy:
            opts["proxy"] = self.proxy
        if self.insecure:
            opts["nocheckcertificate"] = True
        if self.quality == "mp3":
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        else:
            opts["merge_output_format"] = "mp4"
        if self.cookies_browser:
            opts["cookiesfrombrowser"] = (self.cookies_browser,)
        return opts

    # ---------- main ----------
    def run(self):
        os.makedirs(self.download_dir, exist_ok=True)
        opts = self._base_opts()
        used_alt = 0
        err = "unknown error"
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            if self._cancel:
                self.canceled.emit()
                return
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(self.url, download=True)
                    base = ydl.prepare_filename(info)
                path = self._locate(base, opts)
                self.ok.emit(path or base)
                return
            except yt_dlp.utils.DownloadCancelled:
                self.canceled.emit()
                return
            except Exception as e:
                if self._cancel:
                    self.canceled.emit()
                    return
                err = _err_msg(e)
                low = err.lower()

                if "ssl" in low or "certificate" in low:
                    if not opts.get("nocheckcertificate"):
                        opts["nocheckcertificate"] = True
                        self._emit_attempt(attempt)
                        continue
                if "requested format" in low:
                    opts["format"] = "best"
                    self._emit_attempt(attempt)
                    continue
                if "ffmpeg" in low or "merging" in low:
                    # fall back to a single pre-merged file; no ffmpeg needed
                    if self.quality == "mp3":
                        self.failed.emit(err)   # MP3 without ffmpeg is impossible
                        return
                    opts.pop("merge_output_format", None)
                    opts.pop("postprocessors", None)
                    h = None
                    try:
                        h = int(self.quality)
                    except (TypeError, ValueError):
                        pass
                    opts["format"] = (f"best[height<={h}][vcodec!=none]/best[vcodec!=none]/best"
                                      if h else "best[vcodec!=none]/best")
                    self._emit_attempt(attempt)
                    continue
                if _is_youtube(self.url) and (utils.error_is_network(err) or
                                              any(t in low for t in ALT_TRIGGERS)) \
                        and used_alt < len(YT_ALT_ARGS):
                    opts["extractor_args"] = dict(YT_ALT_ARGS[used_alt])
                    used_alt += 1
                    self._emit_attempt(attempt)
                    continue
                # nothing else we can try
                self.failed.emit(err)
                return
        self.failed.emit(err)

    def _emit_attempt(self, n: int):
        self.attempt.emit(n + 1, self.MAX_ATTEMPTS)

    def _locate(self, base: str, opts: dict) -> str | None:
        """The real output file may differ from prepare_filename after merging/MP3 conversion."""
        root, _ = os.path.splitext(base)
        cands = [root + ".mp4", base, root + ".webm", root + ".mkv",
                 root + ".m4a", root + ".opus", root + ".ogg", root + ".wav"]
        if opts.get("postprocessors"):
            cands.insert(0, root + ".mp3")
        for c in cands:
            if os.path.isfile(c):
                return c
        return None


def _err_msg(e: Exception) -> str:
    """Short, user-facing error text from a yt-dlp exception."""
    s = str(e)
    if "ERROR:" in s:
        s = s.split("ERROR:")[-1].strip()
    return s[:600] if s else type(e).__name__
