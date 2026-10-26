# -*- coding: utf-8 -*-
"""Main window: URL bar, download queue table, settings tab, fa/en switching."""
import os

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QBrush, QColor, QDesktopServices, QIcon, QAction
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel,
                             QLineEdit, QMainWindow, QMessageBox, QProgressBar,
                             QPushButton, QSpinBox, QStatusBar, QStyle,
                             QTabWidget, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget, QHeaderView, QFormLayout)

from . import settings as cfgmod
from . import utils
from .dialogs import PlaylistDialog, QualityDialog
from .i18n import tr
from .worker import AnalyzeWorker, DownloadWorker

COL_NUM, COL_TITLE, COL_QUALITY, COL_SIZE, COL_PROGRESS, COL_SPEED, COL_ETA, COL_STATUS = range(8)

STATUS_KEY = {
    "waiting": "st_waiting", "starting": "st_starting", "downloading": "st_downloading",
    "postprocess": "st_postprocess", "done": "st_done", "error": "st_error",
    "canceled": "st_canceled",
}
STATUS_COLOR = {
    "waiting": "#374151", "starting": "#374151", "downloading": "#2f6fed",
    "postprocess": "#b45309", "done": "#15803d", "error": "#dc2626",
    "canceled": "#6b7280",
}
ACTIVE_STATES = ("starting", "downloading", "postprocess")
FINISHED_STATES = ("done", "error", "canceled")


