"""
УСТАРЕЛО, не используется приложением.

Раньше из templatePOUO4.docx собирался отдельный templatePOUO4.generated.docx.
Сейчас Jinja и структура раздела 9 правятся напрямую в:
  app/report/templates/templatePOUO4.docx

Файл скрипта сохранён только как справочная копия логики OOXML-патчей.
Попытка запуска из командной строки завершается с кодом 2 и подсказкой.
"""
from __future__ import annotations

import sys

import shutil
import zipfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATES_DIR = ROOT / "app/report/templates"

NS_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _w(tag: str) -> str:
    return f"{{{NS_URI}}}{tag}"


def _elem_text(el: ET.Element) -> str:
    return "".join((node.text or "") for node in el.iter(_w("t")))


def _section_heading(txt: str) -> str | None:
    t = txt.strip()
    if t.startswith("9.1"):
        return "9.1"
    if t.startswith("9.2"):
        return "9.2"
    if t.startswith("9.3"):
        return "9.3"
    return None


def _keep_91(el: ET.Element, txt: str) -> bool:
    if el.tag == _w("tbl"):
        return "Внешний диаметр трубопровода" in txt
    if "СП 12.13130" in txt:
        return False
    if "Рmax" in txt and "Р0" in txt and "∆Р" in txt:
        return False
    if "∆Р =" in txt or "ΔР =" in txt:
        return False
    if "Выводы." in txt and "В результате расчета" in txt:
        return False
    if "Расчеты воздействий для открытого" in txt:
        return False
    if "Ситуационный план представлен" in txt:
        return False
    if txt.strip().startswith("9.1"):
        return True
    if "На рассматриваемой внутренней территории проходит газопровод" in txt:
        return True
    if "P =" in txt and "КПа" in txt:
        return True
    if "М = Ψ" in txt:
        return True
    if "М =" in txt and ("кг/cек" in txt or "кг/сек" in txt):
        return True
    if "Масса топлива, поступающего в котельную" in txt:
        return True
    if "Запорная арматура находится" in txt:
        return True
    compact = (
        txt.replace(" ", "")
        .replace("\u00a0", "")
        .replace("\u2009", "")
        .replace("\u202f", "")
    )
    if "M1Т=" in compact or "M1T=" in compact:
        return True
    if "V2Т" in txt and "объем газа" in txt.lower():
        return True
    if "V2Т=" in compact or "V2T=" in compact:
        return True
    if "M2Т=" in compact or "M2T=" in compact:
        return True
    if "Общая масса газа" in txt:
        return True
    if "Mг =" in txt or "Мг =" in txt:
        return True
    if "mг =" in txt.lower() or "{{ indoor_explosion.mass_cloud }}" in txt:
        return True
    if "{{ indoor_explosion.conclusion }}" in txt:
        return True
    return False


def _keep_92(el: ET.Element, txt: str) -> bool:
    if el.tag == _w("tbl"):
        return False
    if txt.strip().startswith("9.2"):
        return True
    if "Эффективный диаметр" in txt and "огненного шара" in txt:
        return True
    if txt.strip().startswith("Ds = 5,33"):
        return True
    if "Высота" in txt and "огненного шара" in txt:
        return True
    if "Длительность существования" in txt:
        return True
    if "{{ fireball_params.ts_s }}" in txt:
        return True
    if "Интенсивность теплового излучения" in txt and "огненного шара" in txt:
        return True
    if "q =" in txt and "Ef" in txt and "{{ fireball_params.Ef_kw_m2 }}" in txt:
        return True
    return False


def _keep_93(el: ET.Element, txt: str) -> bool:
    if el.tag == _w("tbl"):
        return False
    return "{{ jet_fire.reason }}" in txt


def _clear_para_keep_ppr(p: ET.Element) -> None:
    for child in list(p):
        if child.tag != _w("pPr"):
            p.remove(child)


def _first_run_rpr(template_p: ET.Element) -> ET.Element | None:
    for r in template_p.iter(_w("r")):
        rpr = r.find(_w("rPr"))
        if rpr is not None:
            return deepcopy(rpr)
    return None


