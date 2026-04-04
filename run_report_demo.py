# run_report_demo.py
from app.core.models import Project, POUO, PipeRow
from app.report.word_builder import render_report_for_project
from app.core.engine import compute_project  # <-- важно


def main():
    print("1) Собираю Project...")

    project = Project(
        name="Паспорт безопасности объекта ТЭК",
        object_name="Газовая котельная",
        address="Калининград (пример)",
        pouos=[
            POUO(
                code="POUO2",
                title="Котельная: наружный газопровод ВД (узел подключения)",
                is_indoor=False,
                fuel_id="methane",  # алиас -> natgas
                inputs={
                    "P0_kpa": 500,
                    "t_shutoff_s": 60,
                    # опционально для ТВС:
                    "range_id": 3,
                    "tvs_r_max_m": 200,
                },
                pipes=[
                    PipeRow(name="Участок 1", length_m=30, diameter_mm=57, pressure_kpa=500, is_accident=True),
                    PipeRow(name="Участок 2", length_m=12, diameter_mm=32, pressure_kpa=500, is_accident=False),
                ],
                results={},
            ),
        ],
    )

    print("2) Считаю результаты (engine.compute_project)...")
    compute_project(project)

    # Быстрый вывод, чтобы понять что посчиталось
    for p in project.pouos:
        print("\n---", p.code, "---")
        print("keys:", list(p.results.keys()))
        if "release" in p.results:
            print("G:", p.results["release"].get("G_kg_s"), "m_release:", p.results["release"].get("m_release_kg"))

    print("\n3) Рендерю Word (шаблон по карте POUO2 → templatePOUO2.docx)...")
    name = render_report_for_project(
        project,
        output_path="out/Отчет_тестовый.docx",
    )
    print("4) Готово: out/Отчет_тестовый.docx, шаблон:", name)


if __name__ == "__main__":
    main()
