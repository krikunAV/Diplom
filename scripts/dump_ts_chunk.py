from pathlib import Path

xml = Path("out/_head_templatePOUO3_document.xml").read_text(encoding="utf-8")
start = xml.find('<w:t xml:space="preserve"> = 0,92 × m</w:t>')
Path("out/pouo3_ts_chunk.txt").write_text(xml[start : start + 2500], encoding="utf-8")
print("start", start)
