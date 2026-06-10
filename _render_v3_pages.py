# -*- coding: utf-8 -*-
"""
把 v3 PDF 渲染为每页 PNG，命名为 page_001.png ... page_NNN.png
DPI=150 平衡清晰度和文件大小。同时输出总页数和每页文字摘要，便于规划视觉检查。
"""
import sys, io, os, re
sys.stdout = io.open(r'f:\Gorsachius magnificus\_v3_visual\_render.log','w',encoding='utf-8')

import fitz  # PyMuPDF

PDF = r'f:\Gorsachius magnificus\_v3_visual\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_最终_格式合规_v3.pdf'
OUT_DIR = r'f:\Gorsachius magnificus\_v3_visual\pages'
os.makedirs(OUT_DIR, exist_ok=True)

doc = fitz.open(PDF)
n = len(doc)
print(f"PDF 总页数: {n}")
print(f"PDF 文件: {PDF}")
print(f"输出目录: {OUT_DIR}")

# 用 150 dpi 渲染
zoom = 150 / 72.0
mat = fitz.Matrix(zoom, zoom)

page_summaries = []
for i, page in enumerate(doc, start=1):
    pix = page.get_pixmap(matrix=mat)
    out = os.path.join(OUT_DIR, f"page_{i:03d}.png")
    pix.save(out)
    text = page.get_text()
    summary = text.strip()[:120].replace('\n', ' ')
    page_summaries.append((i, summary, os.path.getsize(out)))

print(f"\n所有 {n} 页 PNG 已生成。")
print(f"\n每页摘要（用于规划视觉检查）:")
for i, summ, sz in page_summaries:
    print(f"  P{i:03d} [{sz/1024:.0f} KB]  {summ}")

doc.close()
print("\n完成。")
