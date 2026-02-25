# app/ui_tk/main_window_tk.py
from __future__ import annotations
from pathlib import Path
from pathlib import Path
from app.core.engine import compute_project, EngineConfig
import json
import tkinter as tk
from tkinter import ttk, messagebox

from app.core.scenarios import SCENARIOS
from app.core.fuels import FUELS, get_fuel

try:
    from app.core.models import Project, POUO, PipeRow
    from app.report.word_builder import render_report
    HAS_REPORT = True
except Exception:
    HAS_REPORT = False


class MainWindowTk(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Диплом ТЭК — выбор ПОУО/топлива/труб (tkinter)")
        self.geometry("1240x800")

        self.project_pouos = []

        self._build_top()
        self._build_room_block()
        self._build_table()
        self._build_project_list()
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

        ttk.Label(frm, text="Исходное давление P0, кПа:").grid(row=2, column=0, sticky="w", padx=8, pady=6)
        self.in_p0 = ttk.Entry(frm, width=20)
        self.in_p0.grid(row=2, column=1, sticky="w", padx=8, pady=6)

        ttk.Label(frm, text="Время до отсечки t, с:").grid(row=3, column=0, sticky="w", padx=8, pady=6)
        self.in_tsh = ttk.Entry(frm, width=20)
        self.in_tsh.grid(row=3, column=1, sticky="w", padx=8, pady=6)

        self.space_lbl = ttk.Label(frm, text="", foreground="#666")
        self.space_lbl.grid(row=4, column=1, sticky="w", padx=8, pady=6)

    def _build_room_block(self):
        self.frm_room = ttk.LabelFrame(self, text="Параметры помещения (только для indoor-сценариев)")
        ttk.Label(self.frm_room, text="Объём помещения V, м³:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.in_vroom = ttk.Entry(self.frm_room, width=20)
        self.in_vroom.grid(row=0, column=1, sticky="w", padx=8, pady=6)

    def _build_table(self):
        frm = ttk.LabelFrame(self, text="2) Трубопроводы (отметь аварийный участок ☑)")
        frm.pack(fill="both", expand=True, padx=10, pady=10)

        cols = ("acc", "length_m", "diam_mm")
        self.tree = ttk.Treeview(frm, columns=cols, show="headings", height=12)

        self.tree.heading("acc", text="Авария")
        self.tree.heading("length_m", text="Длина L, м")
        self.tree.heading("diam_mm", text="Диаметр D, мм")

        self.tree.column("acc", width=80, anchor="center")
        self.tree.column("length_m", width=180, anchor="center")
        self.tree.column("diam_mm", width=180, anchor="center")

        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)

        scroll = ttk.Scrollbar(frm, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="left", fill="y", pady=8)

        right = ttk.Frame(frm)
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
        frm_sel = ttk.LabelFrame(self, text="3) Выбранные сценарии (ПОУО) в проекте")
        frm_sel.pack(fill="both", expand=False, padx=10, pady=(0, 10))

        cols2 = ("code", "fuel", "space")
        self.tree_pouos = ttk.Treeview(frm_sel, columns=cols2, show="headings", height=6)
        self.tree_pouos.heading("code", text="ПОУО")
        self.tree_pouos.heading("fuel", text="Топливо")
        self.tree_pouos.heading("space", text="Тип")
        self.tree_pouos.column("code", width=560, anchor="w")
        self.tree_pouos.column("fuel", width=220, anchor="center")
        self.tree_pouos.column("space", width=160, anchor="center")
        self.tree_pouos.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)

        scroll2 = ttk.Scrollbar(frm_sel, orient="vertical", command=self.tree_pouos.yview)
        self.tree_pouos.configure(yscrollcommand=scroll2.set)
        scroll2.pack(side="left", fill="y", pady=8)

        btns = ttk.Frame(frm_sel)
        btns.pack(side="left", fill="y", padx=10, pady=8)

        ttk.Button(btns, text="Добавить ПОУО в проект", command=self.add_pouo_to_project).pack(fill="x", pady=2)
        ttk.Button(btns, text="Удалить выбранный", command=self.delete_selected_pouo).pack(fill="x", pady=2)
        ttk.Button(btns, text="Очистить все", command=self.clear_project).pack(fill="x", pady=2)

    def calculate_only(self):
        try:
            project = self._compute_and_return_project()
            msg = self._make_summary_text(project)
            messagebox.showinfo("Результаты расчёта", msg if msg.strip() else "Нет данных.")
        except Exception as e:
            messagebox.showerror("Ошибка расчёта", str(e))

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

        self.space_lbl.config(text="Тип пространства: Помещение" if sc.space == "indoor" else "Тип пространства: Открытая площадка")

        self._fuel_title_to_id = {}
        values = []
        for fid in sc.allowed_fuels:
            values.append(FUELS[fid].title)
            self._fuel_title_to_id[FUELS[fid].title] = fid
        self.cb_fuel["values"] = values
        self.cb_fuel.current(0)
        self.fuel_var.set(values[0])

        if sc.needs_room_volume:
            self.frm_room.pack(fill="x", padx=10, pady=(0, 10))
        else:
            self.frm_room.pack_forget()

    def _selected_scenario_id(self) -> str:
        return self.scenario_var.get().split("—")[0].strip()

    def _selected_fuel_id(self) -> str:
        title = self.fuel_var.get().strip()
        return self._fuel_title_to_id.get(title, "natgas")

    def _on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)  # '#1' - авария
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
        return float(s.replace(",", "."))

    # ---------------- data ----------------
    def collect_data(self) -> dict:
        sid = self._selected_scenario_id()
        sc = SCENARIOS[sid]

        fuel_id = self._selected_fuel_id()
        fuel = get_fuel(fuel_id)

        inputs = {
            "P0_kpa": self._parse_float_entry(self.in_p0, 0.0),
            "t_shutoff_s": self._parse_float_entry(self.in_tsh, 0.0),
        }
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
                "is_accident": is_acc
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
        }

    def validate(self):
        data = self.collect_data()
        sc = SCENARIOS[data["scenario_id"]]
        errors = []

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
        Возвращает объект Project (dataclass).
        """
        pouos_data = self.project_pouos[:] if self.project_pouos else [self.collect_data()]

        pouos = []
        for item in pouos_data:
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
                            pressure_kpa=0.0,  # если нужно — добавим ввод позже
                        )
                        for p in item["pipes"]
                    ],
                    results={}
                )
            )

        project = Project(
            name="Паспорт безопасности объекта ТЭК",
            object_name="(заполнить позже)",
            address="(заполнить позже)",
            pouos=pouos
        )
        return project

    def _compute_and_return_project(self):
        """
        Собирает проект и прогоняет расчёты.
        Возвращает project с заполненными results.
        """
        project = self._build_project_from_selected()
        cfg = EngineConfig(make_charts=True)  # графики нужны для 7.1/7.2/7.3
        compute_project(project, cfg)
        return project

    def _make_summary_text(self, project: Project) -> str:
        """
        Краткий отчёт для проверки в UI (без Word).
        """
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

            # Release
            rel = p.results.get("release")
            if rel:
                lines.append(f"  Аварийный участок: {rel.get('accident_pipe')}")
                lines.append(f"  P, кПа: {rel.get('P_up_kpa')}, d, мм: {rel.get('d_hole_mm')}")
                lines.append(f"  G, кг/с: {round(rel.get('G_kg_s', 0.0), 6)}")
                lines.append(f"  m_release, кг: {round(rel.get('m_release_kg', 0.0), 6)}")
                lines.append(f"  m_cloud, кг: {round(rel.get('m_cloud_kg', 0.0), 6)}")

            # Fireball
            fb = p.results.get("fireball")
            if isinstance(fb, dict) and "params" in fb:
                z = fb.get("zones") or []
                lines.append("  Fireball зоны (q→r): " + ", ".join([f"{zz['q_thr_kw_m2']}→{zz['r_m']}" for zz in z]))
            elif isinstance(fb, dict) and fb.get("skip_reason"):
                lines.append(f"  Fireball: пропуск ({fb['skip_reason']})")

            # Jet fire
            jf = p.results.get("jet_fire")
            if isinstance(jf, dict) and "params" in jf:
                z = jf.get("zones") or []
                lines.append("  JetFire зоны (q→r): " + ", ".join([f"{zz['q_thr_kw_m2']}→{zz['r_m']}" for zz in z]))

            # TVS explosion
            tvs = p.results.get("tvs_explosion")
            if isinstance(tvs, dict) and "params" in tvs:
                # возьмём максимум ΔP для контроля
                table = tvs.get("table") or []
                if table:
                    max_row = max(table, key=lambda r: r.get("deltaP_Pa", 0.0))
                    lines.append(
                        f"  TVS: max ΔP={round(max_row.get('deltaP_Pa', 0.0) / 1000, 3)} кПа при r={max_row.get('r_m')} м")
            elif isinstance(tvs, dict) and tvs.get("skip_reason"):
                lines.append(f"  TVS: пропуск ({tvs['skip_reason']})")

            lines.append("")  # пустая строка между ПОУО

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

        # ✅ абсолютные пути (чтобы не ловить FileNotFoundError)
        app_dir = Path(__file__).resolve().parents[1]  # .../app
        root_dir = Path(__file__).resolve().parents[2]  # корень проекта

        template_path = app_dir / "report" / "templates" / "template.docx"
        if not template_path.exists():
            # если используешь другой шаблон
            template_path2 = app_dir / "report" / "templates" / "template2.docx"
            template_path = template_path2

        output_path = root_dir / "out" / "Отчет_из_UI.docx"

        try:
            render_report(
                template_path=str(template_path),
                output_path=str(output_path),
                project=project
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
