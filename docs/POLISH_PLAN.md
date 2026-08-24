# 《夜游漫记》汉化润色与校对——总体计划（可接手）

> 本文档是润色任务的唯一权威计划与交接说明。任何接手者（人或 AI）先读完本文件，
> 再读 `polish/progress.json` 确认进度，然后从下一个未审条目继续。

## 1. 任务定义

对当前全部 6652 条译文做逐条文学审校（不是抽查，不是机翻重跑）。目标：

1. **上下文连贯**：每句话在其对话/文本序列中审校，不当孤句翻译。代词、称呼、
   时态、情绪线必须与前后文一致。
2. **消除机翻感**：按 `docs/STYLE_GUIDE.md`"去除机翻腔"一节执行——拆英语长定语链、
   删空泛支架词（进行/能够/将会/关于/对于/这意味着）、避免"被……所……"、
   不连续三层"的"、对白必须能朗读顺口。
3. **与前作风格一致**：《密教模拟器》《司辰之书》官方简中的语体是基准——
   凝练、克制、半文半白的秘教语汇只用于 lore 文本，对话自然现代。
4. **考据准确**：史实、地名、宗教与神话指涉逐项核实；不确定的写入 notes，不臆造。
5. **信达雅**：忠实原文含义（包括有意的含混、悖论、冷幽默），表达地道，文气得体。

## 2. 质量标准与既有规范（必读）

- `docs/STYLE_GUIDE.md`——总体标尺、文本层级、句法标点、去机翻腔、强制 QA。
  **本文件的一切裁决不得违反它**；它与本计划冲突时，以 STYLE_GUIDE 为准。
- `docs/USER_GLOSSARY.md`——面向玩家的术语考据表（433 个当前有效概念，每项有独立证据链）。
- `glossary/glossary.csv`——内部术语表（521 个当前有效精确词形，QA 强校验）。
- `glossary/final_term_audit.jsonl`——436 个历史与新增概念的逐项终审账本（含 3 个退役项）。
- `glossary/potential_term_audit.jsonl`——全量源文开放发现的 2817 个候选及逐项纳入／并入／排除结论。
- `glossary/provisional_row_audit.jsonl`——v2.6.0 全部 279 条临时 notes 的改译／保留历史。
- `glossary/predecessor_exact_source_audit.jsonl`——83 条前作官中完全同源英文的逐条比对。
- `glossary/link_targets.csv`——`[[链接]]` 固定译名。

### 术语增删改纪律

- 术语表**不大改**。确有必要时：在 `polish/decisions.md` 记录【英文原词、概念类别、
  同层级前作近邻词、最终译名、排除的候选、理由】，然后同步改 `glossary/glossary.csv`
  与 `docs/USER_GLOSSARY.md`。改术语后必须全局检查既有译文中该词的所有出现。
- `Skill=技艺`、九大伟大之术三字名等已定裁决**不得翻案**（见 STYLE_GUIDE 术语原则）。

## 3. 参考语料（按优先级）

1. 本作英文原文与实际上下文：`build/merged_k97/review_catalog.jsonl` 的 `contexts`
   字段（asset_file / path_id / field_path / game_object），游戏内实测截图。
2. 前作官方简中全文（本机 Steam 目录，直接可读）：
   - 《司辰之书》：`D:\Steam\steamapps\common\Book of Hours\bh_Data\StreamingAssets\bhcontent\loc_zh-hans\`
     （elements/recipes/endings/legacies 等 JSON；长篇书籍文本在 `longformloc/zh-hans`）
   - 《密教模拟器》：`D:\Steam\steamapps\common\Cultist Simulator\cultistsimulator_Data\StreamingAssets\content\loc_zh-hans\`
3. 本作 Steam 官方简中商店页；秘史/司辰之书中文 Wiki（见 STYLE_GUIDE 参考优先级）。

## 4. 语料结构与数据流（改动前必须理解）

```
translations_k97/chunk_001..015.jsonl   ← 润色工作对象（每行一条：
                                                         id / source / translation / status / notes）
        ↓ merge_and_validate_translations.py（打包脚本自动调用）
build/merged_k97/review_catalog.jsonl                  ← 合并产物，带 contexts
        ↓ bake_translations.py                           ← 需游戏处于【原版未打补丁】状态
build/baked_assets/（level*、resources.assets 等）        ← 译文直接烘进游戏资产
        ↓ build_lang_swap_map.py
build/baked_assets/lang_swap.json                        ← F9 热切换映射表
        ↓ build_current_test_install.ps1 → 安装脚本
