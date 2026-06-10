# -*- coding: utf-8 -*-
"""
诊断 v2 文档：
1. 上下标问题
   a. 当前实际带 w:vertAlign 的 run 列表
   b. 可疑应为上下标但用 ASCII 文本的位置（km2, m2, R2, CO2, x_ij, H2O, SO2 等）
   c. 公式纯文本残留
2. 交叉引用问题
"""
import re
import sys
import io
from docx import Document
from docx.oxml.ns import qn
from collections import Counter, defaultdict

# 重定向 stdout 到 UTF-8 文件，避免 GBK 编码错误
LOG_PATH = r"f:\Gorsachius magnificus\_diagnose_subsup_xref.log"
sys.stdout = io.open(LOG_PATH, 'w', encoding='utf-8')

DOC = r"E:\大学\万物春\erci\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_最终_格式合规_v2.docx"

doc = Document(DOC)
paras = doc.paragraphs

print("=" * 80)
print("【一】上下标诊断")
print("=" * 80)

# 1.a 当前 vertAlign 带的 run
print("\n--- 1.a 当前已带 vertAlign 的 run ---")
vert_cnt = 0
vert_examples = []
for pi, p in enumerate(paras):
    for ri, r in enumerate(p.runs):
        rpr = r._element.find(qn('w:rPr'))
        if rpr is not None:
            va = rpr.find(qn('w:vertAlign'))
            if va is not None:
                val = va.get(qn('w:val'))
                vert_cnt += 1
                if len(vert_examples) < 25:
                    ctx = p.text[:50]
                    vert_examples.append((pi, ri, val, r.text, ctx))

print(f"vertAlign run 总数: {vert_cnt}")
for pi, ri, val, txt, ctx in vert_examples:
    print(f"  P{pi} R{ri} [{val}] '{txt}' | ctx={ctx!r}")

# 1.b 可疑应为上下标但用 ASCII 文本
print("\n--- 1.b 可疑 ASCII 上下标候选 ---")
# 匹配: km2 km3 m2 m3 R2 CO2 H2O SO2 NO2 等
patterns_sup = [
    (r'\bkm2\b', '应为 km²'),
    (r'\bkm3\b', '应为 km³'),
    (r'\bm2\b(?!l)', '应为 m²'),  # 排除 m2l
    (r'\bm3\b', '应为 m³'),
    (r'\bR2\b', '应为 R²'),
    (r'\bCO2\b', '应为 CO₂'),
    (r'\bSO2\b', '应为 SO₂'),
    (r'\bH2O\b', '应为 H₂O'),
    (r'\bNO2\b', '应为 NO₂'),
    (r'\bNH4\b', '应为 NH₄'),
    (r'10\^\d', '应为 10ⁿ'),
    (r'x_\{?[a-z]+\}?', 'LaTeX 下标残留'),
    (r'\^\\?prime', "LaTeX 撇号残留 (^\\prime)"),
    (r'\^\{?[a-zA-Z0-9]+\}?', 'LaTeX 上标残留'),
]
suspicious_hits = defaultdict(list)
for pi, p in enumerate(paras):
    text = p.text
    if not text:
        continue
    for pat, desc in patterns_sup:
        for m in re.finditer(pat, text):
            suspicious_hits[desc].append((pi, m.group(), text[max(0,m.start()-20):m.end()+20]))

for desc, hits in suspicious_hits.items():
    if hits:
        print(f"\n  >>> {desc}  ({len(hits)} 处)")
        for pi, kw, ctx in hits[:8]:
            print(f"      P{pi} '{kw}' | ...{ctx}...")

# 1.c 公式纯文本残留（前 PLUS 节中已清理过 84 个 OMML，但纯文本字符可能仍残留）
print("\n--- 1.c 公式纯文本残留 ---")
formula_residue = []
for pi, p in enumerate(paras):
    text = p.text
    if re.search(r'\\(prime|alpha|beta|gamma|theta|sum|frac|sqrt|times|cdot)\b', text):
        formula_residue.append((pi, text[:120]))
    if re.search(r'\$[^$]+\$', text):  # LaTeX $...$ inline
        formula_residue.append((pi, text[:120]))

for pi, t in formula_residue[:15]:
    print(f"  P{pi}: {t!r}")
