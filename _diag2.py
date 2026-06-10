# -*- coding: utf-8 -*-
"""
诊断 v2 文档（输出到 UTF-8 文件，避免 PowerShell GBK 编码问题）：
1. 上下标问题
2. 交叉引用问题
3. 公式编号
"""
import re
from docx import Document
from docx.oxml.ns import qn
from collections import defaultdict

DOC = r"E:\大学\万物春\erci\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_最终_格式合规_v2.docx"
LOG = r"f:\Gorsachius magnificus\_diag2.log"

doc = Document(DOC)
paras = doc.paragraphs
lines = []
def w(s=""): lines.append(str(s))

w("=" * 80)
w("【一】上下标诊断")
w("=" * 80)

# 1.a 当前 vertAlign 的 run，按段落聚合
w("\n--- 1.a vertAlign run 总数及按段分布 ---")
vert_by_para = defaultdict(list)
total_vert = 0
empty_vert = 0
for pi, p in enumerate(paras):
    for ri, r in enumerate(p.runs):
        rpr = r._element.find(qn('w:rPr'))
        if rpr is not None:
            va = rpr.find(qn('w:vertAlign'))
            if va is not None:
                val = va.get(qn('w:val'))
                vert_by_para[pi].append((ri, val, r.text))
                total_vert += 1
                if not r.text:
                    empty_vert += 1

w(f"vertAlign run 总数: {total_vert}（其中空 run = {empty_vert}）")
w(f"涉及段落数: {len(vert_by_para)}")
w("\n按段落聚合（仅显示有意义内容）:")
for pi in sorted(vert_by_para):
    runs = vert_by_para[pi]
    txts = [t for _,_,t in runs if t]
    if not txts:
        # 全空 run 段也单独标记
        w(f"  P{pi}: {len(runs)} 空 superscript run（全废）, ctx={paras[pi].text[:60]!r}")
    else:
        w(f"  P{pi}: 共 {len(runs)} run，有文本 {len(txts)} 个: {txts}, ctx={paras[pi].text[:60]!r}")

# 1.b 可疑 ASCII 上下标候选（先用 ord 检查避免编码问题）
w("\n--- 1.b 可疑 ASCII 上下标候选 ---")
patterns_sup = [
    (r'\bkm2\b', 'km2 -> km^2'),
    (r'\bkm3\b', 'km3 -> km^3'),
    (r'\bm2\b(?!l)', 'm2 -> m^2'),
    (r'\bm3\b(?!\w)', 'm3 -> m^3'),
    (r'\bR2\b', 'R2 -> R^2'),
    (r'\bCO2\b', 'CO2 -> CO_2'),
    (r'\bSO2\b', 'SO2 -> SO_2'),
    (r'\bH2O\b', 'H2O -> H_2O'),
    (r'\bNO2\b', 'NO2 -> NO_2'),
    (r'\bNH4\b', 'NH4 -> NH_4'),
    (r'10\^?\d+', '10n -> 10^n'),
    (r'x_\{?[a-z]+\}?', 'LaTeX subscript residue'),
    (r"\^\\?prime", "LaTeX prime residue"),
    (r"_\{?ij\}?", "subscript ij residue"),
]
hits = defaultdict(list)
for pi, p in enumerate(paras):
    text = p.text
    if not text:
        continue
    for pat, desc in patterns_sup:
        for m in re.finditer(pat, text):
            hits[desc].append((pi, m.group(), text[max(0,m.start()-25):m.end()+25]))

for desc, hs in hits.items():
    if not hs:
        continue
    w(f"\n  >>> {desc}  ({len(hs)} hits)")
    for pi, kw, ctx in hs[:10]:
        w(f"      P{pi} '{kw}' | ...{ctx}...")
    if len(hs) > 10:
        w(f"      ...还有 {len(hs)-10} 处")

# 1.c 公式纯文本残留
w("\n--- 1.c 公式纯文本残留 (LaTeX 命令未渲染) ---")
residue = []
for pi, p in enumerate(paras):
    text = p.text
    if re.search(r'\\(prime|alpha|beta|gamma|theta|sum|frac|sqrt|times|cdot|cdots|leq|geq|neq)\b', text):
        residue.append((pi, text[:150]))
    if re.search(r'\$[^$\n]+\$', text):
        residue.append((pi, text[:150]))
w(f"共 {len(residue)} 处可疑公式残留:")
for pi, t in residue[:15]:
    w(f"  P{pi}: {t!r}")

