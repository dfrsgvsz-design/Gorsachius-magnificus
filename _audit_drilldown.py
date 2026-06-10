# -*- coding: utf-8 -*-
"""
v3 审计 WARN/INFO 深度排查：
1. B4 正文字号字体检测细节（取第一个长度>30 的 Normal 段是不是承诺书段）
2. J5 「横县」1 处的精确位置和上下文
3. J2 耕地减少 180.96 的出处与上下文
4. I5 7 个无 [J]/[M] 类型标识的文献
5. A5/A6 中文摘要和关键词的实际格式（确认是否真的缺失）
6. J1 4 段含 2025 但未标 PLUS 的具体段
"""
import re
import sys
import io
from collections import Counter
from docx import Document
from docx.oxml.ns import qn

DOC = r'E:\大学\万物春\erci\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_最终_格式合规_v3.docx'
LOG = r'f:\Gorsachius magnificus\_drilldown.txt'

sys.stdout = io.open(LOG, 'w', encoding='utf-8')

doc = Document(DOC)
paras = doc.paragraphs

def get_run_size(r):
    return r.font.size if r.font.size else None
def get_ea_font(r):
    rPr = r._element.find(qn('w:rPr'))
    if rPr is None: return None
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None: return None
    return rFonts.get(qn('w:eastAsia'))

print("=" * 80)
print("【1】B4 正文字号字体误检确认 — 找出真正的正文段")
print("=" * 80)

# 模拟原脚本逻辑：第一个长度>30 的 Normal 段
first_normal = None
for pi, p in enumerate(paras):
    if p.style.name == 'Normal' and p.text.strip() and len(p.text) > 30:
        first_normal = (pi, p)
        break
if first_normal:
    pi, p = first_normal
    r = p.runs[0]
    sz = get_run_size(r)
    ea = get_ea_font(r)
    print(f"\n  脚本采样段: P{pi}")
    print(f"    style.name = {p.style.name!r}")
    print(f"    长度 = {len(p.text)} 字")
    print(f"    内容前 200 字: {p.text[:200]!r}")
    print(f"    R0 字号 = {sz.pt if sz else '继承'}")
    print(f"    R0 eastAsia 字体 = {ea or '继承'}")

# 找出所有 Normal 段，按字号字体分布
print("\n  所有 Normal 段（长度>30）的 R0 字号字体分布:")
normal_meta = []
for pi, p in enumerate(paras):
    if p.style.name != 'Normal': continue
    if not p.text.strip() or len(p.text) <= 30: continue
    if not p.runs: continue
    r = p.runs[0]
    sz = get_run_size(r)
    ea = get_ea_font(r)
    normal_meta.append((pi, sz.pt if sz else None, ea, p.text[:50]))

dist = Counter((s, f) for _, s, f, _ in normal_meta)
print(f"\n  共 {len(normal_meta)} 个 Normal 长段。R0 字号/字体分布:")
for k, v in dist.most_common(10):
    print(f"    {k} -> {v} 段")

# 列出非主流字号字体的 Normal 段
mainstream = dist.most_common(1)[0][0]
print(f"\n  主流: {mainstream}")
print(f"\n  非主流段（前 15）:")
non_mainstream = [(pi, s, f, t) for pi, s, f, t in normal_meta if (s, f) != mainstream]
for pi, s, f, t in non_mainstream[:15]:
    print(f"    P{pi} [size={s} font={f}] {t!r}")
print(f"  共 {len(non_mainstream)} 段非主流")

print("\n" + "=" * 80)
print("【2】「横县」1 处精确位置")
print("=" * 80)
for pi, p in enumerate(paras):
    if '横县' in p.text:
        idx = p.text.find('横县')
        ctx = p.text[max(0,idx-50):idx+50]
        print(f"  P{pi}: ...{ctx}...")

print("\n" + "=" * 80)
print("【3】耕地减少 180.96 的出处与上下文")
print("=" * 80)
for pi, p in enumerate(paras):
    if '180.96' in p.text:
        idx = p.text.find('180.96')
        ctx = p.text[max(0,idx-80):idx+80]
        print(f"  P{pi}: ...{ctx}...")
    if '214.15' in p.text:
        idx = p.text.find('214.15')
        ctx = p.text[max(0,idx-50):idx+50]
        print(f"  P{pi} (214.15): ...{ctx}...")

print("\n" + "=" * 80)
print("【4】7 个无 [J]/[M] 类型标识的文献")
print("=" * 80)
ref_items = []
for pi, p in enumerate(paras):
    t = p.text.strip()
    m = re.match(r'^\[(\d+)\]', t)
    if m:
        ref_items.append((pi, int(m.group(1)), t))

untyped = []
for pi, n, t in ref_items:
    if not re.search(r'\[([JMDCRNGPZUTOS])\]', t):
        untyped.append((pi, n, t))
print(f"  共 {len(untyped)} 个无类型标识:")
for pi, n, t in untyped:
    print(f"\n  P{pi} [{n}]:")
    print(f"    {t[:300]}")

print("\n" + "=" * 80)
print("【5】A5/A6 中文摘要 + 关键词 实际格式")
print("=" * 80)
# 找包含「摘要」字的所有段
print("  全文中含「摘要」字的段:")
for pi, p in enumerate(paras[:100]):
    if '摘要' in p.text or '摘 要' in p.text:
        print(f"    P{pi}: {p.text[:120]!r}")
print("\n  全文中含「关键词」字的段:")
for pi, p in enumerate(paras[:100]):
    if '关键词' in p.text or '关 键 词' in p.text:
        print(f"    P{pi}: {p.text[:150]!r}")
print("\n  前 30 段一览（用于看封面/摘要结构）:")
for pi in range(min(40, len(paras))):
    t = paras[pi].text.strip()
    if t:
        print(f"    P{pi:3d} [{paras[pi].style.name}]: {t[:80]!r}")

print("\n" + "=" * 80)
print("【6】J1 含 2025 但未标 PLUS 的段（待排查）")
print("=" * 80)
plus_kw = ['PLUS', '模拟', '情景']
for pi, p in enumerate(paras):
    if '2025' not in p.text:
        continue
    if not any(k in p.text for k in plus_kw):
        idx = p.text.find('2025')
        ctx = p.text[max(0,idx-60):idx+60]
        print(f"  P{pi}: ...{ctx}...")

print("\n" + "=" * 80)
print("【7】A4 目录验证 — 文档前 50 段中是否有 TOC 字段")
print("=" * 80)
for pi in range(min(50, len(paras))):
    p = paras[pi]
    # 检查 docx XML 中是否含 SDT 或 TOC 域
    el = p._element
    xml_str = el.xml if hasattr(el,'xml') else ''
    has_toc = 'TOC' in xml_str.upper() or 'sdtPr' in xml_str or '<w:tab' in xml_str
    if has_toc or '目录' in p.text or '目 录' in p.text:
        print(f"  P{pi} [{p.style.name}] toc_marker={has_toc}: {p.text[:80]!r}")

print("\n排查完成")
