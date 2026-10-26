# -*- coding: utf-8 -*-
"""VideoGrabber entry point. Run: python main.py"""
import sys

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

APP_QSS = """
* { font-family: "Segoe UI", "Tahoma"; font-size: 10pt; }
QMainWindow, QDialog { background: #f4f6fb; }
QWidget { color: #1f2937; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #ffffff; border: 1px solid #d0d7e2; border-radius: 6px;
    padding: 6px 10px; min-height: 18px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #2f6fed; }
QComboBox::drop-down { border: none; width: 22px; }
QPushButton {
    background: #eef2f9; color: #1f2937; border: 1px solid #d0d7e2;
    border-radius: 6px; padding: 7px 16px;
}
QPushButton:hover { background: #e2e9f6; }
QPushButton:pressed { background: #d3ddf0; }
QPushButton:disabled { color: #9aa3af; background: #f1f3f7; }
QPushButton#primary { background: #2f6fed; color: #ffffff; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #245bd0; }
QPushButton#primary:pressed { background: #1d4fb8; }
QPushButton#danger { color: #c02626; }
QToolBar { background: #ffffff; border-bottom: 1px solid #e3e8f0; padding: 4px; spacing: 6px; }
QToolButton { padding: 6px 14px; border-radius: 6px; }
QToolButton:hover { background: #eef2f9; }
QTableWidget {
    background: #ffffff; border: 1px solid #e3e8f0; border-radius: 8px;
    gridline-color: #eef1f6; selection-background-color: #dbe7ff;
    selection-color: #111827; alternate-background-color: #fafbfe;
}
QHeaderView::section {
    background: #f1f4f9; border: none; padding: 8px 6px; font-weight: 600;
}
QProgressBar {
    border: 1px solid #d0d7e2; border-radius: 6px; background: #ffffff;
    text-align: center; min-height: 14px; max-height: 18px;
}
QProgressBar::chunk { background: #2f6fed; border-radius: 5px; }
QTabWidget::pane { border: 1px solid #e3e8f0; border-radius: 8px; background: #ffffff; }
QTabBar::tab { padding: 8px 20px; background: transparent; }
QTabBar::tab:selected { color: #2f6fed; border-bottom: 2px solid #2f6fed; }
QStatusBar { background: #f4f6fb; color: #4b5563; }
QListWidget { background: #ffffff; border: 1px solid #d0d7e2; border-radius: 6px; padding: 4px; }
QListWidget::item { padding: 6px 4px; border-radius: 4px; }
QListWidget::item:selected { background: #dbe7ff; color: #111827; }
QMessageBox { background: #ffffff; }
QLabel { background: transparent; }
"""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("VideoGrabber")
    app.setOrganizationName("VideoGrabber")
    app.setStyle("Fusion")
    f = QFont("Segoe UI", 10)
    app.setFont(f)
    app.setStyleSheet(APP_QSS)

    from app.main_window import MainWindow
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
