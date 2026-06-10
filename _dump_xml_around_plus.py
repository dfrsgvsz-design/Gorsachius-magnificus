# -*- coding: utf-8 -*-
"""导出 P189-P205 的 XML 结构以诊断公式渲染问题"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import zipfile
import os
import re

V3 = r'E:\大学\万物春\erci\郑春铃+横州市土地利用变化与生态安全评价(1)_PLUS修订版_v3.docx'
ORIG = r'E:\大学\万物春\erci\郑春铃+横州市土地利用变化与生态安全评价(1).docx.bak_before_plus_revision'

def search_latex(path, label):
    print(f'\n========== {label}: {path} ==========')
    with zipfile.ZipFile(path) as z:
        with z.open('word/document.xml') as f:
            data = f.read().decode('utf-8')
    print(f'文档总长度: {len(data):,} chars')
    
    # 搜索 LaTeX 源码字符串
    patterns = ['x_{ij}', 'x_{i', '\\prime', '\\frac', 'min(x_j)', 'max(x_j)',
                'oMathPara', 'oMath ', '<m:f>', 'latex', 'TeX']
    for pat in patterns:
        # 使用 re.escape 避免特殊字符问题
        n = data.count(pat)
        if n > 0:
            print(f'  [{pat}]: {n} 处')
    
    # 找出 "PLUS模型情景模拟" 周围 1000 字符
    idx = data.find('PLUS模型情景模拟')
    if idx > 0:
        snippet = data[max(0, idx-300):idx+1500]
        print(f'\n--- "PLUS模型情景模拟" 附近 XML 片段 (idx={idx}) ---')
        print(snippet)
        print('--- 片段结束 ---')

search_latex(V3, 'v3')
# search_latex(ORIG, '原稿 bak')  # 暂不输出，避免太多
