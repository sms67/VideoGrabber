# -*- coding: utf-8 -*-
"""Dialogs shown after analyzing a link: quality picker, playlist picker,
censorship help and a network doctor that pinpoints where the connection dies."""
from html import escape

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPushButton,
                             QVBoxLayout)

from . import utils
from .i18n import tr

QUALITY_KEYS = ["best", "2160", "1440", "1080", "720", "480", "360", "mp3"]


class QualityDialog(QDialog):
    """Let the user pick a quality for a single video (per settings: ask every time)."""

    def __init__(self, info: dict, lang: str, url: str = "", parent=None):
        super().__init__(parent)
        self.lang = lang
        self.url = url
        self.setWindowTitle(tr(lang, "quality_title"))
        self.setMinimumWidth(430)

        lay = QVBoxLayout(self)
        title = info.get("title") or "?"
        lay.addWidget(QLabel(f"<h3>{escape(title)}</h3>"))
        sub_parts = []
        if info.get("uploader") or info.get("channel"):
            sub_parts.append(escape(info.get("uploader") or info.get("channel")))
        if info.get("duration"):
            sub_parts.append(f"{tr(lang, 'duration')}: {utils.human_duration(info['duration'])}")
        if sub_parts:
            lay.addWidget(QLabel(" — ".join(sub_parts)))

        opts = [{"key": "best", "label": tr(lang, "q_best"), "size": None}]
        opts += utils.available_qualities(info)
        opts.append({"key": "mp3", "label": tr(lang, "q_mp3"), "size": None})

        self.list = QListWidget(self)
        for o in opts:
            text = o["label"]
            if o.get("size"):
                text += f"   (~{utils.human_size(o['size'])})"
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, o["key"])
            self.list.addItem(it)
        self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        lay.addWidget(self.list)

        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(tr(lang, "add_to_queue"), self)
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        cancel = QPushButton(tr(lang, "cancel"), self)
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)

    def selected_key(self) -> str:
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else "best"


class PlaylistDialog(QDialog):
    """Show playlist entries with checkboxes; user picks videos + one quality for all."""

    def __init__(self, info: dict, lang: str, parent=None):
        super().__init__(parent)
        self.lang = lang
        self.entries = [e for e in (info.get("entries") or []) if e]
        self.results = []            # list of (url, title)
        self.results_quality = "best"
        self.setWindowTitle(tr(lang, "pl_title"))
        self.resize(520, 560)

        lay = QVBoxLayout(self)
        head = QLabel(f"<h3>{escape(info.get('title') or tr(lang, 'pl_title'))}</h3>"
                      f"<span>{tr(lang, 'pl_videos').format(n=len(self.entries))}</span>")
        lay.addWidget(head)
        lay.addWidget(QLabel(tr(lang, "pl_hint")))

        self.search = QLineEdit(self)
        self.search.setPlaceholderText(tr(lang, "pl_search"))
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)

        self.listw = QListWidget(self)
        for e in self.entries:
            t = e.get("title") or e.get("id") or "?"
            dur = utils.human_duration(e.get("duration"))
            text = f"{t}   [{dur}]" if dur != "—" else t
            it = QListWidgetItem(text)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)
            it.setData(Qt.ItemDataRole.UserRole, e)
            it.setToolTip(t)
            self.listw.addItem(it)
        self.listw.itemChanged.connect(lambda *_: self._update_count())
        lay.addWidget(self.listw)

        sel_row = QHBoxLayout()
        b_all = QPushButton(tr(lang, "pl_select_all"), self)
        b_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        b_none = QPushButton(tr(lang, "pl_deselect"), self)
        b_none.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        sel_row.addWidget(b_all)
        sel_row.addWidget(b_none)
        sel_row.addStretch(1)
        lay.addLayout(sel_row)

        q_row = QHBoxLayout()
        q_row.addWidget(QLabel(tr(lang, "pl_quality"), self))
        self.combo = QComboBox(self)
        for k in QUALITY_KEYS:
            self.combo.addItem(utils.quality_label(k, lang), k)
        self.combo.setCurrentIndex(0)
        q_row.addWidget(self.combo, 1)
        lay.addLayout(q_row)

        self.lbl_count = QLabel("", self)
        lay.addWidget(self.lbl_count)
        self._update_count()

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        ok = QPushButton(tr(lang, "add_to_queue"), self)
        ok.setObjectName("primary")
        ok.clicked.connect(self._on_add)
        cancel = QPushButton(tr(lang, "cancel"), self)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        lay.addLayout(btn_row)

    # ---------- helpers ----------
    def _filter(self, text: str):
        t = (text or "").lower()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            it.setHidden(t not in it.text().lower())

    def _set_all(self, state: Qt.CheckState):
        for i in range(self.listw.count()):
            self.listw.item(i).setCheckState(state)

    def _update_count(self):
        n = sum(1 for i in range(self.listw.count())
                if self.listw.item(i).checkState() == Qt.CheckState.Checked)
        self.lbl_count.setText(tr(self.lang, "pl_count").format(n=n))

    def _on_add(self):
        self.results_quality = self.combo.currentData() or "best"
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            if it.checkState() != Qt.CheckState.Checked:
                continue
            e = it.data(Qt.ItemDataRole.UserRole) or {}
            url = e.get("webpage_url") or e.get("url") or ""
            title = e.get("title") or url
            if url:
                self.results.append((url, title))
        self.accept()


