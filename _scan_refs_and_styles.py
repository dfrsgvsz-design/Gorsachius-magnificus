# -*- coding: utf-8 -*-
"""扫描参考文献完整范围 + 一级标题/正文样式样本"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from docx import Document
from docx.oxml.ns import qn

DOC = r'E:\大学\万物春\erci\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_最终.docx'
doc = Document(DOC)
paras = doc.paragraphs

print('==== 参考文献节扫描 ====')
ref_start = -1
for i, p in enumerate(paras):
    if p.text.strip() == '参考文献':
        ref_start = i
        break
print(f'"参考文献" 标题段: P{ref_start}')

ref_items = []
ref_end = -1
for i in range(ref_start + 1, len(paras)):
    t = paras[i].text.strip()
    if not t:
        continue
    if t == '致谢' or t == '附录':
        ref_end = i
        print(f'参考文献节结束于 P{i}: "{t}"')
        break
    ref_items.append((i, t))

print(f'\n参考文献条目数: {len(ref_items)}')
for idx, (i, t) in enumerate(ref_items, 1):
    print(f'  [{idx}] P{i}: {t[:90]}')

print('\n==== Heading 1 样式样本 ====')
h1_count = 0
for i, p in enumerate(paras):
    if p.style.name == 'Heading 1' and p.text.strip():
        h1_count += 1
        if h1_count <= 3 and p.runs:
            run = p.runs[0]
            size = run.font.size
            rPr = run._element.find(qn('w:rPr'))
            ea, asc = None, None
            if rPr is not None:
                rFonts = rPr.find(qn('w:rFonts'))
                if rFonts is not None:
                    ea = rFonts.get(qn('w:eastAsia'))
                    asc = rFonts.get(qn('w:ascii'))
            print(f'  P{i}: "{p.text[:30]}" size={size}, ascii={asc}, eastAsia={ea}')
print(f'Heading 1 总数: {h1_count}')

print('\n==== Normal 正文样式样本（前 3 个长段） ====')
n_count = 0
for i, p in enumerate(paras):
    if p.style.name == 'Normal' and len(p.text) > 50:
        n_count += 1
        if n_count <= 3 and p.runs:
            run = p.runs[0]
            size = run.font.size
            rPr = run._element.find(qn('w:rPr'))
            ea, asc = None, None
            if rPr is not None:
                rFonts = rPr.find(qn('w:rFonts'))
                if rFonts is not None:
                    ea = rFonts.get(qn('w:eastAsia'))
                    asc = rFonts.get(qn('w:ascii'))
            print(f'  P{i}: size={size}, ascii={asc}, eastAsia={ea} | "{p.text[:50]}"')
