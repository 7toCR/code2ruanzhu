# -*- coding: utf-8 -*-
"""把一份已有的说明书 .docx 拆成 content.py，用于“正文不动、按参考件重新排版”或换图后重新生成。

用法:
  python3 docx_to_content.py 旧说明书.docx --out content.py [--media-dir figs_old]

- 标题按样式名（heading 1/2/3）识别为 h1/h2/h3；带编号的段落记为 ('li', 文字)；表格记为 ('table', 行列表)；
  图片导出到 --media-dir 并登记到 FIG，紧跟其后的“图 3-1 标题”图题作为图题文字，不再单独保留。
- 正文里的“图3-1”会换成 {图:key} 占位，重新生成时按新的图号自动替换。
- 导出的旧图带 {'scale': …} 选项，重新生成时保持原文档中的显示尺寸；换成新渲染的流程图 PNG 时删掉该选项。
- 文字从 XML 中取出时已还原 &lt; 等转义字符，写回时由 build_docx.py 统一转义，不会出现“&amp;lt;”。
- 封面行无法可靠识别：TITLE 取目录之前的前几个非空段，请按模板封面的行数核对后再用。
"""
import argparse
import os
import re
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rz_common import docx_xml, para_text, style_names, top_elements  # noqa: E402

CAP = re.compile(r'^\s*图\s*(\d+(?:\s*[-－—.．]\s*\d+)?)\s+(.+?)\s*$')
REF = re.compile(r'图\s*(\d+(?:\s*[-－—.．]\s*\d+)?)')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('docx')
    ap.add_argument('--out', required=True)
    ap.add_argument('--media-dir', default='figs_old')
    a = ap.parse_args()

    doc = docx_xml(a.docx)
    names = style_names(a.docx)
    rels = docx_xml(a.docx, 'word/_rels/document.xml.rels')
    rid2t = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
    rid2t.update({x: y for y, x in re.findall(r'Target="([^"]+)"[^>]*Id="([^"]+)"', rels)})
    body = doc[doc.index('<w:body>') + 8:doc.rindex('<w:sectPr')]
    els = top_elements(body)
    toc_i = next((k for k, (t, x) in enumerate(els) if t == 'sdt' and 'Table of Contents' in x), None)
    cover, title = [], []
    stop, prev = False, ''

    for t, x in els[:toc_i if toc_i is not None else 0]:
        for p in re.findall(r'<w:p\b[^>]*>.*?</w:p>', x, re.S):
            s = para_text(p).strip()
            if not s or s in cover:
                continue
            cover.append(s)
            if s in ('修订历史', '修订记录', '版本记录', '目录'):
                stop = True
            ver = re.fullmatch(r'[Vv]?\d+(\.\d+)+', s) and len(prev) > 4    # 单独一行的版本号算封面行，“版本”标签后的不算
            short = len(s) <= 4 and not ver
            prev = s
            if stop or short or s.endswith((':', '：')) or re.search(r'\d{4}\s*[-年./]', s):
                continue                       # 封面表格的标签、日期、修订记录不算封面标题行
            title.append(s)
    start = toc_i + 1 if toc_i is not None else 0

    def level(px):
        sid = re.search(r'<w:pStyle w:val="([^"]+)"', px)
        nm = names.get(sid.group(1), '') if sid else ''
        m = re.match(r'(?:heading|标题)\s*(\d)', nm)
        return int(m.group(1)) if m else 0

    os.makedirs(a.media_dir, exist_ok=True)
    blocks, figs, labels = [], {}, {}
    zf = zipfile.ZipFile(a.docx)
    k = 0
    seq = els[start:]
    skip = set()
    for idx, (t, x) in enumerate(seq):
        if idx in skip:
            continue
        if t == 'tbl':
            rows = [[' '.join(para_text(p) for p in re.findall(r'<w:p\b[^>]*>.*?</w:p>', c, re.S)).strip()
                     for c in re.findall(r'<w:tc\b.*?</w:tc>', r, re.S)] for r in re.findall(r'<w:tr\b.*?</w:tr>', x, re.S)]
            blocks.append(('table', rows))
            continue
        if t != 'p':
            continue
        txt = para_text(x).strip()
        lv = level(x)
        brk = '<w:pageBreakBefore/>' in x or ('w:type="page"' in x and
                                              x.find('w:type="page"') < (x.find('<w:t') if '<w:t' in x else len(x)))
        if brk and blocks and blocks[-1] != ('pb',) or (brk and not blocks):
            blocks.append(('pb',))           # 分页符、段前分页；照参考件排版且一级标题自带段前分页时，生成时会自动跳过
        if '<w:drawing' in x or '<w:pict' in x:
            rid = re.search(r'r:(?:embed|id)="([^"]+)"', x)
            if not rid or rid.group(1) not in rid2t:
                continue
            k += 1
            key = 'f%02d' % k
            src = 'word/' + rid2t[rid.group(1)].lstrip('/').replace('word/', '')
            ext = os.path.splitext(src)[1] or '.png'
            dst = os.path.join(a.media_dir, '%s%s' % (key, ext))
            with zf.open(src) as fi, open(dst, 'wb') as fo:
                shutil.copyfileobj(fi, fo)
            alt = re.search(r'descr="([^"]*)"', x)
            alt = alt.group(1) if alt else ''
            nxt = seq[idx + 1] if idx + 1 < len(seq) else None
            if nxt and nxt[0] == 'p':
                m = CAP.match(para_text(nxt[1]))
                if m:
                    labels[re.sub(r'\s|[－—.．]', '-', m.group(1))] = key
                    alt = m.group(2)
                    skip.add(idx + 1)
            opt = {}
            ext_m = re.search(r'<wp:extent cx="(\d+)"', x)
            if ext_m and ext.lower() in ('.png', '.jpg', '.jpeg'):
                try:
                    from PIL import Image
                    w_px = Image.open(dst).size[0]
                    # build_docx 把流程图 PNG 当作 3 倍图：原生宽 = 像素宽 / 3（96 dpi）
                    opt = {'scale': round(int(ext_m.group(1)) / 914400 * 96 / (w_px / 3), 3)}
                except Exception:
                    opt = {}
            figs[key] = (dst, alt or key, opt) if opt else (dst, alt or key)
            blocks.append(('fig', key))
            continue
        if not txt:
            continue
        if lv:
            blocks.append(('h%d' % min(lv, 3), txt))
        elif '<w:numPr>' in x:
            blocks.append(('li', txt))
        else:
            blocks.append(('p', txt))

    def sub(s):
        def rep(m):
            lab = re.sub(r'\s|[－—.．]', '-', m.group(1))
            return '{图:%s}' % labels[lab] if lab in labels else m.group(0)
        return REF.sub(rep, s)
    blocks = [(b[0], sub(b[1])) if b[0] in ('p', 'li') else b for b in blocks]

    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n# 由 docx_to_content.py 从 %s 拆出；核对 TITLE、替换 FIG 中的图片路径后再生成。\n\n'
                % os.path.basename(a.docx))
        f.write('# 目录之前的非空段（封面候选）：%r\n' % cover[:8])
        f.write('TITLE = %r\n' % title[:3])
        f.write('NUMBERED = %r\n\n' % bool(labels))
        f.write('FIG = {\n')
        for key, spec in figs.items():
            f.write('    %r: %r,\n' % (key, spec))
        f.write('}\n\nBLOCKS = [\n')
        for b in blocks:
            f.write('    %r,\n' % (b,))
        f.write(']\n')
    print('写出 %s：%d 个块，%d 张图（图题 %d 个），%d 个表格；图片在 %s/'
          % (a.out, len(blocks), len(figs), len(labels), sum(1 for b in blocks if b[0] == 'table'), a.media_dir))


if __name__ == '__main__':
    main()