class ProxyHelpDialog(QDialog):
    """Step-by-step guide for bypassing censorship (VPN/proxy apps + ports)."""

    def __init__(self, lang: str, parent=None):
        super().__init__(parent)
        self.lang = lang
        self.setWindowTitle(tr(lang, "proxy_help"))
        self.setMinimumSize(560, 420)

        lay = QVBoxLayout(self)
        body = QLabel(self)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setOpenExternalLinks(True)
        body.setWordWrap(True)
        body.setText(tr(lang, "help_html"))
        lay.addWidget(body, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(tr(lang, "ok"), self)
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        lay.addLayout(row)


# ============================ network doctor ============================

class DoctorWorker(QThread):
    """Runs 4 connectivity tests in order and reports each result.
    Emits raw data only — the dialog does the translation."""
    step = pyqtSignal(int, str, str)   # index, status(ok/fail/warn/skip), payload
    verdict = pyqtSignal(str, str)     # verdict key, working proxy (or "")

    def __init__(self, proxy: str = "", parent=None):
        super().__init__(parent)
        self.proxy, _ = utils.normalize_proxy(proxy)

    def run(self):
        direct_ok = False
        proxy_ok = False
        found = ""

        # 1) DNS
        ips = utils.resolve_dns("www.youtube.com")
        if not ips:
            self.step.emit(0, "fail", "")
        elif utils.dns_looks_poisoned(ips):
            self.step.emit(0, "warn", ips[0])
        else:
            self.step.emit(0, "ok", ",".join(ips[:3]))

        # 2) direct
        ok, detail = utils.net_check(proxy="", timeout=8)
        direct_ok = ok
        self.step.emit(1, "ok" if ok else "fail", detail)

        # 3) configured proxy
        if self.proxy:
            ok, detail = utils.net_check(proxy=self.proxy, timeout=10)
            proxy_ok = ok
            self.step.emit(2, "ok" if ok else "fail", detail)
            if proxy_ok:
                found = self.proxy
        else:
            self.step.emit(2, "skip", "")

        # 4) auto-detect ports (only when nothing works yet)
        if not found and not direct_ok:
            try:
                ps = utils.detect_proxies()
            except Exception:
                ps = []
            if ps:
                found = ps[0]
                self.step.emit(3, "ok", ps[0])
            else:
                self.step.emit(3, "fail", "")
        else:
            self.step.emit(3, "skip", "")

        if found:
            self.verdict.emit("doctor_verdict_proxy", found)
        elif direct_ok:
            self.verdict.emit("doctor_verdict_direct", "")
        else:
            self.verdict.emit("doctor_verdict_none", "")


class NetworkDoctorDialog(QDialog):
    """Step-by-step connectivity tests with a plain-language verdict."""

    STEP_KEYS = ("doctor_step_dns", "doctor_step_direct",
                 "doctor_step_proxy", "doctor_step_detect")

    def __init__(self, lang: str, proxy: str = "", parent=None):
        super().__init__(parent)
        self.lang = lang
        self.proxy_arg = proxy or ""
        self.chosen_proxy = ""
        self.setWindowTitle(tr(lang, "doctor_title"))
        self.setMinimumWidth(560)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        self.rows = []          # [(title_label, status_label, detail_label)]
        for key in self.STEP_KEYS:
            row = QHBoxLayout()
            t = QLabel(tr(lang, key), self)
            t.setMinimumWidth(230)
            s = QLabel(tr(lang, "doctor_none"), self)
            s.setMinimumWidth(80)
            row.addWidget(t)
            row.addWidget(s)
            row.addStretch(1)
            lay.addLayout(row)
            d = QLabel("", self)
            d.setWordWrap(True)
            d.setStyleSheet("color:#6b7280; padding: 0 12px; font-size: 11px;")
            lay.addWidget(d)
            self.rows.append((t, s, d))

        self.lbl_verdict = QLabel("", self)
        self.lbl_verdict.setWordWrap(True)
        self.lbl_verdict.setStyleSheet("background:#eef2f9; border:1px solid #d0d7e2;"
                                       "border-radius:6px; padding:10px;")
        lay.addWidget(self.lbl_verdict)

        btn_row = QHBoxLayout()
        self.btn_run = QPushButton(tr(lang, "doctor_run"), self)
        self.btn_run.setObjectName("primary")
        self.btn_run.clicked.connect(self._on_run)
        self.btn_apply = QPushButton(tr(lang, "doctor_apply"), self)
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._on_apply)
        close = QPushButton(tr(lang, "ok"), self)
        close.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_apply)
        btn_row.addStretch(1)
        btn_row.addWidget(close)
        lay.addLayout(btn_row)

    # ---------- slots ----------
    def _on_run(self):
        self.btn_run.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.lbl_verdict.setText("")
        for _t, s, d in self.rows:
            s.setText(tr(self.lang, "doctor_wait"))
            s.setStyleSheet("")
            d.setText("")
        self._worker = DoctorWorker(self._current_proxy())
        self._worker.step.connect(self._on_step)
        self._worker.verdict.connect(self._on_verdict)
        self._worker.start()

    def _current_proxy(self) -> str:
        return self.proxy_arg

    def _on_step(self, idx: int, status: str, payload: str):
        _t, s, d = self.rows[idx]
        key = {"ok": "doctor_ok", "fail": "doctor_fail", "warn": "doctor_warn"} \
            .get(status, "doctor_none")
        s.setText(tr(self.lang, key))
        color = {"ok": "#15803d", "fail": "#dc2626", "warn": "#b45309"}.get(status, "#6b7280")
        s.setStyleSheet(f"color:{color}; font-weight:600;")
        if idx == 0:
            if status == "warn":
                d.setText(tr(self.lang, "doctor_dns_poison").format(ip=payload))
            elif payload:
                d.setText(tr(self.lang, "doctor_dns_detail").format(ips=payload))
        else:
            d.setText((payload or "")[:220])

    def _on_verdict(self, key: str, proxy: str):
        self.btn_run.setEnabled(True)
        self.lbl_verdict.setText(tr(self.lang, key))
        if proxy:
            self.chosen_proxy = proxy
            self.btn_apply.setEnabled(True)

    def _on_apply(self):
        self.accept()
