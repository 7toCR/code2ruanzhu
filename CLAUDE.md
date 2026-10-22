# Claude Code Instructions

This repository publishes the ruanzhu-docs agent skill for preparing Chinese software copyright (软件著作权 / 软著) registration materials from source code: detailed design documents with Mermaid flowcharts, user manuals built around user-supplied screenshots, 60-page source-code documents, information cards, and compliance reviews.

## Project Skill

Use `.claude/skills/ruanzhu-docs/SKILL.md` when the task involves 软著 materials: writing a 设计说明书 or 软件说明书, generating a 源代码文档, counting 源程序量, filling a 信息采集卡, or checking whether existing materials meet the registration rules.

## Repository Rules

- Keep users' source code, generated materials, applicant names, credit codes, ID numbers, and screenshots out of git. The bundled example under `assets/example/` is fictional; keep it that way.
- Do not add local machine paths, usernames, API keys, tokens, cookies, phone numbers, emails, addresses, or identity numbers to `skills/` or `.claude/skills/`.
- Keep skill instructions concise; move long rules into `references/`.
- Preserve UTF-8 Markdown and the existing Simplified Chinese terminology.

## Validation

Run skill validation after changes:

```powershell
$env:PYTHONUTF8='1'; python <skill-creator>/scripts/quick_validate.py skills/ruanzhu-docs
$env:PYTHONUTF8='1'; python <skill-creator>/scripts/quick_validate.py .claude/skills/ruanzhu-docs
git diff --check
```

Smoke-test the scripts on the bundled example (outputs go to a temporary folder outside git; needs Pillow, LibreOffice with Python UNO, poppler-utils, and mmdc for the render step):

```bash
mkdir -p /tmp/rz && cp -R skills/ruanzhu-docs/assets/example/. /tmp/rz/ && cd /tmp/rz
S=<repo>/skills/ruanzhu-docs/scripts
python3 $S/mmd_check.py lint flowcharts && python3 $S/mmd_check.py render flowcharts
python3 $S/build_docx.py --content content.py --out out/示例温控终端嵌入式软件_详细设计说明书.docx --auto-toc
python3 $S/check_ruanzhu.py design out/示例温控终端嵌入式软件_详细设计说明书.docx --name 示例温控终端嵌入式软件 --version V1.0
python3 $S/source_code_docx.py build src --name 示例温控终端嵌入式软件 --version V1.0 -o out/示例温控终端嵌入式软件_源代码.docx --pdf
python3 $S/check_ruanzhu.py source out/示例温控终端嵌入式软件_源代码.docx --name 示例温控终端嵌入式软件 --version V1.0
python3 $S/fill_info_card.py <repo>/skills/ruanzhu-docs/assets/template_info_card.docx info_card.json -o out/示例_信息采集卡.docx
python3 $S/check_ruanzhu.py card info_card.json
```

The example code is only 363 lines, so its design document is 9 pages; do not pass `--code-lines` in the smoke test (it would report P01 by design). The card check reports K02 because applicant fields are intentionally 【待填】.

Keep `skills/ruanzhu-docs/` and `.claude/skills/ruanzhu-docs/` identical (`diff -r`).

To judge whether a change improves the materials, follow `evals/README.md` (fixed conditions, several projects and runs, blind pairwise review with `evals/rubric.md`). Never commit files under `evals/inputs/` or `evals/runs/`.
