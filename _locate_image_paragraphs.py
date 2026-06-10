# -*- coding: utf-8 -*-
"""定位所有含嵌入图片的段落 + 对应标题段"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from docx import Document
from docx.oxml.ns import qn

DOC = r'E:\大学\万物春\erci\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_最终_格式合规.docx'
doc = Document(DOC)
paras = doc.paragraphs

# 含图片的段（用 w:drawing 或 w:pic 或 w:object 判断）
image_paras = []
for i, p in enumerate(paras):
    has_drawing = len(p._p.findall('.//' + qn('w:drawing'))) > 0
    has_pic = len(p._p.findall('.//' + qn('w:pict'))) > 0
    has_object = len(p._p.findall('.//' + qn('w:object'))) > 0
    if has_drawing or has_pic or has_object:
        image_paras.append((i, has_drawing, has_pic, has_object))

print(f'==== 含图片的段落数: {len(image_paras)} ====\n')
for i, hd, hp, ho in image_paras:
    tags = []
    if hd: tags.append('drawing')
    if hp: tags.append('pict')
    if ho: tags.append('object')
    # 邻近段（前1段+后1段）
    prev_text = paras[i-1].text[:60] if i > 0 else ''
    next_text = paras[i+1].text[:60] if i+1 < len(paras) else ''
    cur_text = paras[i].text[:60]
    print(f'P{i:3d} [{",".join(tags):10s}] cur="{cur_text}"')
    print(f'      ↑P{i-1:3d}: "{prev_text}"')
    print(f'      ↓P{i+1:3d}: "{next_text}"')
    print()

print('\n==== 图标题段 + 临近含图段映射 ====')
for i, p in enumerate(paras):
    t = p.text.strip()
    m = re.match(r'^图\s*\d+', t)
    if m:
        # 检查前后段是否含图
        prev_has_img = False
        next_has_img = False
        if i > 0:
            prev_has_img = len(paras[i-1]._p.findall('.//' + qn('w:drawing'))) > 0
        if i+1 < len(paras):
            next_has_img = len(paras[i+1]._p.findall('.//' + qn('w:drawing'))) > 0
        marker = ''
        if prev_has_img: marker += '↑img '
        if next_has_img: marker += '↓img '
        print(f'P{i}: {t[:50]}  ({marker})')
