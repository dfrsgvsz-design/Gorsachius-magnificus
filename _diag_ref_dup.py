# -*- coding: utf-8 -*-
"""
诊断参考文献段 [N][N] 双重编号根因：
- 列出每条文献段的 runs 结构
- 看 [N][N] 是字符串"[N][N]"还是 "[N]" + "[N]" 两个 run
- 同时定位 [3] 文献的字符间距异常根因
"""
import sys, io, re
sys.stdout = io.open(r'f:\Gorsachius magnificus\_diag_ref_dup.txt','w',encoding='utf-8')

from docx import Document
from docx.oxml.ns import qn

DOC = r'E:\大学\万物春\erci\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_最终_格式合规_v3.docx'
doc = Document(DOC)
paras = doc.paragraphs

# 找参考文献段
ref_paras = []
for pi, p in enumerate(paras):
    t = p.text.strip()
    if re.match(r'^\[(\d+)\]', t):
        ref_paras.append((pi, p))

print(f"共找到 {len(ref_paras)} 个参考文献段")

# 取前 5 条 + [3]（关注间距） + 最后 1 条做详细分析
sample_idxs = list(range(min(5, len(ref_paras)))) + [2] + [len(ref_paras)-1]
sample_idxs = sorted(set(sample_idxs))

for si in sample_idxs:
    pi, p = ref_paras[si]
    print(f"\n{'='*80}")
    print(f"文献 #{si+1}  P{pi}")
    print(f"{'='*80}")
    print(f"text = {p.text!r}")
    print(f"runs ({len(p.runs)} 个):")
    for ri, r in enumerate(p.runs):
        rpr = r._element.find(qn('w:rPr'))
        sz = '继承'
        ea = '继承'
        sup = ''
        if rpr is not None:
            sz_el = rpr.find(qn('w:sz'))
            if sz_el is not None:
                sz = sz_el.get(qn('w:val'))
            rf = rpr.find(qn('w:rFonts'))
            if rf is not None:
                ea = rf.get(qn('w:eastAsia')) or '继承'
            va = rpr.find(qn('w:vertAlign'))
            if va is not None:
                sup = f' [{va.get(qn("w:val"))}]'
        print(f"  R{ri:2d} sz={sz} ea={ea}{sup} text={r.text!r}")

# 看 paragraph_format 是否有 numbering / list
print(f"\n{'='*80}")
print(f"段落 numbering/list 属性检查")
print(f"{'='*80}")
for si in range(min(3, len(ref_paras))):
    pi, p = ref_paras[si]
    pPr = p._element.find(qn('w:pPr'))
    if pPr is not None:
        numPr = pPr.find(qn('w:numPr'))
        if numPr is not None:
            print(f"  P{pi}: HAS numPr  -> {numPr.attrib if numPr.attrib else 'has children'}")
            for child in numPr:
                print(f"    child: {child.tag} {child.attrib}")
        else:
            print(f"  P{pi}: 无 numPr (不是 list)")
    else:
        print(f"  P{pi}: 无 pPr")
    print(f"    style.name = {p.style.name!r}")

print(f"\n完成")