def _paragraph_with_text(template_p: ET.Element, text: str) -> ET.Element:
    p = ET.Element(_w("p"))
    p_pr = template_p.find(_w("pPr"))
    if p_pr is not None:
        p.append(deepcopy(p_pr))
    r = ET.SubElement(p, _w("r"))
    rpr = _first_run_rpr(template_p)
    if rpr is not None:
        r.append(rpr)
    t = ET.SubElement(r, _w("t"))
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    return p


def _set_heading_plain(p: ET.Element, title: str) -> None:
    rpr_src = _first_run_rpr(p)
    _clear_para_keep_ppr(p)
    r = ET.SubElement(p, _w("r"))
    if rpr_src is not None:
        r.append(rpr_src)
    else:
        r_pr_fallback = ET.Element(_w("rPr"))
        rf = ET.SubElement(r_pr_fallback, _w("rFonts"))
        rf.set(_w("cs"), "Times New Roman")
        sz = ET.SubElement(r_pr_fallback, _w("sz"))
        sz.set(_w("val"), "28")
        sz_cs = ET.SubElement(r_pr_fallback, _w("szCs"))
        sz_cs.set(_w("val"), "28")
        r.append(r_pr_fallback)
    t = ET.SubElement(r, _w("t"))
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = title


def _rewrite_ds_mass_note(p: ET.Element) -> None:
    txt = _elem_text(p)
    if "где m - масса продукта" not in txt:
        return
    _clear_para_keep_ppr(p)
    r = ET.SubElement(p, _w("r"))
    r_pr = ET.Element(_w("rPr"))
    rf = ET.SubElement(r_pr, _w("rFonts"))
    rf.set(_w("cs"), "Times New Roman")
    sz = ET.SubElement(r_pr, _w("sz"))
    sz.set(_w("val"), "24")
    sz_cs = ET.SubElement(r_pr, _w("szCs"))
    sz_cs.set(_w("val"), "24")
    r.append(r_pr)
    t = ET.SubElement(r, _w("t"))
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = (
        "Ds = 5,33 × m0,327. Масса выброса (расчёт ведётся по полной массе Mg)."
    )


def finalize_structure(xml_string: str) -> str:
    ET.register_namespace("w", NS_URI)

    stripped = xml_string.strip()
    decl = ""
    inner = stripped
    if stripped.startswith("<?xml"):
        pos = stripped.find("?>")
        if pos != -1:
            decl = stripped[: pos + 2]
            inner = stripped[pos + 2 :].lstrip()

    tree = ET.fromstring(inner.encode("utf-8"))
    body_el = tree.find(f".//{{{NS_URI}}}body")
    if body_el is None:
        raise RuntimeError("w:body not found")

    children = list(body_el)
    sect_pr = None
    if children and children[-1].tag == _w("sectPr"):
        sect_pr = children[-1]
        content = children[:-1]
    else:
        content = children

    section_state: str | None = None
    out: list[ET.Element] = []

    for el in content:
        txt = _elem_text(el)
        hs = _section_heading(txt)

        if hs == "9.3":
            section_state = "9.3"
            continue

        if hs:
            section_state = hs

        if section_state is None and hs is None:
            continue

        active = hs or section_state
        if active is None:
            continue

        keep = False
        if active == "9.1":
            keep = _keep_91(el, txt)
        elif active == "9.2":
            keep = _keep_92(el, txt)
            if (
                not keep
                and el.tag == _w("p")
                and "{{ jet_fire.reason }}" in txt
            ):
                section_state = "9.3"
                keep = True
        else:
            keep = _keep_93(el, txt)

        if keep:
            out.append(el)

    conclusion_idx = None
    conclusion_p: ET.Element | None = None
    for i, el in enumerate(out):
        if el.tag == _w("p") and "{{ indoor_explosion.conclusion }}" in _elem_text(el):
            conclusion_idx = i
            conclusion_p = el
            break

    delta_line = "Избыточное давление ΔP: {{ indoor_explosion.delta_p }} кПа"
    if conclusion_p is not None and conclusion_idx is not None:
        if not any(delta_line in _elem_text(el) for el in out):
            ins = _paragraph_with_text(conclusion_p, delta_line)
            out.insert(conclusion_idx, ins)

    for el in out:
        if el.tag != _w("p"):
            continue
        ttxt = _elem_text(el)
        if ttxt.strip().startswith("9.1"):
            el_t = (
                "9.1 Расчёт параметров волны давления при разрыве газопровода в "
                "замкнутом пространстве"
            )
            _set_heading_plain(el, el_t)
        elif ttxt.strip().startswith("9.2"):
            el_t = (
                "9.2 Прогнозирование зоны поражения тепловым излучением «огненного шара»"
            )
            _set_heading_plain(el, el_t)
        elif "где m - масса продукта" in ttxt:
            _rewrite_ds_mass_note(el)

    for el in list(body_el):
        body_el.remove(el)
    for el in out:
        body_el.append(el)
    if sect_pr is not None:
        body_el.append(sect_pr)

    rough = ET.tostring(tree, encoding="unicode")
    rough = rough.replace("\u2014", "-").replace("\u2013", "-")
    rough = rough.replace("\u2212", "-")

    legacy = (
        ("П.7.1 Выброс и ТВС-взрыв", "9.1 Расчёт параметров волны давления при разрыве газопровода в замкнутом пространстве"),
        (
            "П.7.3 Огненный шар",
            "9.2 Прогнозирование зоны поражения тепловым излучением «огненного шара»",
        ),
        (
            "П.7.2 Факельное горение",
            "9.3 Прогнозирование зоны поражения тепловым излучением факельного горения",
        ),
    )
    for a, b in legacy:
        rough = rough.replace(a, b)

    if decl:
        return decl + "\n" + rough
    return rough


