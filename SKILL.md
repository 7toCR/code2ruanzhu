---
name: ruanzhu-docs
description: 软著（计算机软件著作权登记）材料全流程：读源代码画 Mermaid 流程图并生成详细设计说明书 .docx；围绕用户提供的截图写软件说明书；生成前后各 30 页、每页 50 行的源代码文档并统计源程序量；起草并填写信息采集卡；审查已有材料是否合规（页眉页码、目录、每个模块的流程图、页数与代码量、说明书—代码—申请表三重匹配）并列出缺失材料。用户提到软著、软件著作权、设计说明书、软件说明书、用户手册、源代码文档、鉴别材料、信息采集卡、软著申请表，或问软著材料是否合规、还缺什么时使用。
---

# 软著材料：源代码 → 说明书、源代码文档、信息采集卡

把一个软件的源代码整理成软件著作权登记材料的草稿，交给申请人和代理机构确认后提交。产出是草稿，不是法律意见；登记规则以代理机构和版权保护中心的最新要求为准，交付时说一次。

## 好材料的标准

1. **三重匹配**：说明书写到的每个功能都能在提交的源代码里找到实现；采集卡的功能描述、运行环境、源程序量与说明书和代码一致。三者取自同一代码基线。
2. **只写代码能证实的内容**：每个数字（周期、端口、帧 ID、地址、缓冲长度）都有出处，措辞强度不超过代码能证明的范围。
3. **形式合规**：页眉为“软件全称 版本号”并有连续页码；每个功能模块有流程图；说明书页数与源程序量相称；源代码前后各 30 页、每页不少于 50 行、首尾完整、不含第三方代码。
4. **不编造**：申请人信息、开发完成日期、发表情况只用用户给的；截图只用用户给的；不知道的写【待填】。

## 分工

- **你来做**：读代码、建事实表、画流程图、写设计说明书、生成源代码文档、统计源程序量、起草采集卡的技术字段、审查已有材料。
- **只能由申请人提供**：软件说明书的界面截图；著作权人名称、证件号码、所在地；真实的开发完成日期和发表情况；营业执照；签字盖章、经办人身份证号和手抄承诺；合作或委托合同。

## 模式

| 用户的说法 | 模式 | 产物 |
|---|---|---|
| 帮我写软著 / 准备全套材料 | full | 设计说明书 + 源代码文档 + 采集卡 + 检查结果 |
| 写设计说明书 | design | 流程图目录 + 设计说明书 |
| 写软件说明书 / 用户手册（附截图） | manual | 软件说明书 |
| 生成源代码文档 / 统计代码行数 | source | 源代码文档 + 统计 |
| 填采集卡 / 申请表 | card | 采集卡（Word + Markdown） |
| 看看是否合规 / 还缺什么材料 | review | 按严重程度排序的问题清单 + 缺失材料 |

## 流程（建任务清单，逐项勾掉）

### 1. 接收

- 确认输入：源代码路径和要登记的分支或提交、参考软著（版式样本）、目标模板、截图、软件全称和版本号、采集卡模板、交付位置、用户自己的规则文件。能从文件中读到的不要问（全称和版本号通常在模板封面或页眉里）。只有不知道写哪个软件、或代码基线有多个候选且差异大时才停下来问。
- 读 `references/registration-rules.md`，每次都读：规则会影响你对用户说什么。其中第 4 节要求**开始前**用一两句话告知用户 AI 承诺问题，由用户决定是否继续。
- review 模式直接转到 `references/compliance-review.md`。

### 2. 代码基线与事实表

按 `references/code-facts.md` 确定基线、区分自研与第三方代码，写 `facts.md`。这是后面所有材料的依据。

### 3. 流程图

按 `references/flowcharts.md` 规划图表（每个功能章节至少一张），写 .mmd，运行 `mmd_check.py lint` 和 `render`，逐张看 PNG 改到干净，写 flowcharts/README.md。

### 4. 设计说明书

按 `references/design-doc-writing.md` 选版式、定章节、写正文；按 `references/document-generation.md` 写 content.py，运行：

```bash
python3 <skill>/scripts/build_docx.py --content content.py --out out/<全称>_详细设计说明书.docx --auto-toc [--template 模板.docx]
```

