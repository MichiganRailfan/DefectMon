
import sys
import json
import os

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QFileDialog, QFrame, QMessageBox,
    QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class MonitorWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Audio Processing Monitor")
        self.resize(1100, 700)

        self.json_path = "rail_telemetry.json"
        self.records = []

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #111827;
                color: #e5e7eb;
                font-family: Segoe UI, sans-serif;
            }

            QFrame#header {
                background-color: #202936;
                border-radius: 8px;
            }

            QFrame#panel {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 8px;
            }

            QLabel#title {
                font-size: 22px;
                font-weight: bold;
                color: white;
            }

            QLabel#subtitle {
                color: #9ca3af;
                font-size: 11px;
            }

            QLabel#metric {
                font-size: 28px;
                font-weight: bold;
                color: #60a5fa;
            }

            QPushButton {
                background-color: #334155;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 16px;
            }

            QPushButton:hover {
                background-color: #475569;
            }

            QTableWidget {
                background-color: #1f2937;
                alternate-background-color: #263449;
                gridline-color: #374151;
                border: none;
                selection-background-color: #2563eb;
                selection-color: white;
            }

            QHeaderView::section {
                background-color: #263449;
                color: #cbd5e1;
                padding: 9px;
                border: none;
                font-weight: bold;
            }

            QTableWidget::item {
                padding: 7px;
            }
        """)

        self.build_ui()
        self.load_json()

    def build_ui(self):

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # HEADER
        header = QFrame()
        header.setObjectName("header")

        header_layout = QHBoxLayout(header)

        title_layout = QVBoxLayout()

        title = QLabel("Audio Processing Monitor")
        title.setObjectName("title")

        subtitle = QLabel("LOCAL RECORD PROCESSING DASHBOARD")
        subtitle.setObjectName("subtitle")

        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        self.status_label = QLabel("JSON: Not loaded")
        self.status_label.setStyleSheet("color: #60a5fa;")

        header_layout.addWidget(self.status_label)

        layout.addWidget(header)

        # METRICS
        metrics = QHBoxLayout()

        self.record_count = self.create_metric(
            metrics, "RECORDS LOADED", "0"
        )

        self.file_count = self.create_metric(
            metrics, "SOURCE FILES", "0"
        )

        layout.addLayout(metrics)

        # HISTORY PANEL
        history_panel = QFrame()
        history_panel.setObjectName("panel")

        history_layout = QVBoxLayout(history_panel)

        history_title = QLabel("Processing History")
        history_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))

        history_layout.addWidget(history_title)

        self.table = QTableWidget()
        self.table.setColumnCount(3)

        self.table.setHorizontalHeaderLabels([
            "Timestamp",
            "Audio File",
            "Processing Status"
        ])

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )

        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )

        self.table.setAlternatingRowColors(True)

        self.table.itemSelectionChanged.connect(
            self.show_selected_record
        )

        history_layout.addWidget(self.table)

        layout.addWidget(history_panel, 1)

        # SELECTED RECORD
        details_panel = QFrame()
        details_panel.setObjectName("panel")

        details_layout = QVBoxLayout(details_panel)

        details_title = QLabel("Selected Record")
        details_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))

        self.details = QLabel(
            "Select a record from the history above."
        )

        self.details.setStyleSheet(
            "color: #9ca3af; padding: 5px;"
        )

        details_layout.addWidget(details_title)
        details_layout.addWidget(self.details)

        layout.addWidget(details_panel)

        # BUTTONS
        buttons = QHBoxLayout()

        load_button = QPushButton("Load JSON")
        load_button.clicked.connect(self.choose_json)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.load_json)

        buttons.addWidget(load_button)
        buttons.addWidget(refresh_button)
        buttons.addStretch()

        layout.addLayout(buttons)

    def create_metric(self, layout, name, value):

        panel = QFrame()
        panel.setObjectName("panel")

        panel_layout = QVBoxLayout(panel)

        label = QLabel(name)
        label.setStyleSheet("color: #9ca3af;")

        number = QLabel(value)
        number.setObjectName("metric")

        panel_layout.addWidget(label)
        panel_layout.addWidget(number)

        layout.addWidget(panel)

        return number

    def choose_json(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select processing log",
            "",
            "JSON Files (*.json)"
        )

        if path:
            self.json_path = path
            self.load_json()

    def load_json(self):

        if not os.path.exists(self.json_path):
            self.status_label.setText("JSON: File not found")
            return

        try:
            with open(self.json_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, list):
                raise ValueError("Expected a JSON array.")

            self.records = data
            self.populate_table()

            self.status_label.setText(
                "JSON: " + os.path.basename(self.json_path)
            )

        except (OSError, json.JSONDecodeError, ValueError) as error:

            QMessageBox.warning(
                self,
                "JSON Error",
                str(error)
            )

    def populate_table(self):

        self.table.setRowCount(0)

        source_files = set()

        for index, record in enumerate(self.records):

            if not isinstance(record, dict):
                continue

            timestamp = record.get("timestamp") or "Unknown"
            filename = record.get("file_name") or "Unknown"

            if filename != "Unknown":
                source_files.add(filename)

            row = self.table.rowCount()
            self.table.insertRow(row)

            values = [
                str(timestamp),
                str(filename),
                "Record loaded"
            ]

            for column, value in enumerate(values):

                item = QTableWidgetItem(value)

                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter |
                    Qt.AlignmentFlag.AlignLeft
                )

                self.table.setItem(row, column, item)

            self.table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, index
            )

        self.record_count.setText(str(self.table.rowCount()))
        self.file_count.setText(str(len(source_files)))

    def show_selected_record(self):

        row = self.table.currentRow()

        if row < 0:
            return

        item = self.table.item(row, 0)

        if item is None:
            return

        index = item.data(Qt.ItemDataRole.UserRole)
        record = self.records[index]

        timestamp = record.get("timestamp", "Unknown")
        filename = record.get("file_name", "Unknown")

        self.details.setText(
            f"Timestamp: {timestamp}\n"
            f"Source file: {filename}\n"
            f"Status: Record successfully loaded."
        )


if __name__ == "__main__":

    app = QApplication(sys.argv)

    window = MonitorWindow()
    window.show()

    sys.exit(app.exec())
