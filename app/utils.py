# -*- coding: utf-8 -*-
"""Small helpers: human-readable sizes, ffmpeg detection, yt-dlp format selectors,
censorship-aware error classification and local proxy auto-detection."""
import os
import shutil
import socket
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor


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


# ================= censorship-aware helpers =================

# (port, type) — default local ports of common proxy apps used in Iran:
# v2rayN 10808/10809, NekoRay 2080/2081, Clash 7890/7891, Oblivion(Warp) 40000,
# Hiddify 12334, Tor 9050, privoxy 8118, classic socks 1080, generic http 8080/8888
COMMON_PROXY_PORTS = [
    (10808, "socks5"), (10809, "http"),   # v2rayN
    (2080, "socks5"), (2081, "http"),     # NekoRay / NekoBox
    (7890, "http"), (7891, "socks5"),     # Clash / Clash Verge
    (1080, "socks5"),                     # classic socks
    (40000, "socks5"),                    # Oblivion / Warp
    (12334, "http"),                      # Hiddify
    (20170, "socks5"), (20171, "http"),   # Xray / misc
    (9050, "socks5"),                     # Tor
    (8118, "http"),                       # privoxy
    (8080, "http"), (8888, "http"),       # generic http proxies
]


def classify_error(msg: str) -> str:
    """Rough classification of a yt-dlp failure for user-facing hints."""
    m = (msg or "").lower()
    net_kw = ("timed out", "timeout", "connection reset", "connection refused",
              "getaddrinfo", "name or service not known", "temporary failure",
              "unable to download webpage", "network is unreachable",
              "10060", "10054", "ssl", "certificate", "tunnel connection failed",
              "proxy", "http error 40", "http error 5")
    if any(k in m for k in net_kw):
        return "net"
    if any(k in m for k in ("sign in", "age", "login", "private", "cookies")):
        return "auth"
    if "unsupported url" in m:
        return "badurl"
    return "other"


def _socks5_connect(host, port, target_host, target_port, timeout):
    sock = socket.create_connection((host, int(port)), timeout=timeout)
    sock.settimeout(timeout)
    sock.sendall(b"\x05\x01\x00")                       # greeting: no auth
    resp = sock.recv(2)
    if len(resp) < 2 or resp[0] != 5 or resp[1] != 0:
        raise OSError("not a socks5 proxy")
    addr = target_host.encode()
    req = b"\x05\x01\x00\x03" + bytes([len(addr)]) + addr + int(target_port).to_bytes(2, "big")
    sock.sendall(req)
    resp = sock.recv(32)
    if len(resp) < 2 or resp[1] != 0:
        raise OSError("socks5 connect failed")
    return sock


def _http_connect(host, port, target_host, target_port, timeout):
    sock = socket.create_connection((host, int(port)), timeout=timeout)
    sock.settimeout(timeout)
    req = (f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
           f"Host: {target_host}:{target_port}\r\n\r\n").encode()
    sock.sendall(req)
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(1024)
        if not chunk:
            raise OSError("proxy closed connection")
        data += chunk
    if b" 200" not in data.split(b"\r\n", 1)[0]:
        raise OSError("proxy refused CONNECT")
    return sock


def probe_proxy(proxy_host, proxy_port, ptype, timeout=4.0,
                target_host="www.youtube.com", target_port=443):
    """True if https://target is reachable through this (possibly local) proxy."""
    try:
        if ptype == "socks5":
            sock = _socks5_connect(proxy_host, proxy_port, target_host, target_port, timeout)
        else:
            sock = _http_connect(proxy_host, proxy_port, target_host, target_port, timeout)
        try:
            ctx = ssl.create_default_context()
            tls = ctx.wrap_socket(sock, server_hostname=target_host)
            tls.settimeout(timeout)
            tls.sendall(f"HEAD /generate_204 HTTP/1.1\r\nHost: {target_host}\r\n"
                        f"Connection: close\r\n\r\n".encode())
            resp = tls.recv(512)
            return bool(resp)
        finally:
            try:
                sock.close()
            except Exception:
                pass
    except Exception:
        return False


def detect_proxies(host="127.0.0.1", ports=None, timeout=3.5, target_host="www.youtube.com"):
    """Probe common local proxy ports (both socks5 and http) in parallel.
    Returns list of working proxy URLs, socks5 first."""
    base = ports or COMMON_PROXY_PORTS
    tests = list(base)
    tests += [(p, "http" if t == "socks5" else "socks5") for p, t in base]  # try both types
    tests = list(dict.fromkeys(tests))  # dedupe, keep order

    def test(item):
        port, ptype = item
        ok = probe_proxy(host, port, ptype, timeout, target_host=target_host)
        return (f"{ptype}://{host}:{port}", ok)

    found = []
    try:
        with ThreadPoolExecutor(max_workers=12) as ex:
            for url, ok in ex.map(test, tests):
                if ok:
                    found.append(url)
    except Exception:
        pass
    found.sort(key=lambda u: 0 if u.startswith("socks5") else 1)
    return found
