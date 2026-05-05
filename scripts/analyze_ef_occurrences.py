"""Разовый анализ вхождений блока Ef в templatePOUO4 (HEAD)."""
from __future__ import annotations

import io
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NEEDLE = (
    '<w:t xml:space="preserve"> = 80 кВт/м</w:t></w:r><w:r w:rsidRPr="0066523E">'
    '<w:rPr><w:rFonts w:cs="Times New Roman"/><w:sz w:val="24"/><w:szCs w:val="24"/>'
    '<w:vertAlign w:val="superscript"/></w:rPr><w:t>2</w:t></w:r>'
)


def main() -> None:
    raw = subprocess.check_output(
        ["git", "show", "HEAD:app/report/templates/templatePOUO4.docx"],
        cwd=ROOT,
    )
    xml = zipfile.ZipFile(io.BytesIO(raw)).read("word/document.xml").decode("utf-8")
    idx = 0
    k = 0
    while True:
        i = xml.find(NEEDLE, idx)
        if i == -1:
            break
        k += 1
        prev = xml[max(0, i - 400) : i]
        chunk = prev + "\n---NEEDLE---\n" + xml[i : i + len(NEEDLE)]
        (ROOT / "out" / f"ef_occ_{k}_context.txt").write_text(chunk, encoding="utf-8")
        idx = i + 1
    print("occurrences", k)


if __name__ == "__main__":
    main()
