# -*- coding: utf-8 -*-
"""软著材料形式检查：设计说明书 / 源代码文档 / 信息采集卡 JSON。

用法:
  python3 check_ruanzhu.py design 说明书.docx --name 软件全称 --version V1.0 [--code-lines 12953] [--min-lines 30] [--json 报告.json]
  python3 check_ruanzhu.py source 源代码.docx --name 软件全称 --version V1.0 [--lines-per-page 50] [--json 报告.json]
  python3 check_ruanzhu.py card   采集卡.json [--design 说明书.docx] [--stats 源代码统计.json] [--json 报告.json]

输出 ERROR / WARN / INFO 三级结果，退出码：有 ERROR 时为 1。
检查项代码与含义见 references/compliance-review.md。页数、页码、目录、每页行数依赖 LibreOffice 渲染，
与 Word 的分页可能差一两页，差 1 页只给 WARN。
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rz_common import (convert, default_header_parts, docx_xml, header_footer_text, norm, para_text,  # noqa: E402
                       paragraphs, pdf_pages)

FORBIDDEN = re.compile(r'[（(【\[]\s*待(确认|补充|定|核实|完善)|待(确认|补充|核实)[：:]|TODO|TBD|FIXME|XXX|推测|猜测|\?\?\?')
LINKS = re.compile(r'https?://|www\.|[\w.+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b|copyright|©|版权所有|all rights reserved', re.I)
COMPANY = re.compile(r'[一-龥A-Za-z]{2,30}(有限公司|有限责任公司|股份公司|集团)|Co\.,?\s*Ltd|Inc\.|GmbH', re.I)
FIRST_PERSON = re.compile(r'我们|本人|笔者|我司|咱们')
EXEMPT_FIG = re.compile(r'概述|引言|简介|编写目的|项目背景|背景|运行要求|运行环境|系统要求|环境要求|硬件环境|软件环境|术语|定义|'
                        r'参考|修订|附录|部署|安装|数据库|接口|需求|目录|版本|说明书|总结|其他')
CAPTION = re.compile(r'^图\s*(\d+)(?:\s*[-－—.．]\s*(\d+))?\s+\S')
FIG_REF = re.compile(r'如图\s*(\d+(?:\s*[-－—.．]\s*\d+)?)\s*所示')


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, code, msg):
        self.items.append(dict(level=level, code=code, msg=msg))

    def show(self, title):
        print('==', title)
        order = {'ERROR': 0, 'WARN': 1, 'INFO': 2}
        for it in sorted(self.items, key=lambda x: order[x['level']]):
            print('%-5s %s  %s' % (it['level'], it['code'], it['msg']))
        ne = sum(1 for i in self.items if i['level'] == 'ERROR')
        nw = sum(1 for i in self.items if i['level'] == 'WARN')
        print('合计：%d 个 ERROR，%d 个 WARN' % (ne, nw))
        return ne


def header_checks(R, docx, name, version):
    hf = header_footer_text(docx)
    parts = default_header_parts(docx)
    heads = [hf[p][0] for p in parts.get('header', []) if p in hf] or [v[0] for k, v in hf.items() if k.startswith('header')]
    htxt = norm(' '.join(heads))
    if not heads:
        R.add('ERROR', 'H01', '没有页眉。页眉应标注“软件全称 版本号”，与申请表一致')
    else:
        if name and norm(name) not in htxt:
            R.add('ERROR', 'H01', '页眉未包含软件全称“%s”（页眉文字：%s）' % (name, ' / '.join(h.strip() for h in heads)[:80]))
        if version and norm(version) not in htxt:
            R.add('ERROR', 'H01', '页眉未包含版本号“%s”' % version)
    if not any(v[1] for v in hf.values()):
        R.add('ERROR', 'H02', '页眉页脚中没有 PAGE 页码域，页码需连续且位于页眉右上角或页脚')
    if name and not re.search(r'(软件|系统|平台)$', name):
        R.add('WARN', 'H03', '软件全称建议以“软件”“系统”或“平台”结尾：%s' % name)


def toc_entries(paras):
    out = []
    for p in paras:
        if re.match(r'toc \d', p['style']) or p['style'] in ('目录 1', '目录 2', '目录 3'):
            x = p['xml']
            i = x.rfind('<w:tab/>')
            if i < 0:
                m = re.match(r'(.*?)(\d+)$', p['text'].strip())
                if m:
                    out.append((m.group(1).strip(), int(m.group(2))))
                continue
            title, page = para_text(x[:i]).strip(), para_text(x[i:]).strip()
            if title and re.fullmatch(r'\d+', page):
                out.append((title, int(page)))
    return out


def heading_level(style):
    m = re.match(r'heading (\d)', style)
    if m:
        return int(m.group(1))
    m = re.match(r'标题 (\d)', style)
    return int(m.group(1)) if m else None


def find_heading_page(pages, title, start):
    t = norm(title)
    bare = norm(re.sub(r'^[\d.]+\s*', '', title))
    for i in range(start, len(pages)):
        for line in pages[i].splitlines():
            if re.search(r'\.{4,}|…{2,}', line):
                continue
            l = norm(line)
            if l == t or l == bare or (bare and l.endswith(bare) and re.fullmatch(r'[\d.第章节、一二三四五六七八九十：:]*', l[:-len(bare)] or '')):
                return i
    return None


def pdf_images_pages(pdf):
    r = subprocess.run(['pdfimages', '-list', pdf], capture_output=True, text=True)
    pages = set()
    for line in r.stdout.splitlines()[2:]:
        f = line.split()
        if f and f[0].isdigit():
            pages.add(int(f[0]))
    return pages


def design(a):
    R = Report()
    docx = a.docx
    header_checks(R, docx, a.name, a.version)
    paras = paragraphs(docx)
    doc = docx_xml(docx)
    body = [p for p in paras if not re.match(r'toc', p['style']) and not p['in_table']]
    text_all = '\n'.join(p['text'] for p in body)

    if a.name and norm(a.name) not in norm(text_all):
        R.add('ERROR', 'N01', '正文没有出现软件全称“%s”' % a.name)
    for code, rx, lvl, what in (('W01', FORBIDDEN, 'ERROR', '待确认/TODO 类字样'), ('W02', LINKS, 'WARN', '网址/邮箱/版权字样'),
                                ('W03', COMPANY, 'WARN', '公司名称'), ('W04', FIRST_PERSON, 'WARN', '第一人称')):
        hits = [p['text'][:60] for p in body if rx.search(p['text'])]
        if hits:
            R.add(lvl, code, '正文出现%s %d 处，例如：%s' % (what, len(hits), ' | '.join(hits[:3])))
    if '<w:ins ' in doc or '<w:del ' in doc or docx_xml(docx, 'word/comments.xml'):
        R.add('WARN', 'D01', '文档含修订痕迹或批注，提交前请接受全部修订并删除批注')

    # 封面
    toc_idx = next((i for i, p in enumerate(paras) if re.match(r'toc', p['style']) or norm(p['text']) == '目录'), len(paras))
    cover = [p for p in paras[:toc_idx] if p['text'].strip()]
    if any(p['num'] for p in cover[:6]):
        R.add('WARN', 'C02', '封面标题段带有项目符号或编号：%s' % [p['text'][:20] for p in cover[:6] if p['num']])
    pre = doc[:doc.find(paras[toc_idx]['xml'])] if toc_idx < len(paras) else ''
    blanks = []
    for row in re.findall(r'<w:tr\b(?:(?!<w:tr[ >]).)*?</w:tr>', pre, re.S):
        cells = [para_text(c).strip() for c in re.findall(r'<w:tc\b.*?</w:tc>', row, re.S)]
        k = 0
        while k < len(cells) - 1:
            lab = cells[k]
            j = k + 1
            while j < len(cells) and re.fullmatch(r'[:：]', cells[j]):
                j += 1
            colon = lab.endswith((':', '：')) or j > k + 1
            if colon and re.sub(r'[:：\s]', '', lab) and j < len(cells) and not cells[j]:
                blanks.append(re.sub(r'[:：\s]', '', lab))
            k = j
    if blanks:
        R.add('WARN', 'C01', '封面表格有空白项：%s（填写真实信息或删除该行）' % '、'.join(blanks))

    # 篇幅
    words = len(norm(''.join(p['text'] for p in body if not heading_level(p['style']))))
    if words < 500:
        R.add('ERROR', 'L01', '正文仅 %d 字，核心功能描述不足 500 字' % words)
    else:
        R.add('INFO', 'L01', '正文约 %d 字' % words)

    # 章节与流程图
    secs, stack = [], []
    for i, p in enumerate(body):
        lv = heading_level(p['style'])
        if lv and p['text'].strip():
            secs.append(dict(level=lv, title=p['text'].strip(), start=i, img=False, text=0, child=False))
            continue
        if secs:
            if p['img']:
                secs[-1]['img'] = True
            secs[-1]['text'] += len(norm(p['text']))
    for k, s in enumerate(secs):
        nxt = secs[k + 1] if k + 1 < len(secs) else None
        s['child'] = bool(nxt and nxt['level'] > s['level'])
    top = min([s['level'] for s in secs] or [1])
    cover_titles = {norm(p['text']) for p in cover}
    missing = [s['title'] for s in secs if not s['child'] and not s['img'] and s['text'] > 0
               and not EXEMPT_FIG.search(s['title']) and norm(s['title']) not in cover_titles and s['level'] >= top]
    if missing:
        R.add('ERROR', 'F01', '%d 个功能章节没有流程图（每个模块都需要流程图）：%s' % (len(missing), '、'.join(missing)))
    nimg = sum(1 for p in body if p['img'])
    R.add('INFO', 'F00', '共 %d 张图，%d 个章节' % (nimg, len(secs)))
    caps = [CAPTION.match(p['text'].strip()) for p in body]
    caps = [m for m in caps if m]
    if caps:
        labels = ['%s-%s' % (m.group(1), m.group(2)) if m.group(2) else m.group(1) for m in caps]
        dup = sorted({x for x in labels if labels.count(x) > 1})
        if dup:
            R.add('ERROR', 'F02', '图号重复：%s' % dup)
        refs = set(re.sub(r'\s|[－—.．]', '-', r) for r in FIG_REF.findall(text_all))
        bad = sorted(r for r in refs if r not in labels)
        if bad:
            R.add('ERROR', 'F03', '正文引用了不存在的图号：%s' % bad)
        if len(caps) < nimg:
            R.add('WARN', 'F04', '有 %d 张图没有图题（图题格式“图 3-1 标题”）' % (nimg - len(caps)))

    if a.no_render:
        return R
    pdf = a.pdf or convert(docx, 'pdf', a.outdir)
    pages = pdf_pages(pdf)
    n = len(pages)
    R.add('INFO', 'P00', 'LibreOffice 渲染共 %d 页（%s）' % (n, pdf))
    if a.code_lines:
        need = 40 if a.code_lines >= 100000 else 20 if a.code_lines >= 10000 else 15
        if n < need:
            R.add('ERROR', 'P01', '源程序量 %d 行，说明书需不少于 %d 页，当前 %d 页' % (a.code_lines, need, n))
        else:
            R.add('INFO', 'P01', '源程序量 %d 行，要求不少于 %d 页，当前 %d 页' % (a.code_lines, need, n))
    if n > 60:
        R.add('INFO', 'P03', '超过 60 页，一般交存时提交前 30 页和后 30 页')
    # 每页行数
    imgp = pdf_images_pages(pdf)
    toc_pages = {i for i, t in enumerate(pages) if '目录' in t[:400] or len(re.findall(r'\.{6,}', t)) >= 3}
    thin = []
    for i, t in enumerate(pages):
        if i == 0 or i == n - 1 or i in toc_pages or (i + 1) in imgp or '修订' in t[:300]:
            continue
        rows = [l for l in t.splitlines() if l.strip()]
        rows = [l for l in rows if not (a.name and norm(a.name) in norm(l)) and not re.fullmatch(r'\s*(\d+|\d+\s*of\s*\d+|第\s*\d+\s*页.*)\s*', l)]
        if len(rows) < a.min_lines:
            thin.append('%d(%d行)' % (i + 1, len(rows)))
    if thin:
        R.add('WARN', 'P02', '无图页面行数少于 %d 行：%s。常见原因是章节前强制分页，或下一张图放不下被推到下一页；可去掉分页、缩小图片或调整段落'
              % (a.min_lines, '、'.join(thin)))
    # 页眉逐页
    if a.name:
        nohead = [i + 1 for i, t in enumerate(pages) if norm(a.name) not in norm('\n'.join(t.splitlines()[:4]))]
        if nohead:
            R.add('WARN', 'H04', '这些页的页眉中找不到软件全称：%s' % nohead[:20])
    # 目录页码
    toc = toc_entries(paras)
    if not toc:
        R.add('WARN', 'T02', '没有找到目录（或目录域未生成），建议插入目录')
    else:
        start = max(toc_pages) if toc_pages else 1          # 目录末页本身可能已开始正文
        bad1, bad2, miss = [], [], []
        cur = start
        for title, pg in toc:
            if norm(title) in cover_titles:
                continue
            real = find_heading_page(pages, title, cur)
            if real is None:
                miss.append(title)
                continue
            cur = real
            d = abs((real + 1) - pg)
            if d >= 2:
                bad2.append('%s：目录%d/实际%d' % (title, pg, real + 1))
            elif d == 1:
                bad1.append('%s：目录%d/实际%d' % (title, pg, real + 1))
        if bad2:
            R.add('WARN', 'T01', '目录页码与正文不符（在 Word 中右键目录→更新域→更新整个目录）：%s' % '；'.join(bad2[:8]))
        if bad1:
            R.add('INFO', 'T01', '目录页码差 1 页（可能是渲染差异，建议在 Word 中更新目录后复核）：%s' % '；'.join(bad1[:8]))
        if miss:
            R.add('WARN', 'T03', '目录条目在正文中找不到：%s' % miss[:8])
    return R


def source(a):
    R = Report()
    header_checks(R, a.docx, a.name, a.version)
    paras = [p for p in paragraphs(a.docx)]
    lines = [p['text'] for p in paras]
    code = [l for l in lines if l.strip()]
    if not code:
        R.add('ERROR', 'S00', '文档中没有代码')
        return R
    first, last = code[0].strip(), code[-1].strip()
    if not re.match(r'(#\s*(include|ifndef|pragma|define)|import |from |using |package |namespace |<|<\?php|#!|/\*|//)', first):
        R.add('WARN', 'S01', '首行不像文件开头：%s' % first[:60])
    if not re.search(r'[}>;)\]]$|^end\b|^\s*fi$', last):
        R.add('WARN', 'S02', '末行不像完整的结尾：%s' % last[:60])
    sus = [l.strip()[:60] for l in code if LINKS.search(l) or COMPANY.search(l)]
    if sus:
        R.add('WARN', 'S03', '%d 行含网址/邮箱/版权/公司名，例如：%s' % (len(sus), ' | '.join(sus[:3])))
    blank = len(lines) - len(code)
    com = sum(1 for l in code if re.match(r'\s*(//|/\*|\*|#(?!include|define|if|endif|else|elif|pragma|undef|ifdef|ifndef)|--|<!--)', l))
    ratio = (blank + com) / max(len(lines), 1)
    R.add('WARN' if ratio > 0.30 else 'INFO', 'S04', '注释+空行约占 %.0f%%（要求不超过 30%%）' % (ratio * 100))
    if a.no_render:
        return R
    pdf = a.pdf or convert(a.docx, 'pdf', a.outdir)
    pages = pdf_pages(pdf)
    n = len(pages)
    if n > 60:
        R.add('ERROR', 'S05', '共 %d 页，一般交存只需前 30 页和后 30 页，共 60 页' % n)
    elif n < 60:
        R.add('INFO', 'S05', '共 %d 页（不足 60 页时提交全部代码）' % n)
    else:
        R.add('INFO', 'S05', '共 60 页')
    short = []
    for i, t in enumerate(pages[:-1]):
        rows = [l for l in t.splitlines() if l.strip() and not (a.name and norm(a.name) in norm(l))]
        if len(rows) < a.lines_per_page:
            short.append('%d(%d行)' % (i + 1, len(rows)))
    if short:
        R.add('ERROR', 'S06', '每页应不少于 %d 行，不足的页：%s' % (a.lines_per_page, '、'.join(short[:15])))
    return R


DATE = re.compile(r'(\d{4})\s*[-./年]\s*(\d{1,2})\s*[-./月]\s*(\d{1,2})')


def pdate(s):
    m = DATE.search(s or '')
    return dt.date(*map(int, m.groups())) if m else None


def clen(s):
    return len(re.sub(r'\s', '', s or ''))


def card(a):
    R = Report()
    d = json.load(open(a.json_in, encoding='utf-8'))
    name = d.get('软件名称', '')
    req = ['软件名称', '版本号', '软件分类', '开发完成日期', '发表状态', '开发方式', '著作权人', '开发的硬件环境', '运行的硬件环境',
           '开发该软件的操作系统', '软件开发环境/开发工具', '该软件的运行平台/操作系统', '软件运行支撑环境/支持软件', '编程语言',
           '源程序量', '开发目的', '面向领域/行业', '软件的主要功能', '软件的技术特点']
    miss = [k for k in req if not d.get(k)]
    if miss:
        R.add('ERROR', 'K01', '缺少字段：%s' % '、'.join(miss))
    ph = [k for k, v in d.items() if '【待' in json.dumps(v, ensure_ascii=False)]
    if ph:
        R.add('WARN', 'K02', '仍有待填写项：%s' % '、'.join(ph))
    if name and not re.search(r'(软件|系统|平台)$', name):
        R.add('WARN', 'K03', '软件全称建议以“软件”“系统”或“平台”结尾')
    if d.get('版本号') and not re.fullmatch(r'V\d+(\.\d+){1,2}', d['版本号']):
        R.add('WARN', 'K04', '版本号建议写成 V1.0 形式：%s' % d['版本号'])
    f = clen(d.get('软件的主要功能'))
    if f and '【待' not in d.get('软件的主要功能', '') and not 500 <= f <= 1300:
        R.add('ERROR', 'K05', '“软件的主要功能”为 %d 字，新版申请表要求 500–1300 字' % f)
    for k, lim in (('开发目的', 50), ('面向领域/行业', 30), ('软件的技术特点', 100), ('开发的硬件环境', 50), ('运行的硬件环境', 50),
                   ('开发该软件的操作系统', 50), ('软件开发环境/开发工具', 50), ('该软件的运行平台/操作系统', 50),
                   ('软件运行支撑环境/支持软件', 50)):
        if clen(d.get(k)) > lim:
            R.add('WARN', 'K06', '“%s”%d 字，建议控制在 %d 字内（以申请系统实际限制为准）' % (k, clen(d.get(k)), lim))
    done, pub, est = pdate(d.get('开发完成日期')), pdate(d.get('首次发表日期')), pdate(d.get('公司成立日期'))
    if d.get('开发完成日期') and not done and '【待' not in str(d.get('开发完成日期')):
        R.add('ERROR', 'K07', '开发完成日期格式无法识别：%s' % d.get('开发完成日期'))
    if done and done > dt.date.today():
        R.add('ERROR', 'K07', '开发完成日期晚于今天')
    if '已发表' in str(d.get('发表状态')):
        if not pub or not d.get('首次发表地点'):
            R.add('ERROR', 'K08', '已发表时须填写首次发表日期和地点')
        elif done and pub <= done:
            R.add('ERROR', 'K08', '首次发表日期须晚于开发完成日期，且不能是同一天')
    if est and done and (done - est).days < 182:
        R.add('WARN', 'K09', '开发完成日期距公司成立不足半年（%s → %s）' % (est, done))
    try:
        n = int(str(d.get('源程序量', '0')).replace(',', '').replace('行', ''))
        if n <= 0:
            raise ValueError
    except ValueError:
        R.add('ERROR', 'K10', '源程序量应为正整数行数')
        n = 0
    env = ' '.join(str(d.get(k, '')) for k in req[7:13])
    if re.search(r'Android|安卓', env, re.I) and re.search(r'iOS|iPhone', env, re.I):
        R.add('WARN', 'K11', '运行环境同时出现安卓和 iOS，模板要求二者不能同时出现')
    if re.search(r'手机|Android|iOS', env, re.I) and re.search(r'PC|电脑|Windows|服务器', d.get('运行的硬件环境', ''), re.I):
        R.add('WARN', 'K11', '运行硬件环境同时出现电脑和手机，模板要求二者不能同时出现')
    owners = d.get('著作权人') or []
    for o in owners if isinstance(owners, list) else [owners]:
        if isinstance(o, dict):
            cid = str(o.get('证件号码', ''))
            if o.get('证件类型', '').startswith(('营业执照', '统一社会信用代码')) and cid and '【' not in cid \
                    and not re.fullmatch(r'[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}', cid):
                R.add('WARN', 'K12', '统一社会信用代码格式不正确：%s' % cid)
    if a.design:
        hf = ' '.join(v[0] for v in header_footer_text(a.design).values())
        if name and norm(name) not in norm(hf):
            R.add('ERROR', 'K13', '说明书页眉中的软件名称与采集卡不一致')
        if d.get('版本号') and norm(d['版本号']) not in norm(hf):
            R.add('ERROR', 'K13', '说明书页眉中的版本号与采集卡不一致')
    if a.stats and n:
        st = json.load(open(a.stats, encoding='utf-8'))['totals']
        if abs(st['lines'] - n) > max(50, st['lines'] * 0.02):
            R.add('WARN', 'K14', '源程序量 %d 与统计结果 %d 行不一致' % (n, st['lines']))
    return R


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for c in ('design', 'source'):
        p = sub.add_parser(c)
        p.add_argument('docx')
        p.add_argument('--name', required=True)
        p.add_argument('--version', required=True)
        p.add_argument('--pdf', help='已有的 PDF（默认用 LibreOffice 转换）')
        p.add_argument('--outdir', help='PDF 输出目录')
        p.add_argument('--no-render', action='store_true', help='不转 PDF，只做文本检查')
        p.add_argument('--json')
        if c == 'design':
            p.add_argument('--code-lines', type=int)
            p.add_argument('--min-lines', type=int, default=30)
        else:
            p.add_argument('--lines-per-page', type=int, default=50)
    p = sub.add_parser('card')
    p.add_argument('json_in')
    p.add_argument('--design')
    p.add_argument('--stats')
    p.add_argument('--json')
    a = ap.parse_args()
    R = {'design': design, 'source': source, 'card': card}[a.cmd](a)
    ne = R.show({'design': '设计说明书检查', 'source': '源代码文档检查', 'card': '信息采集卡检查'}[a.cmd])
    if a.json:
        json.dump(R.items, open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    sys.exit(1 if ne else 0)


if __name__ == '__main__':
    main()
