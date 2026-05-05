"""Вспомогательно: вытащить фрагменты OOXML из дампов (разовый анализ)."""
from __future__ import annotations

from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    xml = (root / "out/_head_templatePOUO3_document.xml").read_text(encoding="utf-8")
    lines: list[str] = []

    a = xml.find('<w:t xml:space="preserve"> = 3,7</w:t>')
    lines.append(f"Ds tail pos {a}")
    lines.append(xml[a : a + 520] if a != -1 else "none")

    h = xml.find("<w:t>/2 = ")
    lines.append(f"\nH pos {h}")
    lines.append(xml[h : h + 480] if h != -1 else "none")

    h2 = xml.find('<w:t xml:space="preserve">/2 = </w:t>')
    lines.append(f"\nH2 pos {h2}")
    lines.append(xml[h2 : h2 + 280] if h2 != -1 else "none")

    t = xml.find("ts = 0,92")
    lines.append(f"\nts pos {t}")
    lines.append(xml[t : t + 580] if t != -1 else "none")

    e = xml.find(" = 80 кВт/м")
    lines.append(f"\nEf pos {e}")
    lines.append(xml[e - 120 : e + 320] if e != -1 else "none")

    (root / "out/pouo3_blocks.txt").write_text("\n".join(lines), encoding="utf-8")

    if h2 != -1:
        (root / "out/pouo3_h_full.txt").write_text(xml[h2 : h2 + 400], encoding="utf-8")

    tsf = xml.find('<w:t xml:space="preserve"> = 0,92 × m</w:t>')
    if tsf != -1:
        (root / "out/pouo3_ts_full.txt").write_text(xml[tsf : tsf + 1400], encoding="utf-8")

    print("wrote out/pouo3_blocks.txt")


if __name__ == "__main__":
    main()
