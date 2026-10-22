# -*- coding: utf-8 -*-
"""从渲染出的 PDF 中查找各标题所在页，供目录回填。
用法: python3 toc_pages.py 文档.pdf toc_entries.json  （通常由 build_docx.py --auto-toc 调用）
toc_entries.json: [[级别, 标题文字, 书签名], ...]；标题可带编号（“3.1 软件总体结构”），
模板用自动编号而 PDF 中编号格式不同（如“第3章”）时，按去掉编号后的标题匹配。"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rz_common import norm, pdf_pages  # noqa: E402

PREFIX = re.compile(r'[\d.第章节、一二三四五六七八九十：:]*')


def line_matches(line, text):
    l, t = norm(line), norm(text)
    if not l:
        return False
    if l == t:
        return True
    bare = norm(re.sub(r'^[\d.]+\s*', '', text))
    if bare and l.endswith(bare) and PREFIX.fullmatch(l[:-len(bare)]):
        return True
    return False


def find_pages(pdf, entries):
    pages = pdf_pages(pdf)
    n = len(pages)
    toc_page = max([i for i, p in enumerate(pages) if '目录' in p[:600]] or [0])
    res, miss, cur = {}, [], toc_page
    for lvl, text, name in entries:
        if lvl == 1 and cur == toc_page and not re.match(r'^\d', text):
            res[name] = 1                        # 参考版式中进入目录的封面标题行
            continue
        found = None
        for i in range(cur, n):
            lines = [l for l in pages[i].splitlines() if not re.search(r'\.{4,}|…{2,}', l)]
            if any(line_matches(l, text) for l in lines):
                found = i + 1
                break
        if found is None:
            miss.append(text)
            res[name] = res.get(name, 1)
        else:
            res[name] = found
            cur = found - 1
    return res, miss, n


if __name__ == '__main__':
    entries = json.load(open(sys.argv[2]))
    res, miss, n = find_pages(sys.argv[1], entries)
    print(json.dumps(res, ensure_ascii=False, indent=1), '\npages', n, 'missing', miss)
