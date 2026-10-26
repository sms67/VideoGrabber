# -*- coding: utf-8 -*-
"""Dialogs shown after analyzing a link: quality picker and playlist picker."""
from html import escape

from PyQt6.QtCore import Qt
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
