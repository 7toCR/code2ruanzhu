# -*- coding: utf-8 -*-
"""ruanzhu-docs 各脚本共用的小工具：LibreOffice 转换、PDF 逐页文字、DOCX 段落与页眉读取、中文宽度。

只依赖 Python 标准库；转换 PDF 需要 LibreOffice（soffice），读 PDF 需要 poppler-utils（pdfinfo、pdftotext）。
"""
import collections
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import zipfile

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def norm(s):
    """去掉所有空白，用于中文文本比对。"""
    return re.sub(r'\s+', '', s or '')


def disp_width(s):
    """按显示宽度计数：全角/宽字符记 2，其余记 1。"""
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)


def soffice_bin():
    for b in ('soffice', 'libreoffice'):
        p = shutil.which(b)
        if p:
            return p
    mac = '/Applications/LibreOffice.app/Contents/MacOS/soffice'
    if os.path.exists(mac):
        return mac
    raise SystemExit('ERROR 找不到 LibreOffice（soffice）。请安装 LibreOffice，或在 Claude 的云端工作区运行本脚本。')


FONT_ALIAS = {'宋体': 'Noto Sans Mono CJK SC', 'SimSun': 'Noto Sans Mono CJK SC', '新宋体': 'Noto Sans Mono CJK SC',
              'NSimSun': 'Noto Sans Mono CJK SC'}


def preview_fontconfig(tmpdir):
    """Linux 预览专用：没有宋体时，把宋体映射到同样“西文半角等宽”的 Noto Sans Mono CJK SC，
    否则 LibreOffice 会用比例字体代替，代码行提前折行，页数和每页行数都会失真。返回 FONTCONFIG_FILE 路径或 None。"""
    if not shutil.which('fc-list') or not os.path.exists('/etc/fonts/fonts.conf'):
        return None
    have = subprocess.run(['fc-list', ':', 'family'], capture_output=True, text=True).stdout
    if 'SimSun' in have or '宋体' in have or 'Noto Sans Mono CJK SC' not in have:
        return None
    alias = ''.join('<alias binding="strong"><family>%s</family><prefer><family>%s</family></prefer></alias>' % (k, v)
                    for k, v in FONT_ALIAS.items())
    p = os.path.join(tmpdir, 'fonts.conf')
    open(p, 'w', encoding='utf-8').write('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
                                         '<include ignore_missing="yes">/etc/fonts/fonts.conf</include>%s</fontconfig>' % alias)
    return p


def convert(src, fmt='pdf', outdir=None, timeout=300, mono_preview=False):
    """用独立的 LibreOffice 配置目录转换文件，避免与已打开的 LibreOffice 冲突。返回输出文件路径。
    mono_preview=True（只用于固定行距的源代码文档）时，在没有宋体的 Linux 上做预览字体映射（见 preview_fontconfig）；
    说明书是自动行距，映射后的字体行高不同，反而会让页数失真，所以默认不映射。"""
    outdir = outdir or os.path.dirname(os.path.abspath(src))
    os.makedirs(outdir, exist_ok=True)
    prof = tempfile.mkdtemp(prefix='rz_lo_')
    env = dict(os.environ)
    fc = preview_fontconfig(prof) if mono_preview else None
    if fc:
        env['FONTCONFIG_FILE'] = fc
    try:
        r = subprocess.run([soffice_bin(), '-env:UserInstallation=file://' + prof, '--headless',
                            '--convert-to', fmt, '--outdir', outdir, src],
                           capture_output=True, text=True, timeout=timeout, env=env)
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    out = os.path.join(outdir, os.path.splitext(os.path.basename(src))[0] + '.' + fmt.split(':')[0])
    if not os.path.exists(out):
        raise SystemExit('ERROR 转换失败：%s\n%s' % (src, (r.stderr or r.stdout)[-800:]))
    return out


def page_fill(pdf):
    """各页正文最后一行的位置（0 = 正文顶部，1 = 正文底部）。页眉页脚按“多数页面在同一高度都有文字”识别后排除。
    图片不含文字，图在页底时会偏小，只用于无图页面。"""
    html = subprocess.run(['pdftotext', '-bbox', pdf, '-'], capture_output=True, text=True).stdout
    pages = []
    for m in re.finditer(r'<page width="[\d.]+" height="([\d.]+)">(.*?)</page>', html, re.S):
        h = float(m.group(1))
        pages.append([(float(a) / h, float(b) / h) for a, b in
                      re.findall(r'<word xMin="[\d.]+" yMin="([\d.]+)" xMax="[\d.]+" yMax="([\d.]+)">', m.group(2))])
    cnt = collections.Counter(y for p in pages for y in {round(a, 3) for a, _ in p})
    fixed = {y for y, c in cnt.items() if c >= max(2, 0.6 * len(pages))}
    body = [[w for w in p if round(w[0], 3) not in fixed] for p in pages]
    ys = [(min(a for a, _ in p), max(b for _, b in p)) for p in body if p]
    if not ys:
        return [0.0] * len(pages)
    top, bot = min(a for a, _ in ys), max(b for _, b in ys)
    return [round((max(b for _, b in p) - top) / max(bot - top, 1e-6), 2) if p else 0.0 for p in body]


