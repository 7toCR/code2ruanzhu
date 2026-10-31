# -*- coding: utf-8 -*-
"""照参考件同款排版：从一份已获批的参考软著中取出各类段落的版式，供 build_docx.py --like 使用。

取出的版式（都是参考件里真实段落的 pPr 和首个文字 run 的 rPr）：
  h1/h2/h3  各级标题（含是否“段前分页”、自动编号样式）
  body      正文（出现最多的版式）；参考件对含长英文名的段落用了 wordWrap 时一并沿用
  bullet    项目符号段（出现最多的版式，含 numId）
  fig, cap  图片段与紧随其后的图题段（图题形如“图 3-1 标题”）
  toc       目录：标题段、首条目（含 TOC 域开头）、各级条目、结尾段
另外记录：参考件正文有没有表格（没有时建议把表格改写成“具体字段解释如下：”加项目符号）。

模板与参考件不是同一个文件时，import_into() 会把这些段落用到的样式、编号定义从参考件补进模板：
同名样式沿用模板里的样式 ID，模板没有的样式整段复制（连同 basedOn 链），编号定义复制并改用新 ID。
"""
import collections
import os
import re
import zipfile
from xml.sax.saxutils import escape

from rz_common import top_elements

CAP = re.compile(r'^\s*图\s*\d+(?:\s*[-－—.．]\s*\d+)?\s+\S')
PPR_ORDER = ['pStyle', 'keepNext', 'keepLines', 'pageBreakBefore', 'framePr', 'widowControl', 'numPr',
             'suppressLineNumbers', 'pBdr', 'shd', 'tabs', 'suppressAutoHyphens', 'kinsoku', 'wordWrap',
             'overflowPunct', 'topLinePunct', 'autoSpaceDE', 'autoSpaceDN', 'bidi', 'adjustRightInd', 'snapToGrid',
             'spacing', 'ind', 'contextualSpacing', 'mirrorIndents', 'suppressOverlap', 'jc', 'textDirection',
             'textAlignment', 'textboxTightWrap', 'outlineLvl', 'divId', 'cnfStyle', 'rPr', 'sectPr', 'pPrChange']


def _clean(x):
    return re.sub(r'\s(?:w14:paraId|w14:textId|w:rsid\w*)="[^"]*"', '', x)


