# -*- coding: utf-8 -*-
"""提取 v4 PDF 每页纯文本前 200 字符，确认参考文献实际渲染顺序"""
import sys, io
sys.stdout = io.open(r'f:\Gorsachius magnificus\_v4_pdf_scan.txt','w',encoding='utf-8')

import fitz
PDF = r'f:\Gorsachius magnificus\_v4_visual\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_最终_格式合规_v4.pdf'
doc = fitz.open(PDF)
for i, page in enumerate(doc, start=1):
    text = page.get_text().strip().replace('\n', ' ')[:180]
    print(f"P{i:03d}: {text}")
doc.close()
