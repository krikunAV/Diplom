# app/ui_tk/main_window_tk.py
from __future__ import annotations
from pathlib import Path
from app.core.engine import compute_project, EngineConfig
import json
import tkinter as tk
from tkinter import ttk, messagebox

from app.core.scenarios import SCENARIOS
from app.core.fuels import FUELS, get_fuel
from app.ui_tk.debug_output import build_calculation_debug_output
from app.core.calcs.tvs.probit_zones import ZONE_ABSENT


def _fmt_zone_radius(val) -> str:
    """Форматирует радиус зоны для краткого вывода."""
    if val is None:
        return "> 200 м"
    if val == ZONE_ABSENT:
        return "не реализуется"
    try:
        return f"{round(float(val), 1)} м"
    except (TypeError, ValueError):
        return str(val)

try:
    from app.core.models import Project, POUO, PipeRow
    from app.report.word_builder import render_report
    HAS_REPORT = True
except Exception:
    HAS_REPORT = False


class MainWindowTk(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Диплом ТЭК — паспорт безопасности ТЭК")
        self.geometry("980x640")
        self.minsize(780, 480)

        self.project_pouos = []
        self._build_top()
        self._build_room_block()   # создаёт self.frm_room (не пакует)
        self._build_tank_block()   # создаёт self.frm_tank (не пакует)
        self._build_table()        # создаёт self.frm_pipes (не пакует)
        self._build_project_list() # создаёт self.frm_sel (пакует сразу — опорная точка)
        self._build_buttons()
        self._on_scenario_change()

    # ---------------- UI blocks ----------------

    def _build_top(self):
        frm = ttk.LabelFrame(self, text="1) Сценарий и общие исходные данные")
        frm.pack(fill="x", padx=10, pady=10)

        ttk.Label(frm, text="Сценарий (ПОУО):").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.scenario_var = tk.StringVar()
        self.cb_scenario = ttk.Combobox(frm, textvariable=self.scenario_var, state="readonly", width=90)
        self.cb_scenario["values"] = [f"{sid} — {SCENARIOS[sid].title}" for sid in SCENARIOS.keys()]
        self.cb_scenario.current(0)
        self.cb_scenario.grid(row=0, column=1, sticky="w", padx=8, pady=6)
        self.cb_scenario.bind("<<ComboboxSelected>>", lambda e: self._on_scenario_change())

        ttk.Label(frm, text="Топливо:").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        self.fuel_var = tk.StringVar()
        self.cb_fuel = ttk.Combobox(frm, textvariable=self.fuel_var, state="readonly", width=40)
        self.cb_fuel.grid(row=1, column=1, sticky="w", padx=8, pady=6)

        # P0 и t_shutoff — скрываются для tank-сценариев
        self.lbl_p0 = ttk.Label(frm, text="Исходное давление P0, кПа:")
        self.lbl_p0.grid(row=2, column=0, sticky="w", padx=8, pady=6)
        self.in_p0 = ttk.Entry(frm, width=20)
        self.in_p0.grid(row=2, column=1, sticky="w", padx=8, pady=6)

        self.lbl_tsh = ttk.Label(frm, text="Время до отсечки t, с:")
        self.lbl_tsh.grid(row=3, column=0, sticky="w", padx=8, pady=6)
        self.in_tsh = ttk.Entry(frm, width=20)
        self.in_tsh.grid(row=3, column=1, sticky="w", padx=8, pady=6)

        self.space_lbl = ttk.Label(frm, text="", foreground="#666")
        self.space_lbl.grid(row=4, column=1, sticky="w", padx=8, pady=6)

    def _build_room_block(self):
        """Параметры помещения. Пакуется/снимается через _refresh_layout()."""
        self.frm_room = ttk.LabelFrame(self, text="Параметры помещения (только для indoor-сценариев)")
        ttk.Label(self.frm_room, text="Объём помещения V, м³:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.in_vroom = ttk.Entry(self.frm_room, width=20)
        self.in_vroom.grid(row=0, column=1, sticky="w", padx=8, pady=6)

    def _build_tank_block(self):
        """Блок для резервуарного парка (POUO1). Пакуется/снимается через _refresh_layout()."""
        self.frm_tank = ttk.LabelFrame(self, text="2) Параметры резервуарного парка")
        self.frm_tank.columnconfigure(0, weight=1)
        self.frm_tank.columnconfigure(1, weight=1)

        # ── левая панель: ёмкости ──────────────────────────────────────────
        grp_tanks = ttk.LabelFrame(self.frm_tank, text="Ёмкости")
        grp_tanks.grid(row=0, column=0, padx=(12, 6), pady=8, sticky="nsew")

        ttk.Label(grp_tanks, text="Объём одной ёмкости, м³:").grid(
            row=0, column=0, sticky="w", padx=10, pady=7)
        self.in_tank_volume = ttk.Entry(grp_tanks, width=16)
        self.in_tank_volume.grid(row=0, column=1, sticky="w", padx=10, pady=7)

        ttk.Label(grp_tanks, text="Количество ёмкостей:").grid(
            row=1, column=0, sticky="w", padx=10, pady=7)
        self.in_tank_count = ttk.Entry(grp_tanks, width=16)
        self.in_tank_count.insert(0, "1")
        self.in_tank_count.grid(row=1, column=1, sticky="w", padx=10, pady=7)

        # ── правая панель: пролив ──────────────────────────────────────────
        grp_spill = ttk.LabelFrame(self.frm_tank, text="Параметры пролива")
        grp_spill.grid(row=0, column=1, padx=(6, 12), pady=8, sticky="nsew")

        ttk.Label(grp_spill, text="Площадь пролива, м²:").grid(
            row=0, column=0, sticky="w", padx=10, pady=7)
        self.in_spill_area = ttk.Entry(grp_spill, width=16)
        self.in_spill_area.grid(row=0, column=1, sticky="w", padx=10, pady=7)

        ttk.Label(grp_spill, text="Время испарения, с:").grid(
            row=1, column=0, sticky="w", padx=10, pady=7)
        self.in_spill_duration = ttk.Entry(grp_spill, width=16)
        self.in_spill_duration.insert(0, "3600")
        self.in_spill_duration.grid(row=1, column=1, sticky="w", padx=10, pady=7)

        # ── строка: плотность персонала ───────────────────────────────────
        grp_exposure = ttk.LabelFrame(self.frm_tank, text="Персонал")
        grp_exposure.grid(row=1, column=0, columnspan=2, padx=(12, 12), pady=(0, 6), sticky="ew")
        grp_exposure.columnconfigure(1, weight=1)

        ttk.Label(grp_exposure, text="Плотность персонала, чел/га:").grid(
            row=0, column=0, sticky="w", padx=10, pady=6)
        self.in_people_density = ttk.Entry(grp_exposure, width=16)
        self.in_people_density.insert(0, "0")
        self.in_people_density.grid(row=0, column=1, sticky="w", padx=10, pady=6)
        ttk.Label(grp_exposure, text="(0 — расчёт площадей без числа людей)",
                  foreground="#888").grid(row=0, column=2, sticky="w", padx=(4, 10), pady=6)

        # ── подсказка ──────────────────────────────────────────────────────
        ttk.Label(
            self.frm_tank,
            text="Топливо: СУГ (lpg) или дизельное (diesel)  ·  Трубопроводы не требуются",
            foreground="#888",
        ).grid(row=2, column=0, columnspan=2, padx=14, pady=(0, 8), sticky="w")

    def _build_table(self):
        """Таблица трубопроводов. Пакуется/снимается через _refresh_layout()."""
        self.frm_pipes = ttk.LabelFrame(self, text="2) Трубопроводы (отметь аварийный участок ☑)")

        cols = ("acc", "length_m", "diam_mm")
        self.tree = ttk.Treeview(self.frm_pipes, columns=cols, show="headings", height=8)

        self.tree.heading("acc", text="Авария")
        self.tree.heading("length_m", text="Длина L, м")
        self.tree.heading("diam_mm", text="Диаметр D, мм")

        self.tree.column("acc", width=80, anchor="center")
        self.tree.column("length_m", width=180, anchor="center")
        self.tree.column("diam_mm", width=180, anchor="center")

        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)

        scroll = ttk.Scrollbar(self.frm_pipes, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="left", fill="y", pady=8)

        right = ttk.Frame(self.frm_pipes)
        right.pack(side="left", fill="y", padx=10, pady=8)

        ttk.Label(right, text="Добавить/редактировать строку:").pack(anchor="w", pady=(0, 6))

        ttk.Label(right, text="Длина, м").pack(anchor="w")
        self.in_len = ttk.Entry(right, width=18)
        self.in_len.pack(anchor="w", pady=(0, 8))

        ttk.Label(right, text="Диаметр, мм").pack(anchor="w")
        self.in_diam = ttk.Entry(right, width=18)
        self.in_diam.pack(anchor="w", pady=(0, 12))

        ttk.Button(right, text="Добавить", command=self.add_row).pack(fill="x", pady=2)
        ttk.Button(right, text="Обновить выбранную", command=self.update_selected).pack(fill="x", pady=2)
        ttk.Button(right, text="Удалить выбранную", command=self.delete_selected).pack(fill="x", pady=2)
        ttk.Button(right, text="Заполнить пример", command=self.fill_demo).pack(fill="x", pady=(12, 2))

        self.tree.bind("<<TreeviewSelect>>", lambda e: self._load_selected_to_inputs())
        self.tree.bind("<Button-1>", self._on_tree_click)

    def _build_project_list(self):
        # self.frm_sel пакуется сразу — служит опорной точкой для before=
        self.frm_sel = ttk.LabelFrame(self, text="3) Выбранные сценарии (ПОУО) в проекте")
        self.frm_sel.pack(fill="both", expand=False, padx=10, pady=(0, 10))

        cols2 = ("code", "fuel", "space")
        self.tree_pouos = ttk.Treeview(self.frm_sel, columns=cols2, show="headings", height=4)
        self.tree_pouos.heading("code", text="ПОУО")
        self.tree_pouos.heading("fuel", text="Топливо")
        self.tree_pouos.heading("space", text="Тип")
        self.tree_pouos.column("code", width=560, anchor="w")
        self.tree_pouos.column("fuel", width=220, anchor="center")
        self.tree_pouos.column("space", width=160, anchor="center")
        self.tree_pouos.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)

        scroll2 = ttk.Scrollbar(self.frm_sel, orient="vertical", command=self.tree_pouos.yview)
        self.tree_pouos.configure(yscrollcommand=scroll2.set)
        scroll2.pack(side="left", fill="y", pady=8)

        btns = ttk.Frame(self.frm_sel)
        btns.pack(side="left", fill="y", padx=10, pady=8)

        ttk.Button(btns, text="Добавить ПОУО в проект", command=self.add_pouo_to_project).pack(fill="x", pady=2)
        ttk.Button(btns, text="Удалить выбранный", command=self.delete_selected_pouo).pack(fill="x", pady=2)
        ttk.Button(btns, text="Очистить все", command=self.clear_project).pack(fill="x", pady=2)

    def calculate_only(self):
        try:
            project = self._compute_and_return_project()
            self._show_debug_window(project)
        except Exception as e:
            messagebox.showerror("Ошибка расчёта", str(e))

    def _show_debug_window(self, project):
        """Открывает отдельное окно с подробными результатами расчёта."""
        win = tk.Toplevel(self)
        win.title("Подробные результаты расчёта (7.1 / 7.2 / 7.3)")
        win.geometry("860x700")
        win.minsize(600, 400)

        frm = ttk.Frame(win)
        frm.pack(fill="both", expand=True, padx=8, pady=8)

        txt = tk.Text(
            frm,
            font=("Courier New", 10),
            wrap="none",
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            selectbackground="#264f78",
            padx=8,
            pady=8,
        )
        txt.pack(side="left", fill="both", expand=True)

        scroll_y = ttk.Scrollbar(frm, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=scroll_y.set)
        scroll_y.pack(side="left", fill="y")

        scroll_x = ttk.Scrollbar(win, orient="horizontal", command=txt.xview)
        txt.configure(xscrollcommand=scroll_x.set)
        scroll_x.pack(fill="x", padx=8, pady=(0, 8))

        all_text_parts = []
        for p in project.pouos:
            all_text_parts.append(build_calculation_debug_output(p.results))

        full_text = "\n\n".join(all_text_parts)
        txt.insert("1.0", full_text if full_text.strip() else "Нет данных.")
        txt.config(state="disabled")

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="Закрыть", command=win.destroy).pack(side="right")
        ttk.Button(
            btn_frame, text="Копировать всё",
            command=lambda: (win.clipboard_clear(), win.clipboard_append(full_text))
        ).pack(side="right", padx=8)

    def _build_buttons(self):
        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=10, pady=(0, 10))

        ttk.Button(frm, text="Проверить данные", command=self.validate).pack(side="left")
        ttk.Button(frm, text="Показать JSON", command=self.show_json).pack(side="left", padx=8)
        ttk.Button(frm, text="Рассчитать", command=self.calculate_only).pack(side="left", padx=8)

        if HAS_REPORT:
            ttk.Button(frm, text="Сформировать Word", command=self.build_word).pack(side="left", padx=8)
        else:
            ttk.Label(frm, text="(Word-генерация не подключена)", foreground="#a00").pack(side="left", padx=10)

    # ---------------- handlers ----------------

    def _on_scenario_change(self):
        sid = self._selected_scenario_id()
        sc = SCENARIOS[sid]

        self.space_lbl.config(
            text="Тип пространства: Помещение" if sc.space == "indoor" else "Тип пространства: Открытая площадка"
        )

        # Обновляем список топлив
        self._fuel_title_to_id = {}
        values = []
        for fid in sc.allowed_fuels:
            values.append(FUELS[fid].title)
            self._fuel_title_to_id[FUELS[fid].title] = fid
        self.cb_fuel["values"] = values
        self.cb_fuel.current(0)
        self.fuel_var.set(values[0])

        # Показываем/скрываем P0 и t_shutoff
        if sc.needs_pressure:
            self.lbl_p0.grid()
            self.in_p0.grid()
        else:
            self.lbl_p0.grid_remove()
            self.in_p0.grid_remove()

        if sc.needs_shutoff:
            self.lbl_tsh.grid()
            self.in_tsh.grid()
        else:
            self.lbl_tsh.grid_remove()
            self.in_tsh.grid_remove()

        self._refresh_layout()

    def _refresh_layout(self):
        """Перепаковывает блоки frm_room / frm_tank / frm_pipes согласно текущему сценарию.

        Все три блока вставляются before=self.frm_sel, чтобы сохранить порядок:
        frm_top → [frm_room] → [frm_tank] → [frm_pipes] → frm_sel → кнопки.
        """
        self.frm_room.pack_forget()
        self.frm_tank.pack_forget()
        self.frm_pipes.pack_forget()

        sc = SCENARIOS[self._selected_scenario_id()]

        if sc.needs_room_volume:
            self.frm_room.pack(fill="x", padx=10, pady=(0, 10), before=self.frm_sel)

        if sc.needs_tank:
            self.frm_tank.pack(fill="x", padx=10, pady=(0, 10), before=self.frm_sel)

        if sc.needs_pipes:
            self.frm_pipes.pack(fill="both", expand=True, padx=10, pady=10, before=self.frm_sel)

    def _selected_scenario_id(self) -> str:
        return self.scenario_var.get().split("—")[0].strip()

    def _selected_fuel_id(self) -> str:
        title = self.fuel_var.get().strip()
        return self._fuel_title_to_id.get(title, "natgas")

    def _on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)  # '#1' — авария
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        if col == "#1":
            for iid in self.tree.get_children():
                vals = list(self.tree.item(iid, "values"))
                vals[0] = "☐"
                self.tree.item(iid, values=vals)
            vals = list(self.tree.item(row_id, "values"))
            vals[0] = "☑"
            self.tree.item(row_id, values=vals)

    # ---------------- table ops ----------------

    def add_row(self):
        L, D = self._parse_pipe_inputs()
        if L is None:
            return
        self.tree.insert("", "end", values=("☐", L, D))
        self.in_len.delete(0, tk.END)
        self.in_diam.delete(0, tk.END)

    def update_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Внимание", "Выбери строку в таблице.")
            return
        L, D = self._parse_pipe_inputs()
        if L is None:
            return
        old = list(self.tree.item(sel[0], "values"))
        acc = old[0]
        self.tree.item(sel[0], values=(acc, L, D))

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        self.tree.delete(sel[0])

    def fill_demo(self):
        sid = self._selected_scenario_id()
        sc = SCENARIOS[sid]

        if sc.needs_tank:
            self.in_tank_volume.delete(0, tk.END)
            self.in_tank_volume.insert(0, "50")
            self.in_tank_count.delete(0, tk.END)
            self.in_tank_count.insert(0, "4")
            self.in_spill_area.delete(0, tk.END)
            self.in_spill_area.insert(0, "200")
            self.in_spill_duration.delete(0, tk.END)
            self.in_spill_duration.insert(0, "3600")
            self.in_people_density.delete(0, tk.END)
            self.in_people_density.insert(0, "5")
            return

        self.in_p0.delete(0, tk.END)
        self.in_p0.insert(0, "600")
        self.in_tsh.delete(0, tk.END)
        self.in_tsh.insert(0, "300")
        for item in self.tree.get_children():
            self.tree.delete(item)
        demo = [
            ("☑", 30, 57),
            ("☐", 12, 32),
            ("☐", 8, 25),
        ]
        for acc, L, D in demo:
            self.tree.insert("", "end", values=(acc, L, D))

    def _load_selected_to_inputs(self):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        self.in_len.delete(0, tk.END)
        self.in_len.insert(0, str(vals[1]))
        self.in_diam.delete(0, tk.END)
        self.in_diam.insert(0, str(vals[2]))

    def _parse_pipe_inputs(self):
        try:
            L = float(self.in_len.get().replace(",", "."))
            D = float(self.in_diam.get().replace(",", "."))
            if L <= 0 or D <= 0:
                raise ValueError
            return L, D
        except Exception:
            messagebox.showerror("Ошибка", "Проверь длину и диаметр: L>0, D>0.")
            return None, None

    def _parse_float_entry(self, entry: ttk.Entry, default: float = 0.0) -> float:
        s = (entry.get() or "").strip()
        if not s:
            return default
        try:
            return float(s.replace(",", "."))
        except ValueError:
            messagebox.showerror(
                "Ошибка ввода",
                f"Не удалось прочитать число: «{s}».\n"
                "Допустимы только цифры, точка или запятая как разделитель дробной части."
            )
            raise

    def _parse_int_entry(self, entry: ttk.Entry, default: int = 1) -> int:
        s = (entry.get() or "").strip()
        if not s:
            return default
        try:
            return int(float(s.replace(",", ".")))
        except ValueError:
            messagebox.showerror(
                "Ошибка ввода",
                f"Не удалось прочитать целое число: «{s}»."
            )
            raise

    # ---------------- data ----------------

    def collect_data(self) -> dict:
        sid = self._selected_scenario_id()
        sc = SCENARIOS[sid]
        fuel_id = self._selected_fuel_id()
        fuel = get_fuel(fuel_id)

        if sc.needs_tank:
            volume_m3 = self._parse_float_entry(self.in_tank_volume, 0.0)
            count = self._parse_int_entry(self.in_tank_count, 1)
            area_m2 = self._parse_float_entry(self.in_spill_area, 0.0)
            duration_s = self._parse_float_entry(self.in_spill_duration, 3600.0)
            people_density = self._parse_float_entry(self.in_people_density, 0.0)

            inputs = {
                "tank": {
                    "volume_m3": volume_m3,
                    "count": count,
                },
                "spill": {
                    "area_m2": area_m2,
                    "duration_s": duration_s,
                },
                "exposure": {
                    "people_density_per_ha": people_density,
                },
            }
            return {
                "scenario_id": sid,
                "scenario_title": sc.title,
                "space": sc.space,
                "fuel_id": fuel.id,
                "fuel_title": fuel.title,
                "inputs": inputs,
                "pipes": [],
                "accident_index": None,
                "is_tank_park": True,
            }

        # Стандартные сценарии с трубопроводами
        inputs: dict = {}
        if sc.needs_pressure:
            inputs["P0_kpa"] = self._parse_float_entry(self.in_p0, 0.0)
        if sc.needs_shutoff:
            inputs["t_shutoff_s"] = self._parse_float_entry(self.in_tsh, 0.0)
        if sc.needs_room_volume:
            inputs["V_room_m3"] = self._parse_float_entry(self.in_vroom, 0.0)

        pipes = []
        accident_index = None
        for idx, iid in enumerate(self.tree.get_children()):
            v = self.tree.item(iid, "values")
            is_acc = (str(v[0]).strip() == "☑")
            L = float(str(v[1]).replace(",", "."))
            D = float(str(v[2]).replace(",", "."))
            pipes.append({
                "name": f"Участок {idx+1}",
                "length_m": L,
                "diameter_mm": D,
                "is_accident": is_acc,
            })
            if is_acc:
                accident_index = idx

        return {
            "scenario_id": sid,
            "scenario_title": sc.title,
            "space": sc.space,
            "fuel_id": fuel.id,
            "fuel_title": fuel.title,
            "inputs": inputs,
            "pipes": pipes,
            "accident_index": accident_index,
            "is_tank_park": False,
        }

    def validate(self):
        data = self.collect_data()
        sc = SCENARIOS[data["scenario_id"]]
        errors = []

        if sc.needs_tank:
            tank = data["inputs"].get("tank", {})
            spill = data["inputs"].get("spill", {})
            if tank.get("volume_m3", 0.0) <= 0:
                errors.append("Заполни объём одной ёмкости (> 0 м³).")
            if tank.get("count", 0) < 1:
                errors.append("Количество ёмкостей должно быть ≥ 1.")
            if spill.get("area_m2", 0.0) <= 0:
                errors.append("Заполни площадь пролива (> 0 м²).")
            if spill.get("duration_s", 0.0) <= 0:
                errors.append("Заполни время испарения (> 0 с).")
        else:
            if sc.needs_pressure and data["inputs"].get("P0_kpa", 0.0) <= 0:
                errors.append("Заполни P0_kpa (исходное давление).")
            if sc.needs_shutoff and data["inputs"].get("t_shutoff_s", 0.0) <= 0:
                errors.append("Заполни t_shutoff_s (время до отсечки).")
            if sc.needs_room_volume and data["inputs"].get("V_room_m3", 0.0) <= 0:
                errors.append("Заполни V_room_m3 (объём помещения).")

            if sc.needs_pipes:
                if len(data["pipes"]) == 0:
                    errors.append("Добавь хотя бы одну трубу.")
                if len(data["pipes"]) > 0 and data["accident_index"] is None:
                    errors.append("Отметь аварийный участок (☑) в колонке «Авария».")

        if errors:
            messagebox.showerror("Ошибки", "\n".join(errors))
        else:
            messagebox.showinfo("Ок", "Данные корректны ✅")

    def show_json(self):
        data = self.collect_data()
        messagebox.showinfo("JSON", json.dumps(data, ensure_ascii=False, indent=2))

    def _build_project_from_selected(self):
        """
        Собирает Project из self.project_pouos (если пользователь добавлял сценарии),
        иначе — из текущей формы (collect_data()).
        """
        pouos_data = self.project_pouos[:] if self.project_pouos else [self.collect_data()]

        pouos = []
        for item in pouos_data:
            if item.get("is_tank_park"):
                # Резервуарный парк — без труб, без PipeRow
                pouos.append(
                    POUO(
                        code=item["scenario_id"],
                        title=item["scenario_title"],
                        is_indoor=(item["space"] == "indoor"),
                        fuel_id=item["fuel_id"],
                        inputs=item["inputs"],
                        pipes=[],
                        results={},
                    )
                )
            else:
                pouos.append(
                    POUO(
                        code=item["scenario_id"],
                        title=item["scenario_title"],
                        is_indoor=(item["space"] == "indoor"),
                        fuel_id=item["fuel_id"],
                        inputs=item["inputs"],
                        pipes=[
                            PipeRow(
                                name=p["name"],
                                length_m=p["length_m"],
                                diameter_mm=p["diameter_mm"],
                                is_accident=p["is_accident"],
                                pressure_kpa=0.0,
                            )
                            for p in item["pipes"]
                        ],
                        results={},
                    )
                )

        project = Project(
            name="Паспорт безопасности объекта ТЭК",
            object_name="(заполнить позже)",
            address="(заполнить позже)",
            pouos=pouos,
        )
        return project

    def _compute_and_return_project(self):
        """Собирает проект и прогоняет расчёты."""
        project = self._build_project_from_selected()
        cfg = EngineConfig(make_charts=True)
        compute_project(project, cfg)
        return project

    def _make_summary_text(self, project: "Project") -> str:
        lines = []

        for p in project.pouos:
            lines.append(f"{p.code} — {p.title}")

            meta = (p.results.get("meta") or {})
            lines.append(f"  Топливо: {meta.get('fuel_title', p.fuel_id)}")
            lines.append(f"  Тип: {'Помещение' if p.is_indoor else 'Открытая площадка'}")

            if p.results.get("error"):
                lines.append(f"  ❌ Ошибка: {p.results['error']}")
                lines.append("")
                continue

            if "warnings" in p.results:
                for w in p.results["warnings"]:
                    lines.append(f"  ⚠ {w}")

            rel = p.results.get("release")
            if isinstance(rel, dict) and ("P2_kpa" in rel or "P_up_kpa" in rel):
                P2 = rel.get("P2_kpa", rel.get("P_up_kpa"))
                d_mm = rel.get("d_hole_mm")
                if d_mm is None and rel.get("d_m") is not None:
                    d_mm = round(float(rel.get("d_m", 0.0)) * 1000.0, 1)

                lines.append(f"  Аварийный участок: {rel.get('accident_pipe')}")
                lines.append(f"  P2, кПа: {P2}, d, мм: {d_mm}")

                m_dot = rel.get("m_dot_kg_s", rel.get("G_kg_s", 0.0))
                lines.append(f"  M (кг/с): {round(float(m_dot or 0.0), 4)}")
                lines.append(f"  M1T (кг): {round(float(rel.get('M1T_kg', 0.0) or 0.0), 2)}")
                lines.append(f"  V2T (м³): {round(float(rel.get('V2T_m3', 0.0) or 0.0), 2)}")
                lines.append(f"  M2T (кг): {round(float(rel.get('M2T_kg', 0.0) or 0.0), 2)}")
                lines.append(
                    f"  Mg total (кг): {round(float(rel.get('M2_total_kg', rel.get('Mg_kg', 0.0)) or 0.0), 2)}")
                lines.append(f"  m облака (кг): {round(float(rel.get('mr_kg', rel.get('m_cloud_kg', 0.0)) or 0.0), 2)}")

                if rel.get("E_J") is not None:
                    lines.append(f"  Энергозапас E (Дж): {round(float(rel.get('E_J', 0.0)), 2)}")

            fb = p.results.get("fireball")
            if isinstance(fb, dict) and "params" in fb:
                z = fb.get("zones") or []
                lines.append("  Fireball зоны (q→r): " + ", ".join(
                    [f"{zz['q_thr_kw_m2']}→{zz['r_m']}" for zz in z]
                ))
            elif isinstance(fb, dict) and fb.get("skip_reason"):
                lines.append(f"  Fireball: пропуск ({fb['skip_reason']})")

            jf = p.results.get("jet_fire")
            if isinstance(jf, dict) and "params" in jf:
                z = jf.get("zones") or []
                lines.append("  JetFire зоны (q→r): " + ", ".join(
                    [f"{zz['q_thr_kw_m2']}→{zz['r_m']}" for zz in z]
                ))
            elif isinstance(jf, dict) and jf.get("skip_reason"):
                lines.append(f"  JetFire: пропуск ({jf['skip_reason']})")

            tvs = p.results.get("tvs_explosion")
            if isinstance(tvs, dict):
                table = tvs.get("table") or []
                results = tvs.get("results") or {}
                intermediate = tvs.get("intermediate") or {}

                if table:
                    max_row = max(table, key=lambda r: r.get("deltaP_Pa", 0.0))
                    lines.append(
                        f"  TVS: max ΔP = {round(max_row.get('deltaP_Pa', 0.0) / 1000, 3)} кПа "
                        f"при r = {max_row.get('r_m')} м"
                    )

                if intermediate.get("E_J") is not None:
                    lines.append(f"  TVS E (Дж): {round(float(intermediate.get('E_J', 0.0)), 2)}")

                zones_glass = results.get("zones_glass")
                if zones_glass:
                    pretty = ", ".join([f"{k}→{v}" for k, v in zones_glass.items()])
                    lines.append(f"  TVS glass zones: {pretty}")

                zones_people = results.get("zones_people")
                if zones_people:
                    pretty = ", ".join([f"{k}→{v}" for k, v in zones_people.items()])
                    lines.append(f"  TVS people zones: {pretty}")

                zones_buildings = results.get("zones_buildings")
                if zones_buildings:
                    pretty_parts = []
                    for k, v in zones_buildings.items():
                        if isinstance(v, (list, tuple)) and len(v) == 2:
                            r1, r2 = v
                            r1s = _fmt_zone_radius(r1)
                            r2s = _fmt_zone_radius(r2)
                            pretty_parts.append(f"{k}: {r1s}–{r2s}")
                        else:
                            pretty_parts.append(f"{k}: {v}")
                    lines.append(f"  TVS building zones: {', '.join(pretty_parts)}")

                if tvs.get("skip_reason"):
                    lines.append(f"  TVS: пропуск ({tvs['skip_reason']})")

            lines.append("")

        return "\n".join(lines)

    # ---------------- Word (optional) ----------------

    def build_word(self):
        if not HAS_REPORT:
            messagebox.showerror("Ошибка", "Word-генерация не подключена.")
            return

        try:
            project = self._compute_and_return_project()
        except Exception as e:
            messagebox.showerror("Ошибка расчёта", str(e))
            return

        app_dir = Path(__file__).resolve().parents[1]
        root_dir = Path(__file__).resolve().parents[2]

        template_path = app_dir / "report" / "templates" / "template.docx"
        if not template_path.exists():
            template_path = app_dir / "report" / "templates" / "template2.docx"

        output_path = root_dir / "out" / "Отчет_из_UI.docx"

        try:
            render_report(
                template_path=str(template_path),
                output_path=str(output_path),
                project=project,
            )
            messagebox.showinfo("Готово", f"Создан файл:\n{output_path}")
        except Exception as e:
            messagebox.showerror("Ошибка Word", str(e))

    # ---------------- project list ops ----------------

    def add_pouo_to_project(self):
        data = self.collect_data()
        self.project_pouos.append(data)

        sc_title = f"{data['scenario_id']} — {data['scenario_title']}"
        self.tree_pouos.insert(
            "", "end",
            values=(sc_title, data["fuel_title"], "Помещение" if data["space"] == "indoor" else "Открытая площадка")
        )
        messagebox.showinfo("Ок", "ПОУО добавлен в проект ✅")

    def delete_selected_pouo(self):
        sel = self.tree_pouos.selection()
        if not sel:
            return
        idx = self.tree_pouos.index(sel[0])
        self.tree_pouos.delete(sel[0])
        if 0 <= idx < len(self.project_pouos):
            self.project_pouos.pop(idx)

    def clear_project(self):
        for item in self.tree_pouos.get_children():
            self.tree_pouos.delete(item)
        self.project_pouos.clear()
