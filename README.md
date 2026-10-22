<div align="center">

# RuanZhu Docs

**面向软件著作权登记的材料助手：读源代码，生成设计说明书、源代码文档和信息采集卡，并做合规检查**

*Make AI Writing Better for Everyone*

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[快速开始](#快速开始) · [能做什么](#能做什么) · [登记规则要点](#登记规则要点) · [使用须知](#使用须知) · [更新记录](CHANGELOG.md)

</div>

> **© 2026-present [7toCR] · All Rights Reserved**
>
> **欢迎免费公开使用，但严禁将本项目直接复制到其他仓库并声称是你的原创成果。如需引用或参考，请注明原始来源并链接回本仓库。**
>
> 本项目基于 [MIT License](LICENSE) 开源，社区使用规范见 [CLAUSE.md](CLAUSE.md)。

## 为什么做这个项目

软著登记要交三样东西：说明书、源代码文档、申请表。真正费时间的不是排版，而是让三者对得上：说明书写的功能要在代码里找得到，每个模块要有流程图，页数要和代码量相称，源代码要前后各 30 页、每页 50 行，申请表的“主要功能”在 2026 年新版申请表里要写到 500–1300 字。

我们在实际准备嵌入式软件软著材料时，把踩过的坑整理成了这个 Skill：说明书与代码不是同一个分支、辅助模块没有流程图、目录页码过期、章节分页造成只有十几行的页面、源代码混入芯片厂商库、源程序量把第三方库也算进去……这些问题现在都由脚本检查。

## 能做什么

| 能力 | 说明 |
|---|---|
| 📖 读代码建事实表 | 先定代码基线（分支、提交），区分自研与第三方代码，每个参数都注明出处 |
| 🔀 Mermaid 流程图 | 总体结构图、运行流程图，每个功能模块至少一张；自动检查孤立节点、判断框出口和插入后的字号 |
| 📝 详细设计说明书 | 参考版式或编号版式（1 / 3.1 / 4.1.1、图 3-1 图题）；目录页码自动回填；可沿用代理给的模板 |
| 🖼️ 软件说明书 | 围绕用户提供的界面截图撰写，不伪造截图 |
| 💻 源代码文档 | 自动排除第三方和自动生成代码；前后各 30 页、每页 50 行；首尾完整；统计源程序量和注释空行占比 |
| 🗂️ 信息采集卡 | 起草技术字段（主要功能 500–1300 字），按标签填写代理的 .doc/.docx 模板；申请人信息标红【待填】 |
| ✅ 合规检查 | 页眉页码、目录、每模块流程图、页数与代码量、每页行数、待确认字样、日期规则、三重匹配 |

## 快速开始

在支持 Skills 的 AI 工具中，把“读代码 → 画图 → 写说明书 → 生成源代码文档 → 填采集卡 → 检查”整套流程交给 AI。作者主要在 **Claude** 中验证，也兼容 Codex、Claude Code、Cursor、Windsurf。

### 安装

```bash
git clone https://github.com/7toCR/ruanzhu-docs.git
cd ruanzhu-docs
```

| 工具 | 安装方式 |
|---|---|
| Claude 桌面版 / 网页版 | 把 `skills/ruanzhu-docs/` 打包为 zip（zip 内顶层为 `ruanzhu-docs/` 目录），在设置的 Skills 区域上传；已有旧版时先删除再上传 |
| Claude Code | 在本仓库内直接可用（`.claude/skills/ruanzhu-docs/`）；全局使用时复制到 `~/.claude/skills/` |
| Codex | macOS/Linux：`cp -R skills/ruanzhu-docs ~/.codex/skills/`<br>Windows：`Copy-Item -Recurse -Force .\skills\ruanzhu-docs "$env:USERPROFILE\.codex\skills\"` |
| Cursor / Windsurf | 使用 `.cursor/rules/`、`.windsurf/rules/` 中的项目规则，并引用 `skills/ruanzhu-docs/` |

**升级**：本仓库没有版本号，升级即 `git pull` 后重新复制。先删除旧目录再复制，避免已删除的旧文件残留：

```bash
git pull
rm -rf ~/.claude/skills/ruanzhu-docs && cp -R skills/ruanzhu-docs ~/.claude/skills/
```

运行环境：Python 3.9+ 与 Pillow；画流程图需要 Mermaid CLI（`npm i -g @mermaid-js/mermaid-cli`）；生成 PDF、检查页数和填写 .doc 采集卡需要 LibreOffice（填采集卡还需要 LibreOffice 的 Python UNO 接口）；读取 PDF 需要 poppler-utils。

### 使用

直接用自然语言描述任务即可：

- “用 ruanzhu-docs 把这个固件工程写成软著材料，代码以 release 分支为准。”
- “按这份参考软著的版式写详细设计说明书，模板用这个 docx。”
- “生成源代码文档，前后各 30 页，只要 User 和 Common 目录。”
- “帮我填这张信息采集卡。”
- “看看这份说明书是否合规，还缺哪些材料？”

### 输出

- `<全称>_详细设计说明书.docx` 和 PDF 预览；流程图目录（.mmd、.svg、.png 和 README）。
- `<全称>_源代码.docx` 和 `_报告.json`（收录文件、行号范围、排除的第三方文件、可疑行、每页行数）。
- `<全称>_信息采集卡.doc` 和 `_填写内容.md`（含各字段字数）。
- 检查结果：ERROR / WARN / INFO 清单。

<details>
<summary><b>目录结构</b></summary>

```text
skills/ruanzhu-docs/                 Skill 主版本（.claude/skills/ruanzhu-docs/ 为同步镜像）
├── SKILL.md                         工作流与核心规则
├── references/
│   ├── registration-rules.md        登记规则、2026 年申请表变化、AI 承诺、材料清单
│   ├── code-facts.md                代码基线、自研与第三方代码、事实表、措辞强度
│   ├── flowcharts.md                图表规划、Mermaid 写法、渲染检查
│   ├── design-doc-writing.md        说明书版式、章节、每章写法、软件说明书
│   ├── document-generation.md       content.py 格式、模板、目录、目检
│   ├── source-code-doc.md           源代码文档与源程序量
│   ├── info-card.md                 采集卡字段、JSON 格式、填写
│   ├── compliance-review.md         审查模式与检查项代码
│   └── quality-checklist.md         交付前检查清单
├── scripts/
│   ├── mmd_check.py                 流程图检查与渲染
│   ├── build_docx.py                说明书生成（参考版式 / 编号版式）
│   ├── toc_pages.py                 目录页码回填
│   ├── source_code_docx.py          源代码文档与代码量统计
│   ├── fill_info_card.py            填写信息采集卡（LibreOffice UNO）
│   ├── check_ruanzhu.py             说明书 / 源代码文档 / 采集卡检查
│   └── rz_common.py                 公共函数
├── assets/
│   ├── template_design.docx         自带说明书模板（编号版式）
│   ├── template_info_card.docx      通用信息采集卡模板
│   └── example/                     虚构软件的完整示例：源代码、流程图、content.py、采集卡 JSON
└── agents/openai.yaml
evals/                               评估方案：评分细则、盲评流程、结构检查脚本
```

</details>

## 登记规则要点

| 项目 | 要求 |
|---|---|
| 鉴别材料 | 源程序和文档各提交前、后连续 30 页，不足 60 页的全部提交 |
| 每页行数 | 源程序不少于 50 行；文档不少于 30 行（有图的页除外） |
| 页眉页码 | 页眉标注软件名称和版本号，与申请表完全一致；页码连续 |
| 说明书页数 | 代理常用标准：代码 1 万行以下 15 页以上，1 万行以上 20 页以上，10 万行以上 40 页以上 |
| 详细设计说明书 | 嵌入式软件提交；要有整个软件的流程图和各模块的流程图 |
| 软件说明书 | 要有完整界面截图，主要操作配图配文；电脑与手机、安卓与 iOS 不混用 |
| 日期 | 开发完成日期晚于公司成立日期（代理通常要求半年以上）；首次发表日期晚于开发完成日期且不同日 |
| 新版申请表（2026-03） | 据公开报道：主要功能 500–1300 字；签章页经办人签名并附身份证号，手抄承诺 |

详细说明、来源和可信度分级见 [registration-rules.md](skills/ruanzhu-docs/references/registration-rules.md)。

## 使用须知

- 生成内容是供申请人和代理机构审核的草稿，不构成法律意见；登记规则以代理机构和中国版权保护中心的最新要求为准。
- **关于 AI 承诺**：据 2026 年 3 月的公开报道，新版申请表签章页的手抄承诺包含“未使用 AI 开发编写代码、撰写文档或生成登记申请材料”。本工具生成的材料属于 AI 生成内容。请在使用前向代理机构或版权保护中心确认现行表格的要求及如何如实申报，由申请人自行决定；本工具不提供规避方法。
- 申请人信息、开发完成日期、发表情况和界面截图只能由申请人提供，工具不会编造。
- 不要把未公开的源代码、生成的材料或公司、个人信息提交到公开仓库。

## 更新记录与评估

- 更新记录：[CHANGELOG.md](CHANGELOG.md)
- 评估方法（评分细则、盲评流程、结构检查脚本）：[evals/README.md](evals/README.md)

## 致谢

本项目的 README 与仓库结构沿用了姊妹项目 [paper2patent](https://github.com/7toCR/paper2patent) 的组织方式。
