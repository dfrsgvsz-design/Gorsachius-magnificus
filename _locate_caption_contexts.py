# -*- coding: utf-8 -*-
"""
定位每个图/表标题段的精确位置和上下文，规划 F3 引用插入点。
输出到 UTF-8 文件，避免编码问题。
"""
import re
from docx import Document
from docx.oxml.ns import qn

DOC = r"E:\大学\万物春\erci\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_最终_格式合规_v2.docx"
LOG = r"f:\Gorsachius magnificus\_locate_captions.txt"

doc = Document(DOC)
paras = doc.paragraphs
lines = []
def w(s=""): lines.append(str(s))

fig_re = re.compile(r'^图\s*(\d+)[\s：:]')
tab_re = re.compile(r'^表\s*(\d+)[\s：:]')

w("=" * 80)
w("【一】全部图标题段（精确位置+完整标题）")
w("=" * 80)
fig_caps = []
for pi, p in enumerate(paras):
    m = fig_re.match(p.text.strip())
    if m:
        fig_caps.append((pi, int(m.group(1)), p.text.strip()))
for pi, n, t in fig_caps:
    w(f"  P{pi:3d}  图{n:2d}  : {t!r}")

w("\n" + "=" * 80)
w("【二】全部表标题段（精确位置+完整标题）")
w("=" * 80)
tab_caps = []
for pi, p in enumerate(paras):
    m = tab_re.match(p.text.strip())
    if m:
        tab_caps.append((pi, int(m.group(1)), p.text.strip()))
for pi, n, t in tab_caps:
    w(f"  P{pi:3d}  表{n:2d}  : {t!r}")

# 未引用的图表
xref_fig_found = {1, 2, 4, 5, 8, 9, 13}
xref_tab_found = {1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}
missing_fig = [3, 6, 7, 10, 11, 12, 14, 15, 16]
missing_tab = [2, 3]

w("\n" + "=" * 80)
w("【三】未引用图表的标题段及前后 8 段上下文（用于规划插入点）")
w("=" * 80)

for n in missing_fig:
    for pi, num, t in fig_caps:
        if num == n:
            w(f"\n>>> 图{n}（位于 P{pi}）: {t!r}")
            w(f"    上文 P{pi-8}..P{pi-1}:")
            for i in range(max(0, pi-8), pi):
                txt = paras[i].text.strip()
                if txt:
                    w(f"      P{i}: {txt[:120]}")
            w(f"    下文 P{pi+1}..P{pi+8}:")
            for i in range(pi+1, min(len(paras), pi+9)):
                txt = paras[i].text.strip()
                if txt:
                    w(f"      P{i}: {txt[:120]}")
            break

for n in missing_tab:
    for pi, num, t in tab_caps:
        if num == n:
            w(f"\n>>> 表{n}（位于 P{pi}）: {t!r}")
            w(f"    上文 P{pi-8}..P{pi-1}:")
            for i in range(max(0, pi-8), pi):
                txt = paras[i].text.strip()
                if txt:
                    w(f"      P{i}: {txt[:120]}")
            w(f"    下文 P{pi+1}..P{pi+8}:")
            for i in range(pi+1, min(len(paras), pi+9)):
                txt = paras[i].text.strip()
                if txt:
                    w(f"      P{i}: {txt[:120]}")
            break

# 公式编号探查 —— 扫描含 OMML 公式 + 段尾数字编号
w("\n" + "=" * 80)
w("【四】公式编号探查（找 OMML + 段尾编号）")
w("=" * 80)
NS_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
for pi, p in enumerate(paras):
    el = p._element
    has_omml = el.find(f".//{{{NS_M}}}oMath") is not None or el.find(f".//{{{NS_M}}}oMathPara") is not None
    text = p.text.strip()
    m = re.search(r'[（(](\d+(?:\.\d+)?)[）)]\s*$', text)
    if has_omml or m:
        marker = "OMML" if has_omml else "---"
        num = m.group(1) if m else ""
        w(f"  P{pi} [{marker}] tail_num={num!r} text={text[:100]!r}")

# 引用上下标的目标段落原文
w("\n" + "=" * 80)
w("【五】上下标修复目标段原文（精确）")
w("=" * 80)
target_paras = [101, 121, 406, 422]
for pi in target_paras:
    if pi < len(paras):
        w(f"\n>>> P{pi}: {paras[pi].text}")
        for ri, r in enumerate(paras[pi].runs):
            rpr = r._element.find(qn('w:rPr'))
            va_val = None
            if rpr is not None:
                va = rpr.find(qn('w:vertAlign'))
                if va is not None:
                    va_val = va.get(qn('w:val'))
            w(f"    R{ri:2d} [{va_val}] {r.text!r}")

with open(LOG, 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))
print(f"OK -> {LOG}")
print(f"fig_caps={len(fig_caps)} tab_caps={len(tab_caps)}")