def regenerate_pouo4_generated_docx(
    templates_dir: Path | None = None,
    *,
    verbose: bool = True,
) -> Path:
    """
    Копирует templatePOUO4.docx → templatePOUO4.generated.docx в templates_dir
    и применяет подстановки Jinja / финальную разметку раздела 9.
    """
    td = Path(templates_dir) if templates_dir else DEFAULT_TEMPLATES_DIR
    src = td / "templatePOUO4.docx"
    dst = td / "templatePOUO4.generated.docx"
    if not src.is_file():
        raise FileNotFoundError(src)

    shutil.copy2(src, dst)

    with zipfile.ZipFile(dst, "r") as zin:
        xml = zin.read("word/document.xml").decode("utf-8")

    # ── ΔP ────────────────────────────────────────────────────────────────
    xml = xml.replace("<w:t>0,514</w:t>", "<w:t>{{ indoor_explosion.delta_p }}</w:t>")
    xml = xml.replace(
        "<w:t xml:space=\"preserve\">0,514 </w:t>",
        "<w:t xml:space=\"preserve\">{{ indoor_explosion.delta_p }} </w:t>",
    )
    xml = xml.replace(
        "избыточном давлении 0,514 кПа",
        "избыточном давлении {{ indoor_explosion.delta_p }} кПа",
    )

    # ── Mg / m_cloud ──────────────────────────────────────────────────────
    xml = xml.replace(
        "<w:t xml:space=\"preserve\"> + 0,267 = 0,672</w:t>",
        "<w:t xml:space=\"preserve\"> + 0,267 = {{ indoor_explosion.mass_total }}</w:t>",
    )
    xml = xml.replace(
        "<w:t xml:space=\"preserve\"> × Z = 0,672× 0,5 = 0,336 кг (для горючих газов Z = 0,5)</w:t>",
        "<w:t xml:space=\"preserve\"> × Z = {{ indoor_explosion.mass_total }}× 0,5 = {{ indoor_explosion.mass_cloud }} кг (для горючих газов Z = 0,5)</w:t>",
    )
    xml = xml.replace(
        "равной 0,672 кг.",
        "равной {{ indoor_explosion.mass_total }} кг.",
    )

    # ── Ds / H / ts: заменяем целиком несколько <w:r>, чтобы не ломать OOXML ──
    ds_old = (
        "<w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"
        "<w:t xml:space=\"preserve\"> = 4,</w:t></w:r><w:r><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"
        "<w:t>679</w:t></w:r><w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"
        "<w:t xml:space=\"preserve\"> м</w:t></w:r>"
    )
    ds_new = (
        "<w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"
        "<w:t xml:space=\"preserve\"> = {{ fireball_params.Ds_m }} м</w:t></w:r>"
    )
    xml = xml.replace(ds_old, ds_new)

    h_old = (
        "<w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"
        "<w:t>/2 = 2,</w:t></w:r><w:r><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"
        "<w:t>34</w:t></w:r><w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"
        "<w:t xml:space=\"preserve\"> м</w:t></w:r>"
    )
    h_new = (
        "<w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"
        "<w:t>/2 = {{ fireball_params.H_m }} м</w:t></w:r>"
    )
    xml = xml.replace(h_old, h_new)

    ts_old = (
        "<w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"
        "<w:t xml:space=\"preserve\"> = 0,</w:t></w:r><w:r><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"
        "<w:t>82</w:t></w:r><w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"
        "<w:t xml:space=\"preserve\"> сек</w:t></w:r>"
    )
    ts_new = (
        "<w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"
        "<w:t xml:space=\"preserve\"> = {{ fireball_params.ts_s }} сек</w:t></w:r>"
    )
    xml = xml.replace(ts_old, ts_new)

    # ── Ef (число 80 отделено от индекса «2» надстрочным run) ───────────────
    xml = xml.replace(
        "<w:t xml:space=\"preserve\"> = 80 кВт/м</w:t></w:r><w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/><w:vertAlign w:val=\"superscript\"/></w:rPr><w:t>2</w:t></w:r>",
        "<w:t xml:space=\"preserve\"> = {{ fireball_params.Ef_kw_m2 }} кВт/м</w:t></w:r><w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/><w:vertAlign w:val=\"superscript\"/></w:rPr><w:t>2</w:t></w:r>",
    )

    # ── Вывод раздела 9.1 ──────────────────────────────────────────────────
    conclusion_para = (
        "<w:p w:rsidR=\"00FF1BD9\" w:rsidRPr=\"00A03472\" w:rsidRDefault=\"00FF1BD9\" "
        "w:rsidP=\"00FF1BD9\"><w:r><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr>"
        "<w:t xml:space=\"preserve\">{{ indoor_explosion.conclusion }}</w:t>"
        "</w:r></w:p>"
    )
    explosion_tail = (
        "не произойдет.</w:t></w:r></w:p><w:p w:rsidR=\"00FF1BD9\" w:rsidRPr=\"0066523E\" "
        "w:rsidRDefault=\"00FF1BD9\" w:rsidP=\"00FF1BD9\"><w:pPr><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/><w:highlight w:val=\"yellow\"/></w:rPr></w:pPr></w:p>"
    )
    if explosion_tail in xml:
        xml = xml.replace(
            explosion_tail,
            "не произойдет.</w:t></w:r></w:p>"
            + conclusion_para
            + "<w:p w:rsidR=\"00FF1BD9\" w:rsidRPr=\"0066523E\" "
            "w:rsidRDefault=\"00FF1BD9\" w:rsidP=\"00FF1BD9\"><w:pPr><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/><w:highlight w:val=\"yellow\"/></w:rPr></w:pPr></w:p>",
            1,
        )

    # ── Раздел 9.3: весь абзац → jet_fire.reason ─────────────────────────────
    jet_start = xml.find("<w:t>При струйном истечении")
    if jet_start != -1:
        p_open = xml.rfind("<w:p ", 0, jet_start)
        p_close = xml.find("</w:p>", jet_start)
        if p_open != -1 and p_close != -1:
            old_para = xml[p_open : p_close + len("</w:p>")]
            ppr_end = old_para.find("</w:pPr>")
            if ppr_end != -1:
                head = old_para[: ppr_end + len("</w:pPr>")]
                jet_para = (
                    head
                    + "<w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:eastAsia=\"Times New Roman\" "
                    "w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/><w:lang w:eastAsia=\"ru-RU\"/></w:rPr>"
                    "<w:t xml:space=\"preserve\">{{ jet_fire.reason }}</w:t></w:r></w:p>"
                )
                xml = xml[:p_open] + jet_para + xml[p_close + len("</w:p>") :]

    xml = finalize_structure(xml)

    buf = xml.encode("utf-8")
    with zipfile.ZipFile(dst, "r") as zin:
        names = zin.namelist()
        payloads = {n: zin.read(n) for n in names}
    payloads["word/document.xml"] = buf
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, payloads[name])

    if verbose:
        print("OK:", dst)
    return dst


def main() -> None:
    print(
        "Скрипт patch_template_pouo4_generated.py устарел: правьте шаблон "
        "app/report/templates/templatePOUO4.docx напрямую.",
        file=sys.stderr,
    )
    raise SystemExit(2)


if __name__ == "__main__":
    main()
