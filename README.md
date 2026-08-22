# 《夜游漫记》非官方简体中文补丁（AI 辅助翻译）

面向 Weather Factory《Travelling at Night》公开 Steam Demo 的简体中文本地化工程。

- 当前补丁版本：**v2.6.0**（更新日志见 `CHANGELOG.md`）
- 对应游戏构建标识：`2026.8.k.97`（游戏内 `version.txt`；Steam 未公布对应的正式版本号）
- 平台：Windows x64，Unity 6000.4.0f1（Mono）
- 性质：个人制作的**非官方**汉化，与 Weather Factory 无关。初译由 GPT 5.6sol 完成，主要润色与校对由 Kimi K3 完成；终审、术语逐词考据与 k.97 迁移由 OpenAI Codex 接续完成（见随包的术语表与审计账本）。

## 特点

**烘焙式汉化（v2.x 架构）**。译文不经过运行时拦截，而是离线直接写入游戏的序列化资产（对话库、脚注、场景文本、UI 标签、Loc 表……共 9100 余处位点、15 个资产文件）。游戏自己的渲染管线——打字机、对话缓冲、`[[链接]]` 解析、`[q=]` 数值替换、脚注显隐——全部原生运行于中文之上，从根上避免了运行时补丁常见的残句、闪烁、漏译问题。

**F9 中英即时切换**。插件在内存中按精确映射双向改写已加载文本，无需重启；映射表由烘焙目录自动生成（en2zh 零冲突，保证来回切换逐值还原）。

**中文字体后备**。挂载 Noto Sans CJK SC 动态字体，按字符需求生成字形，保持原版排版与字号。

**术语考据体系**。`docs/USER_GLOSSARY.md`（发布包内为《术语表与译名说明》）逐词登记证据类型、置信等级、命名理由与被否决的候选译法；`glossary/final_term_audit.jsonl` 留存 350 个历史概念的逐项终审裁决，不以家族套话代替单词证据。Quote 组件的全部 23 处文学引文（莎士比亚、叶芝、奥登、毕肖普、Leonard Cohen 等）逐条考据出处并记录排版处置。

**全量逐条审校**。约 6700 条译文逐条人工+AI 复核：上下文连贯性、机翻感消除、与前作风格一致性、排比/诗节结构保持。改动全部留痕于 `polish/changelog.jsonl`，裁决记录于 `polish/decisions.md`。

**安全安装器**。双击即用（`一键安装.bat`），逐文件原子替换并全程记录恢复状态；原版文件备份到游戏目录 `.travelling-cn-backup`；卸载器只移除哈希仍与补丁一致的文件，被外部修改过的文件一律保留并报告。游戏版本不符时给出警告并依靠原文精确匹配安全降级。

## 安装

1. 完整解压发布包（不要只取其中几个文件）。
2. 双击 `一键安装.bat`。卸载双击 `一键卸载.bat`。
3. 游戏内按 `F9` 可即时切换中英文。

游戏更新后 Steam 会把被替换的资产恢复为官方英文版（汉化随之失效），届时请先卸载本补丁，待更新完成后安装与新版本对应的新版补丁。

## 项目结构

```
src/TravellingCN/         BepInEx 插件源码（字体挂载、F9 切换、少量 Harmony 补丁）
tools/                    管线与 QA 工具（Python + 一个 PowerShell 打包器）
translations_k97/         当前译文源（按 chunk 分卷的 JSONL）
translations*/            历史译文快照（供游戏更新后 rebase 复用，勿删）
glossary/                 术语表、链接译名表、运行时补充表、位点覆盖表、引文出处
docs/                     风格指南、资料来源、用户术语表、第三方声明、QA 报告
release/                  发布包外层模板（一键 bat、安装/卸载脚本、README）
polish/                   全量润色的进度/改动/裁决留痕
qa/                       QA 处置记录
build/                    本机生成的中间产物（不入库；详见 .gitignore）
dist/                     发布包（不入库，经 GitHub Releases 分发）
```

## 管线（从源码重建）

```
extract_unity_text.py          从游戏资产提取全部玩家可见文本（含位点）
        ↓
prepare_worklist.py            生成工作单（提取器会把 loc 键/程序标识符排除在可译候选外）
        ↓
translations_k97/chunk_*.jsonl  译文（人工+AI 审校的工作对象）
        ↓ merge_and_validate_translations.py   结构 QA：标签/占位符/链接/换行逐一对应
build/merged_k97/              合并产物（review_catalog 带全部位点）
        ↓ bake_translations.py（需游戏处于未打补丁的原版状态）
build/baked_assets/            译文烘进游戏资产
        ↓ build_lang_swap_map.py
build/baked_assets/lang_swap.json   F9 双向映射
        ↓ build_current_test_install.ps1（内建十余项聚焦 QA）
dist/ 发布包
```

游戏更新后的迁移顺序见 `docs/POLISH_PLAN.md`；逐版本的排障与决策记录在 `HANDOFF.md`。

## 权利与发布说明

本工程是非官方社区项目，与 Weather Factory 无隶属关系；不得表述为官方、获得认可或获得背书。

截至 2026-08-11，现行 [Sixth History Community Licence](https://weatherfactory.biz/sixth-history-community-licence/) 的许可作品清单不包含《Travelling at Night》，且明确排除 Weather Factory 其他产品的内容，因此不能把该许可视为本译文补丁的分发授权。本补丁的烘焙发布包内含**经修改的游戏资产文件**（仅替换文本内容），公开分发存在权利不确定性；如需引用或再分发，请自行评估并遵守 Weather Factory 的相关政策。

发布包随附 [BepInEx 5.4.23.5 的 MIT License](https://github.com/BepInEx/BepInEx/blob/v5.4.23.5/LICENSE)、[Noto Sans SC 的 SIL Open Font License 1.1](https://github.com/notofonts/noto-cjk/blob/main/Sans/LICENSE)（OFL 覆盖的字体文件随包分发）、HarmonyX／Harmony／MonoMod／Mono.Cecil／UnityDoorstop 等运行时依赖的适用通知；UnityDoorstop 的对应源代码归档随包提供。版本与来源详情见 `docs/SOURCES.md`、`docs/THIRD_PARTY_NOTICES.md`。

## 致谢

- Weather Factory 与 Alexis Kennedy：游戏本体。
- 前作官方简中与系列中文 Wiki（秘史维基/灰机）的贡献者们：大量固定译名的来源。
- BepInEx／Harmony／UnityDoorstop／TextMeshPro 等开源组件。