`<skill>` 为本技能目录。完整示例见 `assets/example/`（虚构软件，可直接运行）。

### 5. 源代码文档

按 `references/source-code-doc.md`：

```bash
python3 <skill>/scripts/source_code_docx.py stats <自研代码目录...> --json out/源代码统计.json
python3 <skill>/scripts/source_code_docx.py build <自研代码目录...> --name <全称> --version V1.0 -o out/<全称>_源代码.docx --pdf
```

### 6. 信息采集卡

按 `references/info-card.md` 写 JSON（未知项写【待填】），运行：

```bash
python3 <skill>/scripts/fill_info_card.py <采集卡模板> 采集卡.json -o out/<全称>_信息采集卡.doc
```

### 7. 检查

```bash
python3 <skill>/scripts/check_ruanzhu.py design out/<全称>_详细设计说明书.docx --name <全称> --version V1.0 --code-lines <源程序量>
python3 <skill>/scripts/check_ruanzhu.py source out/<全称>_源代码.docx --name <全称> --version V1.0
python3 <skill>/scripts/check_ruanzhu.py card 采集卡.json --design out/<全称>_详细设计说明书.docx --stats out/源代码统计.json
```

- 修掉每个 ERROR，逐个判断 WARN，重跑到干净。检查项含义见 `references/compliance-review.md`。
- 用 `pdftoppm -r 60` 生成缩略图拼起来看，覆盖封面、目录、正文和大图页；Word 与 LibreOffice 的分页可能差一两页。
- 按 `references/quality-checklist.md` 过一遍。

### 8. 交付

- 流程图目录（.mmd、.svg、.png、README.md）写到 `<仓库>/docs/softcopyright/flowcharts/`（新建目录）或用户指定位置；文档写到交付位置，覆盖前先备份（见 document-generation.md 第 4 节）。
- 最后的回复要简短：产出了什么、用了哪个模板和代码基线；待确认事项；需要申请人提供或处理的事项（【待填】字段、截图、营业执照、签章与手抄承诺、合同）；AI 承诺提醒；在 Word 中更新目录。不粘贴大段内容。

## 硬性规则

1. **源代码只读。** 不切换分支，不修改任何源文件、配置或依赖。需要非当前分支的代码时，用 `git archive` 或 `git show` 取到 Claude 的工作区再读。仓库里只往新建的 `docs/softcopyright/` 目录写文件。
2. **不在用户的电脑或项目里安装软件。** mmdc、LibreOffice 等只在 Claude 的云端工作区使用。
3. **只写代码能证实的内容。** 注释与代码不一致时以代码为准。代码确认不了的逻辑，在图和 README 里标“待确认”；说明书正文只写已确认的行为，待确认事项在回复里列给用户。
4. **不编造申请信息。** 著作权人、证件号码、日期、发表情况只照用户给的填，不搜索、不推测、不为满足“半年”“不能同一天”之类的规则倒推日期。
5. **不伪造截图，** 也不用流程图或上位机工具的截图代替被登记软件的界面。
6. **不把第三方代码当自研提交，** 不删除他人的版权声明后收录。
7. **如实对待 AI 使用。** 按 registration-rules.md 第 4 节告知用户；不起草“未使用 AI”的声明，不提供让 AI 生成内容看起来像人工撰写的办法。
8. **用户的代码、说明书、公司和个人信息不写进技能目录或任何公开仓库。**

## 常见请求

| 请求 | 做法 |
|---|---|
| 帮我把这个工程写成软著材料 | full 模式，步骤 1–8 |
| 只要设计说明书 | design 模式，步骤 1–4、7、8 |
| 根据截图写软件说明书 | design-doc-writing.md 第 6 节；没有截图时列出需要的截图 |
| 生成源代码文档 / 源程序量是多少 | source-code-doc.md |
| 帮我填采集卡 | info-card.md；先读说明书和代码，申请人信息标【待填】 |
| 说明书合规吗 / 还缺什么材料 | compliance-review.md |
| 说明书和代码对不上 | code-facts.md 第 1、4 节，先定基线再逐条核对 |
