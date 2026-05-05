"""
Восстановление шаблонов POUO3/POUO4 из последней версии в git (HEAD)
и точечная замена расчётных чисел на плейсхолдеры Jinja (без изменения структуры OOXML).

Запуск из корня репозитория:
  python scripts/restore_pouo3_pouo4_templates_jinja.py

При ошибке записи в app/report/templates (файл занят Word) результат пишется в out/restored_templates/.
"""
from __future__ import annotations

import io
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app/report/templates"
OUT_FALLBACK = ROOT / "out/restored_templates"

GIT_OBJECT_POUO3 = "HEAD:app/report/templates/templatePOUO3.docx"
GIT_OBJECT_POUO4 = "HEAD:app/report/templates/templatePOUO4.docx"


def _git_blob(ref: str) -> bytes:
    return subprocess.check_output(["git", "show", ref], cwd=ROOT)


def _read_document_xml(docx_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        return zin.read("word/document.xml").decode("utf-8")


def _write_docx(docx_bytes: bytes, new_document_xml: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        names = zin.namelist()
        payloads = {n: zin.read(n) for n in names}
    payloads["word/document.xml"] = new_document_xml.encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, payloads[name])
    dest.write_bytes(buf.getvalue())


def _apply(xml: str, old: str, new: str, label: str, log: list[str]) -> str:
    n = xml.count(old)
    if n == 0:
        log.append(f"SKIP\t{label}\t(matches=0)")
        return xml
    log.append(f"OK\t{label}\tx{n}")
    return xml.replace(old, new)


def _apply_pouo4(xml: str, log: list[str]) -> str:
    xml = _apply(
        xml,
        "<w:t>0,514</w:t>",
        "<w:t>{{ indoor_explosion.delta_p }}</w:t>",
        "POUO4 delta_p: <w:t>0,514</w:t>",
        log,
    )
    xml = _apply(
        xml,
        '<w:t xml:space="preserve">0,514 </w:t>',
        '<w:t xml:space="preserve">{{ indoor_explosion.delta_p }} </w:t>',
        "POUO4 delta_p: trailing space run",
        log,
    )
    xml = _apply(
        xml,
        "избыточном давлении 0,514 кПа",
        "избыточном давлении {{ indoor_explosion.delta_p }} кПа",
        "POUO4 delta_p: plain text phrase",
        log,
    )
    xml = _apply(
        xml,
        '<w:t xml:space="preserve"> + 0,267 = 0,672</w:t>',
        '<w:t xml:space="preserve"> + 0,267 = {{ indoor_explosion.mass_total }}</w:t>',
        "POUO4 Mг (сумма с 0,267)",
        log,
    )
    xml = _apply(
        xml,
        '<w:t xml:space="preserve"> × Z = 0,672× 0,5 = 0,336 кг (для горючих газов Z = 0,5)</w:t>',
        '<w:t xml:space="preserve"> × Z = {{ indoor_explosion.mass_total }}× 0,5 = {{ indoor_explosion.mass_cloud }} кг (для горючих газов Z = 0,5)</w:t>',
        "POUO4 mг (облако)",
        log,
    )
    xml = _apply(
        xml,
        "равной 0,672 кг.",
        "равной {{ indoor_explosion.mass_total }} кг.",
        "POUO4 текст «равной … кг»",
        log,
    )
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
    xml = _apply(xml, ds_old, ds_new, "POUO4 Ds (числовой результат)", log)

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
    xml = _apply(xml, h_old, h_new, "POUO4 H", log)

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
    xml = _apply(xml, ts_old, ts_new, "POUO4 ts", log)

    xml = _apply(
        xml,
        "<w:t xml:space=\"preserve\"> = 80 кВт/м</w:t></w:r><w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/><w:vertAlign w:val=\"superscript\"/></w:rPr><w:t>2</w:t></w:r>",
        "<w:t xml:space=\"preserve\"> = {{ fireball_params.Ef_kw_m2 }} кВт/м</w:t></w:r><w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/><w:vertAlign w:val=\"superscript\"/></w:rPr><w:t>2</w:t></w:r>",
        "POUO4 Ef",
        log,
    )
    return xml


def _apply_pouo3(xml: str, log: list[str]) -> str:
    xml = _apply(
        xml,
        "<w:t>0,514</w:t>",
        "<w:t>{{ indoor_explosion.delta_p }}</w:t>",
        "POUO3 delta_p: <w:t>0,514</w:t>",
        log,
    )
    xml = _apply(
        xml,
        '<w:t xml:space="preserve">0,514 </w:t>',
        '<w:t xml:space="preserve">{{ indoor_explosion.delta_p }} </w:t>',
        "POUO3 delta_p: trailing space run",
        log,
    )
    xml = _apply(
        xml,
        "избыточном давлении 0,514 кПа",
        "избыточном давлении {{ indoor_explosion.delta_p }} кПа",
        "POUO3 delta_p: plain text phrase",
        log,
    )
    xml = _apply(
        xml,
        '<w:t xml:space="preserve"> + 0,267 = 0,672</w:t>',
        '<w:t xml:space="preserve"> + 0,267 = {{ indoor_explosion.mass_total }}</w:t>',
        "POUO3 Mг (сумма с 0,267)",
        log,
    )
    xml = _apply(
        xml,
        '<w:t xml:space="preserve"> × Z = 0,672× 0,5 = 0,336 кг (для горючих газов Z = 0,5)</w:t>',
        '<w:t xml:space="preserve"> × Z = {{ indoor_explosion.mass_total }}× 0,5 = {{ indoor_explosion.mass_cloud }} кг (для горючих газов Z = 0,5)</w:t>',
        "POUO3 mг (облако)",
        log,
    )
    ds_old = (
        '<w:r w:rsidRPr="0066523E"><w:rPr><w:rFonts w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        '<w:t xml:space="preserve"> = 3,7</w:t></w:r><w:r><w:rPr><w:rFonts w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        '<w:t xml:space="preserve">4 </w:t></w:r><w:r w:rsidRPr="0066523E"><w:rPr><w:rFonts w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        "<w:t>м</w:t></w:r>"
    )
    ds_new = (
        '<w:r w:rsidRPr="0066523E"><w:rPr><w:rFonts w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        '<w:t xml:space="preserve"> = {{ fireball_params.Ds_m }} м</w:t></w:r>'
    )
    xml = _apply(xml, ds_old, ds_new, "POUO3 Ds (числовой результат)", log)

    h_old = (
        '<w:r w:rsidRPr="0066523E"><w:rPr><w:rFonts w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        '<w:t xml:space="preserve">/2 = </w:t></w:r><w:r><w:rPr><w:rFonts w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        '<w:t>1,87</w:t></w:r><w:r w:rsidRPr="0066523E"><w:rPr><w:rFonts w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        '<w:t xml:space="preserve"> м</w:t></w:r>'
    )
    h_new = (
        '<w:r w:rsidRPr="0066523E"><w:rPr><w:rFonts w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        '<w:t xml:space="preserve">/2 = {{ fireball_params.H_m }} м</w:t></w:r>'
    )
    xml = _apply(xml, h_old, h_new, "POUO3 H", log)

    ts_old = (
        '<w:r w:rsidRPr="0066523E"><w:rPr><w:rFonts w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        '<w:t xml:space="preserve"> = 0,6</w:t></w:r><w:r><w:rPr><w:rFonts w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        '<w:t>6</w:t></w:r><w:r w:rsidRPr="0066523E"><w:rPr><w:rFonts w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        '<w:t xml:space="preserve"> сек</w:t></w:r>'
    )
    ts_new = (
        '<w:r w:rsidRPr="0066523E"><w:rPr><w:rFonts w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>'
        '<w:t xml:space="preserve"> = {{ fireball_params.ts_s }} сек</w:t></w:r>'
    )
    xml = _apply(xml, ts_old, ts_new, "POUO3 ts (числовой результат)", log)

    xml = _apply(
        xml,
        "<w:t xml:space=\"preserve\"> = 80 кВт/м</w:t></w:r><w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/><w:vertAlign w:val=\"superscript\"/></w:rPr><w:t>2</w:t></w:r>",
        "<w:t xml:space=\"preserve\"> = {{ fireball_params.Ef_kw_m2 }} кВт/м</w:t></w:r><w:r w:rsidRPr=\"0066523E\"><w:rPr><w:rFonts w:cs=\"Times New Roman\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/><w:vertAlign w:val=\"superscript\"/></w:rPr><w:t>2</w:t></w:r>",
        "POUO3 Ef",
        log,
    )
    return xml


def _structure_counts(xml: str) -> tuple[int, int]:
    # не использовать xml.count("<w:p") — совпадает с префиксом <w:pPr
    p = len(re.findall(r"<w:p(?:\s[^>]*)?>", xml))
    tbl = len(re.findall(r"<w:tbl(?:\s[^>]*)?>", xml))
    return p, tbl


def main() -> None:
    report_lines: list[str] = []

    pairs = [
        ("POUO3", GIT_OBJECT_POUO3, TEMPLATES / "templatePOUO3.docx", _apply_pouo3),
        ("POUO4", GIT_OBJECT_POUO4, TEMPLATES / "templatePOUO4.docx", _apply_pouo4),
    ]

    for label, git_ref, dest, fn in pairs:
        raw = _git_blob(git_ref)
        xml0 = _read_document_xml(raw)
        p0, t0 = _structure_counts(xml0)
        log: list[str] = []
        xml1 = fn(xml0, log)
        p1, t1 = _structure_counts(xml1)
        report_lines.append(f"=== {label} ===")
        report_lines.append(f"git {git_ref}")
        report_lines.append(f"<w:p count {p0} -> {p1}  OK={p0 == p1}")
        report_lines.append(f"<w:tbl count {t0} -> {t1}  OK={t0 == t1}")
        report_lines.extend(log)
        report_lines.append("")
        if p0 != p1 or t0 != t1:
            raise RuntimeError(f"{label}: изменилась структура документа (p/tbl).")

        targets = [dest, OUT_FALLBACK / dest.name]
        written = False
        for path in targets:
            try:
                _write_docx(raw, xml1, path)
                report_lines.append(f"written {path}")
                written = True
                break
            except OSError as e:
                report_lines.append(f"FAILED write {path}: {e}")
        if not written:
            raise RuntimeError(f"{label}: не удалось записать ни в одно место.")

    rep_path = ROOT / "out/template_jinja_restore_report.txt"
    rep_path.parent.mkdir(parents=True, exist_ok=True)
    rep_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Report written: {rep_path}")


if __name__ == "__main__":
    main()