游戏目录（46 文件哈希核验）
```

- **只改 chunk 文件**，不要直接改 review_catalog.jsonl（它是合并产物；唯一的例外是
  v2.1.16 对三条 loc 键条目的恒等修正，已记录于 HANDOFF.md 第 39 节）。
- 位点级拆分：`glossary/site_overrides.csv` 处理"同一源串在不同显示上下文需要不同
  译文"（如 Spain：地图/脚注标签用裸名，Quote 题签用《西班牙》）。烘焙、
  verify_baked_assets、test_quote_provenance、build_lang_swap_map 四个工具都会
  自动读取它；条目默认译文必须取多数位点的形态。
- 每条被改动的条目：把新译文写入 `translation`，并在 `notes` 追加
  `润色YYYY-MM-DD：<一句话理由>`（原 notes 保留，用 `；` 分隔）。
- **结构红线**（merge QA 会卡）：富文本标签、[[链接]]、`[q=]` 标记、`{0}` 占位符、
  换行数必须与原义逐一对应；只译玩家可见自然语言。
- **News 结构红线**：`patch-notes` 是单条超长 Markdown TextAsset；
  `test_news_patch_notes.py` 必须确认中英文版本标题、顺序和逐段项目数完全一致，
  逐行复刻游戏 `PatchNotesParser` 只接受 ` - ` / ` — ` 标题分隔符的语法，并在正式
  打包时直接回读烘焙后的 `sharedassets3.assets`。
- **回忆显隐红线**：所有 `mypast*` 物品描述与对应 Footnote 必须配对。若英文未揭示态
  是已揭示态的前缀，中文去掉末尾省略号后也必须是逐字前缀；例外只能来自
  英文源文本身的同范围差异，并由 `test_memory_reveal_prefixes.py` 显式登记。
- **F9 模板红线**：以占位符开头的模板只允许整串匹配，不得在长文中做去锚子串扫描；
  会调换占位符顺序的模板（当前为 `{0} in a {1}` / `{1} 中的 {0}`），只有在每个
  捕获组均是独立精确映射键时才能生效。单字性相只能在“数量＋标签”边界内换语言，
  不得加入通用单字子串表。`test_language_swap_regressions.py` 固定两张用户截图的数据夹具。

## 5. 逐条审校流程（每条都走）

**改动门槛（2026-08-18 用户裁决，最高优先级）**：只在以下情况改动——误译/漏义、
术语漂移、结构错误（标签/占位符）、明显机翻腔。**不得为口语化牺牲文学性**
（反例：把"三次心跳之间"改成"的工夫"、把"紧紧相拥，热烈亲吻"拆成"热烈地吻在一起"
——已被用户驳回）。拿不准就保持；原译的节奏和文采即使没有完全贴合英文句式，
也优于一个更"顺"但更平的改写。学究式规整（统一结巴、削平叠合节奏）同样禁止。

1. 读英文原文 → 在 review_catalog 按 `id` 查 contexts，弄清它出现在哪（对话/
   脚注/UI/书籍）。
2. 对话条目：把同一会话的前后条目一起读（contexts 的 asset_file+path_id 相近者），
   确定说话人、情绪、上下句后再动笔。
3. 拿不准的专名/典故：先查 USER_GLOSSARY 与 glossary.csv；再查前作官中语料；
   再查 Wiki/权威资料。仍不确定：译文取最稳妥译法，notes 记"考据待核：<疑点>"。
4. 朗读检查：对白删去英文能自然复述才算过；书面 lore 以文气为准，不要求口语化。
5. 判定结果只有两种：**保持**（原译已达标，不动）或**修改**（写新译+notes）。
   不要为留痕迹而改——无问题的条目明确放过，这同样是审校结论。

### 术语表维护（强制，2026-08-18 用户裁决）

任何术语增删改，必须先判定类别再走记录：
- **前作既有词汇**：给出可访问的灰机 Wiki 词条链接（或前作官中语料文件证据）。
- **新作新词**：给出命名理由（概念类别、构词逻辑）与被排除的候选译名。
记录三处同步：`glossary/glossary.csv`、`glossary/provenance/*.jsonl`
（前作→predecessor.jsonl，新作→travelling_new.jsonl，现实实体→real_world.jsonl，
编辑裁决→editorial.jsonl）、`docs/USER_GLOSSARY.md` 对应章节表行。缺一处即视为未完成。

## 6. 进度跟踪（接手的关键）

- `polish/progress.json`：每 chunk 的 `{total, reviewed, changed, last_id, status}`。
  每完成一个批次就更新；**离开任务前必须落盘**。
- `polish/changelog.jsonl`：每行一条改动 `{id, chunk, old, new, reason}`，审计用。
- `polish/decisions.md`：编辑裁决日志——术语调整、风格裁定、存疑待核清单
  （含"考据待核"条目的汇总）。
- 接手步骤：读本文件 → 读 progress.json 定位 → 读 decisions.md 了解既定裁决 →
  从下个未审条目继续 → 离开前更新三个文件。

## 7. 批次与应用管线

- 工作批次：以 chunk 为单位（450 条/个），内部按 50 条小批推进，每小批落盘一次。
- 应用顺序（每完成若干 chunk 或用户要求出包时执行一次，不必每批都跑）：
  1. 确认游戏已退出（PowerShell：`Get-Process travelling -ErrorAction SilentlyContinue` 无输出）。
  2. 卸载补丁：双击 `build\current_test_install\TravellingAtNight_ZH-CN_current-test\一键卸载.bat`
     （恢复原版资产——bake 必须在原版资产上跑）。
  3. 烘焙：`python tools/bake_translations.py "<游戏根目录>" build/merged_k97/review_catalog.jsonl build/baked_assets --supplement glossary/runtime_supplement.csv --link-targets glossary/link_targets.csv`
     （先跑一次 merge：打包脚本会代跑，或手动
     `python tools/merge_and_validate_translations.py build/worklist_k97/worklist.jsonl translations_k97 build/merged_k97`）。
  4. 重建映射表：`python tools/build_lang_swap_map.py build/merged_k97/review_catalog.jsonl glossary/runtime_supplement.csv build/baked_assets/lang_swap.json`。
  5. 打包+安装+46 文件哈希核验（命令见 HANDOFF.md 各节，版本号顺延）。
- merge/QA 报 structural 错误（标签丢失、占位符不配对）必须当场修掉再打包。

## 8. 完成标准

- 当前 6694 条全部有“保持/修改”结论，progress.json 全 chunk status=done。
- decisions.md 无未解决的"考据待核"（或逐条有用户确认的处置）。
- 全管线跑通，实机抽查至少三段完整对话无异常。
