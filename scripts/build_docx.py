# -*- coding: utf-8 -*-
"""按模板版式生成软著说明书 .docx（详细设计说明书 / 软件说明书通用）。

用法:
  python3 build_docx.py --content content.py --out 输出.docx [--template 模板.docx] [--auto-toc]

模板: 用户给的目标文档（已有封面/页眉）优先；其次用参考软著本身；都没有时用本技能自带的
      assets/template_design.docx（编号版式，页眉含“【软件全称】 【版本号】”占位和右侧页码）。
      只保留模板的封面标题段、页眉页脚、页面设置和样式，正文全部重写。

content.py 可定义:
  TITLE   = ['软件全称', 'V1.0', '详细设计说明书']      # 封面标题行，替换模板前 N 个封面段
  NUMBERED = False     # False：参考软著版式（“一：软件概述”居中标题、图下不加图题）
                       # True ：编号版式（1 / 3.1 / 4.1.1 章节编号，图下加“图 3-1 标题”，目录三级）
  FIG     = {'00': ('flowcharts/00_总体结构.png', '软件总体结构图'),     # 流程图：缩到 2/3 并量化 256 色
             's1': ('shots/登录.png', '登录界面', 'shot')}              # 截图：不量化，过宽才缩
  BLOCKS  = [('h1', '软件概述'),                       # 编号版式的章；参考版式用 ('h2c', '一：软件概述')
             ('h2', '软件总体结构'), ('h3', '下行帧拆分与校验'),
             ('p', '……详情如{图:00}所示。'),             # {图:key} 编号版式替换为“图3-1”，参考版式替换为“下图”
             ('p', '……', 'keep'),                     # 'keep'：与下一段同页
             ('req', '硬件环境：……'),                  # 系统运行要求条目
             ('fields', '具体字段解释如下：', [('名称：', '说明。')]),
             ('table', [['功能码', '名称', '说明'], ['0x01', '查询版本', '……']], {'widths': [2, 3, 9.6]}),
             ('fig', '00'), ('pb',)]
  STYLE   = {...}        # 可选：覆盖自动识别的样式 ID，或 font='宋体'、sz=24（半磅）
  HEADER_REPLACE = [('参考软著名称', '本软件名称')]       # 可选：用参考软著当模板时替换页眉文字
  COVER_FIELDS = {'作者': '张三', '负责人': '李四'}       # 可选：填写模板封面表格中“标签:”右侧的空格
  TOC_COVER = None       # 封面行是否进目录；默认参考版式进、编号版式不进
页眉中的“【软件全称】”“【版本号】”占位会自动替换为 TITLE[0]、TITLE[1]。
--auto-toc: 用 LibreOffice 渲染 PDF 回填目录页码，重复到页码稳定（最多 4 轮）。
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from xml.sax.saxutils import escape

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(os.path.dirname(HERE), 'assets', 'template_design.docx')
EMU_PER_TWIP = 635
MAX_SCALE = 1.0                  # 小流程图不放大（14px 字插入后约 10.5pt），避免字号过大
FIG_PH = re.compile(r'\{图:([^}]+)\}')


def load_content(path):
    spec = importlib.util.spec_from_file_location('content', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def detect_styles(word):
    s = open(os.path.join(word, 'styles.xml'), encoding='utf-8').read()
    names, numbered = {}, {}
    for m in re.finditer(r'<w:style\b[^>]*w:styleId="([^"]+)"[^>]*>(.*?)</w:style>', s, re.S):
        nm = re.search(r'<w:name w:val="([^"]+)"', m.group(2))
        if nm:
            names.setdefault(nm.group(1).lower(), m.group(1))
            numbered[m.group(1)] = '<w:numPr>' in m.group(2)
    st = dict(h1=names.get('heading 1', 'Heading1'), h2=names.get('heading 2', 'Heading2'),
              h3=names.get('heading 3', 'Heading3'), toc=names.get('toc heading', 'TOCHeading'),
              toc1=names.get('toc 1', 'TOC1'), toc2=names.get('toc 2', 'TOC2'), toc3=names.get('toc 3', 'TOC3'),
              link=names.get('hyperlink', 'Hyperlink'))
    missing = [k for k, v in st.items() if v not in names.values()]
    if missing:
        print('WARN 模板缺少样式', missing, '（Word 打开后仍可显示，但标题/目录外观可能不同）')
    st['auto_num'] = {k: numbered.get(st[k], False) for k in ('h1', 'h2', 'h3')}
    return st


def ensure_bullet(word, unpacked):
    """返回一个项目符号列表的 numId；模板没有就新建。"""
    p = os.path.join(word, 'numbering.xml')
    if os.path.exists(p):
        s = open(p, encoding='utf-8').read()
        for m in re.finditer(r'<w:abstractNum\b[^>]*w:abstractNumId="(\d+)".*?</w:abstractNum>', s, re.S):
            lvl0 = re.search(r'<w:lvl w:ilvl="0".*?</w:lvl>', m.group(0), re.S)
            if lvl0 and 'w:val="bullet"' in lvl0.group(0):
                n = re.search(r'<w:num w:numId="(\d+)"[^>]*>\s*<w:abstractNumId w:val="%s"/>' % m.group(1), s)
                if n:
                    return n.group(1)
    else:
        s = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"></w:numbering>')
        rp = os.path.join(word, '_rels/document.xml.rels')
        r = open(rp, encoding='utf-8').read().replace('</Relationships>',
            '<Relationship Id="rIdNumX" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/></Relationships>')
        open(rp, 'w', encoding='utf-8').write(r)
        cp = os.path.join(unpacked, '[Content_Types].xml')
        c = open(cp, encoding='utf-8').read().replace('</Types>',
            '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/></Types>')
        open(cp, 'w', encoding='utf-8').write(c)
    aid, nid = '9001', '9001'
    absn = ('<w:abstractNum w:abstractNumId="%s"><w:multiLevelType w:val="hybridMultilevel"/>'
            '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="\uf06c"/><w:lvlJc w:val="left"/>'
            '<w:pPr><w:ind w:left="420" w:hanging="420"/></w:pPr><w:rPr><w:rFonts w:ascii="Wingdings" w:hAnsi="Wingdings" w:hint="default"/></w:rPr></w:lvl>'
            '</w:abstractNum>') % aid
    num = '<w:num w:numId="%s"><w:abstractNumId w:val="%s"/></w:num>' % (nid, aid)
    if '<w:abstractNum ' in s:
        s = s.replace('<w:abstractNum ', absn + '<w:abstractNum ', 1)
    elif '<w:num ' in s:
        s = s.replace('<w:num ', absn + '<w:num ', 1)
    else:
        s = s.replace('</w:numbering>', absn + '</w:numbering>')
    s = s.replace('</w:numbering>', num + '</w:numbering>')
    open(p, 'w', encoding='utf-8').write(s)
    return nid


class Builder:
    def __init__(self, st, font, sz, text_w, text_h):
        self.st, self.font, self.sz = st, font, sz
        self.text_w, self.text_h = text_w, text_h
        self.bm = 1000
        self.pic = 1000
        f = font
        self.F = '<w:rFonts w:ascii="%s" w:eastAsia="%s" w:hAnsi="%s" w:cs="%s" w:hint="eastAsia"/>' % (f, f, f, f)
        self.SZ = '<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (sz, sz)

    def t(self, s):
        return '<w:t xml:space="preserve">%s</w:t>' % escape(s)

    def run(self, s, bold=False, sz=None):
        szx = self.SZ if sz is None else '<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (sz, sz)
        return '<w:r><w:rPr>%s%s%s</w:rPr>%s</w:r>' % (self.F, '<w:b/><w:bCs/>' if bold else '', szx, self.t(s))

    def p_body(self, s, keep=False):
        return ('<w:p><w:pPr>' + ('<w:keepNext/>' if keep else '') +
                '<w:spacing w:before="0" w:after="0" w:line="360" w:lineRule="auto"/><w:ind w:firstLineChars="200" w:firstLine="%d"/><w:jc w:val="both"/>'
                '<w:rPr>%s%s</w:rPr></w:pPr>' % (self.sz * 20, self.F, self.SZ) + self.run(s) + '</w:p>')

    def p_req(self, s):
        return ('<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="360" w:lineRule="auto"/><w:ind w:firstLineChars="200" w:firstLine="%d"/>'
                '<w:jc w:val="both"/><w:rPr>%s%s</w:rPr></w:pPr>' % (self.sz * 20, self.F, self.SZ) + self.run(s) + '</w:p>')

    def p_bullet(self, label, s):
        return ('<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="%s"/></w:numPr>'
                '<w:spacing w:before="0" w:after="0" w:line="360" w:lineRule="auto"/><w:ind w:left="0" w:firstLineChars="200" w:firstLine="%d"/><w:jc w:val="both"/>'
                '<w:rPr>%s%s</w:rPr></w:pPr>' % (self.st['bullet'], self.sz * 20, self.F, self.SZ)
                + self.run(label) + self.run(s) + '</w:p>')

    def new_bm(self):
        self.bm += 1
        return self.bm, '_Toc9%08d' % self.bm

    def heading(self, level, text, center=False, legacy=False):
        """legacy=True 时沿用参考软著版式的 h2 写法（显式字号与行距）。"""
        i, name = self.new_bm()
        style = self.st['h%d' % level]
        if legacy:
            jc = '<w:jc w:val="center"/>' if center else '<w:spacing w:line="360" w:lineRule="auto"/>'
            sz = '' if center else self.SZ
        else:
            jc = '<w:jc w:val="center"/>' if center else ''
            sz = ''
        x = ('<w:p><w:pPr><w:pStyle w:val="%s"/>%s<w:rPr>%s%s</w:rPr></w:pPr>' % (style, jc, self.F, sz)
             + '<w:bookmarkStart w:id="%d" w:name="%s"/>' % (i, name)
             + '<w:r><w:rPr>%s%s</w:rPr>%s</w:r>' % (self.F, sz, self.t(text))
             + '<w:bookmarkEnd w:id="%d"/></w:p>' % i)
        return x, name

    def p_pagebreak(self):
        return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'

    def p_caption(self, s):
        return ('<w:p><w:pPr><w:keepLines/><w:spacing w:before="60" w:after="200" w:line="240" w:lineRule="auto"/>'
                '<w:ind w:firstLine="0"/><w:jc w:val="center"/></w:pPr>' + self.run(s, bold=True, sz=21) + '</w:p>')

    def p_fig(self, rid, cx, cy, alt, keep=False):
        self.pic += 1
        n = self.pic
        return ('<w:p><w:pPr>%s<w:spacing w:before="120" w:after="0" w:line="240" w:lineRule="auto"/><w:ind w:firstLine="0"/><w:jc w:val="center"/></w:pPr>'
                '<w:r><w:rPr><w:noProof/></w:rPr><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
                '<wp:extent cx="%d" cy="%d"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
                '<wp:docPr id="%d" name="图片 %d" descr="%s"/>'
                '<wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>'
                '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
                '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
                '<pic:nvPicPr><pic:cNvPr id="%d" name="图片 %d" descr="%s"/><pic:cNvPicPr/></pic:nvPicPr>'
                '<pic:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
                '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
                '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
                ) % ('<w:keepNext/>' if keep else '', cx, cy, n, n, escape(alt), n, n, escape(alt), rid, cx, cy)

    def table(self, rows, opts):
        opts = opts or {}
        ncol = max(len(r) for r in rows)
        if opts.get('widths'):
            ws = [float(w) for w in opts['widths']]
        else:
            ws = [max(2, max(len(str(r[c])) if c < len(r) else 0 for r in rows)) ** 0.7 for c in range(ncol)]
        tw = [int(self.text_w * w / sum(ws)) for w in ws]
        b = ''.join('<w:%s w:val="single" w:sz="4" w:space="0" w:color="000000"/>' % k
                    for k in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
        out = ['<w:tbl><w:tblPr><w:tblW w:w="%d" w:type="dxa"/><w:jc w:val="center"/><w:tblBorders>%s</w:tblBorders>'
               '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar>'
               '</w:tblPr><w:tblGrid>%s</w:tblGrid>' % (sum(tw), b, ''.join('<w:gridCol w:w="%d"/>' % w for w in tw))]
        for ri, r in enumerate(rows):
            head = ri == 0 and opts.get('header', True)
            out.append('<w:tr>' + ('<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>' if head else '<w:trPr><w:cantSplit/></w:trPr>'))
            for ci in range(ncol):
                txt = str(r[ci]) if ci < len(r) else ''
                shade = '<w:shd w:val="clear" w:color="auto" w:fill="E7E9EC"/>' if head else ''
                paras = ''.join('<w:p><w:pPr><w:spacing w:before="20" w:after="20" w:line="260" w:lineRule="auto"/>'
                                '<w:jc w:val="%s"/></w:pPr>%s</w:p>' % ('center' if head else 'left', self.run(line, bold=head, sz=21))
                                for line in txt.split('\n'))
                out.append('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s<w:vAlign w:val="center"/></w:tcPr>%s</w:tc>'
                           % (tw[ci], shade, paras))
            out.append('</w:tr>')
        out.append('</w:tbl><w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:p>')
        return ''.join(out)

    def toc(self, entries, pages, page_break=False):
        st, out = self.st, []
        out.append('<w:sdt><w:sdtPr><w:id w:val="-339939018"/><w:docPartObj><w:docPartGallery w:val="Table of Contents"/>'
                   '<w:docPartUnique/></w:docPartObj></w:sdtPr><w:sdtContent>'
                   '<w:p><w:pPr><w:pStyle w:val="%s"/>%s<w:jc w:val="center"/></w:pPr><w:r><w:rPr>%s</w:rPr><w:t>目录</w:t></w:r></w:p>'
                   % (st['toc'], '<w:pageBreakBefore/>' if page_break else '', self.F))
        tab = '<w:tabs><w:tab w:val="right" w:leader="dot" w:pos="%d"/></w:tabs>' % (self.text_w - 10)
        for k, (lvl, text, name) in enumerate(entries):
            style = st['toc%d' % min(lvl, 3)]
            noi = '<w:i w:val="0"/><w:iCs w:val="0"/>'          # 中文模板的 TOC 样式常带斜体
            head = ''
            if k == 0:
                head = ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                        '<w:r><w:instrText xml:space="preserve">TOC \\o "1-3" \\h \\z \\u</w:instrText></w:r>'
                        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>')
            wr = '<w:rPr>%s<w:noProof/><w:webHidden/></w:rPr>' % noi
            out.append('<w:p><w:pPr><w:pStyle w:val="%s"/>%s<w:rPr>%s<w:noProof/></w:rPr></w:pPr>' % (style, tab, noi) + head
                       + '<w:hyperlink w:anchor="%s" w:history="1">' % name
                       + '<w:r><w:rPr><w:rStyle w:val="%s"/>%s%s<w:noProof/></w:rPr>%s</w:r>' % (st['link'], self.F, noi, self.t(text))
                       + '<w:r>%s<w:tab/></w:r>' % wr
                       + '<w:r>%s<w:fldChar w:fldCharType="begin"/></w:r>' % wr
                       + '<w:r>%s<w:instrText xml:space="preserve"> PAGEREF %s \\h </w:instrText></w:r>' % (wr, name)
                       + '<w:r>%s<w:fldChar w:fldCharType="separate"/></w:r>' % wr
                       + '<w:r>%s<w:t>%s</w:t></w:r>' % (wr, pages.get(name, 1))
                       + '<w:r>%s<w:fldChar w:fldCharType="end"/></w:r>' % wr
                       + '</w:hyperlink></w:p>')
        out.append('<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:sdtContent></w:sdt>')
        return ''.join(out)


def set_para_text(p, text):
    """保留段落格式，替换段内文字；去掉原书签。文字没变（只差空格/换行）时原样保留，以免丢掉模板里的手动换行。"""
    p = re.sub(r'<w:bookmark(Start|End)\b[^>]*/>', '', p)
    cur = ''.join(re.findall(r'<w:t\b[^>]*>([^<]*)</w:t>', p))
    if re.sub(r'\s+', '', cur) == re.sub(r'\s+', '', text):
        return p
    runs = list(re.finditer(r'<w:r\b[^>]*>.*?</w:r>', p, re.S))
    first = next((r for r in runs if '<w:t' in r.group(0)), None)
    if first is None:
        return p
    new_first = re.sub(r'<w:t\b[^>]*>.*?</w:t>|<w:t\b[^>]*/>', '\x00', first.group(0), flags=re.S)
    new_first = new_first.replace('\x00', '<w:t xml:space="preserve">%s</w:t>' % escape(text), 1).replace('\x00', '')
    out, last = [], 0
    for r in runs:
        out.append(p[last:r.start()])
        if r is first:
            out.append(new_first)
        elif '<w:t' not in r.group(0):
            out.append(r.group(0))
        last = r.end()
    out.append(p[last:])
    return ''.join(out)


def replace_in_parts(word, old, new):
    hit = 0
    for fn in os.listdir(word):
        if not re.match(r'(header|footer)\d*\.xml$', fn):
            continue
        p = os.path.join(word, fn)
        s = open(p, encoding='utf-8').read()
        if old in s:
            s = s.replace(old, escape(new)); hit += 1
        else:
            def fix(m):
                para = m.group(0)
                txt = ''.join(re.findall(r'<w:t\b[^>]*>([^<]*)</w:t>', para))
                if old not in txt:
                    return para
                return set_para_text(para, txt.replace(old, new))
            s2 = re.sub(r'<w:p\b[^>]*>.*?</w:p>', fix, s, flags=re.S)
            if s2 != s:
                s = s2; hit += 1
        open(p, 'w', encoding='utf-8').write(s)
    return hit


def top_tables(xml):
    """顶层表格的 (起, 止) 位置，正确处理嵌套表格。"""
    spans, depth, start = [], 0, 0
    for m in re.finditer(r'<w:tbl>|</w:tbl>', xml):
        if m.group(0) == '<w:tbl>':
            if depth == 0:
                start = m.start()
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                spans.append((start, m.end()))
    return spans


def fill_cover_fields(body0, fields):
    """封面表格：标签单元格（如“作者:”）右侧为空时写入值。"""
    if not fields:
        return body0, []
    done = []

    def cell_text(c):
        return ''.join(re.findall(r'<w:t\b[^>]*>([^<]*)</w:t>', c))

    def row_fix(m):
        row = m.group(0)
        if '<w:tbl>' in row:                      # 外层框表格的行，交给内层表格处理
            return row
        cells = [c.group(0) for c in re.finditer(r'<w:tc\b.*?</w:tc>', row, re.S)]
        for k, a in enumerate(cells):
            lab = re.sub(r'[\s:：]', '', cell_text(a))
            if lab not in fields:
                continue
            j = k + 1
            while j < len(cells) and re.fullmatch(r'[\s:：]*', cell_text(cells[j])) and re.search(r'[:：]', cell_text(cells[j])):
                j += 1                             # 跳过只放冒号的单元格
            if j >= len(cells) or cell_text(cells[j]).strip():
                continue                           # 已有内容的不覆盖
            cell = cells[j]
            val = escape(str(fields[lab]))
            if re.search(r'<w:t\b', cell):
                newc = re.sub(r'(<w:t\b[^>]*>)[^<]*(</w:t>)', lambda x, v=val: x.group(1) + v + x.group(2), cell, count=1)
            elif '</w:pPr>' in cell:
                newc = cell.replace('</w:pPr>', '</w:pPr><w:r><w:t xml:space="preserve">%s</w:t></w:r>' % val, 1)
            else:
                newc = re.sub(r'(<w:p\b[^>]*>)', lambda x, v=val: x.group(1) + '<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % v, cell, count=1)
            row = row.replace(cell, newc, 1)
            cells[j] = newc
            done.append(lab)
        return row
    body0 = re.sub(r'<w:tr\b(?:(?!<w:tr[ >]).)*?</w:tr>', row_fix, body0, flags=re.S)
    return body0, done


def number_figures(C, numbered):
    """给 fig 块编号，返回 {key: '3-1'}（编号版式）。"""
    labels, ch, k = {}, 0, 0
    for b in C.BLOCKS:
        if b[0] == 'h1':
            ch += 1; k = 0
        elif b[0] == 'fig':
            if b[1] in labels:
                raise ValueError('图 %r 被插入了两次' % b[1])
            k += 1
            labels[b[1]] = '%d-%d' % (ch, k) if ch else '%d' % k
    return labels


def subst(s, labels, numbered):
    def rep(m):
        key = m.group(1)
        if key not in labels:
            raise ValueError('正文引用了不存在或未插入的图 {图:%s}' % key)
        return '图' + labels[key] if numbered else '下图'
    return FIG_PH.sub(rep, s)


def build(template, content_path, out, pages):
    C = load_content(content_path)
    numbered = bool(getattr(C, 'NUMBERED', False))
    toc_cover = getattr(C, 'TOC_COVER', None)
    toc_cover = (not numbered) if toc_cover is None else bool(toc_cover)
    base = os.path.dirname(os.path.abspath(content_path))
    work = tempfile.mkdtemp(prefix='rz_build_')
    with zipfile.ZipFile(template) as z:
        z.extractall(work)
    for root, _, files in os.walk(work):
        for f in files:
            if os.path.islink(os.path.join(root, f)):
                os.remove(os.path.join(root, f))
    word = os.path.join(work, 'word')
    st = detect_styles(word)
    st['bullet'] = ensure_bullet(word, work)
    st.update(getattr(C, 'STYLE', {}) or {})
    reps = list(getattr(C, 'HEADER_REPLACE', []) or [])
    reps += [('【软件全称】', C.TITLE[0])] + ([('【版本号】', C.TITLE[1])] if len(C.TITLE) > 1 else [])
    for old, new in reps:
        hit = replace_in_parts(word, old, new)
        if hit or not old.startswith('【'):
            print('页眉页脚替换', repr(old), '->', repr(new), '命中', hit, '个部件')

    doc = open(os.path.join(word, 'document.xml'), encoding='utf-8').read()
    if 'xmlns:wp=' not in doc[:4000]:
        doc = doc.replace('<w:document ', '<w:document xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" ', 1)
    if 'xmlns:r=' not in doc[:4000]:
        doc = doc.replace('<w:document ', '<w:document xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ', 1)
    bi = doc.index('<w:body>') + len('<w:body>')
    head = doc[:bi]
    sect = re.findall(r'<w:sectPr\b.*?</w:sectPr>', doc, re.S)[-1]
    body0 = doc[bi:doc.rindex('<w:sectPr')]
    pg = re.search(r'<w:pgSz w:w="(\d+)" w:h="(\d+)"', sect)
    mar = {k: int(v) for k, v in re.findall(r'w:(top|bottom|left|right)="(-?\d+)"', re.search(r'<w:pgMar[^>]*/>', sect).group(0))}
    text_w = int(pg.group(1)) - mar['left'] - mar['right']
    text_h = int(pg.group(2)) - mar['top'] - mar['bottom']
    font = st.pop('font', '宋体'); sz = int(st.pop('sz', 24))
    B = Builder(st, font, sz, text_w, text_h)

    # 封面：模板中的封面表格（如有）原样保留并填写；封面标题段取前 N 个一级标题段，不够就取前 N 个非空段
    body0, filled = fill_cover_fields(body0, getattr(C, 'COVER_FIELDS', {}) or {})
    if filled:
        print('封面表格已填写：', '、'.join(filled))
    N = len(C.TITLE)
    tbl_spans = top_tables(body0)
    # 模板中的目录位置：目录之前是封面区，之后是旧正文
    toc_m = re.search(r'<w:sdt>(?:(?!</w:sdt>).)*?w:docPartGallery w:val="Table of Contents"', body0, re.S)
    toc_pos = toc_m.start() if toc_m else None
    if toc_pos is None:
        for m in re.finditer(r'<w:p\b[^>]*>.*?</w:p>', body0, re.S):
            x = m.group(0)
            if any(t0 <= m.start() < t1 for t0, t1 in tbl_spans):
                continue
            if re.search(r'w:pStyle w:val="(%s|%s|%s)"' % (re.escape(st['toc']), re.escape(st['toc1']), re.escape(st['toc2'])), x) \
                    or re.search(r'instrText[^>]*>\s*TOC\b', x):
                toc_pos = m.start()
                break
    limit = toc_pos if toc_pos is not None else len(body0)
    # 封面标题段：目录之前的一级标题段；不够 N 个时取目录之前前 N 个非空段（含封面框表格内的段落）
    paras = [m for m in re.finditer(r'<w:p\b[^>]*>(?:(?!<w:p[ >]).)*?</w:p>', body0, re.S) if m.start() < limit]
    h1 = [m for m in paras if 'w:pStyle w:val="%s"' % st['h1'] in m.group(0)]
    nonempty = [m for m in paras if re.search(r'<w:t\b[^>]*>[^<]*\S[^<]*</w:t>', m.group(0))]
    cover = (h1 if len(h1) >= N else nonempty)[:N]
    if len(cover) < N:
        raise SystemExit('ERROR 模板目录之前只找到 %d 个封面段，TITLE 有 %d 行；请调整 TITLE 行数或换模板' % (len(cover), N))
    toc_entries, titled = [], []
    for m, text in zip(cover, C.TITLE):
        i, name = B.new_bm()
        p = set_para_text(m.group(0), text)
        p = re.sub(r'<w:numPr>.*?</w:numPr>', '', p, flags=re.S)           # 封面行不要项目符号/编号
        if numbered:
            p = re.sub(r'<w:pStyle w:val="%s"/>' % re.escape(st['h1']), '', p)  # 防止封面被章节编号
        if '</w:pPr>' in p:
            p = p.replace('</w:pPr>', '</w:pPr><w:bookmarkStart w:id="%d" w:name="%s"/>' % (i, name), 1)
        else:
            p = re.sub(r'(<w:p\b[^>]*>)', r'\1<w:bookmarkStart w:id="%d" w:name="%s"/>' % (i, name), p, count=1)
        p = p[:p.rindex('</w:p>')] + '<w:bookmarkEnd w:id="%d"/></w:p>' % i
        titled.append(p)
        if toc_cover:
            toc_entries.append((1, text, name))
    # 封面区：模板中目录之前的内容（封面、封面表格、修订记录等）保留，目录及之后的模板正文全部丢弃
    cover_end = cover[-1].end()
    toc_break = False
    if toc_pos is not None and toc_pos >= cover_end:
        cover_end = toc_pos
        first_p = re.search(r'<w:p\b.*?</w:p>', body0[toc_pos:toc_pos + 20000], re.S)
        toc_break = bool(first_p and ('w:type="page"' in first_p.group(0) or '<w:pageBreakBefore/>' in first_p.group(0)))
    else:                                                   # 没有目录：保留紧随封面的分页段
        m = re.match(r'\s*(<w:p\b[^>]*>(?:(?!</w:p>).)*?w:type="page".*?</w:p>)', body0[cover_end:], re.S)
        if m and not re.search(r'<w:t\b[^>]*>[^<]+', m.group(1)):
            cover_end += m.end()
    cover_xml = body0[:cover_end]
    for m, t in zip(cover, titled):
        cover_xml = cover_xml.replace(m.group(0), t, 1)

    # 图片：删除正文原有图片关系，只删不再被其他部件引用的媒体文件
    rels_p = os.path.join(word, '_rels/document.xml.rels')
    rels = open(rels_p, encoding='utf-8').read()
    keep_ids = set(re.findall(r'r:embed="([^"]+)"', cover_xml))
    img_rel = re.compile(r'<Relationship\b[^>]*Type="[^"]*/image"[^>]*/>')
    drop = [r for r in img_rel.findall(rels) if re.search(r'Id="([^"]+)"', r).group(1) not in keep_ids]
    old_targets = set(re.findall(r'Target="([^"]+)"', ''.join(drop)))
    for r in drop:
        rels = rels.replace(r, '')
    other = ''
    for fn in os.listdir(os.path.join(word, '_rels')):
        if fn != 'document.xml.rels':
            other += open(os.path.join(word, '_rels', fn), encoding='utf-8').read()
    for tg in old_targets:
        if 'Target="%s"' % tg not in other and 'Target="%s"' % tg not in rels and os.path.exists(os.path.join(word, tg)):
            os.remove(os.path.join(word, tg))
    os.makedirs(os.path.join(word, 'media'), exist_ok=True)
    max_w = text_w * EMU_PER_TWIP
    max_h = int(min(21.5 * 360000, (text_h - 1700) * EMU_PER_TWIP))
    if numbered:
        max_h = int(min(20.5 * 360000, (text_h - 2300) * EMU_PER_TWIP))   # 给图题留位置
    fig_rel, new_rels = {}, []
    used = [b[1] for b in C.BLOCKS if b[0] == 'fig']
    for k, (key, spec) in enumerate(C.FIG.items()):
        if key not in used:
            print('WARN FIG 中的 %r 没有在 BLOCKS 中使用' % key)
            continue
        path, alt = spec[0], spec[1]
        shot = len(spec) > 2 and spec[2] == 'shot'
        src = path if os.path.isabs(path) else os.path.join(base, path)
        im = Image.open(src)
        w, h = im.size
        im = im.convert('RGB')
        if shot:
            if im.width > 1800:
                im = im.resize((1800, round(im.height * 1800 / im.width)), Image.LANCZOS)
        else:
            im = im.resize((max(1, im.width * 2 // 3), max(1, im.height * 2 // 3)), Image.LANCZOS)
            im = im.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
        dst = 'rzfig%02d.png' % (k + 1)
        im.save(os.path.join(word, 'media', dst), optimize=True)
        rid = 'rIdRz%02d' % (k + 1)
        new_rels.append('<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/%s"/>' % (rid, dst))
        cx = max_w                      # 流程图按正文宽度插入，但不超过原始尺寸（PNG 按 3 倍图计）
        if not shot:
            svg = os.path.splitext(src)[0] + '.svg'
            nat_w = w / 3
            if os.path.exists(svg):
                mv = re.search(r'viewBox="[\d.\-]+ [\d.\-]+ ([\d.]+) ([\d.]+)"', open(svg, encoding='utf-8').read())
                if mv:
                    nat_w = float(mv.group(1))
            cx = min(max_w, int(nat_w / 96 * 914400 * MAX_SCALE))
        if shot:                        # 截图：不超过原始尺寸，但不小于正文宽度的 60%
            cx = max(min(max_w, int(w / 96 * 914400)), int(max_w * 0.6))
        cy = int(cx * h / w)
        if cy > max_h:
            cy = max_h; cx = int(cy * w / h)
        fig_rel[key] = (rid, cx, cy, alt)
    rels = rels.replace('</Relationships>', ''.join(new_rels) + '</Relationships>')
    open(rels_p, 'w', encoding='utf-8').write(rels)
    ctp = os.path.join(work, '[Content_Types].xml')
    ct = open(ctp, encoding='utf-8').read()
    if 'Extension="png"' not in ct:
        ct = ct.replace('<Default ', '<Default Extension="png" ContentType="image/png"/><Default ', 1)
        open(ctp, 'w', encoding='utf-8').write(ct)

    labels = number_figures(C, numbered)
    body, num = [], [0, 0, 0]
    for b in C.BLOCKS:
        kind = b[0]
        if kind in ('h1', 'h2', 'h3', 'h2c'):
            lvl = 2 if kind == 'h2c' else int(kind[1])
            title = b[1]
            if numbered and kind != 'h2c':
                num[lvl - 1] += 1
                for j in range(lvl, 3):
                    num[j] = 0
                no = '.'.join(str(x) for x in num[:lvl])
                auto = st['auto_num'].get('h%d' % lvl)
                shown = title if auto else '%s %s' % (no, title)
                x, name = B.heading(lvl, shown)
                toc_entries.append((lvl, '%s %s' % (no, title), name))
            else:
                x, name = B.heading(lvl, title, center=(kind == 'h2c'), legacy=(kind in ('h2', 'h2c')))
                toc_entries.append((lvl if not toc_cover else max(lvl, 2), title, name))
            body.append(x)
        elif kind == 'p':
            body.append(B.p_body(subst(b[1], labels, numbered), keep=len(b) > 2 and b[2] == 'keep'))
        elif kind == 'req':
            body.append(B.p_req(subst(b[1], labels, numbered)))
        elif kind == 'fields':
            body.append(B.p_body(subst(b[1], labels, numbered), keep=True))
            body += [B.p_bullet(subst(lab, labels, numbered), subst(s, labels, numbered)) for lab, s in b[2]]
        elif kind == 'table':
            rows = [[subst(str(c), labels, numbered) for c in r] for r in b[1]]
            body.append(B.table(rows, b[2] if len(b) > 2 else {}))
        elif kind == 'fig':
            if b[1] not in fig_rel:
                raise ValueError('FIG 中没有 %r' % b[1])
            body.append(B.p_fig(*fig_rel[b[1]], keep=numbered))
            if numbered:
                body.append(B.p_caption('图 %s %s' % (labels[b[1]], fig_rel[b[1]][3])))
        elif kind == 'pb':
            body.append(B.p_pagebreak())
        else:
            raise ValueError('未知块类型 %r' % (kind,))
    xml = head + cover_xml + B.toc(toc_entries, pages, toc_break) + ''.join(body) + sect + '</w:body></w:document>'
    open(os.path.join(word, 'document.xml'), 'w', encoding='utf-8').write(xml)
    if os.path.exists(out):
        os.remove(out)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    subprocess.run(['zip', '-q', '-X', '-r', os.path.abspath(out), '.'], cwd=work, check=True)
    shutil.rmtree(work)
    return toc_entries


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--template', default=None, help='默认使用 assets/template_design.docx')
    ap.add_argument('--content', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--pages', default=None, help='已有页码 JSON（不用 --auto-toc 时）')
    ap.add_argument('--auto-toc', action='store_true')
    a = ap.parse_args()
    template = a.template or DEFAULT_TEMPLATE
    pages = json.load(open(a.pages)) if a.pages and os.path.exists(a.pages) else {}
    entries = build(template, a.content, a.out, pages)
    if a.auto_toc:
        sys.path.insert(0, HERE)
        from rz_common import convert
        from toc_pages import find_pages
        pdfdir = os.path.join(os.path.dirname(os.path.abspath(a.out)), 'pdf')
        new, n, pdf = pages, 0, None
        for rnd in range(4):
            pdf = convert(a.out, 'pdf', pdfdir)
            new, miss, n = find_pages(pdf, entries)
            if miss:
                print('WARN 在 PDF 中找不到这些标题:', miss)
            if new == pages:
                break
            pages = new
            entries = build(template, a.content, a.out, pages)
        json.dump(pages, open(os.path.join(pdfdir, 'pages.json'), 'w'), ensure_ascii=False)
        print('目录页码稳定' if new == pages else 'WARN 4 轮后页码仍在变化', '共', n, '页；PDF:', pdf)
    print('built', a.out, os.path.getsize(a.out), 'bytes')


if __name__ == '__main__':
    main()