class Job:
    _next = 1

    def __init__(self, url, title, quality):
        self.jid = Job._next
        Job._next += 1
        self.url = url
        self.title = title
        self.quality = quality if quality not in (None, "") else "best"
        self.row = -1
        self.worker = None
        self.status = "waiting"
        self.path = None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = cfgmod.load()
        self._jobs = []
        self._workers = []
        self._an = None
        self._last_url = ""
        self._closing = False
        self.lbl_ff = None

        self._build_ui()
        self.apply_lang(self.cfg["lang"])
        self._check_ffmpeg()
        self._prefill_from_clipboard()

    # ================= UI construction =================
    def _build_ui(self):
        self.resize(940, 600)

        tb = self.menuBar()  # keep simple: no menu
        del tb
        toolbar = self.addToolBar("main")
        toolbar.setMovable(False)
        self.act_lang = QAction("", self)
        self.act_lang.triggered.connect(self._toggle_lang)
        toolbar.addAction(self.act_lang)
        self.act_open = QAction("", self)
        self.act_open.triggered.connect(self._open_folder)
        toolbar.addAction(self.act_open)

        style = self.style()
        self.act_open.setIconText("")
        self.act_open.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.addTab(self._build_downloads_tab(), "")
        self.tabs.addTab(self._build_settings_tab(), "")

        st = QStatusBar()
        self.setStatusBar(st)

    def _build_downloads_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        lay.setContentsMargins(12, 12, 12, 12)

        # URL row
        url_row = QHBoxLayout()
        self.ed_url = QLineEdit()
        self.ed_url.returnPressed.connect(self._on_analyze)
        self.btn_paste = QPushButton()
        self.btn_paste.clicked.connect(self._paste_clipboard)
        self.btn_analyze = QPushButton()
        self.btn_analyze.setObjectName("primary")
        self.btn_analyze.clicked.connect(self._on_analyze)
        url_row.addWidget(self.ed_url, 1)
        url_row.addWidget(self.btn_paste)
        url_row.addWidget(self.btn_analyze)
        lay.addLayout(url_row)

        # queue table
        self.table = QTableWidget(0, 8)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_TITLE, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(COL_PROGRESS, QHeaderView.ResizeMode.Stretch)
        for c in (COL_NUM, COL_QUALITY, COL_SIZE, COL_SPEED, COL_ETA, COL_STATUS):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hh.setHighlightSections(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        lay.addWidget(self.table, 1)

        # bottom buttons
        btn_row = QHBoxLayout()
        self.btn_cancel = QPushButton()
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self._cancel_selected)
        self.btn_retry = QPushButton()
        self.btn_retry.clicked.connect(self._retry_selected)
        self.btn_clear_done = QPushButton()
        self.btn_clear_done.clicked.connect(self._clear_finished)
        self.btn_clear_all = QPushButton()
        self.btn_clear_all.clicked.connect(self._clear_all)
        for b in (self.btn_cancel, self.btn_retry, self.btn_clear_done, self.btn_clear_all):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        self.btn_folder = QPushButton()
        self.btn_folder.setObjectName("primary")
        self.btn_folder.clicked.connect(self._open_folder)
        btn_row.addWidget(self.btn_folder)
        lay.addLayout(btn_row)
        return w

    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        form = QFormLayout()
        form.setSpacing(12)
        self._set_labels = {}

        # download dir
        self.ed_dir = QLineEdit()
        b = QPushButton()
        b.clicked.connect(self._browse_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.ed_dir, 1)
        dir_row.addWidget(b)
        dir_w = QWidget()
        dir_w.setLayout(dir_row)
        self._lbl_dir = QLabel()
        self._set_labels["set_dir"] = self._lbl_dir
        form.addRow(self._lbl_dir, dir_w)
        self._btn_browse = b

        # parallel
        self.spin_parallel = QSpinBox()
        self.spin_parallel.setRange(1, 5)
        self._lbl_par = QLabel()
        self._set_labels["set_parallel"] = self._lbl_par
        form.addRow(self._lbl_par, self.spin_parallel)

        # cookies
        self.cmb_cookies = QComboBox()
        self._cookie_values = ["", "chrome", "firefox", "edge", "brave", "opera", "safari", "vivaldi"]
        for v in self._cookie_values:
            self.cmb_cookies.addItem(v.capitalize() if v else "", v)
        self._lbl_cookie = QLabel()
        self._set_labels["set_cookies"] = self._lbl_cookie
        form.addRow(self._lbl_cookie, self.cmb_cookies)

        # playlist default quality
        self.cmb_plq = QComboBox()
        for k in ("best", "2160", "1440", "1080", "720", "480", "360", "mp3"):
            self.cmb_plq.addItem("", k)
        self._lbl_plq = QLabel()
        self._set_labels["set_quality_default"] = self._lbl_plq
        form.addRow(self._lbl_plq, self.cmb_plq)

        # language
        self.cmb_lang = QComboBox()
        self.cmb_lang.addItem("فارسی", "fa")
        self.cmb_lang.addItem("English", "en")
        self._lbl_lang = QLabel()
        self._set_labels["set_lang"] = self._lbl_lang
        form.addRow(self._lbl_lang, self.cmb_lang)

        lay.addLayout(form)
        lay.addStretch(1)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self.btn_save = QPushButton()
        self.btn_save.setObjectName("primary")
        self.btn_save.clicked.connect(self._save_settings)
        save_row.addWidget(self.btn_save)
        lay.addLayout(save_row)
        return w

    # ================= language =================
    def apply_lang(self, lang: str):
        self.cfg["lang"] = lang
        l = lang
        self.setWindowTitle(tr(l, "app_title"))
        self.act_lang.setText(tr(l, "switch_lang"))
        self.act_lang.setToolTip(tr(l, "switch_lang_tip"))
        self.act_open.setToolTip(tr(l, "open_folder"))
        self.tabs.setTabText(0, tr(l, "tab_downloads"))
        self.tabs.setTabText(1, tr(l, "tab_settings"))
        self.ed_url.setPlaceholderText(tr(l, "url_ph"))
        self.btn_paste.setText(tr(l, "paste"))
        self.btn_analyze.setText(tr(l, "analyze"))
        self.table.setHorizontalHeaderLabels([
            tr(l, "col_row"), tr(l, "col_title"), tr(l, "col_quality"), tr(l, "col_size"),
            tr(l, "col_progress"), tr(l, "col_speed"), tr(l, "col_eta"), tr(l, "col_status"),
        ])
        self.btn_cancel.setText(tr(l, "cancel_selected"))
        self.btn_retry.setText(tr(l, "retry_selected"))
        self.btn_clear_done.setText(tr(l, "clear_finished"))
        self.btn_clear_all.setText(tr(l, "clear_all"))
        self.btn_folder.setText(tr(l, "open_folder"))

        self._lbl_dir.setText(tr(l, "set_dir"))
        self._btn_browse.setText(tr(l, "set_browse"))
        self._lbl_par.setText(tr(l, "set_parallel"))
        self._lbl_cookie.setText(tr(l, "set_cookies"))
        self._lbl_plq.setText(tr(l, "set_quality_default"))
        self._lbl_lang.setText(tr(l, "set_lang"))
        self.btn_save.setText(tr(l, "set_save"))
        for i in range(self.cmb_cookies.count()):
            v = self.cmb_cookies.itemData(i)
            self.cmb_cookies.setItemText(i, v.capitalize() if v else tr(l, "cookies_none"))
        for i in range(self.cmb_plq.count()):
            k = self.cmb_plq.itemData(i)
            self.cmb_plq.setItemText(i, utils.quality_label(k, l))

        # refresh quality labels + statuses in table
        for job in self._jobs:
            qi = self.table.item(job.row, COL_QUALITY)
            if qi:
                qi.setText(utils.quality_label(job.quality, l))
            si = self.table.item(job.row, COL_STATUS)
            if si:
                si.setText(tr(l, STATUS_KEY.get(job.status, "st_waiting")))

        if self.lbl_ff:
            self.lbl_ff.setText(tr(l, "err_ffmpeg_short"))

        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft if l == "fa"
                                else Qt.LayoutDirection.LeftToRight)

    def _toggle_lang(self):
        new_lang = "en" if self.cfg["lang"] == "fa" else "fa"
        self.apply_lang(new_lang)
        self.cmb_lang.setCurrentIndex(0 if new_lang == "fa" else 1)
        cfgmod.save(self.cfg)
        self.statusBar().showMessage(tr(new_lang, "status_ready"))

    # ================= settings =================
    def _sync_settings_widgets(self):
        l = self.cfg["lang"]
        self.ed_dir.setText(self.cfg["download_dir"])
        self.spin_parallel.setValue(int(self.cfg.get("max_parallel", 2)))
        i = self._cookie_values.index(self.cfg.get("cookies_browser", "")) \
            if self.cfg.get("cookies_browser", "") in self._cookie_values else 0
        self.cmb_cookies.setCurrentIndex(i)
        for k in range(self.cmb_plq.count()):
            if self.cmb_plq.itemData(k) == self.cfg.get("playlist_quality", "best"):
                self.cmb_plq.setCurrentIndex(k)
                break
        self.cmb_lang.setCurrentIndex(0 if l == "fa" else 1)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, tr(self.cfg["lang"], "set_dir"),
                                             self.ed_dir.text() or "")
        if d:
            self.ed_dir.setText(d)

    def _save_settings(self):
        l = self.cfg["lang"]
        old_lang = l
        self.cfg["download_dir"] = self.ed_dir.text().strip() or self.cfg["download_dir"]
        self.cfg["max_parallel"] = self.spin_parallel.value()
        self.cfg["cookies_browser"] = self.cmb_cookies.currentData() or ""
        self.cfg["playlist_quality"] = self.cmb_plq.currentData() or "best"
        new_lang = self.cmb_lang.currentData() or "fa"
        self.cfg["lang"] = new_lang
        cfgmod.save(self.cfg)
        if new_lang != old_lang:
            self.apply_lang(new_lang)
        self.statusBar().showMessage(tr(self.cfg["lang"], "set_saved"), 4000)

    # ================= analyze flow =================
    def _prefill_from_clipboard(self):
        try:
            from PyQt6.QtWidgets import QApplication
            cb = QApplication.clipboard().text().strip()
            if cb.lower().startswith(("http://", "https://")):
                self.ed_url.setText(cb)
                self.statusBar().showMessage(tr(self.cfg["lang"], "copied_clip"), 8000)
        except Exception:
            pass

    def _paste_clipboard(self):
        from PyQt6.QtWidgets import QApplication
        cb = QApplication.clipboard().text().strip()
        if cb:
            self.ed_url.setText(cb)

    def _on_analyze(self):
        l = self.cfg["lang"]
        url = self.ed_url.text().strip()
        if not url:
            QMessageBox.warning(self, tr(l, "err"), tr(l, "err_no_url"))
            return
        self._last_url = url
        self.btn_analyze.setEnabled(False)
        self.statusBar().showMessage(tr(l, "analyzing"))
        self._an = AnalyzeWorker(url, self.cfg.get("cookies_browser", ""))
        self._an.done.connect(self._on_analyzed)
        self._an.failed.connect(self._on_analyze_failed)
        self._an.start()

    def _on_analyze_failed(self, msg: str):
        l = self.cfg["lang"]
        self.btn_analyze.setEnabled(True)
        self.statusBar().showMessage(tr(l, "status_ready"))
        QMessageBox.critical(self, tr(l, "err"),
                             tr(l, "err_analyze") + "\n\n" + (msg or "")[:600])

    def _on_analyzed(self, info: dict):
        l = self.cfg["lang"]
        self.btn_analyze.setEnabled(True)
        self.statusBar().showMessage(tr(l, "status_ready"))
        if not info:
            return
        if info.get("_type") == "playlist" and info.get("entries"):
            dlg = PlaylistDialog(info, l, self)
            if dlg.exec() and dlg.results:
                q = dlg.results_quality
                for u, t in dlg.results:
                    self._add_job(u, t, q)
                self.statusBar().showMessage(tr(l, "items_added").format(n=len(dlg.results)), 6000)
        else:
            dlg = QualityDialog(info, l, self._last_url)
            if dlg.exec():
                u = info.get("webpage_url") or info.get("original_url") or self._last_url
                self._add_job(u, info.get("title") or u, dlg.selected_key())

    # ================= queue management =================
    def _row_of(self, job: Job) -> int:
        if 0 <= job.row < len(self._jobs) and self._jobs[job.row] is job:
            return job.row
        try:
            r = self._jobs.index(job)
        except ValueError:
            return -1
        job.row = r
        return r

    def _add_job(self, url, title, quality) -> Job:
        l = self.cfg["lang"]
        job = Job(url, title, quality)
        r = self.table.rowCount()
        self.table.insertRow(r)
        job.row = r

        num = QTableWidgetItem(str(job.jid))
        num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        tit = QTableWidgetItem(title or url)
        tit.setToolTip(url)
        qit = QTableWidgetItem(utils.quality_label(job.quality, l))
        sz = QTableWidgetItem(tr(l, "unknown_size"))
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setFormat("%p%")
        sp = QTableWidgetItem("—")
        et = QTableWidgetItem("—")
        st = QTableWidgetItem(tr(l, "st_waiting"))
        self._color_item(st, "waiting")

        self.table.setItem(r, COL_NUM, num)
        self.table.setItem(r, COL_TITLE, tit)
        self.table.setItem(r, COL_QUALITY, qit)
        self.table.setItem(r, COL_SIZE, sz)
        self.table.setCellWidget(r, COL_PROGRESS, bar)
        self.table.setItem(r, COL_SPEED, sp)
        self.table.setItem(r, COL_ETA, et)
        self.table.setItem(r, COL_STATUS, st)

        self._jobs.append(job)
        self._pump()
        return job

    def _color_item(self, item: QTableWidgetItem, status: str):
        item.setForeground(QBrush(QColor(STATUS_COLOR.get(status, "#111827"))))

    def _set_status(self, job: Job, status: str):
        job.status = status
        r = self._row_of(job)
        if r < 0:
            return
        it = self.table.item(r, COL_STATUS)
        if it:
            it.setText(tr(self.cfg["lang"], STATUS_KEY.get(status, status)))
            self._color_item(it, status)

    def _pump(self):
        if self._closing:
            return
        active = sum(1 for j in self._jobs
                     if j.worker and j.worker.isRunning() and j.status in ACTIVE_STATES)
        slots = int(self.cfg.get("max_parallel", 2)) - active
        for j in list(self._jobs):
            if slots <= 0:
                break
            if j.status == "waiting":
                self._start(j)
                slots -= 1

    def _start(self, job: Job):
        self._set_status(job, "starting")
        w = DownloadWorker(job.url, job.quality, self.cfg["download_dir"],
                           self.cfg.get("cookies_browser", ""))
        job.worker = w
        w.progress.connect(lambda d, jb=job: self._on_progress(jb, d))
        w.ok.connect(lambda p, jb=job: self._on_ok(jb, p))
        w.failed.connect(lambda m, jb=job: self._on_failed(jb, m))
        w.canceled.connect(lambda jb=job: self._on_canceled(jb))
        w.finished.connect(lambda jb=job: self._worker_finished(jb))
        self._workers.append(w)
        w.start()

    def _worker_finished(self, job: Job):
        if job.worker in self._workers:
            self._workers.remove(job.worker)
        self._pump()

    def _on_progress(self, job: Job, d: dict):
        r = self._row_of(job)
        if r < 0 or job.status in ("done", "error", "canceled"):
            return
        status = d.get("status")
        bar = self.table.cellWidget(r, COL_PROGRESS)
        if status == "downloading":
            self._set_status(job, "downloading")
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            sz_item = self.table.item(r, COL_SIZE)
            if total:
                if bar:
                    bar.setRange(0, 100)
                    bar.setValue(int(done * 100 / total) if total else 0)
                if sz_item:
                    sz_item.setText(f"{utils.human_size(done)} / {utils.human_size(total)}")
            else:
                if bar:
                    bar.setRange(0, 0)  # busy
                if sz_item:
                    sz_item.setText(utils.human_size(done))
            sp_item = self.table.item(r, COL_SPEED)
            if sp_item:
                sp_item.setText(utils.human_speed(d.get("speed")))
            et_item = self.table.item(r, COL_ETA)
            if et_item:
                et_item.setText(utils.human_eta(d.get("eta")))
        elif status in ("finished", "postprocessing"):
            self._set_status(job, "postprocess")
            if bar:
                bar.setRange(0, 0)

    def _on_ok(self, job: Job, path: str):
        r = self._row_of(job)
        job.path = path
        self._set_status(job, "done")
        if r >= 0:
            bar = self.table.cellWidget(r, COL_PROGRESS)
            if bar:
                bar.setRange(0, 100)
                bar.setValue(100)
            sz_item = self.table.item(r, COL_SIZE)
            try:
                sz_item.setText(utils.human_size(os.path.getsize(path)))
            except Exception:
                pass
            sp = self.table.item(r, COL_SPEED)
            et = self.table.item(r, COL_ETA)
            if sp:
                sp.setText("—")
            if et:
                et.setText("—")
            st = self.table.item(r, COL_STATUS)
            if st:
                st.setToolTip(path)

    def _on_failed(self, job: Job, msg: str):
        self._set_status(job, "error")
        r = self._row_of(job)
        if r >= 0:
            st = self.table.item(r, COL_STATUS)
            if st:
                st.setToolTip(msg[:600])
                st.setText(tr(self.cfg["lang"], "st_error") + " !")

    def _on_canceled(self, job: Job):
        self._set_status(job, "canceled")
        r = self._row_of(job)
        if r >= 0:
            bar = self.table.cellWidget(r, COL_PROGRESS)
            if bar:
                bar.setRange(0, 100)
                bar.setValue(0)

    # ================= row actions =================
    def _selected_jobs(self) -> list:
        rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})
        return [self._jobs[r] for r in rows if 0 <= r < len(self._jobs)]

    def _cancel_selected(self):
        l = self.cfg["lang"]
        jobs = self._selected_jobs()
        if not jobs:
            QMessageBox.information(self, tr(l, "err"), tr(l, "err_no_selection"))
            return
        for job in jobs:
            if job.status in ("done", "error", "canceled"):
                continue
            if job.worker and job.worker.isRunning():
                job.worker.cancel()
            self._set_status(job, "canceled")
            r = self._row_of(job)
            if r >= 0:
                bar = self.table.cellWidget(r, COL_PROGRESS)
                if bar:
                    bar.setRange(0, 100)
                    bar.setValue(0)

    def _retry_selected(self):
        l = self.cfg["lang"]
        jobs = self._selected_jobs()
        if not jobs:
            QMessageBox.information(self, tr(l, "err"), tr(l, "err_no_selection"))
            return
        for job in jobs:
            if job.status not in FINISHED_STATES:
                continue
            r = self._row_of(job)
            if r >= 0:
                bar = self.table.cellWidget(r, COL_PROGRESS)
                if bar:
                    bar.setRange(0, 100)
                    bar.setValue(0)
                for col in (COL_SIZE, COL_SPEED, COL_ETA, COL_STATUS):
                    it = self.table.item(r, col)
                    if it:
                        it.setToolTip("")
                        it.setText(tr(l, "unknown_size") if col == COL_SIZE else
                                   "—" if col in (COL_SPEED, COL_ETA) else "")
            self._set_status(job, "waiting")
        self._pump()

    def _remove_rows(self, jobs: list):
        for job in sorted(jobs, key=lambda j: j.row, reverse=True):
            r = self._row_of(job)
            if r >= 0:
                self.table.removeRow(r)
                if job in self._jobs:
                    self._jobs.remove(job)
        for i, job in enumerate(self._jobs):
            job.row = i

    def _clear_finished(self):
        done = [j for j in self._jobs
                if j.status in FINISHED_STATES and not (j.worker and j.worker.isRunning())]
        self._remove_rows(done)

    def _clear_all(self):
        l = self.cfg["lang"]
        if not self._jobs:
            return
        if QMessageBox.question(self, tr(l, "confirm"), tr(l, "confirm_clear_all"),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                ) != QMessageBox.StandardButton.Yes:
            return
        for j in self._jobs:
            if j.worker and j.worker.isRunning():
                j.worker.cancel()
        self._remove_rows(list(self._jobs))

    def _open_folder(self):
        d = self.cfg["download_dir"]
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    # ================= misc =================
    def _check_ffmpeg(self):
        if not utils.find_ffmpeg():
            l = self.cfg["lang"]
            self.lbl_ff = QLabel(tr(l, "err_ffmpeg_short"))
            self.lbl_ff.setStyleSheet("color:#b45309; padding: 0 8px;")
            self.statusBar().addPermanentWidget(self.lbl_ff)
            QMessageBox.warning(self, tr(l, "warn"), tr(l, "err_ffmpeg"))

    def closeEvent(self, event):
        l = self.cfg["lang"]
        active = [j for j in self._jobs if j.worker and j.worker.isRunning()
                  and j.status not in FINISHED_STATES]
        if active:
            ans = QMessageBox.question(
                self, tr(l, "confirm"), tr(l, "ask_close"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ans != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._closing = True
        for j in self._jobs:
            if j.worker and j.worker.isRunning():
                j.worker.cancel()
        for w in list(self._workers):
            w.wait(3000)
        event.accept()
