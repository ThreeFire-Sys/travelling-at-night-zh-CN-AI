# 资料来源与使用边界

本工程以本机安装的公开 Steam Demo 的英文资源、稳定文本 ID 和实际界面上下文为唯一翻译底稿。初次抽取后，Demo 先后更新至 `2026.8.i.75`、`2026.8.j.18` 与 `2026.8.j.33`；最终译文已按 `2026.8.j.33` 重新抽取、差异迁移并验证。该标识并非 Steam 公布的正式版本号。其他资料只用于核对系列术语、人物关系与文风，不以社区页面覆盖游戏原文。

## 版本与许可的官方主源

- [Steam 商店页：Travelling At Night](https://store.steampowered.com/app/2915730/Travelling_at_Night/)：开发者与发行商均为 Weather Factory；商店页提供官方简体中文简介及 Demo 下载。简介中的现行译名用于新作术语校核，但不会机械覆盖前作既定术语或玩家已确认的编辑裁决。
- [Weather Factory：公开 Demo 公告](https://weatherfactory.biz/all-aboard/)（2026-07-16）：公告确认 Steam 公开 Demo 于 2026-08-10 上线；页面没有公布上述内部构建标识。
- [Weather Factory：Sixth History Community Licence](https://weatherfactory.biz/sixth-history-community-licence/)（最后更新于 2022-11-28）：用于判断社区许可范围。
- [BepInEx 5.4.23.5 官方发布页](https://github.com/BepInEx/BepInEx/releases/tag/v5.4.23.5)、[该标签的许可证](https://github.com/BepInEx/BepInEx/blob/v5.4.23.5/LICENSE)与[依赖清单](https://github.com/BepInEx/BepInEx/blob/v5.4.23.5/README.md)：BepInEx 5.x 项目本体适用 MIT License；官方发行包还包含其 README 所列的运行时依赖。
- [Noto Sans CJK 官方许可证](https://github.com/notofonts/noto-cjk/blob/main/Sans/LICENSE)：Noto Sans SC 适用 SIL Open Font License 1.1。

## 第一优先级：本地 Demo

- `resources.assets` 中的 `TravellingDDB`、`LocData` 与游戏 ScriptableObject。
- 场景和预制体中的 TextMeshPro / UGUI 文本。
- `travelling.scripts.dll` 与 `DialogueSystem.dll` 中的运行时文本路径和字段语义。

`2026.8.j.33` 提取清单共 6627 个翻译槽位，对应 6627 个运行时原文 SHA-256 指纹；其中 6611 项包含玩家可见文本，另有 16 项为必须原样保留的控制字符串。清单覆盖对话、对话界面、128 条场景交互标题、脚注、引用、完整版本新闻 TextAsset、物品/机制数据、UI 与其他玩家可见文本。发行目录只保存英文原文的 SHA-256 指纹和中文译文；运行时仍作精确匹配，游戏更新后改变的原文会回退英文，不做模糊替换。

## 系列术语与风格参考

- [《夜游漫记·卷一》既有中文页](https://boh.huijiwiki.com/wiki/%E3%80%8A%E5%A4%9C%E6%B8%B8%E6%BC%AB%E8%AE%B0%C2%B7%E5%8D%B7%E4%B8%80%E3%80%8B)
- [秘史 Wiki：准则](https://mansus.huijiwiki.com/wiki/%E5%87%86%E5%88%99)
- [秘史 Wiki：司辰](https://mansus.huijiwiki.com/wiki/%E5%8F%B8%E8%BE%B0)
- [秘史 Wiki：伟大之术](https://mansus.huijiwiki.com/wiki/%E4%BC%9F%E5%A4%A7%E4%B9%8B%E6%9C%AF)
- [秘史 Wiki：《夜游漫记》脚注](https://mansus.huijiwiki.com/wiki/%E5%A4%9C%E6%B8%B8%E6%BC%AB%E8%AE%B0/%E8%84%9A%E6%B3%A8)
- [秘史 Wiki：创作者问答](https://mansus.huijiwiki.com/wiki/%E5%88%9B%E4%BD%9C%E8%80%85%E9%97%AE%E7%AD%94)
- [《司辰之书》中文 Wiki：宁娜·拉格斯](https://boh.huijiwiki.com/wiki/%E5%AE%81%E5%A8%9C%C2%B7%E6%8B%89%E6%A0%BC%E6%96%AF)、[秘史 Wiki：太阳的喜剧](https://mansus.huijiwiki.com/wiki/%E5%A4%AA%E9%98%B3%E7%9A%84%E5%96%9C%E5%89%A7)与[残阳](https://mansus.huijiwiki.com/wiki/%E6%AE%8B%E9%98%B3)：交叉核定 Nina Lagasse 为“宁娜·拉格斯”，简称“宁娜”，并统一 Lagasse / Lagash 为“拉格斯／拉格什”。
- [Weather Factory：脚注设计说明](https://weatherfactory.biz/its-not-a-codex/)
- [Weather Factory：《Travelling At Night》介绍](https://weatherfactory.biz/travelling-at-night/)

Wiki 的新作页面仍随 Alpha / Demo 更新，存在“邦国/国家”“辉冕/冕之触”等并行译法；它们只作为候选语料，不作为版本、权利或许可结论的依据。最终取舍记录在 `glossary/glossary.csv` 和逐条翻译 `notes` 中。

## 前作本地文本

本机可用的《密教模拟器》简中资源只覆盖部分 DLC，且安装来源无法作为完整、干净的官方语料链证明。本工程仅从中蒸馏固定术语与句法特征，不复制或打包前作语言文件，也不逐段复刻旧译文。

## 权利与发布

译文是针对本 Demo 英文原文创作的新译。本工程是非官方社区项目，与 Weather Factory 无隶属关系；除非另行取得书面许可，不得表述为官方、获得认可或获得背书。

截至 2026-08-11，现行 Sixth History Community Licence 的许可作品清单只列出《Cultist Simulator》（含 DLC）、《BOOK OF HOURS》（含 DLC）和《The Lady Afterwards》，并明确排除 Weather Factory 其他产品的内容。《Travelling At Night》不在清单中，因此该许可不能视为分发本作译文补丁的授权；公开分发完整译文补丁前，应另行取得 Weather Factory 的书面许可或确认。

发布包不包含 `resources.assets`、完整英文游戏文案、前作中文语言包或本工程的审校工作表；用户必须自行从官方渠道取得 Demo。构建脚本会随包保留 BepInEx 5.4.23.5 项目本体的 MIT License、Noto Sans SC 的 SIL Open Font License 1.1，以及 HarmonyX、Harmony、MonoMod、Mono.Cecil、UnityDoorstop 等随附运行时依赖的适用通知；UnityDoorstop 4.5.0 的对应源代码归档也已随包提供。构建器会在任一必需许可文件缺失时拒绝生成 ZIP。第三方许可完备不改变《Travelling At Night》译文公开分发仍须另行取得权利人书面许可或确认的边界。
