# -*- coding: utf-8 -*-
"""Mermaid 流程图检查与渲染。
  python3 mmd_check.py lint   <目录>            # 孤立节点、判断框出口不足 2 条
  python3 mmd_check.py render <目录> [图名...]   # 生成 .svg 与 3 倍 .png，并报告插入 A4 后的字号
需要 mmdc（@mermaid-js/mermaid-cli）。只在 Claude 的云端工作区安装，不装进用户项目。
"""
import glob, json, os, re, subprocess, sys, tempfile

TEXT_W_CM, MAX_H_CM = 14.65, 21.5      # 与 build_docx.py 一致：A4、左右边距 3.17 cm
KW = ('subgraph', 'class', 'classDef', 'style', 'linkStyle', 'flowchart', 'graph', 'direction', 'end', 'click')
SHAPE_OPEN = r'(\(\[|\[\[|\[\(|\(\(|\{\{|\[/|\[\\|\[|\{|\(|>)'


def strip_cfg(s):
    return s.split('---', 2)[2] if s.lstrip().startswith('---') else s


def lint(d):
    ok = True
    for p in sorted(glob.glob(os.path.join(d, '*.mmd'))):
        body = strip_cfg(open(p, encoding='utf-8').read())
        lines = [l.strip() for l in body.splitlines() if l.strip() and not l.strip().startswith('%%')]
        subs = set(re.findall(r'^subgraph\s+([A-Za-z]\w*)', '\n'.join(lines), re.M))
        nodes, decs, out, inc = set(), set(), {}, {}
        for l in lines:
            if l.split()[0] in KW:
                continue
            l = re.sub(r'"[^"]*"', '""', l)                                    # 忽略引号内的标签文字
            for m in re.finditer(r'(?:^|[\s&>|-])([A-Za-z]\w*)\s*' + SHAPE_OPEN, l):
                nodes.add(m.group(1))
                if m.group(2) == '{':
                    decs.add(m.group(1))
            if not re.search(r'--|==|-\.|~~~', l):
                continue
            t = re.sub(r'\|[^|]*\|', ' ', l)                                   # 连线标签 |…|
            t = re.sub(r'--\s*"[^"]*"\s*-->|--\s+[^->]+?\s+-->', '-->', t)       # -- 文字 -->
            t = re.sub(r'"[^"]*"', '', t)                                       # 引号内文字
            t = re.sub(r'(\(\[|\[\[|\[\(|\(\(|\{\{|\[/|\[\\)[^\]\)\}]*(\]\)|\]\]|\)\]|\)\)|\}\}|/\]|\\\])', '', t)
            t = re.sub(r'\[[^\]]*\]|\{[^}]*\}|\([^)]*\)', '', t)
            parts = re.split(r'\s*(?:<?[-=.]{2,}[->ox]?|~~~)\s*', t)
            ids = [re.findall(r'[A-Za-z]\w*', x) for x in parts]
            for a, b in zip(ids, ids[1:]):
                for x in a:
                    for y in b:
                        out[x] = out.get(x, 0) + 1
                        inc[y] = inc.get(y, 0) + 1
        orphans = sorted(k for k in nodes if k not in out and k not in inc and k not in subs)
        baddec = sorted(k for k in decs if out.get(k, 0) < 2)
        name = os.path.basename(p)
        if orphans or baddec:
            ok = False
            print('%-40s 孤立节点=%s 判断框出口<2=%s' % (name, orphans, baddec))
        else:
            print('%-40s ok  %d 个节点' % (name, len(nodes)))
    print('ALL OK' if ok else '有问题，请修改后重跑')
    return ok


def puppeteer_cfg():
    cfg = {'args': ['--no-sandbox']}
    for c in (os.environ.get('CHROME'), '/opt/pw-browsers/chromium'):
        if c and os.path.exists(c):
            cfg['executablePath'] = c
            break
    p = os.path.join(tempfile.gettempdir(), 'mmdc_puppeteer.json')
    json.dump(cfg, open(p, 'w'))
    return p


def render(d, names):
    pp = puppeteer_cfg()
    files = [os.path.join(d, n if n.endswith('.mmd') else n + '.mmd') for n in names] or sorted(glob.glob(os.path.join(d, '*.mmd')))
    for p in files:
        base = p[:-4]
        src = open(p, encoding='utf-8').read()
        fs = re.search(r'fontSize:\s*"?(\d+)', src)
        font_px = int(fs.group(1)) if fs else 16
        r = subprocess.run(['mmdc', '-i', p, '-o', base + '.svg', '-p', pp, '-w', '4000', '-b', 'white'],
                           capture_output=True, text=True)
        if r.returncode or not os.path.exists(base + '.svg'):
            print('RENDER FAIL', os.path.basename(p), (r.stderr or r.stdout)[-600:])
            continue
        subprocess.run(['mmdc', '-i', p, '-o', base + '.png', '-p', pp, '-w', '4000', '-s', '3', '-b', 'white'],
                       capture_output=True, text=True)
        svg = open(base + '.svg', encoding='utf-8').read()
        w, h = [float(x) for x in re.search(r'viewBox="[\d.\-]+ [\d.\-]+ ([\d.]+) ([\d.]+)"', svg).groups()[:2]]
        wcm, hcm = w / 96 * 2.54, h / 96 * 2.54
        sc = min(TEXT_W_CM / wcm, MAX_H_CM / hcm, 1.0)   # 与 build_docx 一致：按正文宽度插入、过高按高度，不放大
        pt = font_px * 0.75 * sc
        flag = '  <-- 字太小，考虑拆图或改 TB/LR' if pt < 6 else ('  <-- 偏小' if pt < 7 else '')
        if hcm * sc >= MAX_H_CM - 0.05 and wcm * sc < TEXT_W_CM * 0.6:
            flag += '  <-- 又高又窄，考虑改为 LR 或拆图'
        print('%-40s %5.0fx%-5.0fpx  插入后 %4.1fx%4.1fcm  正文字号≈%.1fpt%s'
              % (os.path.basename(base), w, h, wcm * sc, hcm * sc, pt, flag))


if __name__ == '__main__':
    cmd, d, *rest = sys.argv[1:]
    if cmd == 'lint':
        sys.exit(0 if lint(d) else 1)
    elif cmd == 'render':
        render(d, rest)
    else:
        print(__doc__)
