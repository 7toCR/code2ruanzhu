# -*- coding: utf-8 -*-
"""ruanzhu-docs 各脚本共用的小工具：LibreOffice 转换、PDF 逐页文字、DOCX 段落与页眉读取、中文宽度。

只依赖 Python 标准库；转换 PDF 需要 LibreOffice（soffice），读 PDF 需要 poppler-utils（pdfinfo、pdftotext）。
"""
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


def convert(src, fmt='pdf', outdir=None, timeout=300):
    """用独立的 LibreOffice 配置目录转换文件，避免与已打开的 LibreOffice 冲突。返回输出文件路径。"""
    outdir = outdir or os.path.dirname(os.path.abspath(src))
    os.makedirs(outdir, exist_ok=True)
    prof = tempfile.mkdtemp(prefix='rz_lo_')
    try:
        r = subprocess.run([soffice_bin(), '-env:UserInstallation=file://' + prof, '--headless',
                            '--convert-to', fmt, '--outdir', outdir, src],
                           capture_output=True, text=True, timeout=timeout)
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    out = os.path.join(outdir, os.path.splitext(os.path.basename(src))[0] + '.' + fmt.split(':')[0])
    if not os.path.exists(out):
        raise SystemExit('ERROR 转换失败：%s\n%s' % (src, (r.stderr or r.stdout)[-800:]))
    return out


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
