# -*- coding: utf-8 -*-
"""回滚 F1 对致谢节的误编号 [29]-[35]"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from docx import Document
from docx.oxml.ns import qn

DST = r'E:\大学\万物春\erci\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_最终_格式合规.docx'

doc = Document(DST)
paras = doc.paragraphs

# 定位致谢节起点（"致 谢" 含空格，或 "致谢"）
thanks_start = -1
for i, p in enumerate(paras):
    t = p.text.strip()
    # 移除 [N] 编号后判断
    t_clean = re.sub(r'^\[\d+\]\s*', '', t)
    if t_clean in ('致谢', '致 谢') or re.match(r'^致\s*谢$', t_clean):
        thanks_start = i
        print(f'致谢节起点: P{i}, 文本: "{t}"')
        break

if thanks_start < 0:
    print('未找到致谢节')
    sys.exit(1)

# 从致谢节起点开始，遍历到文档末尾，移除每段首部的 [N] 编号
removed = 0
for i in range(thanks_start, len(paras)):
    p = paras[i]
    t = p.text
    if not t.strip():
        continue
    m = re.match(r'^\[(\d+)\]\s*', t)
    if m:
        # 在 run 级别移除前缀
        if p.runs:
            first_run = p.runs[0]
            prefix = m.group(0)
            if first_run.text.startswith(prefix):
                first_run.text = first_run.text[len(prefix):]
            else:
                # 前缀可能跨多个 run，使用全段重设
                full = t[len(prefix):]
                # 清空所有 run，第一 run 设置完整文本
                for r in p.runs[1:]:
                    r.text = ''
                p.runs[0].text = full
        removed += 1
        print(f'  [回滚] P{i}: 移除 "{m.group(0)}" → "{p.text[:60]}"')

print(f'\n共回滚 {removed} 处误编号')

doc.save(DST)
print(f'已保存: {DST}')
