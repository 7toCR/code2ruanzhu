# -*- coding: utf-8 -*-
"""在旧版 Word（.doc）里做等长文字替换，例如收录文件变化后改采集卡上的源程序量。

用法:
  python3 doc_replace.py 采集卡.doc --replace 12953=12872 [--replace 旧=新 ...] [-o 新.doc] [--all] [--no-check]

- .doc 是二进制格式，没有可靠的免费写入工具；正文文字以 UTF-16LE 存放，新旧文字长度（字符数）相同时可以原位替换，
  不改变文件结构。长度不同时脚本拒绝替换：请在 Word 中手改，或用 fill_info_card.py 重新生成 .docx。
- 每个旧文字默认必须恰好出现一次（避免误改别处的同样数字）；确实要全部替换时加 --all。
- 不加 -o 时原位修改，先把原文件备份为“<文件名>_原版备份.doc”（已有备份时不覆盖）。
- 默认用 LibreOffice 把新旧文件都转成纯文本，核对只有指定的文字发生了变化。
"""
import argparse
import difflib
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rz_common import convert  # noqa: E402


def doc_text(path):
    d = tempfile.mkdtemp(prefix='rz_doctxt_')
    try:
        out = convert(path, 'txt:Text (encoded):UTF8', d)
        return open(out, encoding='utf-8', errors='replace').read().splitlines()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('doc')
    ap.add_argument('--replace', action='append', required=True, metavar='旧=新')
    ap.add_argument('-o', '--out')
    ap.add_argument('--all', action='store_true', help='旧文字出现多次时全部替换')
    ap.add_argument('--no-check', action='store_true', help='不用 LibreOffice 核对替换结果')
    a = ap.parse_args()

    raw = open(a.doc, 'rb').read()
    data = bytearray(raw)
    pairs = []
    for r in a.replace:
        if '=' not in r:
            raise SystemExit('ERROR --replace 的格式是 旧=新：%s' % r)
        old, new = r.split('=', 1)
        if len(old) != len(new):
            raise SystemExit('ERROR “%s”与“%s”字数不同（%d / %d），.doc 只能做等长替换；请在 Word 中修改，'
                             '或用 fill_info_card.py 重新生成 .docx' % (old, new, len(old), len(new)))
        bo, bn = old.encode('utf-16-le'), new.encode('utf-16-le')
        hits, i = [], data.find(bo)
        while i >= 0:
            hits.append(i)
            i = data.find(bo, i + 1)
        hits = [h for h in hits if h % 2 == 0]          # UTF-16 文字从偶数偏移开始
        if not hits:
            raise SystemExit('ERROR 找不到“%s”（可能被拆成多段格式或以其他编码保存，请在 Word 中修改）' % old)
        if len(hits) > 1 and not a.all:
            raise SystemExit('ERROR “%s”出现 %d 次，为避免误改已停止；确认全部替换时加 --all' % (old, len(hits)))
        for h in hits:
            data[h:h + len(bo)] = bn
        pairs.append((old, new, len(hits)))

    out = a.out or a.doc
    if not a.out:
        base, ext = os.path.splitext(a.doc)
        bak = base + '_原版备份' + ext
        if not os.path.exists(bak):
            shutil.copy2(a.doc, bak)
            print('已备份原文件：', bak)
        src_for_check = bak
    else:
        src_for_check = a.doc
    open(out, 'wb').write(bytes(data))
    for old, new, k in pairs:
        print('替换 “%s” → “%s”：%d 处' % (old, new, k))
    print('写出', out)

    if a.no_check:
        return
    before, after = doc_text(src_for_check), doc_text(out)
    changed = [l for l in difflib.unified_diff(before, after, lineterm='', n=0) if l[:1] in '+-' and l[:3] not in ('+++', '---')]
    expect_old = {o for o, _, _ in pairs}
    expect_new = {n for _, n, _ in pairs}
    bad = [l for l in changed if not any(x in l for x in (expect_old if l[0] == '-' else expect_new))]
    for l in changed[:20]:
        print('   ' + l)
    if bad:
        print('WARN 有不属于本次替换的文字变化，请在 Word 中打开核对')
    elif not changed:
        print('WARN LibreOffice 读出的文字没有变化，替换位置可能不在正文（例如在文档属性里），请在 Word 中核对')
    else:
        print('核对通过：只有指定的文字发生变化')


if __name__ == '__main__':
    main()
