# -*- coding: utf-8 -*-
"""按字段 JSON 填写软著信息采集卡（.doc / .docx 模板），并输出一份 Markdown 版填写内容。

用法:
  python3 fill_info_card.py 采集卡模板.doc 采集卡.json -o 输出.doc [--md 输出.md] [--keep-hints]

做法:
  - 用 LibreOffice（UNO）打开模板，在所有表格（含嵌套表格）里按“标签单元格”定位字段：
    标签去掉空格、斜杠、冒号、星号和括号说明后与字段名比对，例如“软件开发环境 / 开发工具 /”对应“软件开发环境/开发工具”。
  - 普通字段写入标签右侧单元格；表头式布局（著作权人：姓名或名称 / 证件类型 / 证件号码 / 省份/城市）写入下方单元格。
  - 选择题（软件分类、软件作品说明、发表状态、开发方式、权利取得方式、权利范围）用 ⊙ 标选中项、○ 标其余项；
    选项分列在多个单元格时（如软件分类）逐格标记。发表状态同时写入首次发表日期和地点，未发表时清空提示文字。
  - 写入的文字统一设为黑色、去掉底色；值里的【待填…】占位标红，方便用户补全。
  - 原模板不改动；输出格式按 -o 的扩展名（.doc / .docx / .odt）。
  - 无论能否调用 LibreOffice，都会写出 Markdown 版填写内容（含各字段字数），可直接对照申请系统逐项粘贴。
依赖: LibreOffice 及其 Python UNO 接口（Linux 装 python3-uno；macOS 用 LibreOffice 自带的 python 运行本脚本）。
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ORDER = ['软件名称', '版本号', '软件简称', '软件分类', '软件作品说明', '开发完成日期', '发表状态', '首次发表日期', '首次发表地点',
         '开发方式', '著作权人', '权利取得方式', '权利范围', '开发的硬件环境', '运行的硬件环境', '开发该软件的操作系统',
         '软件开发环境/开发工具', '该软件的运行平台/操作系统', '软件运行支撑环境/支持软件', '编程语言', '源程序量', '开发目的',
         '面向领域/行业', '软件的主要功能', '软件的技术特点']
CHOICES = {'软件分类': ['应用软件', '嵌入式软件', '中间件', '操作系统'], '软件作品说明': ['原创', '修改'],
           '发表状态': ['已发表', '未发表'], '开发方式': ['独立开发', '合作开发', '委托开发', '下达任务开发'],
           '权利取得方式': ['原始取得', '继受取得'], '权利范围': ['全部', '部分']}
OWNER_FIELDS = ['姓名或名称', '证件类型', '证件号码', '省份/城市']
MARKS = '⊙○●◯□☑■◉'


def nl(s):
    s = re.sub(r'[（(][^）)]*[）)]', '', s or '')
    return re.sub(r'[\s/／:：*＊ ]', '', s)


def as_text(v):
    if isinstance(v, (int, float)):
        return str(v)
    return v or ''


def clen(s):
    return len(re.sub(r'\s', '', s or ''))


def write_md(d, path):
    out = ['# %s 软件著作权信息采集卡' % d.get('软件名称', ''), '',
           '> 由 ruanzhu-docs 生成。【待填】项需申请人补充；字数为不含空白的字符数。', '', '| 字段 | 内容 | 字数 |', '|---|---|---|']
    for k in ORDER:
        if k not in d:
            continue
        v = d[k]
        if k == '著作权人':
            owners = v if isinstance(v, list) else [v]
            v = '；'.join('、'.join('%s：%s' % (f, o.get(f, '')) for f in OWNER_FIELDS) for o in owners if isinstance(o, dict))
        v = as_text(v)
        out.append('| %s | %s | %d |' % (k, v.replace('\n', '<br>').replace('|', '\\|'), clen(v)))
    extra = [k for k in d if k not in ORDER]
    for k in extra:
        out.append('| %s | %s | %d |' % (k, as_text(json.dumps(d[k], ensure_ascii=False) if not isinstance(d[k], str) else d[k]).replace('\n', '<br>'), clen(as_text(d[k]) if isinstance(d[k], str) else '')))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    open(path, 'w', encoding='utf-8').write('\n'.join(out) + '\n')


# ---------------- UNO ----------------
def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close(); return p


def start_office():
    import uno  # noqa: F401
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from rz_common import soffice_bin
    port = free_port()
    prof = tempfile.mkdtemp(prefix='rz_uno_')
    proc = subprocess.Popen([soffice_bin(), '-env:UserInstallation=file://' + prof, '--headless', '--invisible',
                             '--nologo', '--norestore', '--accept=socket,host=127.0.0.1,port=%d;urp;' % port],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver', local)
    ctx = None
    for _ in range(120):
        try:
            ctx = resolver.resolve('uno:socket,host=127.0.0.1,port=%d;urp;StarOffice.ComponentContext' % port)
            break
        except Exception:
            time.sleep(0.5)
    if ctx is None:
        proc.terminate(); raise SystemExit('ERROR 无法连接 LibreOffice')
    desk = ctx.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop', ctx)
    return proc, prof, desk


def pv(n, v):
    from com.sun.star.beans import PropertyValue
    p = PropertyValue(); p.Name = n; p.Value = v; return p


def col_idx(c):
    n = 0
    for ch in c:
        n = n * 26 + ord(ch) - 64
    return n


def col_name(n):
    s = ''
    while n:
        n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s


def has_nested(cell):
    en = cell.getText().createEnumeration()
    while en.hasMoreElements():
        if en.nextElement().supportsService('com.sun.star.text.TextTable'):
            return True
    return False


def set_cell(cell, text):
    cell.setString(text)
    cur = cell.createTextCursor(); cur.gotoStart(False); cur.gotoEnd(True)
    cur.CharColor = 0x000000
    for prop, val in (('CharBackTransparent', True), ('CharBackColor', -1), ('CharHighlight', -1)):
        try:
            cur.setPropertyValue(prop, val)
        except Exception:
            pass


def mark(text, options, chosen):
    for opt in options:
        sym = '⊙' if chosen and (opt == chosen or chosen.startswith(opt)) else '○'
        text = re.sub(r'[%s]\s*(?=%s)' % (MARKS, re.escape(opt)), sym + ' ', text)
    return text


def fill(template, data, out, keep_hints):
    proc, prof, desk = start_office()
    log, used, hints, nph = [], set(), [], 0
    try:
        import uno
        doc = desk.loadComponentFromURL(uno.systemPathToFileUrl(os.path.abspath(template)), '_blank', 0, (pv('Hidden', True),))
        labels = {nl(k): k for k in ORDER + OWNER_FIELDS}
        tables = doc.getTextTables()
        owners = data.get('著作权人') or []
        owners = owners if isinstance(owners, list) else [owners]
        for ti in range(tables.getCount()):
            t = tables.getByIndex(ti)
            grid = {}
            for cn in t.getCellNames():
                m = re.fullmatch(r'([A-Z]+)(\d+)', cn)
                if m:
                    grid[(col_idx(m.group(1)), int(m.group(2)))] = cn

            def cell(c, r):
                return t.getCellByName(grid[(c, r)]) if (c, r) in grid else None

            for (c, r), cn in sorted(grid.items(), key=lambda x: (x[0][1], x[0][0])):
                lc = t.getCellByName(cn)
                lab = labels.get(nl(lc.getString()))
                if not lab or has_nested(lc):          # 含嵌套表格的外层单元格只是容器
                    continue
                right = cell(c + 1, r)
                right_is_label = right is not None and nl(right.getString()) in labels
                if lab in OWNER_FIELDS:                 # 表头式：值写在下方各行
                    for i, o in enumerate(owners):
                        tgt = cell(c, r + 1 + i)
                        if tgt is None or not isinstance(o, dict) or lab not in o:
                            continue
                        set_cell(tgt, as_text(o[lab])); used.add('著作权人')
                        log.append('%s[%d] -> %s.%s' % (lab, i + 1, t.getName(), grid[(c, r + 1 + i)]))
                    if len(owners) > 1 and cell(c, r + len(owners)) is None:
                        log.append('WARN 模板只有 %d 行著作权人，其余请手工添加' % sum(1 for k in grid if k[0] == c and k[1] > r))
                    continue
                if lab not in data or lab == '著作权人':
                    continue
                val = data[lab]
                if lab in CHOICES:
                    chosen = as_text(val)
                    opts = CHOICES[lab]
                    tgt = right if right is not None and not has_nested(right) else None
                    if tgt is not None and re.search('[%s]' % MARKS, tgt.getString()):
                        txt = mark(tgt.getString(), opts, chosen)
                        if lab == '发表状态':
                            pub = chosen.startswith('已发表')
                            txt = re.sub(r'(首次发表日期[:：])[^\n]*', lambda m: m.group(1) + (' ' + as_text(data.get('首次发表日期')) if pub else ''), txt)
                            txt = re.sub(r'(首次发表地点[:：])[^\n]*', lambda m: m.group(1) + (' ' + as_text(data.get('首次发表地点')) if pub else ''), txt)
                            used.update(['首次发表日期', '首次发表地点'])
                        set_cell(tgt, txt.replace('\u00a0', ' '))
                        log.append('%s -> %s.%s（选择 %s）' % (lab, t.getName(), grid[(c + 1, r)], chosen))
                    else:                               # 选项分布在若干单元格（如软件分类）
                        n = 0
                        for cn2 in t.getCellNames():
                            c2 = t.getCellByName(cn2)
                            txt = re.sub('[%s]' % MARKS, '', c2.getString()).strip()
                            if txt in opts and not has_nested(c2):
                                set_cell(c2, ('⊙ ' if txt == chosen else '○ ') + txt); n += 1
                        if n:
                            log.append('%s -> %s（%d 个选项单元格，选择 %s）' % (lab, t.getName(), n, chosen))
                        else:
                            log.append('WARN 找不到“%s”的选项位置（%s.%s）' % (lab, t.getName(), cn))
                            continue
                    used.add(lab)
                    continue
                if right is not None and not right_is_label and not has_nested(right):
                    tgt, tname = right, grid[(c + 1, r)]
                elif right_is_label and cell(c, r + 1) is not None and not has_nested(cell(c, r + 1)):
                    tgt, tname = cell(c, r + 1), grid[(c, r + 1)]
                else:
                    log.append('WARN 找不到“%s”的填写位置（%s.%s）' % (lab, t.getName(), cn))
                    continue
                set_cell(tgt, as_text(val)); used.add(lab)
                log.append('%s -> %s.%s' % (lab, t.getName(), tname))
        # 剩余提示文字
        for ti in range(tables.getCount()):
            t = tables.getByIndex(ti)
            for cn in t.getCellNames():
                txt = t.getCellByName(cn).getString()
                if re.search(r'\*必须填写|可以不填|请填写|如果已发表必须填写', txt) and not keep_hints:
                    hints.append('%s.%s: %s' % (t.getName(), cn, txt.strip()[:30]))
        sd = doc.createSearchDescriptor(); sd.SearchString = '【[^】]*】'; sd.SearchRegularExpression = True
        found = doc.findAll(sd)
        nph = found.getCount()
        for i in range(nph):
            found.getByIndex(i).CharColor = 0xFF0000
        ext = os.path.splitext(out)[1].lower()
        flt = {'.doc': 'MS Word 97', '.docx': 'MS Word 2007 XML', '.odt': 'writer8'}.get(ext, 'MS Word 97')
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        doc.storeToURL(uno.systemPathToFileUrl(os.path.abspath(out)), (pv('FilterName', flt),))
        doc.close(True)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except Exception:
            proc.kill()
        shutil.rmtree(prof, ignore_errors=True)
    return log, used, hints, nph


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('template')
    ap.add_argument('json_in')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--md')
    ap.add_argument('--keep-hints', action='store_true', help='不报告模板中残留的“*必须填写”等提示')
    a = ap.parse_args()
    data = json.load(open(a.json_in, encoding='utf-8'))
    md = a.md or os.path.splitext(a.out)[0] + '_填写内容.md'
    write_md(data, md)
    print('Markdown：', md)
    try:
        import uno  # noqa: F401
    except ImportError:
        print('WARN 当前 Python 无法导入 uno，未生成 Word 采集卡。Linux 请安装 python3-uno；macOS 请用 '
              '/Applications/LibreOffice.app/Contents/Resources/python 运行本脚本。')
        sys.exit(2)
    log, used, hints, nph = fill(a.template, data, a.out, a.keep_hints)
    for l in log:
        print('  ', l)
    unused = [k for k in data if k not in used and k not in ('公司成立日期', '备注')]
    if unused:
        print('WARN 这些字段在模板中没有找到对应位置：%s' % '、'.join(unused))
    if hints:
        print('WARN 模板中仍有提示文字未被替换：%s' % ' | '.join(hints[:8]))
    print('已写出 %s；【待填】占位 %d 处（标红）' % (a.out, nph))


if __name__ == '__main__':
    main()
