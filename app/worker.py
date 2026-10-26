# -*- coding: utf-8 -*-
"""Background workers (QThread) wrapping yt-dlp: link analysis + downloads."""
import os

import yt_dlp
from PyQt6.QtCore import QThread, pyqtSignal

from . import utils


class AnalyzeWorker(QThread):
    """Extract metadata for a URL (single video or flat playlist)."""
    done = pyqtSignal(object)     # info dict
    failed = pyqtSignal(str)      # error message

    def __init__(self, url: str, cookies_browser: str = "", parent=None):
        super().__init__(parent)
        self.url = (url or "").strip()
        self.cookies_browser = cookies_browser or ""

    def run(self):
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",   # fast for playlists, full for single videos
            "socket_timeout": 25,
            "retries": 3,
        }
        if self.cookies_browser:
            opts["cookiesfrombrowser"] = (self.cookies_browser,)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            self.done.emit(info or {})
        except yt_dlp.utils.DownloadCancelled:
            pass
        except Exception as e:
            self.failed.emit(_err_msg(e))


class DownloadWorker(QThread):
    """Download a single item; reports progress/ok/failed/canceled."""
    progress = pyqtSignal(object)  # yt-dlp hook dict or {'status': 'postprocessing'}
    ok = pyqtSignal(str)           # final file path
    failed = pyqtSignal(str)
    canceled = pyqtSignal()

    def __init__(self, url, quality, download_dir, cookies_browser="", parent=None):
        super().__init__(parent)
        self.url = url
        self.quality = quality if quality not in (None, "") else "best"
        self.download_dir = download_dir
        self.cookies_browser = cookies_browser or ""
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

    # ---------- main ----------
    def run(self):
        os.makedirs(self.download_dir, exist_ok=True)
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
            "concurrent_fragment_downloads": 4,   # much faster on HLS/DASH streams
            "windowsfilenames": True,             # sanitize illegal Windows chars
            "socket_timeout": 30,
        }
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

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                base = ydl.prepare_filename(info)
            path = self._locate(base)
            self.ok.emit(path or base)
        except yt_dlp.utils.DownloadCancelled:
            self.canceled.emit()
        except Exception as e:
            if self._cancel:
                self.canceled.emit()
            else:
                self.failed.emit(_err_msg(e))

    def _locate(self, base: str) -> str | None:
        """The real output file may differ from prepare_filename after merging/MP3 conversion."""
        root, _ = os.path.splitext(base)
        cands = [root + ".mp4", root + ".mp3", base,
                 root + ".webm", root + ".mkv", root + ".m4a",
                 root + ".opus", root + ".ogg", root + ".wav"]
        if self.quality == "mp3":
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