def pdf_pages(pdf):
    """返回逐页文字列表（-layout 模式）。"""
    info = subprocess.run(['pdfinfo', pdf], capture_output=True, text=True).stdout
    n = int(re.search(r'Pages:\s+(\d+)', info).group(1))
    return [subprocess.run(['pdftotext', '-f', str(i), '-l', str(i), '-layout', pdf, '-'],
                           capture_output=True, text=True).stdout for i in range(1, n + 1)]


def docx_xml(path, part='word/document.xml'):
    with zipfile.ZipFile(path) as z:
        try:
            return z.read(part).decode('utf-8')
        except KeyError:
            return ''


def para_text(p_xml):
    t = ''.join(re.findall(r'<w:t\b[^>]*>([^<]*)</w:t>', p_xml))
    return (t.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
             .replace('&apos;', "'").replace('&amp;', '&'))


def style_names(path):
    """styleId -> 样式名（小写）。"""
    s = docx_xml(path, 'word/styles.xml')
    return {m.group(1): m.group(2).lower() for m in
            re.finditer(r'<w:style\b[^>]*w:styleId="([^"]+)"[^>]*>\s*<w:name w:val="([^"]+)"', s)}


def paragraphs(path):
    """正文段落列表：dict(style=样式名, text=文字, img=是否含图片, pb=段内是否有分页符, num=是否带编号, xml=原文)。
    表格内段落带 in_table=True。"""
    doc = docx_xml(path)
    names = style_names(path)
    body = doc[doc.find('<w:body>'):]
    out = []
    # 粗略区分表格内外
    pos = 0
    tbl_spans = [(m.start(), m.end()) for m in re.finditer(r'<w:tbl>.*?</w:tbl>', body, re.S)]
    for m in re.finditer(r'<w:p\b[^>]*>.*?</w:p>|<w:p\b[^>]*/>', body, re.S):
        x = m.group(0)
        sid = re.search(r'<w:pStyle w:val="([^"]+)"', x)
        out.append(dict(style=names.get(sid.group(1), sid.group(1)) if sid else 'normal',
                        text=para_text(x), img=('<w:drawing' in x or '<w:pict' in x),
                        pb=('w:type="page"' in x or '<w:pageBreakBefore/>' in x),
                        num=('<w:numPr>' in x),
                        in_table=any(a <= m.start() < b for a, b in tbl_spans), xml=x))
    return out


def header_footer_text(path):
    """返回 {部件名: (文字, 是否含 PAGE 域)}。"""
    res = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if re.match(r'word/(header|footer)\d*\.xml$', n):
                x = z.read(n).decode('utf-8')
                # 去掉域结果（如 PAGE 的缓存页码），避免与正文文字拼在一起
                plain = re.sub(r'<w:fldChar w:fldCharType="separate"/>.*?<w:fldChar w:fldCharType="end"/>', '', x, flags=re.S)
                plain = re.sub(r'<w:fldSimple\b.*?</w:fldSimple>', '', plain, flags=re.S)
                txt = para_text(plain)
                has_page = bool(re.search(r'instrText[^>]*>\s*PAGE\b|w:instr="\s*PAGE\b', x))
                res[os.path.basename(n)] = (txt, has_page)
    return res


def default_header_parts(path):
    """sectPr 中 type=default 的页眉/页脚部件文件名。"""
    doc = docx_xml(path)
    rels = docx_xml(path, 'word/_rels/document.xml.rels')
    rid2t = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
    rid2t.update({a: b for b, a in re.findall(r'Target="([^"]+)"[^>]*Id="([^"]+)"', rels)})
    parts = {}
    for kind in ('header', 'footer'):
        for m in re.finditer(r'<w:%sReference w:type="(\w+)" r:id="([^"]+)"/>' % kind, doc):
            if m.group(1) == 'default':
                parts.setdefault(kind, []).append(os.path.basename(rid2t.get(m.group(2), '')))
    return parts


def top_elements(body):
    """按顺序返回顶层的段落、表格和内容控件（sdt）。"""
    out, i, n = [], 0, len(body)
    pat = re.compile(r'<w:(p|tbl|sdt)\b')
    while i < n:
        m = pat.search(body, i)
        if not m:
            break
        tag = m.group(1)
        if tag == 'p' and body.startswith('/>', body.find('>', m.start()) - 1):
            end = body.find('>', m.start()) + 1
            out.append(('p', body[m.start():end])); i = end; continue
        depth, j = 0, m.start()
        opener = re.compile(r'<w:%s\b[^>]*?(/?)>|</w:%s>' % (tag, tag))
        for mm in opener.finditer(body, m.start()):
            if mm.group(0).startswith('</'):
                depth -= 1
            elif mm.group(1) != '/':
                depth += 1
            if depth == 0:
                j = mm.end(); break
        out.append((tag, body[m.start():j])); i = j
    return out