def _text(p):
    t = ''.join(re.findall(r'<w:t\b[^>]*>([^<]*)</w:t>', p))
    return (t.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&apos;', "'").replace('&amp;', '&'))


def _ppr(p):
    m = re.search(r'<w:pPr>.*?</w:pPr>', p, re.S)
    return m.group(0) if m else '<w:pPr></w:pPr>'


def _rpr(p):
    for r in re.findall(r'<w:r\b[^>]*>.*?</w:r>', p, re.S):
        if '<w:t' in r:
            m = re.search(r'<w:rPr>.*?</w:rPr>', r, re.S)
            return m.group(0) if m else ''
    return ''


def _sig(ppr):
    s = re.sub(r'<w:rPr>.*?</w:rPr>', '', ppr, flags=re.S)
    return re.sub(r'<w:(keepNext|keepLines|wordWrap)\b[^>]*/>', '', s)


def ppr_set(ppr, tag, xml):
    """在 pPr 中按 schema 顺序放入（或替换）一个子元素。"""
    ppr = re.sub(r'<w:%s\b[^>]*/>|<w:%s\b[^>]*>.*?</w:%s>' % (tag, tag, tag), '', ppr, flags=re.S)
    later = PPR_ORDER[PPR_ORDER.index(tag) + 1:]
    m = re.search(r'<w:(%s)\b' % '|'.join(later), ppr)
    pos = m.start() if m else ppr.rindex('</w:pPr>')
    return ppr[:pos] + xml + ppr[pos:]


class Profile:
    def __init__(self, path):
        self.path = path
        z = zipfile.ZipFile(path)
        rd = lambda n: z.read(n).decode('utf-8') if n in z.namelist() else ''
        doc, self.styles_xml, self.numbering_xml = rd('word/document.xml'), rd('word/styles.xml'), rd('word/numbering.xml')
        self.theme_xml = rd('word/theme/theme1.xml')
        self.names = {m.group(1): m.group(2).lower() for m in
                      re.finditer(r'<w:style\b[^>]*w:styleId="([^"]+)"[^>]*>\s*<w:name w:val="([^"]+)"', self.styles_xml)}
        body = doc[doc.index('<w:body>') + 8:doc.rindex('<w:sectPr')]
        els = top_elements(body)
        toc_i = next((k for k, (t, x) in enumerate(els) if t == 'sdt' and 'Table of Contents' in x), None)
        self.toc = self._toc(els[toc_i][1]) if toc_i is not None else None
        after = els[toc_i + 1:] if toc_i is not None else els
        self.has_tables = any(t == 'tbl' for t, _ in after)
        self.t = {}
        bodies, bullets = collections.Counter(), collections.Counter()
        first = {}
        self.wordwrap = False
        ps = [x for t, x in after if t == 'p']
        for k, p in enumerate(ps):
            lv = self.level(p)
            txt = _text(p).strip()
            if lv and 'h%d' % lv not in self.t:
                self.t['h%d' % lv] = p
            if lv:
                continue
            if ('<w:drawing' in p or '<w:pict' in p):
                if 'fig' not in self.t:
                    self.t['fig'] = p
                    if k + 1 < len(ps) and CAP.match(_text(ps[k + 1])):
                        self.t['cap'] = ps[k + 1]
                continue
            if CAP.match(txt) or not txt:
                continue
            sig = _sig(_ppr(p))
            if '<w:numPr>' in p:
                bullets[sig] += 1; first.setdefault(('b', sig), p)
            elif len(txt) >= 15:
                bodies[sig] += 1; first.setdefault(('p', sig), p)
                self.wordwrap |= '<w:wordWrap w:val="0"/>' in p
        if bodies:
            self.t['body'] = first[('p', bodies.most_common(1)[0][0])]
        if bullets:
            self.t['bullet'] = first[('b', bullets.most_common(1)[0][0])]
        self.h1_break = '<w:pageBreakBefore/>' in _ppr(self.t.get('h1', ''))
        self.has_captions = 'cap' in self.t
        self.idmap, self.nummap = {}, {}

    # ---------- 读取 ----------
    def level(self, p):
        sid = re.search(r'<w:pStyle w:val="([^"]+)"', p)
        nm = self.names.get(sid.group(1), '') if sid else ''
        m = re.match(r'(?:heading|标题)\s*(\d)$', nm)
        return int(m.group(1)) if m else 0

    def _toc(self, sdt):
        paras = re.findall(r'<w:p\b[^>]*>.*?</w:p>|<w:p\b[^>]*/>', sdt, re.S)
        if not paras:
            return None
        lv = {}
        for p in paras:
            sid = re.search(r'<w:pStyle w:val="([^"]+)"', p)
            nm = self.names.get(sid.group(1), '') if sid else ''
            m = re.match(r'toc (\d)$', nm)
            if m and 'fldCharType="begin"' not in p.split('<w:hyperlink', 1)[0] and '<w:hyperlink' in p:
                lv.setdefault(int(m.group(1)), p)
        entries = [p for p in paras if '<w:hyperlink' in p]
        if not entries:
            return None
        first = next((p for p in entries if 'TOC \\o' in p or 'TOC \\\\o' in p), entries[0])
        i0, i1 = paras.index(entries[0]), paras.index(entries[-1])
        return dict(head=sdt[:sdt.index(paras[0])], tail=sdt[sdt.rindex(paras[-1]) + len(paras[-1]):],
                    title=''.join(paras[:i0]), first=first, levels=lv, end=''.join(paras[i1 + 1:]))

    def auto_numbered(self, kind):
        """该段落是否由样式或段落编号自动产生“1”“3.1”这类编号（是则标题文字不再手写编号）。"""
        p = self.t.get(kind, '')
        if '<w:numPr>' in _ppr(p):
            return True
        sid = re.search(r'<w:pStyle w:val="([^"]+)"', p)
        seen = set()
        while sid and sid.group(1) not in seen:
            seen.add(sid.group(1))
            m = re.search(r'<w:style\b[^>]*w:styleId="%s"[^>]*>.*?</w:style>' % re.escape(sid.group(1)), self.styles_xml, re.S)
            if not m:
                return False
            if '<w:numPr>' in m.group(0):
                return True
            sid = re.search(r'<w:basedOn w:val="([^"]+)"', m.group(0))
        return False

    def style_ids(self):
        xs = ' '.join(v for v in self.t.values())
        if self.toc:
            xs += ' '.join([self.toc['title'], self.toc['first'], self.toc['end']] + list(self.toc['levels'].values()))
        return set(re.findall(r'<w:(?:pStyle|rStyle) w:val="([^"]+)"', xs))

    def num_ids(self):
        return set(re.findall(r'<w:numId w:val="(\d+)"', ' '.join(self.t.values())))

    # ---------- 写出 ----------
    def _map(self, x):
        for a, b in self.idmap.items():
            x = re.sub(r'(<w:(?:pStyle|rStyle) w:val=")%s(")' % re.escape(a), r'\g<1>%s\2' % b, x)
        for a, b in self.nummap.items():
            x = x.replace('<w:numId w:val="%s"/>' % a, '<w:numId w:val="%s"/>' % b)
        return x

    def has(self, kind):
        return kind in self.t

    def para(self, kind, text, bm=None, keep=False, center=False, long_ascii=False):
        p = self.t[kind]
        ppr, rpr = _ppr(p), _rpr(p)
        if keep:
            ppr = ppr_set(ppr, 'keepNext', '<w:keepNext/>')
        if center:
            ppr = ppr_set(ppr, 'jc', '<w:jc w:val="center"/>')
        if long_ascii and self.wordwrap and kind == 'body' and '<w:wordWrap' not in ppr:
            ppr = ppr_set(ppr, 'wordWrap', '<w:wordWrap w:val="0"/>')
        run = '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (rpr, escape(text))
        if bm:
            run = '<w:bookmarkStart w:id="%d" w:name="%s"/>%s<w:bookmarkEnd w:id="%d"/>' % (bm[0], bm[1], run, bm[0])
        return self._map(_clean('<w:p>%s%s</w:p>' % (ppr, run)))

    def fig_para(self, drawing_run):
        return self._map(_clean('<w:p>%s%s</w:p>' % (_ppr(self.t['fig']), drawing_run)))

    def toc_xml(self, entries, pages):
        T = self.toc

        def fill(tpl, text, name, page):
            old = re.search(r'w:anchor="([^"]+)"', tpl).group(1)
            x = tpl.replace('"%s"' % old, '"%s"' % name).replace(' %s ' % old, ' %s ' % name)
            ts = list(re.finditer(r'<w:t(?: [^>]*)?>[^<]*</w:t>', x))
            if not ts:
                return x
            last = ts[-1]
            x = x[:last.start()] + '<w:t>%s</w:t>' % page + x[last.end():]
            first = re.search(r'<w:t(?: [^>]*)?>[^<]*</w:t>', x)
            return x[:first.start()] + '<w:t xml:space="preserve">%s</w:t>' % escape(text) + x[first.end():]
        out = [T['head'], T['title']]
        for k, (lvl, text, name) in enumerate(entries):
            if k == 0:
                tpl = T['first']
            else:
                tpl = T['levels'].get(lvl) or T['levels'].get(max([l for l in T['levels'] if l <= lvl] or [0]), T['first'])
                if 'fldCharType="begin"' in tpl.split('<w:hyperlink', 1)[0]:        # 首条目带域开头，不能重复
                    tpl = re.sub(r'(<w:pPr>.*?</w:pPr>).*?(<w:hyperlink)', r'\1\2', tpl, count=1, flags=re.S)
            out.append(fill(tpl, text, name, pages.get(name, 1)))
        out.append(T['end'] or '<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
        out.append(T['tail'])
        return self._map(_clean(''.join(out)))

    def east_asian_font(self):
        m = re.search(r'<a:minorFont>.*?<a:font script="Hans" typeface="([^"]*)"', self.theme_xml, re.S)
        return m.group(1) if m else ''

    # ---------- 补样式与编号定义 ----------
    def import_into(self, word, unpacked):
        sp = os.path.join(word, 'styles.xml')
        ts = open(sp, encoding='utf-8').read()
        tnames = {}
        for m in re.finditer(r'<w:style\b[^>]*w:styleId="([^"]+)"[^>]*>\s*<w:name w:val="([^"]+)"', ts):
            tnames.setdefault(m.group(2).lower(), m.group(1))
        tids = {v: k for k, v in tnames.items()}
        blocks = {m.group(1): m.group(0) for m in re.finditer(r'<w:style\b[^>]*w:styleId="([^"]+)"[^>]*>.*?</w:style>', self.styles_xml, re.S)}
        added = []

        def need(sid):
            if sid in self.idmap or sid in added:
                return
            nm = self.names.get(sid, '')
            if sid in tids and tids[sid] == nm:
                return
            if nm and nm in tnames:
                self.idmap[sid] = tnames[nm]
                return
            new = sid if sid not in tids else sid + 'Ref'
            if new != sid:
                self.idmap[sid] = new
            blk = blocks.get(sid)
            if not blk:
                return
            added.append(sid)
            for dep in re.findall(r'<w:(?:basedOn|next|link) w:val="([^"]+)"', blk):
                need(dep)
        for sid in sorted(self.style_ids()):
            need(sid)
        if added:
            ins = ''
            for sid in added:
                blk = blocks[sid]
                for a, b in self.idmap.items():
                    blk = re.sub(r'(w:(?:styleId|val)=")%s(")' % re.escape(a), r'\g<1>%s\2' % b, blk)
                ins += blk
            ts = ts.replace('</w:styles>', ins + '</w:styles>')
            open(sp, 'w', encoding='utf-8').write(ts)
        # 编号定义
        ids = self.num_ids()
        if ids and self.numbering_xml:
            np_ = os.path.join(word, 'numbering.xml')
            if not os.path.exists(np_):
                from build_docx import ensure_numbering_part
                ensure_numbering_part(word, unpacked)
            tn = open(np_, encoding='utf-8').read()
            base = 9300
            def lvl0(xml, nid):
                m = re.search(r'<w:num w:numId="%s"[^>]*>.*?<w:abstractNumId w:val="(\d+)"/>.*?</w:num>' % nid, xml, re.S)
                ab = m and re.search(r'<w:abstractNum\b[^>]*w:abstractNumId="%s".*?</w:abstractNum>' % m.group(1), xml, re.S)
                if not ab:
                    return None, None
                l0 = re.search(r'<w:lvl w:ilvl="0".*?</w:lvl>', ab.group(0), re.S)
                key = re.sub(r'\s(?:w:tplc|w15:\w+)="[^"]*"', '', l0.group(0)) if l0 else ''
                return m, (ab, key)
            for nid in sorted(ids):
                m, ab_key = lvl0(self.numbering_xml, nid)
                if not m:
                    continue
                ab, key = ab_key
                _, tk = lvl0(tn, nid)
                if tk and tk[1] == key:
                    continue                           # 模板里同号的编号定义与参考件相同，直接沿用
                base += 1
                abx = re.sub(r'w:abstractNumId="%s"' % m.group(1), 'w:abstractNumId="%d"' % base, ab.group(0), count=1)
                abx = re.sub(r'<w:nsid [^>]*/>|<w:tmpl [^>]*/>', '', abx)
                numx = '<w:num w:numId="%d"><w:abstractNumId w:val="%d"/></w:num>' % (base, base)
                if '<w:num ' in tn:
                    tn = tn.replace('<w:num ', abx + '<w:num ', 1)
                else:
                    tn = tn.replace('</w:numbering>', abx + '</w:numbering>')
                tn = tn.replace('</w:numbering>', numx + '</w:numbering>')
                self.nummap[nid] = str(base)
            open(np_, 'w', encoding='utf-8').write(tn)
        return added

    def summary(self):
        have = [k for k in ('h1', 'h2', 'h3', 'body', 'bullet', 'fig', 'cap') if k in self.t]
        return ('参考件版式：%s；目录%s；一级标题%s段前分页；%s表格；%s' %
                ('、'.join(have), '已取到' if self.toc else '未取到', '' if self.h1_break else '不',
                 '有' if self.has_tables else '没有', '有图题（编号版式）' if self.has_captions else '无图题'))


# ---------- 与参考件对比（check_ruanzhu.py --like 使用） ----------
KINDS = {'h1': '一级标题', 'h2': '二级标题', 'h3': '三级标题', 'body': '正文', 'bullet': '项目符号段',
         'fig': '图片段', 'cap': '图题'}


def _children(x, names):
    """把 pPr / rPr 拆成 {标签: 规范化后的 XML}，样式 ID 换成样式名，编号 ID、rsid、书签不参与比较。"""
    x = _clean(x)
    x = re.sub(r'<w:rPr>.*?</w:rPr>', '', x, flags=re.S) if x.startswith('<w:pPr') else x
    x = re.sub(r'^<w:[pr]Pr>|</w:[pr]Pr>$', '', x)
    x = re.sub(r'<w:pStyle w:val="([^"]+)"/>', lambda m: '<w:pStyle w:val="%s"/>' % names.get(m.group(1), m.group(1)), x)
    x = re.sub(r'<w:numId w:val="\d+"/>', '<w:numId/>', x)
    out = {}
    for m in re.finditer(r'<w:(\w+)\b[^>]*?/>|<w:(\w+)\b[^>]*>.*?</w:\2>', x, re.S):
        tag = m.group(1) or m.group(2)
        if tag not in ('keepNext', 'keepLines'):
            out[tag] = m.group(0)
    return out


def _style_block(styles_xml, sid):
    m = re.search(r'<w:style\b[^>]*w:styleId="%s"[^>]*>.*?</w:style>' % re.escape(sid), styles_xml, re.S)
    return m.group(0) if m else ''


def _effective(prof, p):
    """段落自身格式叠加样式链（basedOn）后的 pPr / rPr 子元素。"""
    ppr, rpr = {}, {}
    sid = re.search(r'<w:pStyle w:val="([^"]+)"', p)
    chain, seen = [], set()
    while sid and sid.group(1) not in seen:
        seen.add(sid.group(1))
        blk = _style_block(prof.styles_xml, sid.group(1))
        if not blk:
            break
        chain.append(blk)
        sid = re.search(r'<w:basedOn w:val="([^"]+)"', blk)
    for blk in reversed(chain):
        mp = re.search(r'<w:pPr>.*?</w:pPr>', blk, re.S)
        mr = re.search(r'<w:rPr>.*?</w:rPr>', blk, re.S)
        ppr.update(_children(mp.group(0), prof.names) if mp else {})
        rpr.update(_children(mr.group(0), prof.names) if mr else {})
    ppr.update(_children(_ppr(p), prof.names))
    rpr.update(_children(_rpr(p), prof.names))
    ppr.pop('pStyle', None)
    for k in ('lang', 'noProof'):
        rpr.pop(k, None)
    return ppr, rpr


def _short(x, n=80):
    return x if len(x) <= n else x[:n - 1] + '…'


def page_setup(path):
    doc = zipfile.ZipFile(path).read('word/document.xml').decode('utf-8')
    sect = re.findall(r'<w:sectPr\b.*?</w:sectPr>', doc, re.S)
    sect = _clean(sect[-1]) if sect else ''
    out = {}
    for tag in ('pgSz', 'pgMar', 'cols', 'docGrid', 'lnNumType', 'titlePg'):
        m = re.search(r'<w:%s\b[^>]*/>' % tag, sect)
        if m:
            out[tag] = m.group(0)
    return out


def layout_diff(target, ref):
    """返回 [(类别, 说明)]：目标文档与参考件在各类段落版式、页面设置、目录上的差异。空列表表示一致。"""
    T, R = Profile(target), Profile(ref)
    diffs = []
    for k, label in KINDS.items():
        if k not in R.t:
            continue
        if k not in T.t:
            if k in ('h1', 'h2', 'body', 'cap'):
                diffs.append((label, '参考件有这类段落，目标文档里没找到'))
            continue
        tp, tr = _effective(T, T.t[k])
        rp, rr = _effective(R, R.t[k])
        bad = []
        for what, a, b in (('段落', tp, rp), ('文字', tr, rr)):
            for tag in sorted(set(a) | set(b)):
                if a.get(tag) != b.get(tag):
                    bad.append('%s.%s' % (what, tag))
        if bad:
            ex = bad[0].split('.', 1)
            src_t = (tp if ex[0] == '段落' else tr).get(ex[1], '无')
            src_r = (rp if ex[0] == '段落' else rr).get(ex[1], '无')
            diffs.append((label, '%s 不同（例如 %s：目标 %s，参考 %s）' % ('、'.join(bad[:6]), ex[1], _short(src_t), _short(src_r))))
    ps_t, ps_r = page_setup(target), page_setup(ref)
    bad = [k for k in sorted(set(ps_t) | set(ps_r)) if ps_t.get(k) != ps_r.get(k)]
    if bad:
        diffs.append(('页面设置', '%s 不同（目标 %s，参考 %s）' % ('、'.join(bad), _short(ps_t.get(bad[0], '无')), _short(ps_r.get(bad[0], '无')))))
    if bool(R.toc) != bool(T.toc):
        diffs.append(('目录', '参考件%s目录，目标文档%s' % ('有' if R.toc else '没有', '有' if T.toc else '没有')))
    elif R.toc:
        for lv in sorted(R.toc['levels']):
            if lv not in T.toc['levels']:
                diffs.append(('目录', '目标文档目录缺少第 %d 级条目' % lv))
                continue
            a, _ = _effective(T, T.toc['levels'][lv])
            b, _ = _effective(R, R.toc['levels'][lv])
            bad = [x for x in sorted(set(a) | set(b)) if a.get(x) != b.get(x)]
            if bad:
                diffs.append(('目录', '第 %d 级条目段落 %s 不同' % (lv, '、'.join(bad[:5]))))
    if R.h1_break != T.h1_break:
        diffs.append(('一级标题', '参考件%s段前分页，目标文档%s' % ('' if R.h1_break else '不', '是' if T.h1_break else '不是')))
    if R.has_captions != T.has_captions:
        diffs.append(('图题', '参考件%s图题，目标文档%s' % ('有' if R.has_captions else '没有', '有' if T.has_captions else '没有')))
    return diffs
