# 流程图：规划、Mermaid 写法、渲染与检查

详细设计说明书要有“整个软件的流程图和各个模块的流程图”。审查时最常见的缺陷，是辅助模块（采集、升级、电源等）只有文字没有图。规划时先保证每个功能章节至少一张图。

## 1. 规划图表

- `00_软件总体结构`：分层画出模块关系（例如 上位机通信层 → 应用协议层 → 任务处理层 → 总线通信层 → 设备层），区分命令下行、状态上行、控制信号和物理链路。
- `01_软件运行流程`：上电或启动 → 初始化 → 调度器或主循环 → 若干并行支路（例如命令下行、状态上行、巡检、异常处理）。
- 从 `02` 起，**每个功能章节至少一张图**，包括温度/姿态采集、固件升级、电源管理这类容易被省略的模块。图太宽或太高时，按执行单元（任务、中断、接口函数）拆成 `NNa`、`NNb`，不要硬塞进一张图。
- 固件升级类模块通常要两张：主控升级（进入升级 → 写入 → 校验 → 提交 → 确认/回滚）和外设升级（如 CAN IAP：进入 Boot → 分段下发 → 校验 → 写入 → 进度上报 → 中止）。
- 不需要图的章节：软件概述、系统运行要求、引言、运行与部署、接口与数据结构（用表格）。

## 2. 每个 .mmd 的开头配置

总体框图这类大图可以把 nodeSpacing 和 rankSpacing 调成 14 和 34。子图标题被节点压住时，加 `subGraphTitleMargin`。

```
---
config:
  theme: base
  fontFamily: "Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif"
  themeVariables:
    fontSize: 14px
    primaryColor: "#ffffff"
    primaryTextColor: "#1a1a1a"
    primaryBorderColor: "#333333"
    lineColor: "#3a3a3a"
    clusterBorder: "#9aa3ad"
    edgeLabelBackground: "#ffffff"
  flowchart:
    useMaxWidth: false
    curve: basis
    nodeSpacing: 26
    rankSpacing: 22
    padding: 8
---
%% 图 NN 标题（主要代码依据：xxx.c 的 func()）
flowchart TB
```

## 3. 符号约定

| 形状 | 写法 | 用途 | class |
|---|---|---|---|
| 圆角端点 | `A(["开始"])` | 开始、结束、任务入口 | term |
| 矩形 | `B["处理"]` | 处理步骤 | proc |
| 菱形 | `C{"条件？"}` | 判断，每个出口都标“是/否”或具体条件 | dec |
| 平行四边形 | `D[/"收到数据"/]` | 数据输入或输出 | io |
| 双竖线矩形 | `E[["func()<br/>说明（见图 NN）"]]` | 子过程，另有图 | sub |
| 浅紫圆角端点 | `I(["XX中断回调"])` | 中断上下文入口 | isr |
| 圆形 | `J(("继续"))` | 循环汇合点 | join |

classDef 写在每张图末尾：

```
  classDef term fill:#e9edf2,stroke:#333,stroke-width:1.2px,color:#111
  classDef proc fill:#ffffff,stroke:#333,stroke-width:1px,color:#111
  classDef dec fill:#fffaf0,stroke:#333,stroke-width:1px,color:#111
  classDef io fill:#eef4fb,stroke:#333,stroke-width:1px,color:#111
  classDef sub fill:#f4f0fa,stroke:#333,stroke-width:1px,color:#111
  classDef isr fill:#f4f0fa,stroke:#333,stroke-width:1.2px,color:#111
  classDef join fill:#ffffff,stroke:#333,stroke-width:1px,color:#111,font-size:12px
```

## 4. 写法要点（都是实际踩过的坑）

- 节点文字一律加引号；连线标签里含括号等符号时也要加引号，例如 `-->|"是 (FIFO 有空位)"|`，否则解析报错。
- 每行不超过约 14 个汉字，用 `<br/>` 换行。节点里写函数名时带 `()`，参数从简。
- `fontFamily` 必须放在 config 顶层，放进 themeVariables 不生效；必须设 `useMaxWidth: false`，否则图会被压到 800 px 宽。
- 用默认的 dagre 布局，不用 ELK：中文长节点在 ELK 下会排乱。
- 总体框图里的上行连线写成「接收方 `<-.->` 发送方」，再用 `linkStyle <序号> marker-end:none` 隐藏终点箭头。这样分层仍保持自上而下，箭头也指向接收方。连线序号按定义顺序从 0 数起（含子图内的连线和 `~~~`），增删连线后要重新核对。
- 用 `A ~~~ B` 不可见连线对齐并排的几列。互不相连的几列表示相互独立的执行单元，要在 README 里说明。
- 循环要回到前面的步骤时，经汇合点 `(( ))` 回连，避免长回边横穿整张图。
- 第一行 `%%` 注释写图号、标题和主要代码依据。待确认或未编译的分支，在节点文字里注明“（待确认）”或“（未编译）”；这种图进入说明书前要先确认或删掉该分支。
- 流程图里的数字、条件和说明书正文、代码三者一致；改了一处要同步另外两处。

## 5. 渲染与检查

```bash
python3 <skill>/scripts/mmd_check.py lint   <flowcharts目录>   # 孤立节点、出口少于 2 条的判断框
python3 <skill>/scripts/mmd_check.py render <flowcharts目录>   # 生成 .svg 和 3 倍 .png，报告插入 A4 后的字号
```

- 需要 mmdc（`npm i -g @mermaid-js/mermaid-cli`），只装在 Claude 的云端工作区，不装进用户项目。
- 插入后的字号目标不低于 7 pt；00、01 这类全景图不低于 5.5 pt 也可接受。小图不会被放大（与 build_docx 一致，按原始尺寸插入）。字号不够时，改变方向（LR 与 TB 互换）、拆图或精简文字；报告“又高又窄”时考虑改为 LR。
- 用 Read 逐张查看 PNG。箭头交叉、标签压线、子图标题被遮挡、判断分支含糊、节点重叠都要改到干净为止。拆图后要重新运行 lint，防止连线丢失。

## 6. flowcharts/README.md

依次包含：

1. 代码依据：仓库、分支、提交、工程目录，以及实际读过的文件列表。
2. 图表清单：图号、文件名、内容、主要代码依据。
3. 总体框图中的模块与源文件对照表。
4. 关键分析结论：任务表、协议或总线映射、异常处理。
5. 与既有描述不一致或未能确认的事项：逐条编号，写明代码里怎么写、图里怎么画。
6. 绘图约定。
7. 渲染与编辑方法：mmdc 命令；可以在 mermaid.live、Typora、VS Code 中打开编辑；插入 Word 时用 PNG。