# ---------------- 源代码文本处理（source_code_docx.py 与 check_ruanzhu.py 共用） ----------------
def strip_comments(text, lang):
    """去掉注释，保留换行（行号不乱）。lang：c（含 Java/JS/Go 等 C 风格）、hash、dash、html、asm。
    C 风格跳过字符串与字符常量；hash/dash/asm 只去整行注释，避免误伤字符串里的 #。"""
    if lang == 'c':
        out, i, n = [], 0, len(text)
        while i < n:
            c = text[i]
            if c == '/' and i + 1 < n and text[i + 1] == '/':
                j = text.find('\n', i)
                i = n if j < 0 else j
                continue
            if c == '/' and i + 1 < n and text[i + 1] == '*':
                j = text.find('*/', i + 2)
                seg = text[i:(n if j < 0 else j + 2)]
                out.append('\n' * seg.count('\n'))
                i = n if j < 0 else j + 2
                continue
            if c in '"\'`':
                q, j = c, i + 1
                while j < n and text[j] != q:
                    if text[j] == '\\':
                        j += 1
                    if j >= n or (text[j] == '\n' and q != '`'):
                        break
                    j += 1
                out.append(text[i:j + 1])
                i = j + 1
                continue
            out.append(c)
            i += 1
        return ''.join(out)
    if lang == 'html':
        return re.sub(r'<!--.*?-->', lambda m: '\n' * m.group(0).count('\n'), text, flags=re.S)
    marks = {'hash': ('#',), 'dash': ('--',), 'asm': (';', '@', '//')}.get(lang, ())
    keep = ('#!', '# -*-', '#include', '#define', '#if', '#endif', '#else', '#elif', '#pragma', '#undef')
    res = []
    for l in text.split('\n'):
        t = l.strip()
        if marks and t.startswith(marks) and not t.startswith(keep):
            res.append('')
        else:
            res.append(l)
    return '\n'.join(res)


def collapse_ws(line, quotes='"\'`'):
    """保留行首缩进，把行内连续空格压成一个（引号内不动）。用于对齐空格很多的宏定义、结构体成员。"""
    lead = len(line) - len(line.lstrip(' '))
    body, out, i, q = line[lead:], [], 0, None
    n = len(body)
    while i < n:
        c = body[i]
        if q:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(body[i + 1]); i += 2; continue
            if c == q:
                q = None
        elif c in quotes:
            q = c
            out.append(c)
        elif c == ' ':
            if not out or out[-1] != ' ':
                out.append(' ')
        else:
            out.append(c)
        i += 1
    return ' ' * lead + ''.join(out)


def _cut(s, w):
    acc = 0
    for i, c in enumerate(s):
        acc += 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1
        if acc > w:
            return i
    return len(s)


def smart_wrap(line, width, step=4):
    """按显示宽度折行：优先在空格处断开，其次在逗号、左括号之后或左方括号之前，找不到才硬折；
    续行比原行多缩进 step 格（最多缩进 40 格）。"""
    if disp_width(line) <= width:
        return [line]
    indent = len(line) - len(line.lstrip(' '))
    cont = ' ' * min(indent + step, 40)
    out, cur = [], line
    while disp_width(cur) > width:
        n = _cut(cur, width)
        head = cur[:n]
        lead = len(cur) - len(cur.lstrip(' '))
        floor = lead + (n - lead) // 4
        k = head.rfind(' ')
        p = max(head.rfind(','), head.rfind('(')) + 1
        q = head.rfind('[')
        if k > floor and k >= p - 1:
            part, rest = cur[:k].rstrip(), cur[k + 1:].lstrip()
        elif max(p, q) > floor:
            j = max(p, q)
            part, rest = cur[:j].rstrip(), cur[j:].lstrip()
        else:
            part, rest = head, cur[n:]
        out.append(part)
        if not rest.strip():
            cur = ''
            break
        cur = cont + rest
        if disp_width(cont) >= width - 8:          # 缩进过深时退回原缩进，防止死循环
            cont = ' ' * indent
            cur = cont + rest
    if cur:
        out.append(cur)
    return out


def code_lines_from_docx(path):
    """读出源代码文档每段的文字（每段一行）。"""
    doc = docx_xml(path)
    return [para_text(p) for p in re.findall(r'<w:p\b[^>]*>.*?</w:p>|<w:p\b[^>]*/>', doc, re.S)]


def overlap(lines, other_lines, min_len=6):
    """与另一份源代码文档的重合度：返回 (非平凡行数, 相同行数, 最长连续相同行数)。比较时去掉首尾空白并压缩行内空格。"""
    key = lambda s: re.sub(r'\s+', ' ', s.strip())
    pool = {key(s) for s in other_lines if len(s.strip()) >= min_len}
    nt = same = run = best = 0
    for s in lines:
        k = key(s)
        if len(k) < min_len:
            continue
        nt += 1
        if k in pool:
            same += 1; run += 1; best = max(best, run)
        else:
            run = 0
    return nt, same, best
