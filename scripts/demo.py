"""Create two synthetic source pages with distinct and authored focal regions."""
import json
from pathlib import Path
import sys

import fitz

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
with fitz.open() as doc:
    for number in (1, 2):
        page = doc.new_page(width=792, height=612)
        page.insert_text((60, 75), f"Document walkthrough | page {number}", fontsize=27)
        page.draw_rect((58, 112, 383, 550), fill=(.9, .95, .98))
        page.draw_rect((410, 112, 735, 550), fill=(.93, .96, .9))
        for x, label in ((81, "Input and conditions"), (433, "Result and checks")):
            for line in range(6):
                page.insert_text((x, 160 + line * 66), f"{label}: example {line + 1}", fontsize=17)
    scan = doc[1].get_pixmap(matrix=fitz.Matrix(2, 2))
    doc.delete_page(1)
    doc.new_page(width=792, height=612).insert_image(fitz.Rect(0, 0, 792, 612), pixmap=scan)
    doc.save(root / "demo.pdf")
(root / "notes.json").write_text(json.dumps([{
    "page": 1, "heading": "讀懂兩個區塊", "spoken_title": "文件動態導讀",
    "summary": "先看全頁，再依序對照條件和結果。",
    "focuses": [
        {"rect": [.07, .18, .49, .9], "caption": "左側列出條件。先辨認每一項輸入。"},
        {"rect": [.51, .18, .94, .9], "caption": "右側列出結果。往回比對左側條件。"},
    ],
}]))
(root / "request.json").write_text(json.dumps({"documents": [
    {"id": "demo", "title": "文件動態導讀", "pdf": "demo.pdf", "notes": "notes.json"}
]}))