# ============================================================
# 【二】交叉引用诊断
# ============================================================
w("\n" + "=" * 80)
w("【二】交叉引用诊断")
w("=" * 80)

# 标题段
caption_fig = {}
caption_tab = {}
fig_caption_re = re.compile(r'^图\s*(\d+)[\s：:]')
tab_caption_re = re.compile(r'^表\s*(\d+)[\s：:]')
caption_paras = set()
for pi, p in enumerate(paras):
    t = p.text.strip()
    m = fig_caption_re.match(t)
    if m:
        caption_paras.add(pi); caption_fig[pi] = int(m.group(1)); continue
    m = tab_caption_re.match(t)
    if m:
        caption_paras.add(pi); caption_tab[pi] = int(m.group(1))

w(f"\n--- 2.a 标题段 ---")
w(f"图标题段 {len(caption_fig)} 个，编号 = {sorted(caption_fig.values())}")
w(f"表标题段 {len(caption_tab)} 个，编号 = {sorted(caption_tab.values())}")

# 正文引用
ref_patterns = {
    '图': re.compile(r'图\s*(\d+)'),
    '表': re.compile(r'表\s*(\d+)'),
    '公式': re.compile(r'公式\s*[（(]?(\d+)[）)]?'),
    '式': re.compile(r'式\s*[（(](\d+)[）)]'),
}
xref = {k: [] for k in ref_patterns}
for pi, p in enumerate(paras):
    if pi in caption_paras:
        continue
    t = p.text
    if not t: continue
    for kind, pat in ref_patterns.items():
        for m in pat.finditer(t):
            xref[kind].append((pi, int(m.group(1)), t[max(0,m.start()-15):m.end()+15]))

w(f"\n--- 2.b 正文引用统计 ---")
for kind, hs in xref.items():
    if not hs: continue
    nums = sorted(set(h[1] for h in hs))
    w(f"\n  「{kind}N」共 {len(hs)} 处，编号集 = {nums}")
    for pi, n, c in hs[:40]:
        w(f"    P{pi} 「{kind}{n}」: ...{c}...")
    if len(hs) > 40:
        w(f"    ...还有 {len(hs)-40} 处")

# 越界
w(f"\n--- 2.c 越界检查 ---")
fig_max = max(caption_fig.values(), default=0)
tab_max = max(caption_tab.values(), default=0)
w(f"实际图编号: 1~{fig_max}")
w(f"实际表编号: 1~{tab_max}")
oob_fig = [x for x in xref['图'] if x[1] < 1 or x[1] > fig_max]
oob_tab = [x for x in xref['表'] if x[1] < 1 or x[1] > tab_max]
w(f"图引用越界: {len(oob_fig)} 处")
for pi,n,c in oob_fig:
    w(f"  P{pi} 图{n}: ...{c}...")
w(f"表引用越界: {len(oob_tab)} 处")
for pi,n,c in oob_tab:
    w(f"  P{pi} 表{n}: ...{c}...")

# 公式定义
w(f"\n--- 2.d 公式定义段 (形如 (N) 单独结尾) ---")
formula_def = []
for pi, p in enumerate(paras):
    t = p.text.strip()
    m = re.search(r'[（(](\d+)[）)]\s*$', t)
    if m and len(t) < 80:  # 限制段长，排除正文中的普通括号
        formula_def.append((pi, int(m.group(1)), t[:80]))
w(f"找到 {len(formula_def)} 个候选公式编号段:")
for pi, n, t in formula_def[:25]:
    w(f"  P{pi} ({n}): {t!r}")

# 公式编号范围
formula_max = max([n for _,n,_ in formula_def], default=0)
w(f"\n推定公式最大编号: {formula_max}")
oob_form = [x for x in xref['公式'] + xref['式'] if x[1] < 1 or x[1] > formula_max]
w(f"公式引用越界: {len(oob_form)} 处")
for pi,n,c in oob_form:
    w(f"  P{pi} 公式{n}: ...{c}...")

w("\n" + "=" * 80)
w("诊断完成")

with open(LOG, 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))
print(f"OK -> {LOG}")
print(f"total_vert={total_vert} empty_vert={empty_vert} vert_paras={len(vert_by_para)}")
print(f"fig_titles={len(caption_fig)} tab_titles={len(caption_tab)} formula_def={len(formula_def)}")
print(f"oob_fig={len(oob_fig)} oob_tab={len(oob_tab)} oob_form={len(oob_form)}")
