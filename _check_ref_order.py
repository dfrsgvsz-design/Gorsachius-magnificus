# -*- coding: utf-8 -*-
"""检查 v4 docx 内参考文献段落的真实顺序"""
import sys, io, re
sys.stdout = io.open(r'f:\Gorsachius magnificus\_check_ref_order.txt','w',encoding='utf-8')

from docx import Document
from docx.oxml.ns import qn

V3 = r'E:\大学\万物春\erci\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_最终_格式合规_v3.docx'
V4 = r'E:\大学\万物春\erci\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_最终_格式合规_v4.docx'

for label, path in [("v3", V3), ("v4", V4)]:
    print(f"\n{'='*70}\n{label}: {path}\n{'='*70}")
    doc = Document(path)
    paras = doc.paragraphs
    print(f"段落数: {len(paras)}")
    # 找参考文献段
    refs = []
    for pi, p in enumerate(paras):
        t = p.text.strip()
        m = re.match(r'^\[(\d+)\]', t)
        if m:
            # 跳过 TOC 样式段
            if 'toc' in p.style.name.lower():
                continue
            pPr = p._element.find(qn('w:pPr'))
            has_numpr = False
            if pPr is not None:
                numPr = pPr.find(qn('w:numPr'))
                has_numpr = numPr is not None
            refs.append((pi, int(m.group(1)), has_numpr, t[:80]))
    print(f"\n参考文献段 {len(refs)} 个（按 docx 内段落索引排序）:")
    for pi, n, has_np, text in refs:
        mark = '[LIST]' if has_np else '[NORMAL]'
        print(f"  P{pi:3d}  [{n}]  {mark}  {text}")
    # 特别检查：段落索引是否与编号对应
    if refs:
        nums_by_order = [n for _, n, _, _ in refs]
        print(f"\n段落顺序下的文献编号列: {nums_by_order}")
        if nums_by_order == sorted(nums_by_order):
            print("✓ 段落索引顺序与编号顺序一致")
        else:
            print("✗ 段落索引顺序与编号顺序不一致!")
