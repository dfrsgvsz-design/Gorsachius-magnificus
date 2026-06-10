# -*- coding: utf-8 -*-
"""v4 PDF → PNG 渲染"""
import sys, io, os
sys.stdout = io.open(r'f:\Gorsachius magnificus\_v4_visual\_render.log','w',encoding='utf-8')

import fitz
PDF = r'f:\Gorsachius magnificus\_v4_visual\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_最终_格式合规_v4.pdf'
OUT_DIR = r'f:\Gorsachius magnificus\_v4_visual\pages'
os.makedirs(OUT_DIR, exist_ok=True)

doc = fitz.open(PDF)
n = len(doc)
print(f"PDF 总页数: {n}")
mat = fitz.Matrix(150/72.0, 150/72.0)
for i, page in enumerate(doc, start=1):
    pix = page.get_pixmap(matrix=mat)
    pix.save(os.path.join(OUT_DIR, f"page_{i:03d}.png"))
doc.close()
print(f"{n} 页 PNG 已生成 -> {OUT_DIR}")