print(f"  共 {len(formula_residue)} 处可疑公式残留")

print()
print("=" * 80)
print("【二】交叉引用诊断")
print("=" * 80)

# 2.a 所有"图N""表N""公式N"在正文中出现
ref_patterns = {
    '图': re.compile(r'图\s*(\d+)'),
    '表': re.compile(r'表\s*(\d+)'),
    '公式': re.compile(r'公式\s*[（(]?(\d+)[）)]?'),
    '式': re.compile(r'式\s*[（(](\d+)[）)]'),
}

# 先识别标题段(图N标题/表N标题)，把它们排除
caption_paras = set()  # 标题段的索引
caption_fig = {}  # pi -> 图N
caption_tab = {}  # pi -> 表N
fig_caption_pattern = re.compile(r'^图\s*(\d+)[\s：:]')
tab_caption_pattern = re.compile(r'^表\s*(\d+)[\s：:]')
for pi, p in enumerate(paras):
    text = p.text.strip()
    m = fig_caption_pattern.match(text)
    if m:
        caption_paras.add(pi)
        caption_fig[pi] = int(m.group(1))
        continue
    m = tab_caption_pattern.match(text)
    if m:
        caption_paras.add(pi)
        caption_tab[pi] = int(m.group(1))

print(f"\n--- 2.a 标题段统计 ---")
print(f"图标题段: {len(caption_fig)} 个，编号={sorted(caption_fig.values())}")
print(f"表标题段: {len(caption_tab)} 个，编号={sorted(caption_tab.values())}")

# 2.b 正文中引用
print("\n--- 2.b 正文中各类引用统计与上下文 ---")
xref_hits = {k: [] for k in ref_patterns}
for pi, p in enumerate(paras):
    if pi in caption_paras:
        continue  # 跳过标题段本身
    text = p.text
    if not text:
        continue
    for kind, pat in ref_patterns.items():
        for m in pat.finditer(text):
            num = int(m.group(1))
            ctx = text[max(0,m.start()-15):m.end()+15]
            xref_hits[kind].append((pi, num, ctx))

for kind, hits in xref_hits.items():
    if not hits:
        continue
    nums = sorted(set(h[1] for h in hits))
    print(f"\n  >>> 「{kind}N」共 {len(hits)} 处引用，覆盖编号: {nums}")
    # 列出每个引用
    for pi, num, ctx in hits[:30]:
        print(f"      P{pi} 「{kind}{num}」: ...{ctx}...")
    if len(hits) > 30:
        print(f"      ...还有 {len(hits)-30} 处")

# 2.c 越界检查
print("\n--- 2.c 越界检查 ---")
fig_max = max(caption_fig.values()) if caption_fig else 0
tab_max = max(caption_tab.values()) if caption_tab else 0
print(f"实际图编号: 1~{fig_max}")
print(f"实际表编号: 1~{tab_max}")

oob_fig = [(pi,n,c) for pi,n,c in xref_hits['图'] if n < 1 or n > fig_max]
oob_tab = [(pi,n,c) for pi,n,c in xref_hits['表'] if n < 1 or n > tab_max]
print(f"图引用越界: {len(oob_fig)} 处")
for pi,n,c in oob_fig:
    print(f"  P{pi} 图{n}: ...{c}...")
print(f"表引用越界: {len(oob_tab)} 处")
for pi,n,c in oob_tab:
    print(f"  P{pi} 表{n}: ...{c}...")

# 公式编号
print("\n--- 2.d 公式定义段 ---")
# 找含 (\d+) 单独成段或紧跟公式的形式编号
formula_def = []
for pi, p in enumerate(paras):
    text = p.text.strip()
    # 形式：(1) (2) ... 单独或在末尾
    m = re.search(r'[（(](\d+)[）)]\s*$', text)
    if m:
        formula_def.append((pi, int(m.group(1)), text[:80]))
print(f"找到 {len(formula_def)} 个潜在公式编号段:")
for pi, num, txt in formula_def[:20]:
    print(f"  P{pi} ({num}): {txt!r}")

# 公式引用越界
formula_max = max([n for _,n,_ in formula_def], default=0)
print(f"\n实际公式编号: 1~{formula_max}")

print("\n" + "=" * 80)
print("诊断完成")
