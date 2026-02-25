# app/ui/main_window.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QLabel, QGroupBox
)

from app.core.scenarios import SCENARIOS
from app.core.fuels import FUELS  # у тебя в fuels.py словарь FUELS


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Диплом ТЭК — ввод сценария / топлива / труб")

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # ---------- Блок выбора сценария и топлива ----------
        gb = QGroupBox("1) Сценарий и топливо")
        form = QFormLayout(gb)

        self.cb_scenario = QComboBox()
        self._scenario_ids = list(SCENARIOS.keys())
        for sid in self._scenario_ids:
            self.cb_scenario.addItem(SCENARIOS[sid].title, userData=sid)

        self.cb_fuel = QComboBox()

        form.addRow("Сценарий (ПОУО):", self.cb_scenario)
        form.addRow("Топливо:", self.cb_fuel)

        # пояснение по indoor/outdoor
        self.lbl_space = QLabel("")
        self.lbl_space.setStyleSheet("color: #999;")
        form.addRow("Тип пространства:", self.lbl_space)

        layout.addWidget(gb)

        # ---------- Таблица труб ----------
        gb2 = QGroupBox("2) Трубопроводы (длина и диаметр)")
        v2 = QVBoxLayout(gb2)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Длина L, м", "Диаметр D, мм"])
        self.table.horizontalHeader().setStretchLastSection(True)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Добавить трубу")
        self.btn_del = QPushButton("Удалить выбранную")
        self.btn_demo = QPushButton("Заполнить пример")
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_del)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_demo)

        v2.addLayout(btn_row)
        v2.addWidget(self.table)
        layout.addWidget(gb2)

        # ---------- Нижние кнопки ----------
        bottom = QHBoxLayout()
        self.btn_validate = QPushButton("Проверить данные")
        self.btn_get_json = QPushButton("Показать данные (JSON)")
        bottom.addWidget(self.btn_validate)
        bottom.addWidget(self.btn_get_json)
        bottom.addStretch(1)
        layout.addLayout(bottom)

        # События
        self.cb_scenario.currentIndexChanged.connect(self._on_scenario_changed)
        self.btn_add.clicked.connect(self.add_pipe_row)
        self.btn_del.clicked.connect(self.delete_selected_row)
        self.btn_demo.clicked.connect(self.fill_demo)
        self.btn_validate.clicked.connect(self.validate)
        self.btn_get_json.clicked.connect(self.show_json)

        # инициализация
        self._on_scenario_changed()

    # ---------- Сценарий -> список топлив ----------
    def _on_scenario_changed(self):
        sid = self.cb_scenario.currentData()
        sc = SCENARIOS[sid]

        self.lbl_space.setText("Помещение" if sc.space == "indoor" else "Открытая площадка")

        self.cb_fuel.clear()
        for fuel_id in sc.allowed_fuels:
            fuel = FUELS.get(fuel_id)
            title = fuel.title if fuel else fuel_id
            self.cb_fuel.addItem(title, userData=fuel_id)

    # ---------- Таблица труб ----------
    def add_pipe_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(""))
        self.table.setItem(r, 1, QTableWidgetItem(""))

    def delete_selected_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def fill_demo(self):
        self.table.setRowCount(0)
        demo = [
            (12.0, 57),
            (8.0, 32),
            (4.5, 25),
        ]
        for L, D in demo:
            self.add_pipe_row()
            r = self.table.rowCount() - 1
            self.table.item(r, 0).setText(str(L))
            self.table.item(r, 1).setText(str(D))

    # ---------- Сбор данных ----------
    def collect_data(self) -> dict:
        sid = self.cb_scenario.currentData()
        fuel_id = self.cb_fuel.currentData()

        pipes = []
        for r in range(self.table.rowCount()):
            L_item = self.table.item(r, 0)
            D_item = self.table.item(r, 1)
            L_txt = (L_item.text() if L_item else "").strip().replace(",", ".")
            D_txt = (D_item.text() if D_item else "").strip().replace(",", ".")
            pipes.append({"length_m": L_txt, "diam_mm": D_txt})

        return {
            "scenario_id": sid,
            "scenario_title": SCENARIOS[sid].title,
            "space": SCENARIOS[sid].space,
            "fuel_id": fuel_id,
            "fuel_title": FUELS[fuel_id].title if fuel_id in FUELS else fuel_id,
            "pipes": pipes,
        }

    # ---------- Валидация ----------
    def validate(self):
        data = self.collect_data()
        errors = []

        if not data["fuel_id"]:
            errors.append("Не выбрано топливо.")

        # трубы
        if len(data["pipes"]) == 0:
            errors.append("Добавь хотя бы одну трубу.")

        for i, p in enumerate(data["pipes"], start=1):
            try:
                L = float(p["length_m"])
                if L <= 0:
                    errors.append(f"Труба {i}: длина должна быть > 0")
            except Exception:
                errors.append(f"Труба {i}: некорректная длина '{p['length_m']}'")

            try:
                D = float(p["diam_mm"])
                if D <= 0:
                    errors.append(f"Труба {i}: диаметр должен быть > 0")
            except Exception:
                errors.append(f"Труба {i}: некорректный диаметр '{p['diam_mm']}'")

        if errors:
            QMessageBox.critical(self, "Ошибки", "\n".join(errors))
        else:
            QMessageBox.information(self, "Ок", "Данные корректны ✅")

    def show_json(self):
        import json
        data = self.collect_data()
        QMessageBox.information(self, "JSON", json.dumps(data, ensure_ascii=False, indent=2))
