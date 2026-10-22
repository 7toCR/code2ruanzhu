#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Structural assertions for one or more ruanzhu-docs runs.

Each run directory must contain the run's files (any depth): the design
document DOCX (*说明书*.docx), the source-code DOCX (*源代码*.docx), the
information-card JSON (any .json with a "软件名称" key), and final_message.md.
Writes grading.json into each run directory and prints a summary.

These checks cover form and structure only (materials complete, checker
errors, every functional chapter has a figure, numbers traceable to the code,
no invented applicant data, handover message). Fidelity and writing quality
need rubric.md and a blind comparison.

Usage:
    python evals/grade_structure.py --code inputs/<project> RUN_DIR [RUN_DIR ...] [--owner 公司名]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "ruanzhu-docs" / "scripts"))
import check_ruanzhu  # noqa: E402
from rz_common import paragraphs  # noqa: E402

CODE_EXT = {".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".java", ".kt", ".go", ".rs", ".py", ".js", ".ts",
            ".tsx", ".jsx", ".vue", ".php", ".rb", ".swift", ".m", ".sql", ".s", ".ini", ".json", ".yaml", ".yml",
            ".ioc", ".uvprojx", ".xml", ".gradle", ".toml"}


def pick(run: Path, pattern: str, exclude: str | None = None) -> Path | None:
    hits = [p for p in run.rglob(pattern) if "pdf" not in p.parts and "~$" not in p.name]
    if exclude:
        hits = [p for p in hits if exclude not in p.name]
    return sorted(hits, key=lambda p: (len(p.parts), len(p.name)))[0] if hits else None


def find_card(run: Path) -> tuple[Path | None, dict]:
    for p in sorted(run.rglob("*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and "软件名称" in d:
            return p, d
    return None, {}


def code_corpus(root: Path) -> str:
    parts = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in CODE_EXT and p.stat().st_size < 2_000_000:
            try:
                parts.append(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                pass
    return "\n".join(parts).lower()


def numbers_in_design(docx: Path) -> list[str]:
    nums = []
    for p in paragraphs(str(docx)):
        if p["style"].startswith(("heading", "toc")) or not p["text"].strip():
            continue
        t = re.sub(r"图\s*\d+(\s*[-－]\s*\d+)?", " ", p["text"])
        t = re.sub(r"(19|20)\d{2}\s*年", " ", t)
        for m in re.finditer(r"(?<![\w.])(0x[0-9a-fA-F]+|\d+(?:\.\d+)?)(?![\w])", t):
            v = m.group(1)
            if not v.lower().startswith("0x") and float(v) < 10:
                continue
            nums.append(v.lower())
    return nums


def traceable(num: str, corpus: str) -> bool:
    if num.startswith("0x"):
        h = num[2:].lstrip("0") or "0"
        return re.search(r"0x0*%s(?![0-9a-f])" % re.escape(h), corpus) is not None or str(int(num, 16)) in corpus
    return re.search(r"(?<![\d.])%s(?![\d])" % re.escape(num), corpus) is not None


def run_check(kind: str, **kw) -> list[dict]:
    a = SimpleNamespace(pdf=None, outdir=None, no_render=False, json=None, **kw)
    return getattr(check_ruanzhu, kind)(a).items


def grade(run: Path, corpus: str, owner: str | None) -> dict:
    results = []

    def add(text: str, passed: bool, evidence: str) -> None:
        results.append({"text": text, "passed": bool(passed), "evidence": evidence})

    design = pick(run, "*说明书*.docx")
    source = pick(run, "*源代码*.docx")
    card_path, card = find_card(run)
    msg_path = pick(run, "final_message.md")
    add("三份材料齐全", bool(design and source and card_path),
        "design=%s source=%s card=%s" % (design and design.name, source and source.name, card_path and card_path.name))
    name, ver = card.get("软件名称", ""), card.get("版本号", "V1.0")

    if design and name:
        items = run_check("design", docx=str(design), name=name, version=ver, code_lines=None, min_lines=30)
        errs = [i for i in items if i["level"] == "ERROR"]
        add("设计说明书检查无 ERROR", not errs, "; ".join("%s %s" % (i["code"], i["msg"][:60]) for i in errs) or "ok")
        add("每个功能章节都有流程图", not any(i["code"] == "F01" and i["level"] == "ERROR" for i in items),
            next((i["msg"][:80] for i in items if i["code"] == "F01"), "ok"))
        nums = numbers_in_design(design)
        if nums and corpus:
            ok = [n for n in nums if traceable(n, corpus)]
            rate = len(ok) / len(nums)
            miss = sorted(set(nums) - set(ok))[:15]
            add("说明书数值可在代码中找到（≥70%，派生数值需人工复核）", rate >= 0.7, "%.0f%% (%d/%d)，未找到：%s" % (rate * 100, len(ok), len(nums), miss))
    if source and name:
        items = run_check("source", docx=str(source), name=name, version=ver, lines_per_page=50)
        errs = [i for i in items if i["level"] == "ERROR"]
        add("源代码文档检查无 ERROR", not errs, "; ".join("%s %s" % (i["code"], i["msg"][:60]) for i in errs) or "ok")
    if card_path:
        items = run_check("card", json_in=str(card_path), design=str(design) if design else None, stats=None)
        errs = [i for i in items if i["level"] == "ERROR"]
        add("采集卡检查无 ERROR", not errs, "; ".join("%s %s" % (i["code"], i["msg"][:60]) for i in errs) or "ok")
        owners = card.get("著作权人") or []
        owners = owners if isinstance(owners, list) else [owners]
        names = [str(o.get("姓名或名称", "")) for o in owners if isinstance(o, dict)]
        honest = all("【待" in n or (owner and owner in n) for n in names) if names else False
        add("未编造著作权人信息", honest, "著作权人：%s" % names)
    if msg_path:
        m = msg_path.read_text(encoding="utf-8", errors="ignore")
        add("交付说明提到 AI 承诺", bool(re.search(r"AI|人工智能", m)), "")
        add("交付说明列出需申请人处理的事项", bool(re.search(r"待填|需要你|申请人|营业执照|签章|签字", m)), "")
    else:
        add("有 final_message.md", False, "")
    passed = sum(r["passed"] for r in results)
    out = {"run": str(run), "passed": passed, "total": len(results), "results": results}
    (run / "grading.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--code", help="被登记项目的源代码目录，用于数值溯源")
    ap.add_argument("--owner", help="用户在提示中给出的著作权人名称（给出时允许出现在采集卡中）")
    a = ap.parse_args()
    corpus = code_corpus(Path(a.code)) if a.code else ""
    for r in a.runs:
        g = grade(Path(r), corpus, a.owner)
        print("%-50s %d/%d" % (r, g["passed"], g["total"]))
        for x in g["results"]:
            print("   %s %s  %s" % ("✓" if x["passed"] else "✗", x["text"], x["evidence"][:100]))


if __name__ == "__main__":
    main()
