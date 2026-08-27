// F9 中英文即时切换（LanguageSwap）。
//
// 架构原则：只在内存里改写游戏数据对象的字符串字段，绝不拦截渲染管线。
// 这里不得出现任何 Harmony patch，不得触碰 TMP 的 setter patch/打字机/缓冲，
// 也不得写磁盘上的资产文件。一趟"交换扫描"（Swap Pass）就是遍历全部已加载
// 对象做字符串替换——映射表本身就是过滤器，遍历器刻意保持"笨"，不做模糊匹配。
//
// 显示组件（TMP_Text / UI.Text）的文本走分级流水线（每级输入是上级输出）：
//   Tier 1   整串精确匹配（与数据字段同一映射）；
//   Tier 1.5 去标签精确：剥掉全部 <...> 标签得纯文本再整串查映射（显示管线
//            把 [[X]] 装饰成 <link="X"><color=#...><u>X</u></color></link>，
//            整串因此不等于任何键；映射表里有去 [[]] 的折叠键对应这一级）；
//   Tier 2   模板匹配：含 {n} 占位符的键编译成锚定正则，命中后各捕获组递归
//            走完整流水线，再按目标语言模板手工切片拼接（不做 string.Format）。
//            覆盖运行时拼装串：说话人格式行、技能名列表实例化等；
//   Tier 2.5 文本段精确：按标签切成 标签/文本 交替段，每个文本段整段查映射
//            （覆盖说话人名 "Me" → "我" 等），部分替换，不短路；
//   Tier 3   纯文本子串扫描：构建纯文本 + 到原始串的索引映射，在纯文本上跑
//            桶扫描（CJK≥2 / 拉丁≥4+词边界规则不变，词边界看纯文本邻居），
//            命中区段换算回原始串区间原位替换，未命中部分照抄原始串（标签
//            原样保留）。单趟扫描，绝不重扫已输出内容。
//   Tier 3.5 模板子串：键桶扫描之前，先用去锚模板正则（SubstringPattern，
//            末尾占位符贪婪）在纯文本上收集运行时合成串的匹配区间
//            （"Gained {0} ({1})" 这类 LocData 模板 + 标签拼装行，整串级
//            永远不命中），捕获组递归走完整流水线、按目标模板拼接；键桶
//            扫描跳过模板区间覆盖的位置（模板区间优先，避免二次替换）。
//   Settle   统一收尾：以上任何一级产出的串若仍含 [[Y]]，调用游戏原生管线
//            TravellingUtility.ResolveQualityTokensAndColourizeLinks(
//            result, LinkStyle.Default, hideVisitedLinks: false) 统一装饰：
//            [[Y]] → <link>、按当前链接状态（未读/已读/失效）重算结果串里
//            所有 <link> 的颜色、解析 [q=] 标记。hideVisitedLinks 必须 false，
//            否则已读链接被剥成裸文本。游戏链接颜色本来就是渲染时按状态动态
//            算的（v2.1.4 之前保留旧包装器会把颜色冻结/错位）。异常时回退：
//            [[Y]] 折叠为 Y。数据字段交换不做 Settle（数据必须保留 [[]] 形态）。
// 数据对象的反射字段交换只做整串精确匹配——数据里没有拼装串，不能冒险。
//
// Field 保护（v2.1.3 崩溃修复）：PixelCrushers.DialogueSystem.Field 实例只
// 换 value 字段，且仅当 title 属于文本标题白名单（与烘焙管线口径一致）。
// 否则通用遍历会把 title="Name" 换成 lore 文本"具名者"，LookupValue("Name")
// 返回 null，DialogueDatabase.GetEntrytag 的 Regex.Replace(null) 直接崩溃。
//
// accumulatedText 例外（v2.1.6/v2.1.8 回弹修复）：字幕面板滚动历史存在
// StandardUISubtitlePanel 的 accumulatedText 属性里（存储字段是
// m_accumulatedText，v2.1.6 只配属性名导致路由从未命中），是带装饰的显示
// 文本大 blob，精确匹配永不命中，点"继续"重建 TMP.text 会把历史行覆盖回
// 旧语言。该字段名（声明类型在游戏命名空间内）改走完整显示级流水线。
//
// 字典键重建（v2.1.8 灰色链接修复）：ScriptablesCurator 启动时按当前语言
// label 建好 FootnotesByLabel/SkillsByLabel 等 string 键→对象字典与
// _alternativeToPrimaryLabel；对象的 _label 被交换后键不跟随，另一语言下
// Detailable 解析失败、链接被 ColourizeLinks 算成"失效"灰色。反射遍历对
// string 键 IDictionary 做 Remove(旧键)+重建（值是 string 时也经精确表）。
//
// 已知边界（有意不处理）：
//   - 正在打字机动画中的当前行可能保持旧语言，直到下一行刷新；
//   - 存档/日志里已生成的历史文本保持生成时的语言。
//
// v2.1.9 起的行为补充：
//   - 打字机播放中（TravellingTypewriter.isPlaying）忽略 F9，防止全量揭示
//     与逐字揭示状态交错出残句；
//   - RunSwapPass 分两阶段：先换完全部数据对象（含字典键重建），再换显示
//     组件——SettleLinks 着色时 ScriptablesCurator 字典键已是当前语言，
//     链接不会被判成"失效"灰色；
//   - SettleLinks 颜色继承：被替换的原始串里已有带 <color> 的 <link> 时，
//     用颜色参数重载并沿用原文面板色（对话历史橙色系），否则用
//     LinkStyle.Default；viewed/broken 色从 Default 实例反射一次并缓存；
//   - LanguageSwap.DebugLog（默认 false）：记录每条部分替换文本的层级与
//     原文，以及交换后仍混语（剥标签后同时含 CJK 与拉丁字母）的文本。
//
// 说话人名三层缓存修复（v2.1.11，新行说话人名保持旧语言的根治）：
//   - 字典值递归：ConversationModel.m_characterInfoCache 是
//     Dictionary<int, CharacterInfo>，int 键不重建但值递归走 SwapObjectFields，
//     缓存的 CharacterInfo.Name 跟随当前语言；
//   - sprite 前缀兼容：GetMarkedSpeakerName 把缓存名改成 <sprite=N>名字
//     形态，string 字段精确失配时剥前缀重查一次；
//   - Lua 层同步：每趟交换后遍历 masterDatabase.actors，把 "Display Name"
//     用 DialogueLua.SetActorField 写回 Lua VM 快照（新 CharacterInfo 的
//     语言源 GetLocalizedActorField 读的就是这张表）。
//
// 幂等性：已是目标语言的值不会匹配本方向映射的键/模板/子串，重跑无副作用，
// 因此场景加载后可以直接对全量对象再跑一遍。
//
// 场景浮签（WorldPopup）特例（v2.2.6）：浮签文本由游戏 Display() 时按字符数
// 断行、米纸条底按行重建。扫描链路只换裸文本会导致换行/纸条底脱节溢出；
// 因此英文模式下由 Plugin 的 ComposeWrapped Harmony 前缀把组成段换回英文
// （SwapPopupSegment，新弹出浮签直接正确），F9 切换后由
// RefreshVisibleWorldPopups 重 Compose 可见浮签并重建纸条底。

using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.RegularExpressions;
using BepInEx.Configuration;
using BepInEx.Logging;
using Newtonsoft.Json;
using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace TravellingCN
{
    internal static class LanguageSwap
    {
        private const string MapFileName = "lang_swap.json";
        // 子串安全键阈值：CJK 键至少 2 个汉字（排除"刃""杯"等单字性相名），
        // 纯拉丁键至少 4 字符且匹配时要求词边界（防 "Leon" 误中 "Napoleon"）。
        private const int MinCjkCharsForSubstring = 2;
        private const int MinLatinLengthForSubstring = 4;
        // 模板捕获组递归交换的深度上限，防病态自嵌套。
        private const int MaxSwapDepth = 8;
        private static readonly Regex PlaceholderPattern =
            new Regex(@"\{(\d+)\}", RegexOptions.Compiled);
        // [q=...] 查询令牌：对话文本里的动态占位（玩家别名/性相名/数值等），
        // 游戏显示时已解析成实际值，映射键里的令牌形态因此永远匹配不上显示态
        // ——含 [q=alias.formal.fr] 的段落 F9 双向都掉到子串级，只剩链接词被
        // 换掉（"Color鲜艳"，v2.6.3 用户实测）。建图时把令牌改写成合成占位符，
        // 按模板匹配（见 TryRewriteQueryTokens）。
        private static readonly Regex QueryTokenPattern =
            new Regex(@"\[q=[^\[\]]+\]", RegexOptions.Compiled);
        // 源侧严格相邻的两个查询令牌（"[q=a][q=b]"）：中间无字面锚点，捕获
        // 切分有歧义，不模板化。
        private static readonly Regex AdjacentQueryTokensPattern =
            new Regex(@"\[q=[^\[\]]+\]\[q=", RegexOptions.Compiled);
        // 捕获组必须是独立映射键的模板：字面部分太短/太常见时，任意文本都会
        // 被当成模板实例吞掉重排（v2.6.2 "{0} in a {1}" 把普通句子重排成中英
        // 混杂；v2.6.3 "Not {0}" 把 "Not 'kept', really. ..." 整段换成
        // "非 'kept'…"）。两个方向各自的源形态都要登记。
        private static readonly HashSet<string> ExactGroupTemplates =
            new HashSet<string>(StringComparer.Ordinal)
            {
                "{0} in a {1}",
                "{1} 中的 {0}",
                "Not {0}",
                "非 {0}",
            };
        // [[Y]] 链接占位（折叠键的值保留的原始形态）；Settle 原生装饰失败时
        // 用它把 [[Y]] 折叠回 Y。
        private static readonly Regex BracketLinkPattern =
            new Regex(@"\[\[([^\[\]]+)\]\]", RegexOptions.Compiled);
        // loc 键形态：全大写/数字且至少一个下划线（UI_FOOTNOTE_UNSUBTLE）。
        // 这类字符串是程序查找键，数据层永不交换；YES/LINK 等无下划线的
        // 全大写显示值不受此限制。
        private static readonly Regex LocKeyPattern =
            new Regex(@"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$", RegexOptions.Compiled);
        // 原生装饰只 LogWarning 一次，避免逐文本刷日志。
        private static bool _nativeDecorateFailed;

        // PixelCrushers Field 保护：用 FullName 字符串判断，不新增程序集引用。
        private const string DialogueFieldTypeName = "PixelCrushers.DialogueSystem.Field";
        // 可交换的文本标题白名单（与烘焙管线 prepare_worklist.py 口径一致，
        // 外加资产通用的 "Description"）；其余 Field（"Name"/"Actor"/"Sequence"
        // 等结构字段）一律不碰。
        private static readonly HashSet<string> DialogueTextFieldTitles =
            new HashSet<string>(StringComparer.Ordinal)
            {
                "Dialogue Text",
                "Menu Text",
                "Display Name",
                "WhenUnlockedOverride",
                "WhenLockedOverride",
                "Success Description",
                "Failure Description",
                "Response Menu Sequence",
                "Description",
            };
        private static readonly Regex SkillCheckDescriptionTitlePattern =
            new Regex(@"^SkillCheckModifier_\d+_Description$", RegexOptions.Compiled);

        private static ManualLogSource Log;
        private static ConfigEntry<bool> _enabled;
        private static ConfigEntry<KeyboardShortcut> _toggleKey;
        private static ConfigEntry<bool> _debugLog;

        private static DirectionMap _en2zh;
        private static DirectionMap _zh2en;
        private static bool _mapsLoaded;

        // 默认中文模式：磁盘资产已烘成中文，启动时无需任何操作。
        private static bool _englishMode;

        private sealed class LangSwapFile
        {
#pragma warning disable CS0649 // 字段由 JsonConvert 反序列化填充
            public int version;
            public Dictionary<string, string> en2zh;
            public Dictionary<string, string> zh2en;
#pragma warning restore CS0649
        }

        // 一个方向的交换映射：精确表 + 模板列表 + 子串安全键分桶。
        private sealed class DirectionMap
        {
            internal Dictionary<string, string> Exact;
            internal Dictionary<string, string> Squashed; // 折叠全部空白后的查找键 → 目标值
            internal readonly List<TemplateEntry> Templates = new List<TemplateEntry>();
            internal readonly Dictionary<char, List<SubstringKey>> SubstringBuckets =
                new Dictionary<char, List<SubstringKey>>();
        }

        private sealed class SubstringKey
        {
            internal string Key;
            internal string Value;
            internal bool NeedsWordBoundary; // 纯拉丁键：前后字符不能是拉丁字母
        }

        private sealed class TemplateEntry
        {
            internal Regex Pattern;            // 锚定 ^$ fullmatch（Tier 2）
            internal Regex SubstringPattern;   // 去锚子串匹配（Tier 3.5），末尾占位符贪婪
            internal string FirstLiteral;      // 首个字面段，非空时用于快速预筛
            internal bool StartsWithPlaceholder; // 前置占位符模板只许整串匹配，不许子串扫描
            internal bool RequiresExactGroups; // 会重排前置占位符的模板，每组必须是独立映射键
            internal int[] GroupPlaceholders;  // 捕获组（按出现顺序）对应的占位符序号
            internal TemplateSegment[] Target; // 目标语言模板切片
            internal int LiteralLength;        // 字面部分总长度，用于模板排序（越具体越先）
        }

        private struct TemplateSegment
        {
            internal string Literal;     // 非 null 表示字面段
            internal int Placeholder;    // Literal 为 null 时有效
        }

        private sealed class SwapCounters
        {
            internal int Exact;             // Tier 1 整串精确
            internal int TaglessExact;      // Tier 1.5 去标签精确
            internal int Template;          // Tier 2 模板（整串 fullmatch）
            internal int TemplateSubstring; // Tier 3.5 模板子串
            internal int SegmentExact;      // Tier 2.5 文本段精确
            internal int Substring;         // Tier 3 纯文本子串
            internal int DictionaryKey;     // 字典键重建（ScriptablesCurator ByLabel 等）
            internal int DictionaryKeyConflict; // 新键与既有键冲突而跳过的条数
        }

        // 反射防循环用引用相等比较器（游戏对象可能重写 Equals）。
        private sealed class ReferenceComparer : IEqualityComparer<object>
        {
            public new bool Equals(object x, object y) => ReferenceEquals(x, y);
            public int GetHashCode(object obj) => RuntimeHelpers.GetHashCode(obj);
        }

        internal static void Initialize(ConfigFile config, ManualLogSource logger, string pluginDirectory)
        {
            Log = logger;
            _enabled = config.Bind(
                "LanguageSwap",
                "Enabled",
                true,
                "启用 F9 游戏内中英文即时切换（内存改写，不拦截渲染、不写磁盘）。");
            _toggleKey = config.Bind(
                "LanguageSwap",
                "ToggleKey",
                new KeyboardShortcut(KeyCode.F9),
                "中英文切换热键。");
            _debugLog = config.Bind(
                "LanguageSwap",
                "DebugLog",
                false,
                "调试日志：记录每条部分替换文本的层级与原文、交换后仍混语的文本。");
            LoadMaps(pluginDirectory);
            SceneManager.sceneLoaded += OnSceneLoaded;
        }

        internal static void Shutdown()
        {
            SceneManager.sceneLoaded -= OnSceneLoaded;
        }

        private static void LoadMaps(string pluginDirectory)
        {
            var path = Path.Combine(pluginDirectory, MapFileName);
            if (!File.Exists(path))
            {
                Log.LogWarning($"未找到语言切换映射：{path}；F9 切换不可用。");
                return;
            }
            try
            {
                var loaded = JsonConvert.DeserializeObject<LangSwapFile>(File.ReadAllText(path));
                if (loaded?.en2zh == null || loaded.zh2en == null)
                {
                    Log.LogError("语言切换映射缺少 en2zh/zh2en 表。");
                    return;
                }
                _en2zh = BuildDirectionMap(loaded.en2zh, "en2zh");
                _zh2en = BuildDirectionMap(loaded.zh2en, "zh2en");
                LoadLabelFidelity(pluginDirectory);
                _mapsLoaded = true;
            }
            catch (Exception exception)
            {
                Log.LogError($"语言切换映射无法解析：{exception}");
            }
        }

        // 资产标签保真表（label_fidelity.json，byId/byCn）：通用 zh2en 是按
        // 字符串的函数，多个英文原文共享一个中文标签时只能择一——另一资产的
        // 标签会被换成错的变体，按标签（不区分大小写）解析的链接随之失效
        // （v2.4.13 实测：旅行脚注被换成 "Travel"，作者链接 id "travelling"
        // 失配成青链）。标签字段交换与英文别名注入先查本表。
        private static Dictionary<string, string> _labelFidelityById = new Dictionary<string, string>(StringComparer.Ordinal);
        private static Dictionary<string, string> _labelFidelityByCn = new Dictionary<string, string>(StringComparer.Ordinal);

        private static void LoadLabelFidelity(string pluginDirectory)
        {
            var path = Path.Combine(pluginDirectory, "label_fidelity.json");
            if (!File.Exists(path))
            {
                Log.LogWarning($"未找到标签保真映射：{path}；标签交换退回通用映射。");
                return;
            }
            try
            {
                var loaded = JsonConvert.DeserializeObject<LabelFidelityFile>(File.ReadAllText(path));
                if (loaded?.byId != null)
                {
                    _labelFidelityById = new Dictionary<string, string>(loaded.byId, StringComparer.Ordinal);
                }
                if (loaded?.byCn != null)
                {
                    _labelFidelityByCn = new Dictionary<string, string>(loaded.byCn, StringComparer.Ordinal);
                }
                Log.LogInfo($"标签保真映射：byId {_labelFidelityById.Count} 条，byCn {_labelFidelityByCn.Count} 条。");
            }
            catch (Exception exception)
            {
                Log.LogError($"标签保真映射无法解析：{exception}");
            }
        }

        private sealed class LabelFidelityFile
        {
            public Dictionary<string, string> byId;
            public Dictionary<string, string> byCn;
        }

        // 标签保真查询：CN→EN 方向换标签字段时优先于通用映射。先按资产 id，
        // 再按中文标签（byCn 仅收资产标签域内无冲突的）。
        internal static bool TryGetFidelityEnglishLabel(string assetId, string cnLabel, out string english)
        {
            english = null;
            if (!_mapsLoaded)
            {
                return false;
            }
            if (!string.IsNullOrEmpty(assetId) &&
                _labelFidelityById.TryGetValue(assetId, out english))
            {
                return true;
            }
            if (!string.IsNullOrEmpty(cnLabel) &&
                _labelFidelityByCn.TryGetValue(cnLabel, out english))
            {
                return true;
            }
            english = null;
            return false;
        }

        private static DirectionMap BuildDirectionMap(Dictionary<string, string> raw, string name)
        {
            var map = new DirectionMap
            {
                Exact = new Dictionary<string, string>(raw.Count, StringComparer.Ordinal),
                Squashed = new Dictionary<string, string>(StringComparer.Ordinal),
            };
            var squashedConflict = new HashSet<string>(StringComparer.Ordinal);
            var substringCount = 0;
            foreach (var pair in raw)
            {
                if (string.IsNullOrEmpty(pair.Key) || pair.Value == null)
                {
                    continue;
                }
                map.Exact[pair.Key] = pair.Value;
                // 折叠空白查找键：游戏显示时给长文本插入手动换行
                // （WrapTextAtSpecifiedMaxWidth 把空白改写成 \n），显示态折叠后
                // 会落在【无空白的键】上——所以全部键都进表（v2.2.3 实测：只收
                // 含空白键的优化恰恰漏掉了中文无空白键）。撞键且值不同才封禁。
                var squashedKey = SquashWhitespace(pair.Key);
                if (squashedConflict.Contains(squashedKey))
                {
                    continue;
                }
                if (map.Squashed.TryGetValue(squashedKey, out var existing) &&
                    existing != pair.Value)
                {
                    // v2.4.16：值只差首尾空白不算冲突——源串带排版尾距的主条目
                    // 与其 trimmed 变体必然撞同一个 squash 键；此前一律封禁导致
                    // 这类长文（如教程泡"制作：场所与技艺"）在 EN→CN 时折叠层
                    // 失配掉到子串级（英文句子+中文链接词混排回归）。
                    if (string.Equals(existing?.Trim(), pair.Value?.Trim(), StringComparison.Ordinal))
                    {
                        continue;
                    }
                    map.Squashed.Remove(squashedKey);
                    squashedConflict.Add(squashedKey);
                }
                else
                {
                    map.Squashed[squashedKey] = pair.Value;
                }
                var templateKey = pair.Key;
                var templateValue = pair.Value;
                if (QueryTokenPattern.IsMatch(pair.Key) &&
                    TryRewriteQueryTokens(pair.Key, pair.Value, out var rewrittenKey, out var rewrittenValue))
                {
                    templateKey = rewrittenKey;
                    templateValue = rewrittenValue;
                }
                if (PlaceholderPattern.IsMatch(templateKey))
                {
                    var template = BuildTemplate(templateKey, templateValue);
                    if (template != null)
                    {
                        map.Templates.Add(template);
                    }
                }
                else if (TryBuildSubstringKey(pair.Key, pair.Value, out var substringKey))
                {
                    if (!map.SubstringBuckets.TryGetValue(pair.Key[0], out var bucket))
                    {
                        bucket = new List<SubstringKey>();
                        map.SubstringBuckets[pair.Key[0]] = bucket;
                    }
                    bucket.Add(substringKey);
                    substringCount++;
                }
            }
            // 模板按字面部分长度降序（越具体越先命中）；桶内键长降序（最长匹配优先）。
            map.Templates.Sort((a, b) => b.LiteralLength.CompareTo(a.LiteralLength));
            foreach (var bucket in map.SubstringBuckets.Values)
            {
                bucket.Sort((a, b) => b.Key.Length.CompareTo(a.Key.Length));
            }
            Log.LogInfo(
                $"语言切换映射 {name}：精确 {map.Exact.Count} 条，" +
                $"模板 {map.Templates.Count} 条，子串安全键 {substringCount} 条。");
            return map;
        }

        private static bool TryBuildSubstringKey(string key, string value, out SubstringKey substringKey)
        {
            substringKey = null;
            var cjkCount = CountCjkChars(key);
            bool eligible;
            bool needsWordBoundary;
            if (cjkCount >= MinCjkCharsForSubstring)
            {
                eligible = true;
                needsWordBoundary = false;
            }
            else if (cjkCount == 0 && key.Length >= MinLatinLengthForSubstring)
            {
                eligible = true;
                needsWordBoundary = true;
            }
            else
            {
                eligible = false;
                needsWordBoundary = false;
            }
            if (!eligible)
            {
                return false;
            }
            substringKey = new SubstringKey
            {
                Key = key,
                Value = value,
                NeedsWordBoundary = needsWordBoundary,
            };
            return true;
        }

        private static int CountCjkChars(string text)
        {
            var count = 0;
            foreach (var c in text)
            {
                if (c >= '一' && c <= '鿿') // CJK 统一表意文字基本区
                {
                    count++;
                }
            }
            return count;
        }

        private static bool IsLatinLetter(char c) =>
            (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z');

        // 把含 {n} 占位符的键编译成正则：字面部分 Regex.Escape，占位符 → 捕获
        // 组；目标值切片成 字面/占位符 段序列，交换后按占位符序号手工拼接
        // （不做 string.Format，组内容可能含花括号）。每个模板编译两版：
        //   Pattern          锚定 ^$ fullmatch，供 Tier 2 整串模板匹配；
        //   SubstringPattern 去锚，供 Tier 3.5 在纯文本上作子串匹配。子串版里
        //                    位于模板末尾的占位符用贪婪 (.+)（非贪婪在右无界时
        //                    只会吞 1 个字符），其余保持非贪婪 (.+?)（左端有
        //                    正则最左匹配偏置，不需特殊处理）。
        // 捕获组贪婪特例（v2.3.4）：若占位符紧随的字面段以开括号开头
        // （" ("／"（"），该组改用贪婪——物品名自带括号后缀时（"第三共和国护照
        // （已失效）"／"Third Republic Passport (Invalid)"），非贪婪会在第一个
        // 括号处错切，导致组内容查不到映射、交换后名字残留旧语言（"Gained
        // {0} ({1})" 实测）。贪婪按最右开括号切分，正合"计数括号在最后"的
        // 结构。子串版的贪婪组限制不跨换行（[^\n]+），防长 blob 里跨界。
        private static bool LiteralStartsWithParen(string literal)
        {
            var i = 0;
            while (i < literal.Length && char.IsWhiteSpace(literal[i]))
            {
                i++;
            }
            if (i >= literal.Length)
            {
                return false;
            }
            var c = literal[i];
            return c == '(' || c == '（' || c == '[' || c == '【';
        }

        // 把源/目标串里的 [q=...] 查询令牌改写成模板占位符：同一令牌（按原文
        // 逐字）在两侧取同一合成序号，从两侧既有 {n} 序号之后续起避免冲突。
        // 目标侧出现源侧没有的令牌、或源侧两个令牌严格相邻（无字面锚点，捕获
        // 切分有歧义）时返回 false——该对保持纯精确条目，不模板化。捕获组走
        // 与 {n} 相同的递归交换：解析值若是映射词（如 [q=Pain]→苦痛）会顺带
        // 换语言，若是未映射的别名（Herr Hobson）则原样保留。
        private static bool TryRewriteQueryTokens(
            string source, string target, out string rewrittenSource, out string rewrittenTarget)
        {
            rewrittenSource = null;
            rewrittenTarget = null;
            if (target == null || !QueryTokenPattern.IsMatch(source) ||
                AdjacentQueryTokensPattern.IsMatch(source))
            {
                return false;
            }
            var sourceTokens = new HashSet<string>(StringComparer.Ordinal);
            foreach (Match match in QueryTokenPattern.Matches(source))
            {
                sourceTokens.Add(match.Value);
            }
            foreach (Match match in QueryTokenPattern.Matches(target))
            {
                if (!sourceTokens.Contains(match.Value))
                {
                    return false;
                }
            }
            var usedIndices = new HashSet<int>();
            foreach (Match match in PlaceholderPattern.Matches(source))
            {
                usedIndices.Add(int.Parse(match.Groups[1].Value));
            }
            foreach (Match match in PlaceholderPattern.Matches(target))
            {
                usedIndices.Add(int.Parse(match.Groups[1].Value));
            }
            var tokenIds = new Dictionary<string, int>(StringComparer.Ordinal);
            var nextIndex = 0;
            int SyntheticId(Match tokenMatch)
            {
                if (!tokenIds.TryGetValue(tokenMatch.Value, out var id))
                {
                    while (usedIndices.Contains(nextIndex))
                    {
                        nextIndex++;
                    }
                    id = nextIndex++;
                    usedIndices.Add(id);
                    tokenIds[tokenMatch.Value] = id;
                }
                return id;
            }
            rewrittenSource = QueryTokenPattern.Replace(
                source, match => "{" + SyntheticId(match).ToString() + "}");
            rewrittenTarget = QueryTokenPattern.Replace(
                target, match => "{" + SyntheticId(match).ToString() + "}");
            return true;
        }

        private static TemplateEntry BuildTemplate(string sourceTemplate, string targetTemplate)
        {
            try
            {
                var pattern = new StringBuilder("^");
                var substringPattern = new StringBuilder();
                var groupPlaceholders = new List<int>();
                var literalLength = 0;
                string firstLiteral = null;
                var placeholders = PlaceholderPattern.Matches(sourceTemplate);
                var position = 0;
                for (var i = 0; i < placeholders.Count; i++)
                {
                    var match = placeholders[i];
                    var literal = sourceTemplate.Substring(position, match.Index - position);
                    if (firstLiteral == null && literal.Length > 0)
                    {
                        firstLiteral = literal;
                    }
                    literalLength += literal.Length;
                    pattern.Append(Regex.Escape(literal));
                    substringPattern.Append(Regex.Escape(literal));
                    var followingLiteral = (i + 1 < placeholders.Count)
                        ? sourceTemplate.Substring(
                            match.Index + match.Length,
                            placeholders[i + 1].Index - (match.Index + match.Length))
                        : sourceTemplate.Substring(match.Index + match.Length);
                    var greedyForParen = LiteralStartsWithParen(followingLiteral);
                    pattern.Append(greedyForParen ? "(.+)" : "(.+?)");
                    var isLastToken =
                        i == placeholders.Count - 1 &&
                        match.Index + match.Length == sourceTemplate.Length;
                    substringPattern.Append(
                        isLastToken ? "(.+)" : (greedyForParen ? "([^\n]+)" : "(.+?)"));
                    groupPlaceholders.Add(int.Parse(match.Groups[1].Value));
                    position = match.Index + match.Length;
                }
                var tail = sourceTemplate.Substring(position);
                literalLength += tail.Length;
                pattern.Append(Regex.Escape(tail));
                substringPattern.Append(Regex.Escape(tail));
                pattern.Append("$");

                var targetSegments = new List<TemplateSegment>();
                position = 0;
                foreach (Match match in PlaceholderPattern.Matches(targetTemplate))
                {
                    if (match.Index > position)
                    {
                        targetSegments.Add(new TemplateSegment
                        {
                            Literal = targetTemplate.Substring(position, match.Index - position),
                        });
                    }
                    targetSegments.Add(new TemplateSegment
                    {
                        Literal = null,
                        Placeholder = int.Parse(match.Groups[1].Value),
                    });
                    position = match.Index + match.Length;
                }
                if (position < targetTemplate.Length)
                {
                    targetSegments.Add(new TemplateSegment
                    {
                        Literal = targetTemplate.Substring(position),
                    });
                }

                return new TemplateEntry
                {
                    Pattern = new Regex(pattern.ToString(), RegexOptions.Compiled),
                    SubstringPattern = new Regex(substringPattern.ToString(), RegexOptions.Compiled),
                    FirstLiteral = firstLiteral ?? string.Empty,
                    StartsWithPlaceholder = placeholders.Count > 0 && placeholders[0].Index == 0,
                    RequiresExactGroups = ExactGroupTemplates.Contains(sourceTemplate),
                    GroupPlaceholders = groupPlaceholders.ToArray(),
                    Target = targetSegments.ToArray(),
                    LiteralLength = literalLength,
                };
            }
            catch (Exception exception)
            {
                Log.LogWarning($"模板键编译失败，已跳过：{sourceTemplate}（{exception.Message}）");
                return null;
            }
        }

        // 自动排障驱动用（Diagnostics.AutoProbeSwap）：与 F9 按键完全同路径的换语言触发。
        internal static void DebugToggleNow()
        {
            if (!_enabled.Value || !_mapsLoaded)
            {
                return;
            }
            _englishMode = !_englishMode;
            RunSwapPass(_englishMode ? _zh2en : _en2zh, _englishMode ? "调试切为英文" : "调试切为中文");
        }

        // 与 DebugToggleNow 相同但幂等：目标模式与当前相同时不切换。探针单元
        // 验证用——交换语义敏感的检查不应依赖进入时的模式（v2.6.4 实测：巡测
        // 协程交错把游戏停在英文态，假定中文进入的剥除继承检查必然误报）。
        internal static void DebugSetEnglishMode(bool english)
        {
            if (!_enabled.Value || !_mapsLoaded || _englishMode == english)
            {
                return;
            }
            _englishMode = english;
            RunSwapPass(_englishMode ? _zh2en : _en2zh, _englishMode ? "调试切为英文" : "调试切为中文");
        }

        // 供 QuoteSceneToggleKeyPatch 查询：本帧按下的是否正是语言切换键
        // （v2.7.3 开场语界面 F9 被"任意键继续"吞掉的修复配套）。
        internal static bool ToggleKeyPressedThisFrame()
        {
            return _mapsLoaded && _toggleKey.Value.IsDown();
        }

        internal static void Tick()
        {
            if (!_enabled.Value || !_mapsLoaded)
            {
                return;
            }
            if (_toggleKey.Value.IsDown())
            {
                // 打字机播放中禁止切换（用户明确要求）：交换会全量揭示文本，
                // 与逐字揭示状态交错容易出残句。
                if (IsTypewriterPlaying())
                {
                    Log.LogInfo("打字机进行中，稍候再按 F9。");
                    return;
                }
                _englishMode = !_englishMode;
                RunSwapPass(_englishMode ? _zh2en : _en2zh, _englishMode ? "切换为英文" : "切换为中文");
            }
        }

        // 打字机检测：找类型名 TravellingTypewriter 的对象，反射读 isPlaying
        // 属性，任一在播即视为打字中。结果缓存 0.2s（只在按键时查询，缓存
        // 主要防长按/连打时的重复全量枚举）。
        private const float TypewriterCheckInterval = 0.2f;
        private static float _typewriterCheckedAt = -1f;
        private static bool _typewriterPlaying;

        private static bool IsTypewriterPlaying()
        {
            if (Time.unscaledTime - _typewriterCheckedAt < TypewriterCheckInterval)
            {
                return _typewriterPlaying;
            }
            _typewriterCheckedAt = Time.unscaledTime;
            _typewriterPlaying = false;
            try
            {
                foreach (var obj in Resources.FindObjectsOfTypeAll<UnityEngine.Object>())
                {
                    if (obj == null || obj.GetType().Name != "TravellingTypewriter")
                    {
                        continue;
                    }
                    var property = obj.GetType().GetProperty(
                        "isPlaying",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (property != null && property.GetValue(obj) is bool playing && playing)
                    {
                        _typewriterPlaying = true;
                        break;
                    }
                }
            }
            catch (Exception)
            {
                // 检测失败按未在播处理，不阻塞切换。
            }
            return _typewriterPlaying;
        }

        // 换上的长文本超出底框时的处理。原生游戏显示时用
        // WrapTextAtSpecifiedMaxWidth 按组件 maxWidth（如 toast 520）往文本插 \n
        // 手动换行，底框随内容布局。我们换文本不触发这套，长英文单行溢出
        // （v2.2.0/2.2.4 实测）。v2.2.1 曾因此不动文本只开自动换行，但文本矩形
        // 随内容自动撑宽时并不触发，底框仍被超出。现改为：沿父链找游戏组件的
        // maxWidth 字段，调原生方法按它换行——会改写文本，但 Squashed 层
        // （折叠空白匹配）保证后续交换仍能命中，不再毒化状态机。
        // 原生方法按空格断词换行，对无空格的中文无效（只会尾部追加 \n），
        // 故仅含空格时才调它；中文走末尾的 enableWordWrapping 兜底
        // （TMP 可在 CJK 字符间断行，实测中文浮签换行正常）。
        // 短文本直接跳过（ForceMeshUpdate 有开销）。
        private const int MinOverflowCheckLength = 48;

        private static void RewrapIfOverflow(TMP_Text tmpText)
        {
            try
            {
                if (tmpText is not TextMeshProUGUI ugui ||
                    ugui.text.Length < MinOverflowCheckLength)
                {
                    return;
                }
                // WorldPopup（场景浮签）走自己的重排：米纸条按行重建
                // （RebuildLineStrips），由 RefreshVisibleWorldPopups 调游戏原生
                // ComposeDisplayText 按字符数断行处理，这里插 \n/开自动换行
                // 都会与纸条布局打架。
                if (ugui.GetComponentInParent<Travelling.Interactables.WorldPopup>() != null)
                {
                    return;
                }
                tmpText.ForceMeshUpdate();
                var preferred = tmpText.preferredWidth;
                var maxWidth = FindDeclaredWrapWidth(tmpText.transform);
                if (maxWidth > 0f && preferred > maxWidth + 0.5f &&
                    ugui.text.Contains(' '))
                {
                    Travelling.Utility.TravellingUtility.WrapTextAtSpecifiedMaxWidth(ugui, maxWidth);
                    return;
                }
                var width = tmpText.rectTransform.rect.width;
                if (width > 0f && preferred > width + 0.5f)
                {
                    tmpText.enableWordWrapping = true;
                }
            }
            catch (Exception)
            {
                // 失败保持原样，不影响交换本身。
            }
        }

        // 沿父链找第一个带 float 字段 maxWidth 的游戏组件（如 DismissableToastAlert
        // 的 maxWidth = 520），返回其值；找不到返回 0。
        private static float FindDeclaredWrapWidth(Transform start)
        {
            for (var current = start; current != null; current = current.parent)
            {
                Component[] components;
                try
                {
                    components = current.GetComponents<Component>();
                }
                catch (Exception)
                {
                    continue;
                }
                foreach (var component in components)
                {
                    if (component == null)
                    {
                        continue;
                    }
                    var type = component.GetType();
                    if (!type.FullName.StartsWith("Travelling", StringComparison.Ordinal))
                    {
                        continue;
                    }
                    var field = type.GetField(
                        "maxWidth",
                        BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (field != null && field.FieldType == typeof(float) &&
                        (float)field.GetValue(component) > 0f)
                    {
                        return (float)field.GetValue(component);
                    }
                }
            }
            return 0f;
        }

        // ---- WorldPopup（场景浮签）语言支持 ----        // 浮签显示流程：Display() → ComposeDisplayText() → ComposeWrapped(
        // segments, wrapAfterCharacters) 按字符数（默认 30）插 \n 断行，再由
        // ApplyPaperStripStyle → RebuildLineStrips 按 textInfo 逐行量宽重建米色
        // 纸条底。_authoredBaseText 在 Awake 捕获、是烘焙中文且永不更新，因此：
        //   1) Plugin 里的 ComposeWrapped Harmony 前缀在英文模式下把各段换回
        //      英文（SwapPopupSegment），游戏随后自己断行——新弹出的浮签直接
        //      显示正确语言、正确换行；
        //   2) F9 切换时已显示的浮签由 RefreshVisibleWorldPopups 重新 Compose 并
        //      重建纸条底（扫描链路只换了裸文本，纸条还是旧语言的行宽）。
        // 旧运行时架构（legacy/RuntimePatchPlugin.cs.txt）同款设计；烘焙时代
        // 漏带了它，导致 v2.2.4/2.2.5 浮签切英文后单行溢出纸条。

        // 供插件在运行时给 Footnote 注入英文原标签：作者手写 <link="Mansus">
        // 这类英文 id 的链接在中文界面依赖 alternativeLabels 备用通道解析；
        // 烘焙器对 Footnote 等类型的别名推送因 typetree 建模坑静默失效，
        // 改由运行时注入（v2.2.16）。
        internal static bool TryGetEnglishLabel(string label, out string english)
        {
            english = null;
            if (string.IsNullOrEmpty(label) || !_mapsLoaded)
            {
                return false;
            }
            return _zh2en.Exact.TryGetValue(label, out english);
        }

        // 带资产 id 的版本：先查标签保真表（真实英文标签），退回通用映射。
        internal static bool TryGetEnglishLabel(string assetId, string label, out string english)
        {
            if (TryGetFidelityEnglishLabel(assetId, label, out english))
            {
                return true;
            }
            return TryGetEnglishLabel(label, out english);
        }

        internal static bool IsEnglishMode => _englishMode;

        // 巡测电池用（Diagnostics.AutoProbeSoak）：判断一段剥净显示文本是否
        // 是本方向的精确键——CN 态下命中 en2zh 键 = 应换未换的英文残留。
        internal static bool DebugIsExactEnKey(string plain)
        {
            return _mapsLoaded && !string.IsNullOrEmpty(plain) &&
                   _en2zh.Exact.ContainsKey(plain);
        }

        // ComposeWrapped 补丁用：英文模式下把浮签组成段换回英文。只走精确与
        // 折叠空白两层——整段 authored 文本必定整串命中，子串级若只换出碎片
        // 反而混语。中文模式或未加载时原样返回（烘焙资产本身就是中文）。
        internal static string SwapPopupSegment(string segment)
        {
            if (!_enabled.Value || !_mapsLoaded || !_englishMode ||
                string.IsNullOrEmpty(segment))
            {
                return segment;
            }
            if (_zh2en.Exact.TryGetValue(segment, out var exact))
            {
                return SettleLinks(exact, segment, hideVisitedOverride: false);
            }
            if (_zh2en.Squashed.Count > 0 && HasWhitespace(segment) &&
                _zh2en.Squashed.TryGetValue(SquashWhitespace(segment), out var squashed))
            {
                return SettleLinks(squashed, segment, hideVisitedOverride: false);
            }
            return segment;
        }

        private static FieldInfo _popupPlaqueTextField;
        private static MethodInfo _popupApplyStyleMethod;
        private static bool _popupReflectionResolved;

        // F9 切换后重排所有正在显示的场景浮签：重新 Compose（语言由上面的
        // ComposeWrapped 补丁保证），再调私有的 ApplyPaperStripStyle 让游戏按
        // 新行宽重建米纸条。隐藏浮签不处理——下次 Display 自会重排。
        private static void RefreshVisibleWorldPopups()
        {
            try
            {
                var popupType = typeof(Travelling.Interactables.WorldPopup);
                if (!_popupReflectionResolved)
                {
                    _popupReflectionResolved = true;
                    _popupPlaqueTextField = popupType.GetField(
                        "plaqueText", BindingFlags.Instance | BindingFlags.NonPublic);
                    _popupApplyStyleMethod = popupType.GetMethod(
                        "ApplyPaperStripStyle", BindingFlags.Instance | BindingFlags.NonPublic);
                }
                if (_popupPlaqueTextField == null)
                {
                    return;
                }
                var refreshed = 0;
                foreach (var popup in Resources.FindObjectsOfTypeAll<Travelling.Interactables.WorldPopup>())
                {
                    if (popup == null || !popup.isActiveAndEnabled ||
                        !popup.gameObject.activeInHierarchy || !popup.IsVisible)
                    {
                        continue;
                    }
                    if (_popupPlaqueTextField.GetValue(popup) is not TMP_Text text)
                    {
                        continue;
                    }
                    try
                    {
                        text.SetText(popup.ComposeDisplayText() ?? string.Empty);
                        text.ForceMeshUpdate(false, false);
                        _popupApplyStyleMethod?.Invoke(popup, null);
                        if (text.rectTransform.parent is RectTransform parent)
                        {
                            UnityEngine.UI.LayoutRebuilder.ForceRebuildLayoutImmediate(parent);
                        }
                        refreshed++;
                    }
                    catch (Exception exception)
                    {
                        Log.LogWarning($"切换语言后重排场景浮签失败：{exception.Message}");
                    }
                }
                if (refreshed > 0)
                {
                    Log.LogInfo($"已按当前语言重排 {refreshed} 个可见场景浮签。");
                }
            }
            catch (Exception exception)
            {
                Log.LogWarning($"场景浮签重排扫描失败：{exception.Message}");
            }
        }

        // 折叠全部空白字符（空格/\n/\r/\t/全角空格等），供 Squashed 表查找。
        private static string SquashWhitespace(string value)
        {
            var builder = new StringBuilder(value.Length);
            foreach (var c in value)
            {
                if (!char.IsWhiteSpace(c))
                {
                    builder.Append(c);
                }
            }
            return builder.ToString();
        }

        private static bool HasWhitespace(string value)
        {
            foreach (var c in value)
            {
                if (char.IsWhiteSpace(c))
                {
                    return true;
                }
            }
            return false;
        }

        private static void OnSceneLoaded(Scene scene, LoadSceneMode mode)
        {
            // 新场景对象刚从磁盘载入，内容是中文；仅英文模式需要重跑。
            // 扫描幂等，直接全量重跑即可。
            if (_enabled.Value && _mapsLoaded && _englishMode)
            {
                RunSwapPass(_zh2en, $"场景 {scene.name} 载入（英文模式）");
            }
        }

        private static void RunSwapPass(DirectionMap map, string reason)
        {
            var stopwatch = Stopwatch.StartNew();
            var visited = 0;
            var counters = new SwapCounters();
            UnityEngine.Object[] all;
            try
            {
                all = Resources.FindObjectsOfTypeAll<UnityEngine.Object>();
            }
            catch (Exception exception)
            {
                Log.LogWarning($"语言切换扫描无法枚举对象（{reason}）：{exception}");
                return;
            }
            var seen = new HashSet<object>(new ReferenceComparer());
            // 缓存失效（v2.4.12 链接失效根治）：curator 的 ByLabel 字典与
            // _alternativeToPrimaryLabel 是**惰性构建+永久缓存**（首次链接解析时
            // 按当时语言建键），SwapDictionaryKeys 接触不到它们（字典字段是
            // System 命名空间，字段递归闸门不进）。交换后标签已换语言而缓存仍是
            // 建缓存时的语言：若缓存建于 CN 期，阶段二 SettleLinks 拿 EN 标签来
            // 查必然落空（别名通道只覆盖被注入英文别名的 Footnote，Passion/
            // Aspect 等直查 CN 键字典直接 miss）——链接被判失效打成青色/剥成
            // 裸文本（用户实测：切英文后 Passion/Aspect Pool 全变青链）。
            // 交换开始前统一失效缓存，此后任何解析都按目标语言重建。
            Plugin.RequestCuratorCacheRefresh();
            // 阶段零：ScriptablesCurator 优先。阶段一里经显示管线交换的字段
            // （字幕面板 m_accumulatedText 等）的 SettleLinks 着色依赖 curator
            // 字典键已是目标语言；阶段一内部遍历顺序不定，curator 靠后时历史
            // 文本链接被判失效、打成青色 BROKEN_LINK_COLOR（v2.1.12 实测：
            // 切回中文后"教会"链接变蓝）。
            foreach (var obj in all)
            {
                try
                {
                    if (obj == null || !IsScriptablesCurator(obj.GetType()))
                    {
                        continue;
                    }
                    counters.Exact += SwapObjectFields(obj, map, counters, seen);
                }
                catch (Exception)
                {
                    // 失败则由阶段一的常规遍历兜底。
                }
            }
            // 阶段一：非显示对象（数据字段、字典键重建）。必须先于阶段二——
            // TMP 文本的 SettleLinks 着色依赖 ScriptablesCurator 字典键已是
            // 当前语言，否则 DoesDetailableLabelExist 查不到、链接算成失效灰
            // 色（v2.1.8 单趟混跑实测：着色斑点取决于遍历顺序）。
            foreach (var obj in all)
            {
                // 对象可能在遍历期间被销毁，单个失败不影响整体。
                try
                {
                    if (obj == null)
                    {
                        continue;
                    }
                    visited++;
                    if (obj is TMP_Text || obj is UnityEngine.UI.Text)
                    {
                        continue; // 显示组件留给阶段二
                    }
                    if (IsGameDataType(obj.GetType()))
                    {
                        counters.Exact += SwapObjectFields(obj, map, counters, seen);
                    }
                }
                catch (Exception)
                {
                    // 单个对象失败静默跳过；结果计数里已体现整体进展。
                }
            }
            // 中文态下先复注入脚注英文别名，再进入显示阶段（v2.3.1）：阶段一
            // 的数据交换会把 alternativeLabels 里注入的英文别名一起换掉
            // （"Mansus"→"漫宿"），若等阶段二之后才复注入，显示交换中
            // SettleLinks 重算手写 <link="Mansus"> 的颜色时别名已不在，
            // 链接被判失效、打成青色 BROKEN_LINK_COLOR（v2.3.0 实测：EN→CN
            // 后牡鹿之门详情里的 受仪/太阳的居屋 变青）。英文模式下注入
            // 内部早退，此处调用无副作用。
            Plugin.RequestAlternativeLabelsInjection();
            // 阶段二：显示组件（TMP_Text / UI.Text）。
            foreach (var obj in all)
            {
                try
                {
                    if (obj == null)
                    {
                        continue;
                    }
                    if (obj is TMP_Text tmpText)
                    {
                        // 逐表面对齐"已读链接剥除"（字幕面板读配置；DetailableDisplay
                        // 系看各自 _respectFootnoteSubtlety；其余表面不剥除）。
                        _hideVisitedForCurrentSwap = ResolveHideVisitedForSurface(tmpText);
                        // 字幕面板显示 TMP 的内容 = 历史缓冲+当前行的逐行拼装
                        // （v2.7.3：通用流水线只能子串级损伤它——实测当前行被换成
                        // "movements。 三" 式混排）。与 accumulatedText 同走逐行交换。
                        if (IsSubtitlePanelSurface(tmpText))
                        {
                            var swappedLines = SwapBufferByLines(tmpText.text, map, counters);
                            if (!string.Equals(swappedLines, tmpText.text, StringComparison.Ordinal))
                            {
                                tmpText.text = swappedLines;
                                tmpText.maxVisibleCharacters = 99999;
                                tmpText.firstVisibleCharacter = 0;
                                RewrapIfOverflow(tmpText);
                            }
                            continue;
                        }
                        SwapDisplayText(map, tmpText.text, value =>
                        {
                            tmpText.text = value;
                            // 打字机用 maxVisibleCharacters 逐字揭示文本；换掉
                            // text 后原计数会对新文本造成截断/隐藏（v2.1.1 实测：
                            // 切换瞬间正在打字的历史缓冲只剩前 N 个可见字符）。
                            // 直接全量揭示，让打字机自然结束当前行。
                            tmpText.maxVisibleCharacters = 99999;
                            tmpText.firstVisibleCharacter = 0;
                            // 运行时换上的长文本（如英文）可能超出底框；
                            // 交给 RewrapIfOverflow 按游戏原生方式补换行
                            // （详见该方法注释；Squashed 匹配保证安全）。
                            RewrapIfOverflow(tmpText);
                        }, counters);
                    }
                    else if (obj is UnityEngine.UI.Text uiText)
                    {
                        // 旧式 UI，本游戏可能没有；防御性处理。
                        _hideVisitedForCurrentSwap = false;
                        SwapDisplayText(map, uiText.text, value => uiText.text = value, counters);
                    }
                }
                catch (Exception)
                {
                    // 单个对象失败静默跳过；结果计数里已体现整体进展。
                }
            }
            stopwatch.Stop();
            var dictionaryNote = counters.DictionaryKeyConflict > 0
                ? $"，字典键冲突跳过 {counters.DictionaryKeyConflict} 条"
                : string.Empty;
            Log.LogInfo(
                $"语言切换扫描完成（{reason}）：访问对象 {visited} 个，耗时 {stopwatch.ElapsedMilliseconds} ms；" +
                $"替换：精确 {counters.Exact} 处（去标签 {counters.TaglessExact}），" +
                $"模板 {counters.Template} 处（子串模板 {counters.TemplateSubstring}），" +
                $"文本段 {counters.SegmentExact} 处，子串 {counters.Substring} 段，" +
                $"字典键 {counters.DictionaryKey} 条{dictionaryNote}。");
            // Lua VM 的 actor 快照同步（新行说话人名的语言源）。
            SyncLuaActorDisplayNames();
            // 可见场景浮签（WorldPopup）重排：纸条底按行重建，必须让游戏自己
            // 重 Compose + 断行，不能靠扫描链路换裸文本（v2.2.6 修复）。
            RefreshVisibleWorldPopups();
            // 响应菜单整备（v2.7.1，l.8 选项 F9 回归根治）：选项文本是运行时
            // 拼装串，先把 formattedText 逐件换好，再让按钮自己重排——详见方法注释。
            RebuildActiveResponseMenu(map);
            // 日志详情窗刷新（v2.7.3）：详情第三段是 "<uppercase>状态标签</uppercase>
            // -- 状态描述" 拼装串，扫描链路换不全；直接让日志按当前语言重 DisplayDetailFor。
            RefreshOpenJournalDetail();
            // 交换可能改写了脚注 alternativeLabels 的内容；中文态下复注入英文别名
            // （手写 <link="英文"> 的解析通道，v2.2.16）。
            Plugin.RequestAlternativeLabelsInjection();
            // 捏人链接白名单的 label 缓存同样按建缓存时的语言失效（v2.5.0 实测：
            // 捏人 tooltip 链接 F9 后剥成裸文本）。
            Plugin.ResetCharGenLinkWhitelistCache();
            // 陈旧检测（仅 DebugLog）：交换结束后再跑一趟只读遍历，凡仍匹配
            // 本方向映射键（=本应被换掉却没换）的字符串值都报出来，用于定位
            // 运行态缓存的旧语言字段。
            if (_debugLog.Value)
            {
                ReportStaleFields(map, reason);
            }
        }

        // 历史缓冲逐行交换。缓冲行的真实包装形态（v2.7.3 按 l.31 用户现场
        // 取证重写——旧枚举式前导标签正则不认 <font=..> 与 <sprite="inline"
        // name="star"> 这类命名/双属性标签，整行因此掉进子串级，被术语误伤成
        // "你可真Interesting.Perhaps该Consideration…"）：
        //   A 短对话行：<font=..><b><i><sprite=N>名字 — 正文</color>
        //   B 长对话行：<font=..><b><i><sprite=N>名字</i></b></font> — <color=..>正文</color>
        //   C 系统行：<color=..><i><sprite="inline" name="star"> 模板文本</i></color>
        // 逐行拆成 前导开标签段+说话人前缀+正文+结尾闭标签段：名字整串精确交换
        // （单字名"我"够不到子串两字阈值），正文单独走完整流水线（折叠精确因此
        // 能命中整条目录译文，含 [[链接]]），包装标签原样保留——行级颜色存活。
        // 名字段允许空格（"The elder Janvier"）与夹缝闭标签（B 形）；长度上限
        // 防失控。正文换不动时整行退回通用流水线兜底。
        private static readonly Regex LeadingTagsPattern = new Regex(
            @"^((?:<[a-zA-Z][^>]*>)+)", RegexOptions.Compiled);
        private static readonly Regex TrailingTagsPattern = new Regex(
            @"((?:</[a-zA-Z]+>)+)$", RegexOptions.Compiled);
        private static readonly Regex AnyTagPattern = new Regex(
            @"<[^>]+>", RegexOptions.Compiled);

        // 在 core 里找说话人分隔符 " — "：取第一个出现位置，要求其前的纯文本
        // （剥标签）长度 1..40 且不含 '—'。找不到/超长返回 -1（调用方整行处理）。
        private static int FindSpeakerSeparator(string core)
        {
            var index = core.IndexOf(" — ", StringComparison.Ordinal);
            if (index <= 0)
            {
                return -1;
            }
            var plainName = AnyTagPattern.Replace(core.Substring(0, index), string.Empty);
            if (plainName.Length == 0 || plainName.Length > 40 || plainName.Contains('—'))
            {
                return -1;
            }
            return index;
        }

        private static string SwapBufferByLines(string value, DirectionMap map, SwapCounters counters)
        {
            if (string.IsNullOrEmpty(value))
            {
                return value;
            }
            var lines = value.Split('\n');
            var changed = false;
            for (var i = 0; i < lines.Length; i++)
            {
                var line = lines[i];
                if (string.IsNullOrEmpty(line))
                {
                    continue;
                }
                // 拆包装标签：前导开标签段与结尾闭标签段原样保留，不参与交换。
                var lead = LeadingTagsPattern.Match(line).Groups[1].Value;
                var trail = TrailingTagsPattern.Match(line).Groups[1].Value;
                var core = line.Substring(lead.Length, line.Length - lead.Length - trail.Length);

                string swappedCore = null;
                var separator = FindSpeakerSeparator(core);
                if (separator > 0)
                {
                    // "名字 — 正文"：名字段单独精确交换（段内夹缝标签原样），
                    // 避免它与正文纠缠进流水线。名字不是独立映射键就原样保留；
                    // 正文换不动时整行退回通用流水线兜底。
                    var nameRegion = core.Substring(0, separator);
                    var namePlain = AnyTagPattern.Replace(nameRegion, string.Empty);
                    var nameSwapped = nameRegion;
                    if (map.Exact.TryGetValue(namePlain, out var swappedName))
                    {
                        nameSwapped = nameRegion.Replace(namePlain, swappedName);
                    }
                    var rest = core.Substring(separator + 3);
                    // 正文段自身的前导开标签（<color=..> 等）同样原位保留——
                    // Tier 1.5 去标签精确只回裸值，不剥会丢行级颜色（v2.7.3
                    // 夹具实测：" — <color=..>正文" 换完 color 开标签没了）。
                    var restLead = LeadingTagsPattern.Match(rest).Groups[1].Value;
                    var restCore = rest.Substring(restLead.Length);
                    if (string.IsNullOrEmpty(restCore))
                    {
                        swappedCore = nameSwapped + " — " + restLead;
                    }
                    else if (TrySwapDisplayText(map, restCore, counters, 1, out var pipelineRest))
                    {
                        swappedCore = nameSwapped + " — " + restLead + pipelineRest;
                    }
                }
                if (swappedCore == null)
                {
                    swappedCore = core;
                    if (TrySwapDisplayText(map, core, counters, 1, out var pipelineCore))
                    {
                        swappedCore = pipelineCore;
                    }
                }
                var rebuilt = lead + swappedCore + trail;
                if (rebuilt != line)
                {
                    lines[i] = rebuilt;
                    changed = true;
                }
            }
            return changed ? string.Join("\n", lines) : value;
        }

        // 陈旧字段检测：只读，不写。与交换同构的反射遍历（含 Field 白名单
        // 路径与 string 键字典），凡是仍匹配本方向精确表键的值记录：
        // 对象类型全名、字段路径（. 连接）、值前 80 字符。最多报 30 条。
        private const int MaxStaleReports = 30;

        private sealed class StaleReportContext
        {
            internal int Total;
            internal int Reported;
        }

        private static void ReportStaleFields(DirectionMap map, string reason)
        {
            var stopwatch = Stopwatch.StartNew();
            UnityEngine.Object[] all;
            try
            {
                all = Resources.FindObjectsOfTypeAll<UnityEngine.Object>();
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[LanguageSwap] 陈旧检测无法枚举对象（{reason}）：{exception}");
                return;
            }
            var context = new StaleReportContext();
            var seen = new HashSet<object>(new ReferenceComparer());
            foreach (var obj in all)
            {
                try
                {
                    if (obj == null || obj is TMP_Text || obj is UnityEngine.UI.Text ||
                        !IsGameDataType(obj.GetType()))
                    {
                        continue;
                    }
                    InspectStaleFields(obj, map.Exact, seen, obj.GetType().FullName, context);
                }
                catch (Exception)
                {
                    // 单个对象失败静默跳过。
                }
            }
            stopwatch.Stop();
            Log.LogWarning(
                $"[LanguageSwap] 陈旧字段检测完成（{reason}）：共 {context.Total} 处仍匹配本方向键" +
                $"（已列出前 {context.Reported} 条，耗时 {stopwatch.ElapsedMilliseconds} ms）。");
        }

        private static void InspectStaleFields(
            object instance, Dictionary<string, string> forward, HashSet<object> seen,
            string path, StaleReportContext context)
        {
            if (instance == null || instance is string)
            {
                return;
            }
            var type = instance.GetType();
            if (!type.IsClass || typeof(Delegate).IsAssignableFrom(type) || !seen.Add(instance))
            {
                return;
            }
            if (type.FullName == DialogueFieldTypeName)
            {
                InspectStaleDialogueField(instance, forward, path, context);
                return;
            }
            if (instance is IDictionary dictionary)
            {
                try
                {
                    foreach (DictionaryEntry entry in dictionary)
                    {
                        if (entry.Key is string key && forward.ContainsKey(key))
                        {
                            ReportStale(context, type.FullName, path + "[key]", key);
                        }
                        if (entry.Value is string stringValue)
                        {
                            if (forward.ContainsKey(stringValue))
                            {
                                ReportStale(context, type.FullName, path + "[value]", stringValue);
                            }
                        }
                        else if (entry.Value != null &&
                                 !(entry.Value is UnityEngine.Object))
                        {
                            InspectStaleFields(
                                entry.Value, forward, seen, path + "[" + entry.Key + "]", context);
                        }
                    }
                }
                catch (Exception)
                {
                    // 枚举失败整本跳过。
                }
                return;
            }
            for (var current = type; current != null && current != typeof(object); current = current.BaseType)
            {
                FieldInfo[] fields;
                try
                {
                    fields = current.GetFields(
                        BindingFlags.Instance | BindingFlags.Public |
                        BindingFlags.NonPublic | BindingFlags.DeclaredOnly);
                }
                catch (Exception)
                {
                    continue;
                }
                foreach (var field in fields)
                {
                    object value;
                    try
                    {
                        value = field.GetValue(instance);
                    }
                    catch (Exception)
                    {
                        continue;
                    }
                    if (value == null)
                    {
                        continue;
                    }
                    var fieldPath = path + "." + field.Name;
                    var fieldType = field.FieldType;
                    if (fieldType == typeof(string))
                    {
                        if (forward.ContainsKey((string)value))
                        {
                            ReportStale(context, type.FullName, fieldPath, (string)value);
                        }
                    }
                    else if (typeof(UnityEngine.Object).IsAssignableFrom(fieldType) ||
                             typeof(Delegate).IsAssignableFrom(fieldType))
                    {
                        // Unity 对象引用与委托一律不进入。
                    }
                    else if (value is IList list)
                    {
                        for (var i = 0; i < list.Count; i++)
                        {
                            object element;
                            try
                            {
                                element = list[i];
                            }
                            catch (Exception)
                            {
                                continue;
                            }
                            if (element is string elementString)
                            {
                                if (forward.ContainsKey(elementString))
                                {
                                    ReportStale(
                                        context, type.FullName, fieldPath + "[" + i + "]", elementString);
                                }
                            }
                            else if (element != null && IsGameDataType(element.GetType()))
                            {
                                InspectStaleFields(
                                    element, forward, seen, fieldPath + "[" + i + "]", context);
                            }
                        }
                    }
                    else if (fieldType.IsClass && IsGameDataType(fieldType))
                    {
                        // 与交换路径同款闸门：只递归游戏命名空间，不进 InputSystem 等
                        // 引擎内部类型（只读巡检不需要，且避免噪音报告）。
                        InspectStaleFields(value, forward, seen, fieldPath, context);
                    }
                }
            }
        }

        private static void InspectStaleDialogueField(
            object fieldInstance, Dictionary<string, string> forward, string path, StaleReportContext context)
        {
            var type = fieldInstance.GetType();
            try
            {
                var titleField = type.GetField(
                    "title", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                var valueField = type.GetField(
                    "value", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                if (titleField == null || valueField == null || valueField.FieldType != typeof(string))
                {
                    return;
                }
                var title = titleField.GetValue(fieldInstance) as string;
                var fieldValue = valueField.GetValue(fieldInstance) as string;
                if (string.IsNullOrEmpty(title) || string.IsNullOrEmpty(fieldValue))
                {
                    return;
                }
                if (!DialogueTextFieldTitles.Contains(title) &&
                    !SkillCheckDescriptionTitlePattern.IsMatch(title))
                {
                    return;
                }
                if (forward.ContainsKey(fieldValue))
                {
                    ReportStale(context, type.FullName, path + ".value(" + title + ")", fieldValue);
                }
            }
            catch (Exception)
            {
                // 读取失败跳过。
            }
        }

        private static void ReportStale(
            StaleReportContext context, string typeName, string path, string value)
        {
            context.Total++;
            if (context.Reported >= MaxStaleReports)
            {
                return;
            }
            context.Reported++;
            Log.LogWarning(
                $"[LanguageSwap] 陈旧文本：{typeName} 路径 {path} = \"{TruncateForLog(value, 80)}\"");
        }

        // 显示组件的分级流水线交换；任何一级有产出即写回。
        private static void SwapDisplayText(
            DirectionMap map, string current, Action<string> setter, SwapCounters counters)
        {
            // 排障埋点（v2.4.10）：跟踪含宁娜的文本在交换中的层级归宿。
            if (_debugLog.Value && current != null && current.Contains("宁娜"))
            {
                var hit = TrySwapDisplayText(map, current, counters, 0, out var probeSwapped);
                Log.LogInfo(
                    $"[LanguageSwap] 宁娜文本交换：命中={hit} 原文={TruncateForLog(current, 160)}");
                if (hit)
                {
                    setter(probeSwapped);
                }
                return;
            }
            if (!string.IsNullOrEmpty(current) &&
                TrySwapDisplayText(map, current, counters, 0, out var swapped))
            {
                if (_debugLog.Value && IsMixedLanguage(swapped))
                {
                    Log.LogWarning(
                        $"[LanguageSwap] 交换后仍混语：{TruncateForLog(current, 300)}");
                }
                setter(swapped);
            }
        }

        private static bool TrySwapDisplayText(
            DirectionMap map, string text, SwapCounters counters, int depth, out string swapped)
        {
            // Tier 1：整串精确匹配。
            if (map.Exact.TryGetValue(text, out var exactValue))
            {
                swapped = SettleLinks(exactValue, text);
                counters.Exact++;
                return true;
            }
            // Tier 1.5：去标签精确（显示态带 <link>/<color> 装饰的折叠键文本）。
            if (text.IndexOf('<') >= 0)
            {
                var plainAll = StripTags(text);
                if (plainAll.Length != text.Length &&
                    map.Exact.TryGetValue(plainAll, out var taglessValue))
                {
                    swapped = SettleLinks(taglessValue, text);
                    counters.TaglessExact++;
                    return true;
                }
            }
            // Tier 1.6：折叠全部空白后精确匹配。游戏显示时给长文本插入手动换行
            //（WrapTextAtSpecifiedMaxWidth），显示态与映射键只差空白字符；折叠
            // 两端空白后查 Squashed 表。放在子串级之前——子串级只换短词会造成
            // 中英混杂。
            if (map.Squashed.Count > 0 && HasWhitespace(text) &&
                map.Squashed.TryGetValue(SquashWhitespace(text), out var squashedValue))
            {
                swapped = SettleLinks(squashedValue, text);
                counters.TaglessExact++;
                return true;
            }
            // Tier 1.7：链接还原精确。显示态里 [[X]] 已被解析成
            // <link="id"><color=…>X</color></link>；把每个 link 段还原成
            // [[X]]（仅剥链接段内部的装饰标签），**其余标签原样保留**——
            // 原始键里本就有 <i>/<b> 等排版标签（如教程泡的题辞斜体），
            // 一并剥掉会让精确/折叠两层都失配（v2.4.12 实测"工具提示与
            // 脚注"泡 EN→CN 掉到子串级：正文英文、链接名中文混排）。
            // 提示泡（ToastStackView.Enqueue 在 Show 时一次性组合消息）等
            // 长期停留的表面在打开状态切语言时靠这层整体命中。
            if (text.IndexOf("<link=", StringComparison.Ordinal) >= 0)
            {
                var restoredTagged = LinkRestorePattern.Replace(
                    text, match => "[[" + StripTags(match.Groups[1].Value) + "]]");
                if (restoredTagged != text)
                {
                    // 依次尝试：保标签精确 → 全剥标签精确 → 保标签折叠 → 全剥折叠。
                    // 保标签优先：原键常含 <i>/<b> 排版标签，忠实还原才能命中
                    // 带格式的键；全剥兜底：覆盖显示态被额外套色/套标签的表面。
                    var restoredPlain = StripTags(restoredTagged);
                    if (map.Exact.TryGetValue(restoredTagged, out var restoredValue) ||
                        (restoredPlain != restoredTagged &&
                         map.Exact.TryGetValue(restoredPlain, out restoredValue)))
                    {
                        swapped = SettleLinks(restoredValue, text);
                        counters.TaglessExact++;
                        return true;
                    }
                    // 游戏显示时给长文本插入手动换行：还原链接后再折叠空白查
                    // Squashed 表（v2.4.12 实测：提示泡长文 EN→CN 因换行差异
                    // 精确失配，掉到子串级只剩链接名被换）。
                    if (map.Squashed.Count > 0)
                    {
                        if (HasWhitespace(restoredTagged) &&
                            map.Squashed.TryGetValue(SquashWhitespace(restoredTagged), out var restoredSquashed))
                        {
                            swapped = SettleLinks(restoredSquashed, text);
                            counters.TaglessExact++;
                            return true;
                        }
                        if (restoredPlain != restoredTagged && HasWhitespace(restoredPlain) &&
                            map.Squashed.TryGetValue(SquashWhitespace(restoredPlain), out restoredSquashed))
                        {
                            swapped = SettleLinks(restoredSquashed, text);
                            counters.TaglessExact++;
                            return true;
                        }
                    }
                }
            }
            // Tier 2：模板匹配（运行时拼装串：说话人格式行、技能名列表实例化等）。
            if (depth < MaxSwapDepth)
            {
                foreach (var template in map.Templates)
                {
                    if (!template.StartsWithPlaceholder && template.FirstLiteral.Length > 0 &&
                        !text.StartsWith(template.FirstLiteral, StringComparison.Ordinal))
                    {
                        continue;
                    }
                    Match match;
                    try
                    {
                        match = template.Pattern.Match(text);
                    }
                    catch (Exception)
                    {
                        continue;
                    }
                    if (!match.Success)
                    {
                        continue;
                    }
                    if (template.RequiresExactGroups && !TemplateGroupsAllExact(map, match))
                    {
                        continue;
                    }
                    swapped = SettleLinks(AssembleTemplateSwap(map, template, match, counters, depth), text);
                    counters.Template++;
                    return true;
                }
            }
            // Tier 3.5 + Tier 3：纯文本扫描（部分替换，标签原样保留）——先收集
            // 模板子串区间（合成提示行 "Gained {0} ({1})" 等运行时拼装串），
            // 再做键桶扫描并跳过模板区间覆盖的位置（模板区间优先）。
            // 必须先于 Tier 2.5：含链接名的整句折叠键要优先整体命中，
            // 否则人名先被段级换掉，长键就再也匹配不上（v2.1.3 实测：
            // "我在找一个叫宁娜·拉格斯的女人。"只剩名字被换成英文）。
            var templateSubstringBefore = counters.TemplateSubstring;
            var afterSubstrings = SwapPlainTextSubstrings(
                map, text, counters, depth, out var substringCount);
            counters.Substring += substringCount;
            var templateSubstringCount = counters.TemplateSubstring - templateSubstringBefore;
            // Tier 2.5：文本段精确（部分替换，不短路），在 Tier 3 输出上收尾
            // （覆盖说话人名等短段，如 "我" -> "Me"）。
            var result = SwapTextSegmentsExact(map, afterSubstrings, out var segmentCount);
            counters.SegmentExact += segmentCount;
            if (segmentCount == 0 && substringCount == 0 && templateSubstringCount == 0)
            {
                swapped = null;
                return false;
            }
            if (_debugLog.Value && depth == 0)
            {
                Log.LogInfo(
                    $"[LanguageSwap] 部分替换（3.5:{templateSubstringCount} " +
                    $"3:{substringCount} 2.5:{segmentCount}）：{TruncateForLog(text, 200)}");
            }
            swapped = result;
            return true;
        }

        private static string TruncateForLog(string text, int limit) =>
            text.Length <= limit ? text : text.Substring(0, limit) + "…";

        // 混语判定（调试日志用）：剥掉标签后同时含 CJK 字符与拉丁字母。
        private static bool IsMixedLanguage(string text)
        {
            var plain = StripTags(text);
            var hasCjk = false;
            var hasLatin = false;
            foreach (var c in plain)
            {
                if (c >= '一' && c <= '鿿') // CJK 统一表意文字基本区
                {
                    hasCjk = true;
                }
                else if (IsLatinLetter(c))
                {
                    hasLatin = true;
                }
                if (hasCjk && hasLatin)
                {
                    return true;
                }
            }
            return false;
        }

        // RequiresExactGroups 模板的捕获组校验：每个组（剥标签后）都必须是
        // 本方向的独立映射键，否则该匹配是"恰好长得像模板"的普通文本。
        // Tier 2（整串）与 Tier 3.5（子串）共用。
        private static bool TemplateGroupsAllExact(DirectionMap map, Match match)
        {
            for (var group = 1; group < match.Groups.Count; group++)
            {
                var captured = match.Groups[group].Value;
                var plainCaptured = StripTags(captured);
                if (!map.Exact.ContainsKey(captured) &&
                    !map.Exact.ContainsKey(plainCaptured))
                {
                    return false;
                }
            }
            return true;
        }

        // 模板命中后的组装：每个捕获组递归走完整流水线（组内常是技能名列表，
        // 会落到 Tier 3 把技能名逐个换掉），再按目标模板切片手工拼接。
        // Tier 2（整串 fullmatch）与 Tier 3.5（纯文本子串匹配）共用。
        private static string AssembleTemplateSwap(
            DirectionMap map, TemplateEntry template, Match match, SwapCounters counters, int depth)
        {
            var swappedGroups = new Dictionary<int, string>();
            for (var group = 1; group < match.Groups.Count; group++)
            {
                var placeholder = template.GroupPlaceholders[group - 1];
                var captured = match.Groups[group].Value;
                // 捕获组边界空白原样保留、不参与递归交换（v2.7.3：行首空格被
                // {0} 捕获后随递归丢失——"✧ 弗雷泽…" 换完空格没了）。
                var leadWs = 0;
                while (leadWs < captured.Length && char.IsWhiteSpace(captured[leadWs]))
                {
                    leadWs++;
                }
                var trailWs = 0;
                while (trailWs < captured.Length - leadWs &&
                       char.IsWhiteSpace(captured[captured.Length - 1 - trailWs]))
                {
                    trailWs++;
                }
                var coreCapture = captured.Substring(leadWs, captured.Length - leadWs - trailWs);
                if (coreCapture.Length == 0)
                {
                    swappedGroups[placeholder] = captured;
                    continue;
                }
                string swappedCore;
                // 性相池恢复行的占位组是“1 启, 1 灯”。单字 CJK 术语为防
                // 子串误伤不进 Tier 3，因此在有数量边界的列表中按完整 label
                // 查 Exact，才能在 EN 态恢复 Knock/Lantern。
                if (TrySwapCountedLabelList(map, coreCapture, out var countedGroup))
                {
                    swappedCore = countedGroup;
                }
                else if (TrySwapDisplayText(map, coreCapture, counters, depth + 1, out var swappedGroup))
                {
                    swappedCore = swappedGroup;
                }
                else if (TrySwapNumberWords(coreCapture, out var numberWords))
                {
                    swappedCore = numberWords;
                }
                else
                {
                    swappedCore = coreCapture;
                }
                swappedGroups[placeholder] =
                    captured.Substring(0, leadWs) + swappedCore +
                    captured.Substring(captured.Length - trailWs);
            }
            var builder = new StringBuilder(match.Length);
            foreach (var segment in template.Target)
            {
                if (segment.Literal != null)
                {
                    builder.Append(segment.Literal);
                }
                else if (swappedGroups.TryGetValue(segment.Placeholder, out var groupValue))
                {
                    builder.Append(groupValue);
                }
                // 目标模板引用了源模板没有的占位符序号：丢弃该段。
            }
            return builder.ToString();
        }

        private static bool TrySwapCountedLabelList(
            DirectionMap map, string text, out string swapped)
        {
            swapped = null;
            if (string.IsNullOrEmpty(text))
            {
                return false;
            }
            var builder = new StringBuilder(text.Length + 16);
            var start = 0;
            var replacements = 0;
            while (start < text.Length)
            {
                var separator = text.IndexOfAny(new[] { ',', '，' }, start);
                var end = separator >= 0 ? separator : text.Length;
                var part = text.Substring(start, end - start);
                var match = Regex.Match(part, @"^(\s*\d+\s+)(.+?)(\s*)$");
                if (!match.Success ||
                    !map.Exact.TryGetValue(match.Groups[2].Value, out var mappedLabel))
                {
                    return false;
                }
                builder.Append(match.Groups[1].Value);
                builder.Append(SettleLinks(mappedLabel, match.Groups[2].Value));
                builder.Append(match.Groups[3].Value);
                replacements++;
                if (separator < 0)
                {
                    break;
                }
                builder.Append(text[separator]);
                start = separator + 1;
            }
            if (replacements == 0)
            {
                return false;
            }
            swapped = builder.ToString();
            return true;
        }

        // Tier 2.5：把文本按 <...> 标签切成 标签/文本 交替段，文本段整段查映射。
        private static string SwapTextSegmentsExact(
            DirectionMap map, string text, out int replacedSegments)
        {
            replacedSegments = 0;
            StringBuilder builder = null;
            var index = 0;
            var segmentStart = 0;
            while (index <= text.Length)
            {
                var atTag = false;
                var tagEnd = -1;
                if (index < text.Length && text[index] == '<')
                {
                    tagEnd = text.IndexOf('>', index + 1);
                    atTag = tagEnd > index;
                }
                if (index == text.Length || atTag)
                {
                    // 文本段 [segmentStart, index) 结束，整段查映射。
                    if (index > segmentStart)
                    {
                        var segment = text.Substring(segmentStart, index - segmentStart);
                        if (map.Exact.TryGetValue(segment, out var segmentValue))
                        {
                            if (builder == null)
                            {
                                builder = new StringBuilder(text.Length + 16);
                                builder.Append(text, 0, segmentStart);
                            }
                            builder.Append(SettleLinks(segmentValue, segment));
                            replacedSegments++;
                        }
                        else if (builder != null)
                        {
                            builder.Append(text, segmentStart, index - segmentStart);
                        }
                    }
                    if (atTag)
                    {
                        builder?.Append(text, index, tagEnd - index + 1);
                        index = tagEnd + 1;
                        segmentStart = index;
                        continue;
                    }
                    break;
                }
                index++;
            }
            return replacedSegments == 0 ? text : builder.ToString();
        }

        // Tier 3.5 + Tier 3：先构建纯文本 + 纯文本字符→原始串索引映射（标签
        // 字符不进纯文本）。Tier 3.5 用去锚模板正则在纯文本上收集合成串区间
        // （"Gained {0} ({1})" 这类运行时拼装提示行），捕获组递归走完整流水线、
        // 按目标模板拼接；Tier 3 键桶扫描跳过模板区间覆盖的位置（模板区间优先，
        // 避免键扫描把模板组内文本再换一遍）。所有区间换算回原始串坐标后一趟
        // 拼装输出，未命中部分照抄原始串（标签原样保留）。
        private static string SwapPlainTextSubstrings(
            DirectionMap map, string text, SwapCounters counters, int depth, out int replacedSegments)
        {
            replacedSegments = 0;
            if (map.SubstringBuckets.Count == 0 && map.Templates.Count == 0)
            {
                return text;
            }
            var plain = new StringBuilder(text.Length);
            var indexMap = new List<int>(text.Length);
            var index = 0;
            while (index < text.Length)
            {
                if (text[index] == '<')
                {
                    var close = text.IndexOf('>', index + 1);
                    if (close > index)
                    {
                        index = close + 1;
                        continue;
                    }
                }
                indexMap.Add(index);
                plain.Append(text[index]);
                index++;
            }
            if (indexMap.Count == 0)
            {
                return text;
            }
            var plainText = plain.ToString();

            // Tier 3.5：模板子串区间（纯文本坐标）。模板已按字面部分长度降序，
            // 先收集的先生效；重叠的后命中者丢弃。收集完按起点升序排序
            // （区间与替换值作为一对排序，数量极少，开销可忽略）。
            List<KeyValuePair<int[], string>> templateSpans = null;
            if (depth < MaxSwapDepth)
            {
                foreach (var template in map.Templates)
                {
                    if (template.FirstLiteral.Length > 0 &&
                        plainText.IndexOf(template.FirstLiteral, StringComparison.Ordinal) < 0)
                    {
                        continue;
                    }
                    MatchCollection matches;
                    try
                    {
                        matches = template.SubstringPattern.Matches(plainText);
                    }
                    catch (Exception)
                    {
                        continue;
                    }
                    foreach (Match match in matches)
                    {
                        if (!match.Success || match.Length == 0)
                        {
                            continue;
                        }
                        // 前置占位符模板在子串级只允许贴行首（纯文本坐标 0）的
                        // 匹配："{0} in a {1}" 这类模板去锚扫描会把普通句子当作
                        // 模板实例重排（v2.6.2 双角斧选项实测）；但 "{0} 赞同
                        // （+{1}）" 这类系统行带 ✧/精灵前缀，Tier 2 整串永远
                        // 失配，全靠行首子串匹配整行交换（v2.6.3 赞同行半换
                        // 实测）。RequiresExactGroups 在子串级同样生效——
                        // "Not {0}" 不能把任何以 Not 开头的长段吞成 "非 …"。
                        if (template.StartsWithPlaceholder && match.Index != 0)
                        {
                            continue;
                        }
                        if (template.RequiresExactGroups && !TemplateGroupsAllExact(map, match))
                        {
                            continue;
                        }
                        var spanStart = match.Index;
                        var spanEnd = match.Index + match.Length;
                        if (OverlapsTemplateSpan(templateSpans, spanStart, spanEnd))
                        {
                            continue;
                        }
                        if (templateSpans == null)
                        {
                            templateSpans = new List<KeyValuePair<int[], string>>();
                        }
                        templateSpans.Add(new KeyValuePair<int[], string>(
                            new[] { spanStart, spanEnd },
                            SettleLinks(
                                AssembleTemplateSwap(map, template, match, counters, depth),
                                text.Substring(
                                    indexMap[spanStart],
                                    indexMap[spanEnd - 1] + 1 - indexMap[spanStart]))));
                        counters.TemplateSubstring++;
                    }
                }
                templateSpans?.Sort((a, b) => a.Key[0].CompareTo(b.Key[0]));
            }

            // Tier 3：键桶扫描，跳过模板区间覆盖的位置。
            List<int[]> keySpans = null;
            List<string> keyValues = null;
            var position = 0;
            var coveredIndex = 0;
            while (position < plainText.Length)
            {
                if (templateSpans != null)
                {
                    while (coveredIndex < templateSpans.Count &&
                           templateSpans[coveredIndex].Key[1] <= position)
                    {
                        coveredIndex++;
                    }
                    if (coveredIndex < templateSpans.Count &&
                        templateSpans[coveredIndex].Key[0] <= position &&
                        position < templateSpans[coveredIndex].Key[1])
                    {
                        position = templateSpans[coveredIndex].Key[1];
                        continue;
                    }
                }
                if (map.SubstringBuckets.TryGetValue(plainText[position], out var bucket))
                {
                    var matched = false;
                    foreach (var candidate in bucket)
                    {
                        var key = candidate.Key;
                        if (key.Length > plainText.Length - position ||
                            string.CompareOrdinal(plainText, position, key, 0, key.Length) != 0)
                        {
                            continue;
                        }
                        if (candidate.NeedsWordBoundary)
                        {
                            if (position > 0 && IsLatinLetter(plainText[position - 1]))
                            {
                                continue;
                            }
                            var end = position + key.Length;
                            if (end < plainText.Length && IsLatinLetter(plainText[end]))
                            {
                                continue;
                            }
                        }
                        // 原位替换即可：命中区段若是链接内层文字，旧包装器保留
                        // 也没问题（id 仍是中文别名，烘焙时已写入 alternativeLabels，
                        // 悬停照样解析）；替换值里的 [[Y]] 由 Settle 统一原生装饰。
                        if (keySpans == null)
                        {
                            keySpans = new List<int[]>();
                            keyValues = new List<string>();
                        }
                        keySpans.Add(new[] { position, position + key.Length });
                        keyValues.Add(SettleLinks(
                            candidate.Value,
                            text.Substring(
                                indexMap[position],
                                indexMap[position + key.Length - 1] + 1 - indexMap[position])));
                        position += key.Length;
                        replacedSegments++;
                        matched = true;
                        break; // 桶内已按键长降序，首个命中即最长匹配
                    }
                    if (matched)
                    {
                        continue;
                    }
                }
                position++;
            }
            var templateCount = templateSpans?.Count ?? 0;
            var keyCount = keySpans?.Count ?? 0;
            if (templateCount == 0 && keyCount == 0)
            {
                return text;
            }
            // 合并两类区间（各自按起点升序、互不重叠），一趟拼装。区间间隙按
            // 原始串坐标照抄——v2.3.3 实测旧实现按纯文本坐标取间隙，会把紧贴
            // 替换区间首尾的标签（<font>/<color> 等）整段丢掉：读书界面
            // <font="georgia"><b><i><sprite=N>名字</i></b></font> — <color>正文</color>
            // 格式的行在交换后开场标签被剥、残留闭标签，历史文本颜色全错。
            var builder = new StringBuilder(text.Length + 16);
            var cursorPlain = 0; // 纯文本游标（重叠防御用）
            var cursorOrig = 0;  // 原始串游标
            var ti = 0;
            var ki = 0;
            while (ti < templateCount || ki < keyCount)
            {
                int[] span;
                string value;
                if (ki >= keyCount ||
                    (ti < templateCount && templateSpans[ti].Key[0] < keySpans[ki][0]))
                {
                    span = templateSpans[ti].Key;
                    value = templateSpans[ti].Value;
                    ti++;
                }
                else
                {
                    span = keySpans[ki];
                    value = keyValues[ki];
                    ki++;
                }
                if (span[0] < cursorPlain)
                {
                    continue; // 防御：区间异常重叠时跳过
                }
                var spanOrigStart = indexMap[span[0]];
                var spanOrigEnd = indexMap[span[1] - 1] + 1;
                if (spanOrigStart > cursorOrig)
                {
                    builder.Append(text, cursorOrig, spanOrigStart - cursorOrig);
                }
                builder.Append(value);
                cursorPlain = span[1];
                cursorOrig = spanOrigEnd;
            }
            if (cursorOrig < text.Length)
            {
                builder.Append(text, cursorOrig, text.Length - cursorOrig);
            }
            return builder.ToString();
        }

        private static bool OverlapsTemplateSpan(
            List<KeyValuePair<int[], string>> spans, int start, int end)
        {
            if (spans == null)
            {
                return false;
            }
            foreach (var pair in spans)
            {
                if (start < pair.Key[1] && pair.Key[0] < end)
                {
                    return true;
                }
            }
            return false;
        }

        // Settle：value 里仍含 [[Y]] 时，调用游戏原生管线统一装饰——
        // [[Y]] → <link>、按当前链接状态（未读/已读/失效）重算结果串里所有
        // <link> 的颜色、解析 [q=] 标记。hideVisitedLinks 必须 false，否则
        // 已读链接被剥成裸文本。异常时回退为把 [[Y]] 折叠成 Y（警告只记一次，
        // 避免逐文本刷日志）。数据字段交换不经过这里。
        //
        // 颜色继承（v2.1.9）：sourceText（被替换的原始串）里若已有带
        // <color=#RRGGBB> 的 <link>，说明面板有自己的链接色（对话历史是橙色，
        // LinkStyle.Default 是蓝色系）——改用颜色参数重载，linkColor 用提取色，
        // viewed/broken 色从 LinkStyle.Default 实例读取（反射一次并缓存）。
        // 提取不到则维持 LinkStyle.Default 重载。
        // 含蓄设置联动（v2.2.9）：游戏原生显示时按 FootnoteSubtlety 配置把
        // 已读链接渲染为裸文本（设置项"脚注显隐程度：含蓄"）；我们此前写死
        // false，F9 来回切换后已读链接全部复活，看起来倒像是新鲜显示"丢了
        // 链接"。现与游戏一致：跟配置走。读配置失败时回退 false（旧行为）。
        private static bool HideVisitedLinksForCurrentConfig()
        {
            try
            {
                return Travelling.Infrastructure.Config.GetConfigValueFloat(
                    Travelling.Enums.ConfigKey.FootnoteSubtlety) > 0f;
            }
            catch (Exception)
            {
                return false;
            }
        }

        // v2.2.13：逐表面对齐"已读链接剥除"。阶段二交换每个显示组件前写入
        // （交换全在主线程单趟进行，静态字段安全）。默认 false=保持可见。
        private static bool _hideVisitedForCurrentSwap;

        // 判定一个 TMP 文本所在表面的剥除行为：
        // - 父链上有 DetailableDisplay 系组件（带 _respectFootnoteSubtlety 字段）
        //   时，剥除 = 配置开 && 该标志真（脚注弹窗等标志为假，已读链接保持淡色）；
        // - 字幕面板（TravellingSubtitlePanel）直接读配置；
        // - 其余表面（浮签、toast 等）不剥除。
        private static bool ResolveHideVisitedForSurface(TMP_Text tmpText)
        {
            try
            {
                var subtletyOn = HideVisitedLinksForCurrentConfig();
                // 字幕面板的显示文本与打字机同住一个 GameObject（k.52 代码实证：
                // TravellingSubtitlePanel.Awake 里 _typewriter = subtitleText
                // .gameObject.GetComponent<TravellingTypewriter>()；对话历史与当前行
                // 同属这一个 TMP）。先认这个代码可证的同住组件：v2.3.1 实测字幕 TMP
                // 的父链检测失配（链上 _respectFootnoteSubtlety/TravellingSubtitlePanel
                // 都没匹配上），已读链接在交换后复活成淡色链接；打字机组件是
                // 对话字幕表面的专属标记（其余引用点全是对话 UI 辅助类）。
                foreach (var own in tmpText.gameObject.GetComponents<Component>())
                {
                    if (own != null && own.GetType().Name == "TravellingTypewriter")
                    {
                        return subtletyOn;
                    }
                }
                if (!subtletyOn)
                {
                    return false;
                }
                for (var t = tmpText.transform; t != null; t = t.parent)
                {
                    Component[] components;
                    try
                    {
                        components = t.GetComponents<Component>();
                    }
                    catch (Exception)
                    {
                        continue;
                    }
                    foreach (var component in components)
                    {
                        if (component == null)
                        {
                            continue;
                        }
                        var type = component.GetType();
                        var fullName = type.FullName;
                        if (!fullName.StartsWith("Travelling", StringComparison.Ordinal))
                        {
                            continue;
                        }
                        var field = type.GetField(
                            "_respectFootnoteSubtlety",
                            BindingFlags.Instance | BindingFlags.NonPublic);
                        if (field != null && field.FieldType == typeof(bool))
                        {
                            return field.GetValue(component) is bool respect && respect;
                        }
                        if (type.Name == "TravellingSubtitlePanel")
                        {
                            return true;
                        }
                    }
                }
            }
            catch (Exception)
            {
                // 探测失败按不剥除处理（保持链接可见）。
            }
            return false;
        }

        private static string SettleLinks(string value, string sourceText, bool? hideVisitedOverride = null)
        {
            // 需要装饰的两种形态：[[X]] 折叠链接，以及作者手写死的 <link="X">
            // （后者如"太阳的居屋"——v2.2.16 实测：交换后只剩 <link> 没有颜色
            // 包装，显示为无样式文本）。原生 ColourizeLinks 两者都处理。
            if (string.IsNullOrEmpty(value) ||
                (value.IndexOf("[[", StringComparison.Ordinal) < 0 &&
                 value.IndexOf("<link=", StringComparison.Ordinal) < 0))
            {
                return value;
            }
            try
            {
                // "已读链接剥成裸文本"在游戏里是逐表面行为：字幕面板直接读
                // FootnoteSubtlety 配置；DetailableDisplay 系表面另有各自的
                // _respectFootnoteSubtlety 标志（脚注弹窗等为 false——已读链接
                // 保持淡色而非剥除）。交换重装饰必须逐表面对齐：v2.2.9~2.2.12
                // 全局套配置，把弹窗的淡色链接剥成了裸文本（用户实测）。
                // 该值由阶段二交换前按表面写入（_hideVisitedForCurrentSwap），
                // 浮签组合路径（SwapPopupSegment）显式传 false——浮签总显示链接。
                var hideVisited = hideVisitedOverride ?? _hideVisitedForCurrentSwap;
                // 不传 CharGenLinkContext.ActivePermit：角色创建的白名单谓词按
                // 文本标签匹配、标签集按首次求值时的语言缓存，F9 换语言后失配
                // 会把白名单内链接也剥掉（v2.2.11/2.2.12 实测）；而新鲜显示的
                // 原生过滤本就生效，交换层无需再叠一层。不干涉原版创建界面设计。
                //
                // v2.4.14 一致性语义：交换只换语言，不顺带刷新链接的已读状态。
                // 原版渲染后已读状态变化不会重渲染既有文本（无此机制），若交换
                // 层按"当前状态"重装饰，同一行文字 F9 后链接会突然变淡/剥除
                // （用户实测：点开"心念"后中文态不变，F9 切英文 Passion 变纯文本）。
                // 逐链接继承源文本的当前显示色与剥除形态；配对不上的（源串里
                // 已剥除/新增）走原生状态逻辑兜底。
                string decorated = DecorateLinksPreservingDisplayedState(value, sourceText, hideVisited);
                if (!string.IsNullOrEmpty(decorated))
                {
                    return decorated;
                }
            }
            catch (Exception exception)
            {
                if (!_nativeDecorateFailed)
                {
                    _nativeDecorateFailed = true;
                    Log.LogWarning(
                        $"原生链接装饰失败，后续 [[Y]] 将折叠为裸文字：{exception}");
                }
            }
            return BracketLinkPattern.Replace(value, match => match.Groups[1].Value);
        }

        // 面板自带链接色时的样式实例（缓存复用，主线程逐次改色）。
        private static Travelling.UI.Info.LinkStyle _customLinkStyle;

        private static Travelling.UI.Info.LinkStyle GetCustomLinkStyle(Color link, Color viewed, Color broken)
        {
            if (_customLinkStyle == null)
            {
                _customLinkStyle = ScriptableObject.CreateInstance<Travelling.UI.Info.LinkStyle>();
                _customLinkStyle.bold = true;
            }
            _customLinkStyle.linkColor = link;
            _customLinkStyle.viewedLinkColor = viewed;
            _customLinkStyle.brokenLinkColor = broken;
            return _customLinkStyle;
        }

        // 从原始串里找第一个 <link...> 内的 <color=#RRGGBB>（面板自己的链接色）。
        private static readonly Regex LinkColorPattern = new Regex(
            "<link\\b[^>]*>(?:(?!</link>)[\\s\\S])*?<color=(#[0-9A-Fa-f]{6,8})>",
            RegexOptions.Compiled);

        // Tier 1.7 用：整段 <link="…">…</link> 捕获，替换为 [[内部裸文本]]。
        private static readonly Regex LinkRestorePattern = new Regex(
            "<link\\b[^>]*>([\\s\\S]*?)</link>",
            RegexOptions.Compiled);

        // 完整链接标签（装饰目标侧逐个处理）。
        private static readonly Regex WholeLinkTagPattern = new Regex(
            "<link=\"([^\"]*)\">([\\s\\S]*?)</link>",
            RegexOptions.Compiled);

        // 链接内部的 <color=#RRGGBB>（继承源串显示色用）。
        private static readonly Regex InnerLinkColorPattern = new Regex(
            "<color=(#[0-9A-Fa-f]{6,8})>",
            RegexOptions.Compiled);

        // 交换时逐链接继承源文本的当前显示状态（v2.4.14 一致性语义，v2.5.2 改为
        // 跨语言按词配对）：目标链接的 id 经反向映射回源语言词——源串里它是
        // 裸文本（已读+含蓄剥除）则同样剥除；是链接则继承其显示色；找不到
        // 对应词（交换后新增）才走原生状态逻辑。v2.4.14 的顺序配对在源串有
        // 剥除链接时整体错位（已剥除者不占位），用户实测 Passion 错继承
        // Aspect Pool 的颜色、剥除状态丢失。
        private static string DecorateLinksPreservingDisplayedState(
            string value, string sourceText, bool hideVisitedFallback)
        {
            var linked = Travelling.Utility.TravellingUtility.DoubleBracketsToLink(value, null);
            if (string.IsNullOrEmpty(linked) ||
                linked.IndexOf("<link=", StringComparison.Ordinal) < 0)
            {
                return linked;
            }
            // 源串链接 id → 显示色（无 <color> 包装记 null）。
            var sourceLinkColors = new Dictionary<string, string>(StringComparer.Ordinal);
            if (!string.IsNullOrEmpty(sourceText))
            {
                foreach (Match linkMatch in WholeLinkTagPattern.Matches(sourceText))
                {
                    var colorMatch = InnerLinkColorPattern.Match(linkMatch.Groups[2].Value);
                    sourceLinkColors[linkMatch.Groups[1].Value] =
                        colorMatch.Success ? colorMatch.Groups[1].Value : null;
                }
            }
            // 目标语言词 → 源语言词的反向映射（切英文时 map=zh2en，反向=en2zh）。
            var reverse = (_englishMode ? _en2zh : _zh2en)?.Exact;
            var hasDefaults = TryGetDefaultStyleColors(out var defaultLink, out var viewed, out var broken);
            return WholeLinkTagPattern.Replace(linked, match =>
            {
                var id = match.Groups[1].Value;
                var text = match.Groups[2].Value;
                string sourceWord = null;
                reverse?.TryGetValue(id, out sourceWord);
                if (sourceWord != null && !string.IsNullOrEmpty(sourceText) &&
                    !sourceLinkColors.ContainsKey(sourceWord) && sourceText.Contains(sourceWord))
                {
                    // 剥除继承：源串里该词以裸文本存在（已读剥除），保持剥除。
                    return text;
                }
                if (sourceWord != null && sourceLinkColors.TryGetValue(sourceWord, out var inherited))
                {
                    if (inherited != null)
                    {
                        return $"<link=\"{id}\"><color={inherited}><b>{text}</b></color></link>";
                    }
                    // 源链接无颜色包装（手写裸 link）：保持链接形态不上色。
                    return $"<link=\"{id}\">{text}</link>";
                }
                if (!hasDefaults)
                {
                    return match.Value;
                }
                return Travelling.Utility.TravellingUtility.ColourizeLinks(
                    match.Value, defaultLink, viewed, broken, bold: true, hideVisitedLinks: hideVisitedFallback);
            });
        }

        private static bool TryExtractLinkColor(string sourceText, out Color color)
        {
            color = default;
            if (string.IsNullOrEmpty(sourceText) ||
                sourceText.IndexOf("<link", StringComparison.Ordinal) < 0)
            {
                return false;
            }
            var match = LinkColorPattern.Match(sourceText);
            return match.Success &&
                   ColorUtility.TryParseHtmlString(match.Groups[1].Value, out color);
        }

        // LinkStyle.Default 的 link/viewed/broken 色：实例字段或属性（小写/帕斯卡
        // 命名都试），反射一次并缓存。
        private static bool _styleColorsTried;
        private static bool _styleColorsOk;
        private static Color _defaultLinkColor;
        private static Color _defaultViewedLinkColor;
        private static Color _defaultBrokenLinkColor;

        private static bool TryGetDefaultStyleColors(out Color link, out Color viewed, out Color broken)
        {
            if (!_styleColorsTried)
            {
                _styleColorsTried = true;
                try
                {
                    var style = Travelling.UI.Info.LinkStyle.Default;
                    if (style != null &&
                        TryReadStyleColor(style, "linkColor", out _defaultLinkColor) &&
                        TryReadStyleColor(style, "viewedLinkColor", out _defaultViewedLinkColor) &&
                        TryReadStyleColor(style, "brokenLinkColor", out _defaultBrokenLinkColor))
                    {
                        _styleColorsOk = true;
                    }
                }
                catch (Exception)
                {
                    // 读取失败则 _styleColorsOk 保持 false，兜底链接保持原标签形态。
                }
            }
            link = _defaultLinkColor;
            viewed = _defaultViewedLinkColor;
            broken = _defaultBrokenLinkColor;
            return _styleColorsOk;
        }

        private static bool TryReadStyleColor(object style, string name, out Color color)
        {
            color = default;
            var type = style.GetType();
            const BindingFlags flags =
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
            var pascalName = char.ToUpperInvariant(name[0]) + name.Substring(1);
            foreach (var candidate in new[] { name, pascalName })
            {
                var field = type.GetField(candidate, flags);
                if (field != null && field.FieldType == typeof(Color))
                {
                    color = (Color)field.GetValue(style);
                    return true;
                }
                var property = type.GetProperty(candidate, flags);
                if (property != null && property.PropertyType == typeof(Color) && property.CanRead)
                {
                    color = (Color)property.GetValue(style);
                    return true;
                }
            }
            return false;
        }

        // 剥掉全部 <...> 标签，返回纯文本；无配对 '>' 的 '<' 按字面保留。
        private static string StripTags(string text)
        {
            var builder = new StringBuilder(text.Length);
            var index = 0;
            while (index < text.Length)
            {
                if (text[index] == '<')
                {
                    var close = text.IndexOf('>', index + 1);
                    if (close > index)
                    {
                        index = close + 1;
                        continue;
                    }
                }
                builder.Append(text[index]);
                index++;
            }
            return builder.ToString();
        }

        private static readonly Dictionary<Type, bool> _gameDataTypeCache = new Dictionary<Type, bool>();

        private static bool IsGameDataType(Type type)
        {
            if (_gameDataTypeCache.TryGetValue(type, out var cached))
            {
                return cached;
            }
            var result = ComputeIsGameDataType(type);
            _gameDataTypeCache[type] = result;
            return result;
        }

        private static bool ComputeIsGameDataType(Type type)
        {
            var ns = type.Namespace;
            if (ns != null)
            {
                return ns.StartsWith("Travelling", StringComparison.Ordinal) ||
                       ns.StartsWith("PixelCrushers", StringComparison.Ordinal);
            }
            // 全局命名空间的游戏类型：travelling.scripts.dll 里的 AxisQuality/
            // Quality/VariableQuality/ExperienceQuality/ToastStackView 等没有
            // 命名空间，旧判定把它们整批漏扫——F9 阶段一换不到 AxisQuality 的
            // _label/_description，任务栏详情在重新打开时从未交换的数据重新
            // 组合、回原语言（v2.4.12 实测：物品栏里切英文再开任务栏，"内心
            // 所求？"一段滞留中文）。按程序集名归属兜底。
            var assemblyName = type.Assembly?.GetName().Name;
            return assemblyName != null &&
                   assemblyName.StartsWith("travelling", StringComparison.OrdinalIgnoreCase);
        }

        // 剥掉开头的 <sprite=...> 前缀（说话人名标记），body 为前缀后的内容。
        private static bool TryStripSpritePrefix(string value, out string prefix, out string body)
        {
            prefix = null;
            body = null;
            if (value == null || !value.StartsWith("<sprite=", StringComparison.Ordinal))
            {
                return false;
            }
            var end = value.IndexOf('>');
            if (end <= 0 || end == value.Length - 1)
            {
                return false;
            }
            prefix = value.Substring(0, end + 1);
            body = value.Substring(end + 1);
            return true;
        }

        // Lua 层同步（v2.1.11）：新行说话人名经 DialogueLua.GetLocalizedActorField
        // 从 Lua VM 的数据库快照读取，反射遍历换不到 Lua 表。每趟交换后把每个
        // actor 的 "Display Name"（此时已被交换成当前语言）写回 Lua 快照；Lua 键
        // 用 "Name" 字段值（内部 id，不在 Field 白名单里，永不被动，可安全作键）。
        // 默认语言下 GetLocalizedActorField 与 SetActorField 读写同一槽位
        // （ilspycmd 已核实 StringToLocalizedTableIndex 在默认语言不加后缀）。
        private static bool _luaSyncFailed;

        private static void SyncLuaActorDisplayNames()
        {
            try
            {
                var database = PixelCrushers.DialogueSystem.DialogueManager.masterDatabase;
                if (database == null || database.actors == null)
                {
                    return;
                }
                foreach (var actor in database.actors)
                {
                    if (actor == null || actor.fields == null)
                    {
                        continue;
                    }
                    var name = PixelCrushers.DialogueSystem.Field.LookupValue(actor.fields, "Name");
                    var displayName =
                        PixelCrushers.DialogueSystem.Field.LookupValue(actor.fields, "Display Name");
                    if (string.IsNullOrEmpty(name) || string.IsNullOrEmpty(displayName))
                    {
                        continue;
                    }
                    PixelCrushers.DialogueSystem.DialogueLua.SetActorField(
                        name, "Display Name", displayName);
                }
            }
            catch (Exception exception)
            {
                if (!_luaSyncFailed)
                {
                    _luaSyncFailed = true;
                    Log.LogWarning($"Lua 说话人名同步失败（后续仅静默重试）：{exception}");
                }
            }
        }

        // 反射遍历实例字段（public+nonpublic，含基类链），默认只做整串精确匹配，
        // 递归处理 string、string 数组/List<string>、可序列化嵌套类实例及其
        // 数组/List。不 traverse UnityEngine.Object 引用字段（避免满世界漫游），
        // 不处理静态字段、字典、委托；struct 字段跳过（装箱副本改不回写）。
        // PixelCrushers Field 实例走收窄的专用路径（见 SwapDialogueFieldValue）。
        // 例外：名为 accumulatedText 的字符串字段（声明类型在 Travelling/
        // PixelCrushers 命名空间时）改走完整显示级交换——字幕面板的滚动历史
        // 存在 StandardUISubtitlePanel.accumulatedText 里，是带装饰的显示文本
        // 大 blob，精确匹配永不命中；不换它，点"继续"重建 TMP.text 时会把已
        // 交换的历史行覆盖回旧语言（v2.1.5 实测回弹）。
        // 逻辑查找键（非显示文本）判定：音频库/环境音按这些字符串查条目，
        // 换成中文后查找失败、音效静默消失（v2.4.16 用户实测捏人音效消失）。
        // 显示文本字段（如 MusicTrackListing.DisplayName）不在此列。
        private static bool IsLogicLookupKeyField(string hostTypeName, string fieldName)
        {
            switch (hostTypeName)
            {
                // UiSfx.Play("Select")→AudioFXLibrary.GetListingByName(_name)；
                // ItemAudioFXListing 继承 AudioFXListing（_name 在基类声明）。
                case "AudioFXListing":
                case "AmbientFXListing":
                    return fieldName == "_name";
                // 音乐曲目按 Id 查（GetTrack/TrackIdIsValid）；UseInScenes 是
                // 场景 id 匹配表。DisplayName 是显示文本，不在保护之列。
                case "MusicTrackListing":
                    return fieldName == "Id" ||
                           fieldName == "UseInScenes" ||
                           fieldName == "UseAsFirstTrackInScenes";
                // 环境音床按场景名匹配（AmbienceBedLibrary.GetBedForScene）。
                case "SceneBed":
                    return fieldName == "Scenes";
                default:
                    return false;
            }
        }

        private static int SwapObjectFields(
            object instance, DirectionMap map, SwapCounters counters, HashSet<object> seen)
        {
            if (instance == null || instance is string)
            {
                return 0;
            }
            var type = instance.GetType();
            if (!type.IsClass || typeof(Delegate).IsAssignableFrom(type) || !seen.Add(instance))
            {
                return 0;
            }
            if (type.FullName == DialogueFieldTypeName)
            {
                return SwapDialogueFieldValue(instance, map.Exact);
            }
            // string 键字典：重建键跟随当前语言（ScriptablesCurator 在启动时
            // 按中文 label 建好 FootnotesByLabel/SkillsByLabel 等键→对象字典；
            // 对象的 _label 被换掉后键不跟随，另一语言下 Detailable 解析失败、
            // 链接被算成"失效"灰色——v2.1.7 实测）。
            if (instance is IDictionary dictionary)
            {
                SwapDictionaryKeys(dictionary, map, counters, seen);
                return 0;
            }
            var replaced = 0;
            for (var current = type; current != null && current != typeof(object); current = current.BaseType)
            {
                FieldInfo[] fields;
                try
                {
                    fields = current.GetFields(
                        BindingFlags.Instance | BindingFlags.Public |
                        BindingFlags.NonPublic | BindingFlags.DeclaredOnly);
                }
                catch (Exception)
                {
                    continue;
                }
                foreach (var field in fields)
                {
                    object value;
                    try
                    {
                        value = field.GetValue(instance);
                    }
                    catch (Exception)
                    {
                        continue;
                    }
                    if (value == null)
                    {
                        continue;
                    }
                    var fieldType = field.FieldType;
                    if (fieldType == typeof(string))
                    {
                        // Category 是游戏逻辑字段：VariableQuality/AxisQuality 的
                        // 分类串被拿去和枚举名比较（Category == VariableQualityCategory
                        // .Plan.ToString()，日志面板靠它过滤计划/境况/威胁）。翻译成
                        // "计划"/"境况"/"威胁" 后比较永远失败、日志面板被清空
                        // （v2.1.13/2.1.14 实测）。逻辑字段永不交换。
                        if (field.Name == "Category")
                        {
                            continue;
                        }
                        // 逻辑查找键（非显示文本）永不交换：音频库按这些字符串
                        // 名查条目（UiSfx.Play("Select")→GetListingByName），
                        // 换成中文后查找失败、音效静默消失（v2.4.16 用户实测：
                        // 捏人选职业/心念/加点音效全没）。
                        if (IsLogicLookupKeyField(current.Name, field.Name))
                        {
                            continue;
                        }
                        var stringValue = (string)value;
                        // loc 键形态（全大写+下划线，如 UI_FOOTNOTE_UNSUBTLE）是
                        // 程序查找键而非显示文本，永不交换——OptionStringValue.Label
                        // 被译成中文后 Loc.ForCurrentCulture 查找失败，菜单显示
                        // KEY NOT FOUND（v2.1.15 实测）。YES/LINK 这类全大写值
                        // 无下划线，不受影响。
                        if (LocKeyPattern.IsMatch(stringValue))
                        {
                            continue;
                        }
                        // 标签保真（CN→EN 方向）：标签字段先查 label_fidelity
                        // （资产 id/中文标签 → 真实英文标签），再退回通用映射。
                        // 通用映射按字符串择一，共享中文标签的资产会拿错变体、
                        // 链接按标签解析即失效（v2.4.13 "travelling" 青链实测）。
                        if (ReferenceEquals(map, _zh2en) && IsLabelFieldName(field.Name) &&
                            TryGetFidelityEnglishLabel(GetSiblingId(instance), stringValue, out var fidelityEnglish) &&
                            !string.Equals(stringValue, fidelityEnglish, StringComparison.Ordinal))
                        {
                            try
                            {
                                field.SetValue(instance, fidelityEnglish);
                                replaced++;
                            }
                            catch (Exception)
                            {
                                // 只读/特殊字段写不进去就跳过。
                            }
                            continue;
                        }
                        // accumulatedText 是带装饰的显示文本，走显示级流水线。
                        // StandardUISubtitlePanel 里它是属性，存储字段是
                        // m_accumulatedText（v2.1.6 只配了属性名，路由从未命中）。
                        if ((field.Name == "accumulatedText" || field.Name == "m_accumulatedText") &&
                            IsGameDataType(current))
                        {
                            // 字幕历史缓冲属于字幕面板表面：按 FootnoteSubtlety
                            // 配置剥除已读链接（v2.2.17 之前这里吃到的是上一次
                            // TMP 交换残留的任意值，导致已读链接在切回中文后
                            // 复活——对话里"心念"失色/复色不一致实测）。
                            _hideVisitedForCurrentSwap = HideVisitedLinksForCurrentConfig();
                            // 逐行处理缓冲并直接写回：带"名字 — "前缀的行若整行
                            // 进流水线，前缀会让折叠精确失配、掉到子串级把 [[链接]]
                            // 压平（v2.2.18 实测"心念"失色）。拆成前缀+正文分别
                            // 交换，正文因此能折叠精确命中整条目录译文（含链接）。
                            // 缓冲每行以 \n 收尾（游戏按此行尾续接下一行）；交换
                            // 各层不保证保留行尾空白，丢了会并线（v2.2.17 实测）。
                            var swappedBuffer = SwapBufferByLines(stringValue, map, counters);
                            if (swappedBuffer != stringValue)
                            {
                                var trailing = stringValue.Substring(stringValue.TrimEnd().Length);
                                if (trailing.Length > 0 && !swappedBuffer.EndsWith(trailing, StringComparison.Ordinal))
                                {
                                    swappedBuffer += trailing;
                                }
                                try
                                {
                                    field.SetValue(instance, swappedBuffer);
                                }
                                catch (Exception)
                                {
                                    // 写不进去就跳过。
                                }
                            }
                        }
                        else if (map.Exact.TryGetValue(stringValue, out var mapped))
                        {
                            try
                            {
                                field.SetValue(instance, mapped);
                                replaced++;
                            }
                            catch (Exception)
                            {
                                // 只读/特殊字段写不进去就跳过。
                            }
                        }
                        else if (TryStripSpritePrefix(stringValue, out var spritePrefix, out var strippedBody) &&
                                 map.Exact.TryGetValue(strippedBody, out var mappedBody))
                        {
                            // GetMarkedSpeakerName 会把缓存的 CharacterInfo.Name
                            // 原地改成 <sprite=N>豪梅神父 形态，精确匹配因此失配；
                            // 剥掉开头的 <sprite=...> 前缀再查一次，命中重拼前缀。
                            // 只兼容这一个前缀形态，不扩大。
                            try
                            {
                                field.SetValue(instance, spritePrefix + mappedBody);
                                replaced++;
                            }
                            catch (Exception)
                            {
                                // 写不进去就跳过。
                            }
                        }
                    }
                    else if (typeof(UnityEngine.Object).IsAssignableFrom(fieldType) ||
                             typeof(Delegate).IsAssignableFrom(fieldType))
                    {
                        // Unity 对象引用与委托一律不进入。
                    }
                    else if (value is IList list)
                    {
                        // alternativeLabels 是链接解析的备用通道（中文主 label +
                        // 英文别名）：逐元素语言交换会把别名换成与主标签同语言的
                        // 副本，且每趟往返复制膨胀一份（v2.4.14 探针实测 alt 涨成
                        // [性相池,性相池,性相池,性相池,Aspect Pool]，别名映射表随之
                        // 出现自映射）。别名的语言形态由 InjectAlternativeLabels
                        // 统一维护，交换不碰这个字段。
                        if (field.Name == "alternativeLabels" || field.Name == "_alternativeLabels")
                        {
                            continue;
                        }
                        // 逻辑查找键数组（场景 id 列表等）：同名字段保护，见
                        // IsLogicLookupKeyField（v2.4.16 音效消失修复）。
                        if (IsLogicLookupKeyField(current.Name, field.Name))
                        {
                            continue;
                        }
                        // string[]、List<string>、嵌套类实例的数组/List。
                        for (var i = 0; i < list.Count; i++)
                        {
                            object element;
                            try
                            {
                                element = list[i];
                            }
                            catch (Exception)
                            {
                                continue;
                            }
                            if (element is string elementString)
                            {
                                if (!LocKeyPattern.IsMatch(elementString) &&
                                    map.Exact.TryGetValue(elementString, out var mapped))
                                {
                                    try
                                    {
                                        list[i] = mapped;
                                        replaced++;
                                    }
                                    catch (Exception)
                                    {
                                        // 固定尺寸/只读列表写不进去就跳过。
                                    }
                                }
                            }
                            else if (element != null && IsGameDataType(element.GetType()))
                            {
                                var elementType = element.GetType();
                                if (elementType.IsClass)
                                {
                                    replaced += SwapObjectFields(element, map, counters, seen);
                                }
                                else
                                {
                                    // 结构体元素（ToastStackView._queue 是
                                    // List<QueuedToast>）：list[i] 读出的是装箱
                                    // 拷贝，换完字段必须写回——v2.4.12 实测：交换
                                    // 时仍在排队的教程泡消息不换，弹出显示旧语言。
                                    var structReplaced = SwapStructStringFields(element, map);
                                    if (structReplaced > 0)
                                    {
                                        try
                                        {
                                            list[i] = element;
                                            replaced += structReplaced;
                                        }
                                        catch (Exception)
                                        {
                                            // 只读列表写不进去就跳过。
                                        }
                                    }
                                }
                            }
                        }
                    }
                    else if (fieldType.IsClass && IsGameDataType(fieldType))
                    {
                        // 只递归游戏命名空间（Travelling/PixelCrushers）。v2.3.4 实测：
                        // 无闸门时递归会沿 SubmitSpaceTypingGuard._submit 进入
                        // UnityEngine.InputSystem.InputAction 内部，把动作名 "Submit"
                        // 换成"提交"，游戏按名查绑定随即崩溃（"action 'UI/提交' with
                        // 0 bindings"，点击脚注触发）。显示文本不走这条路（阶段二负责）。
                        replaced += SwapObjectFields(value, map, counters, seen);
                    }
                    else if (value is System.Collections.IEnumerable enumerable &&
                             !(value is IDictionary) && !(value is IList))
                    {
                        // 非列表/字典的集合（Queue<QueuedToast> 等）：交换时仍排在
                        // 队列里的教程泡消息永远不换、弹出时显示旧语言（v2.4.12
                        // 实测）。类元素原地递归；结构体元素（QueuedToast 是 struct，
                        // 枚举出来的是装箱拷贝）原位换字段后须重建集合写回——
                        // Queue<T> 按 Clear+Enqueue 保序重建。string 元素写不回，
                        // 跳过；引擎/System 命名空间元素由 IsGameDataType 闸拦截。
                        replaced += SwapEnumerableElements(value, map, counters, seen);
                    }
                }
            }
            return replaced;
        }

        // 非列表/字典集合的元素交换：类元素原地递归；Queue<T> 的结构体元素
        // （如 ToastStackView.QueuedToast）在装箱拷贝上原位换字段后重建队列写回。
        private static int SwapEnumerableElements(
            object collection, DirectionMap map, SwapCounters counters, HashSet<object> seen)
        {
            var replaced = 0;
            List<object> elements;
            try
            {
                elements = new List<object>();
                foreach (var element in (System.Collections.IEnumerable)collection)
                {
                    elements.Add(element);
                }
            }
            catch (Exception)
            {
                return 0; // 枚举期异常（集合正被碰等）：整集跳过。
            }
            if (elements.Count == 0)
            {
                return 0;
            }
            var changed = false;
            foreach (var element in elements)
            {
                if (element == null || element is string || element is UnityEngine.Object)
                {
                    continue;
                }
                var elementType = element.GetType();
                if (!IsGameDataType(elementType))
                {
                    continue;
                }
                if (elementType.IsClass)
                {
                    replaced += SwapObjectFields(element, map, counters, seen);
                }
                else
                {
                    // 结构体：装箱拷贝上原位换 string 字段（Queue<QueuedToast> 的
                    // Message/Title）。不走 seen——值类型每次装箱都是新对象。
                    replaced += SwapStructStringFields(element, map);
                    changed = true;
                }
            }
            if (!changed)
            {
                return replaced;
            }
            // 仅 Queue<T> 支持写回（Clear + Enqueue 保序）；其他集合的结构体
            // 元素改动只落在拷贝上，白换但不重建（避免误伤未知集合语义）。
            var collectionType = collection.GetType();
            if (collectionType.IsGenericType &&
                collectionType.GetGenericTypeDefinition() == typeof(Queue<>))
            {
                try
                {
                    collectionType.GetMethod("Clear").Invoke(collection, null);
                    var enqueue = collectionType.GetMethod("Enqueue");
                    foreach (var element in elements)
                    {
                        enqueue.Invoke(collection, new[] { element });
                    }
                }
                catch (Exception)
                {
                    // 重建失败：队列保持原样（元素是拷贝，原集合未受损）。
                }
            }
            return replaced;
        }

        // 结构体字段的精简交换：只处理 string 字段的精确映射（LocKey 跳过）。
        // 供 SwapEnumerableElements 的装箱结构体元素使用。
        private static int SwapStructStringFields(object boxedStruct, DirectionMap map)
        {
            var replaced = 0;
            for (var current = boxedStruct.GetType();
                 current != null && current != typeof(object) && current != typeof(ValueType);
                 current = current.BaseType)
            {
                FieldInfo[] fields;
                try
                {
                    fields = current.GetFields(
                        BindingFlags.Instance | BindingFlags.Public |
                        BindingFlags.NonPublic | BindingFlags.DeclaredOnly);
                }
                catch (Exception)
                {
                    continue;
                }
                foreach (var field in fields)
                {
                    if (field.FieldType != typeof(string))
                    {
                        continue;
                    }
                    object raw;
                    try
                    {
                        raw = field.GetValue(boxedStruct);
                    }
                    catch (Exception)
                    {
                        continue;
                    }
                    var value = raw as string;
                    if (string.IsNullOrEmpty(value) || LocKeyPattern.IsMatch(value))
                    {
                        continue;
                    }
                    if (map.Exact.TryGetValue(value, out var mapped) &&
                        !string.Equals(value, mapped, StringComparison.Ordinal))
                    {
                        try
                        {
                            field.SetValue(boxedStruct, mapped);
                            replaced++;
                        }
                        catch (Exception)
                        {
                            // 只读字段写不进去就跳过。
                        }
                    }
                }
            }
            return replaced;
        }

        // 标签字段形态：公开字段 label、私有存储 _label、自动属性 <Label> backing。
        private static bool IsLabelFieldName(string fieldName)
        {
            return fieldName == "label" || fieldName == "_label" ||
                   fieldName == "<Label>k__BackingField";
        }

        // 读对象同级的 id/_id 字符串字段（资产稳定 id），供标签保真按 id 查询。
        private static string GetSiblingId(object instance)
        {
            for (var current = instance.GetType();
                 current != null && current != typeof(object);
                 current = current.BaseType)
            {
                var idField = current.GetField("id", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic) ??
                              current.GetField("_id", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                if (idField != null && idField.FieldType == typeof(string))
                {
                    try
                    {
                        return idField.GetValue(instance) as string;
                    }
                    catch (Exception)
                    {
                        return null;
                    }
                }
            }
            return null;
        }

        // 阶段零专用：类型或其基类名为 ScriptablesCurator（不硬引用类型，
        // 防类型转发/子类差异）。
        private static bool IsScriptablesCurator(Type type)
        {
            for (var current = type; current != null; current = current.BaseType)
            {
                if (current.Name == "ScriptablesCurator")
                {
                    return true;
                }
            }
            return false;
        }

        // string 键字典的键重建：先完整收集要换的键值对（遍历期不修改），
        // 再统一应用——键经精确表变换后不同才 Remove(旧键) + dict[新键] = 值。
        // 值是 string 时经精确表变换，且独立于键是否交换（LocData 的 key→模板串
        // 缓存、curator 别名→主标签字典的值由此跟随语言）。
        // 值是 UnityEngine.Object 引用时不递归（对象本身会被 FindObjectsOfTypeAll
        // 那趟覆盖）。新键与既有键冲突时跳过该条并计数；只读/定点字典由
        // try/catch 跳过。
        // 值递归（v2.1.11）：值不是 string/UnityEngine.Object/集合类型、且类型
        // 在 Travelling/PixelCrushers 命名空间时，递归走 SwapObjectFields——
        // ConversationModel.m_characterInfoCache 是 Dictionary<int, CharacterInfo>，
        // int 键不重建，但缓存的 CharacterInfo.Name 必须跟随当前语言。
        private static void SwapDictionaryKeys(
            IDictionary dictionary, DirectionMap map, SwapCounters counters, HashSet<object> seen)
        {
            List<KeyValuePair<string, object>> entries = null;
            List<object> nestedValues = null;
            try
            {
                foreach (DictionaryEntry entry in dictionary)
                {
                    if (entry.Key is string key)
                    {
                        if (entries == null)
                        {
                            entries = new List<KeyValuePair<string, object>>();
                        }
                        entries.Add(new KeyValuePair<string, object>(key, entry.Value));
                    }
                    var entryValue = entry.Value;
                    if (entryValue != null &&
                        !(entryValue is string) &&
                        !(entryValue is UnityEngine.Object) &&
                        !(entryValue is IDictionary) &&
                        !(entryValue is IList))
                    {
                        var valueType = entryValue.GetType();
                        if (valueType.IsClass && IsGameDataType(valueType))
                        {
                            if (nestedValues == null)
                            {
                                nestedValues = new List<object>();
                            }
                            nestedValues.Add(entryValue);
                        }
                    }
                }
            }
            catch (Exception)
            {
                return; // 枚举期异常（字典正被别的线程碰等）：整本跳过
            }
            if (entries != null)
            {
                foreach (var pair in entries)
                {
                    var oldKey = pair.Key;
                    // 值交换独立于键交换（v2.1.15）：键无映射时值是标签/模板也
                    // 要跟随语言——curator._alternativeToPrimaryLabel 的键是无译文
                    // 的内部别名（不交换），值是主标签（必须交换），否则别名解析
                    // 出旧语言主标签、查主字典必失败（158 处陈旧值实测）。
                    var newValue = pair.Value;
                    var valueSwapped = false;
                    var stringValue = newValue as string;
                    if (stringValue != null &&
                        !LocKeyPattern.IsMatch(stringValue) &&
                        map.Exact.TryGetValue(stringValue, out var mappedValue) &&
                        !string.Equals(stringValue, mappedValue, StringComparison.Ordinal))
                    {
                        newValue = mappedValue;
                        valueSwapped = true;
                    }
                    if (LocKeyPattern.IsMatch(oldKey) ||
                        !map.Exact.TryGetValue(oldKey, out var newKey) ||
                        string.Equals(oldKey, newKey, StringComparison.Ordinal))
                    {
                        if (valueSwapped)
                        {
                            try
                            {
                                dictionary[oldKey] = newValue;
                                counters.DictionaryKey++;
                                if (_debugLog.Value)
                                {
                                    Log.LogInfo(
                                        $"[LanguageSwap] 字典值独立交换：[{oldKey}] = {stringValue} -> {newValue}");
                                }
                            }
                            catch (Exception)
                            {
                                // 只读字典写不进去就跳过。
                            }
                        }
                        continue;
                    }
                    try
                    {
                        if (dictionary.Contains(newKey))
                        {
                            // 新键与既有键冲突：跳过该条，扫描日志里报总数。
                            // 切勿移除旧键——v2.1.13 曾改为移除，风险太大已回退。
                            // 跳过不丢数据：既有新键条目覆盖新语言查询，旧键残留
                            // 只影响旧语言查询，切回旧语言时该键恰好已是对的，自愈。
                            counters.DictionaryKeyConflict++;
                            if (_debugLog.Value)
                            {
                                Log.LogInfo(
                                    $"[LanguageSwap] 字典键冲突跳过：{oldKey} -> {newKey}");
                            }
                            continue;
                        }
                        dictionary.Remove(oldKey);
                        dictionary[newKey] = newValue;
                        counters.DictionaryKey++;
                    }
                    catch (Exception)
                    {
                        // 只读/定点字典写不进去就跳过。
                    }
                }
            }
            if (nestedValues != null)
            {
                foreach (var nested in nestedValues)
                {
                    try
                    {
                        counters.Exact += SwapObjectFields(nested, map, counters, seen);
                    }
                    catch (Exception)
                    {
                        // 单个值失败静默跳过。
                    }
                }
            }
        }

        // PixelCrushers.DialogueSystem.Field 专用收窄路径：只处理名为 value 的
        // 字段，且仅当 title 属于文本标题白名单。title/typeString 等结构字段
        // 一律不碰——v2.1.2 之前通用遍历把 title="Name" 换成 lore 文本，导致
        // LookupValue("Name") 返回 null、GetEntrytag 的 Regex.Replace 崩溃。
        private static int SwapDialogueFieldValue(object fieldInstance, Dictionary<string, string> exact)
        {
            var type = fieldInstance.GetType();
            FieldInfo titleField;
            FieldInfo valueField;
            try
            {
                titleField = type.GetField(
                    "title", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                valueField = type.GetField(
                    "value", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            }
            catch (Exception)
            {
                return 0;
            }
            if (titleField == null || valueField == null || valueField.FieldType != typeof(string))
            {
                return 0;
            }
            string title;
            string fieldValue;
            try
            {
                title = titleField.GetValue(fieldInstance) as string;
                fieldValue = valueField.GetValue(fieldInstance) as string;
            }
            catch (Exception)
            {
                return 0;
            }
            if (string.IsNullOrEmpty(title) || string.IsNullOrEmpty(fieldValue))
            {
                return 0;
            }
            if (!DialogueTextFieldTitles.Contains(title) &&
                !SkillCheckDescriptionTitlePattern.IsMatch(title))
            {
                return 0;
            }
            if (exact.TryGetValue(fieldValue, out var mapped))
            {
                try
                {
                    valueField.SetValue(fieldInstance, mapped);
                    return 1;
                }
                catch (Exception)
                {
                    // 写不进去就跳过。
                }
            }
            return 0;
        }

        // 迟到系统行自愈（v2.7.3，l.31 实测）：游戏新增 0.25s 防误选延迟后，
        // 交换前已生成、交换后才追加进缓冲的系统行（"赞同（+1）"等）保持旧语言
        // ——交换扫描跑在追加之前，永远抓不到它。TravellingSubtitlePanel.
        // SetContent 每次追加后由 Harmony 后缀调用本方法：英文模式下把缓冲与
        // 当前显示按 zh2en 过一遍逐行交换——已是英文的行无 CJK 片段、幂等
        // 不动，迟到的中文行当场换回。中文模式直接早退（此时追加的行本就是
        // 中文，且避免 en2zh 子串级误伤中文行里的拉丁专名）。
        internal static void SwapLateSubtitleAppend(
            Travelling.UI.Dialogue.TravellingSubtitlePanel panel)
        {
            if (!_englishMode || !_mapsLoaded || panel == null)
            {
                return;
            }
            try
            {
                var counters = new SwapCounters();
                var buffer = panel.accumulatedText;
                if (!string.IsNullOrEmpty(buffer))
                {
                    var swapped = SwapBufferByLines(buffer, _zh2en, counters);
                    if (!string.Equals(swapped, buffer, StringComparison.Ordinal))
                    {
                        panel.accumulatedText = swapped;
                    }
                }
                var tmp = panel.subtitleText?.textMeshProUGUI;
                if (tmp != null && !string.IsNullOrEmpty(tmp.text))
                {
                    var swappedVisible = SwapBufferByLines(tmp.text, _zh2en, counters);
                    if (!string.Equals(swappedVisible, tmp.text, StringComparison.Ordinal))
                    {
                        tmp.text = swappedVisible;
                        tmp.maxVisibleCharacters = 99999;
                        tmp.firstVisibleCharacter = 0;
                    }
                }
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[LanguageSwap] 迟到系统行自愈失败：{exception.Message}");
            }
        }

        // 字幕面板表面判定（v2.7.3）：TMP 自身挂 TravellingTypewriter（字幕文本
        // 与打字机同对象），或父链上有 TravellingSubtitlePanel。与
        // ResolveHideVisitedForSurface 的检测口径一致。
        private static bool IsSubtitlePanelSurface(TMP_Text tmpText)
        {
            try
            {
                foreach (var own in tmpText.gameObject.GetComponents<Component>())
                {
                    if (own != null && own.GetType().Name == "TravellingTypewriter")
                    {
                        return true;
                    }
                }
                for (var t = tmpText.transform; t != null; t = t.parent)
                {
                    foreach (var component in t.GetComponents<Component>())
                    {
                        if (component != null &&
                            component.GetType().Name == "TravellingSubtitlePanel")
                        {
                            return true;
                        }
                    }
                }
            }
            catch (Exception)
            {
                // 探测失败按非字幕表面处理（走通用流水线）。
            }
            return false;
        }

        // 日志详情窗刷新（v2.7.3，用户实测：日志页 F9 后详情段不换/混排，
        // 须切走再切回才刷新）。第三段是游戏拼装的 "<uppercase>标签</uppercase>
        // -- 描述" 复合串，数据字段（StateSO._description 等）阶段一已换好；
        // 让 Journal 按当前数据重跑 DisplayDetailFor，三个详情窗格与奖励面板
        // 一并按当前语言重算，链接颜色走游戏原生解析。Journal 在 travelling.hud
        // （插件未引用该程序集），用反射调用。
        private static void RefreshOpenJournalDetail()
        {
            try
            {
                foreach (var obj in Resources.FindObjectsOfTypeAll<MonoBehaviour>())
                {
                    if (obj == null || obj.GetType().FullName != "Travelling.HUD.Journal" ||
                        !obj.gameObject.activeInHierarchy)
                    {
                        continue;
                    }
                    var lastQuality = obj.GetType()
                        .GetField("_lastDisplayedDetailQuality",
                            BindingFlags.Instance | BindingFlags.NonPublic)
                        ?.GetValue(obj);
                    if (lastQuality == null)
                    {
                        continue;
                    }
                    obj.GetType().GetMethod("DisplayDetailFor")?.Invoke(obj, new[] { lastQuality });
                    Log.LogInfo("[LanguageSwap] 日志详情窗已按当前语言重排。");
                }
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[LanguageSwap] 日志详情窗刷新失败：{exception.Message}");
            }
        }

        // 响应菜单整备（v2.7.1，l.8 选项 F9 回归根治）：
        // 选项文本是运行时拼装串（"[需求摘要] [检定] 正文"、"sprite 前缀 +
        // [100%] [标签] 正文"等），整串永不命中映射键；显示级分级流水线只能
        // 子串级部分替换，l.8 实测把 "考虑点些什么。" 损伤成
        // "Consideration点些什么."、把正文整句留在中文。这里分两步根治：
        // 先把 pcResponses 的 formattedText 按"拼装件逐件精确交换"换好
        // （括号摘要内的原子词全是独立映射键；任何一件换不动就整串放弃，
        // 绝不部分替换），再让可见响应按钮按新 formattedText 重新
        // SetFormattedText——文本、自动编号、颜色与检定图标样式都由游戏
        // 自己的 RebuildText/SetBaseLabelColorAndMarkup 重算。
        private static void RebuildActiveResponseMenu(DirectionMap map)
        {
            try
            {
                var manager = PixelCrushers.DialogueSystem.DialogueManager.instance;
                var state = manager != null ? manager.currentConversationState : null;
                var responses = state != null ? state.pcResponses : null;
                if (responses == null || responses.Length == 0)
                {
                    return;
                }
                foreach (var response in responses)
                {
                    var formatted = response?.formattedText;
                    var text = formatted?.text;
                    if (string.IsNullOrEmpty(text))
                    {
                        continue;
                    }
                    var swapped = SwapCompositeOptionText(map, text);
                    if (swapped != null && !string.Equals(swapped, text, StringComparison.Ordinal))
                    {
                        formatted.text = swapped;
                    }
                }
                var rebuiltButtons = 0;
                foreach (var panel in Resources.FindObjectsOfTypeAll<Travelling.UI.Dialogue.TravellingResponseMenuPanel>())
                {
                    if (panel == null || !panel.gameObject.activeInHierarchy)
                    {
                        continue;
                    }
                    var buttons = new List<Travelling.UI.Dialogue.TravellingResponseButton>();
                    if (panel.buttons != null)
                    {
                        buttons.AddRange(panel.buttons);
                    }
                    if (panel.instantiatedButtons != null)
                    {
                        foreach (var go in panel.instantiatedButtons)
                        {
                            var component = go != null
                                ? go.GetComponent<Travelling.UI.Dialogue.TravellingResponseButton>()
                                : null;
                            if (component != null && !buttons.Contains(component))
                            {
                                buttons.Add(component);
                            }
                        }
                    }
                    foreach (var button in buttons)
                    {
                        try
                        {
                            if (button != null && button.gameObject.activeInHierarchy &&
                                button.response?.formattedText != null)
                            {
                                button.SetFormattedText(button.response.formattedText);
                                rebuiltButtons++;
                            }
                        }
                        catch (Exception)
                        {
                            // 单个按钮重排失败不影响整体。
                        }
                    }
                }
                if (rebuiltButtons > 0)
                {
                    Log.LogInfo($"[LanguageSwap] 响应菜单已按当前语言重建（{rebuiltButtons} 个按钮）。");
                }
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[LanguageSwap] 响应菜单重建失败：{exception.Message}");
            }
        }

        // 拼装选项文本逐件交换：前导 sprite/space 标签串原样保留；随后先试整串
        // 精确（含 [[ ]] 数据形态键），不中再剥一组 "[...]"（END 与百分比原样、
        // "数字+物品名"换物品名、多原子摘要按分隔符逐原子精确交换），递归处理
        // 剩余部分。任何一层换不动返回 null——调用方整串放弃，绝不部分替换。
        private static string SwapCompositeOptionText(DirectionMap map, string text)
        {
            if (string.IsNullOrEmpty(text))
            {
                return null;
            }
            var output = new StringBuilder(text.Length + 16);
            var tagRun = OptionLeadingTagRun.Match(text);
            var rest = text;
            if (tagRun.Success)
            {
                output.Append(tagRun.Value);
                rest = text.Substring(tagRun.Length);
            }
            // 标签串后常跟空格（"<sprite…> [100%] …"）：前导空白原样保留。
            var leadSpace = 0;
            while (leadSpace < rest.Length && (rest[leadSpace] == ' ' || rest[leadSpace] == '\t'))
            {
                output.Append(rest[leadSpace]);
                leadSpace++;
            }
            rest = rest.Substring(leadSpace);
            return SwapCompositeOptionRest(map, rest, output, 0) ? output.ToString() : null;
        }

        private static bool SwapCompositeOptionRest(
            DirectionMap map, string rest, StringBuilder output, int depth)
        {
            if (rest.Length == 0)
            {
                return true;
            }
            if (map.Exact.TryGetValue(rest, out var exact))
            {
                output.Append(exact);
                return true;
            }
            if (depth >= 5 || !rest.StartsWith("[", StringComparison.Ordinal))
            {
                return false;
            }
            var close = rest.IndexOf(']');
            if (close <= 1)
            {
                return false;
            }
            var inner = rest.Substring(1, close - 1);
            string swappedGroup;
            if (inner == "END" || OptionPercentPattern.IsMatch(inner))
            {
                swappedGroup = "[" + inner + "]";
            }
            else if (TrySwapBracketInner(map, inner, out var swappedInner))
            {
                swappedGroup = "[" + swappedInner + "]";
            }
            else
            {
                return false;
            }
            output.Append(swappedGroup);
            var next = close + 1;
            while (next < rest.Length && (rest[next] == ' ' || rest[next] == '\n' || rest[next] == '\t'))
            {
                output.Append(rest[next]);
                next++;
            }
            return SwapCompositeOptionRest(map, rest.Substring(next), output, depth + 1);
        }

        private static bool TrySwapBracketInner(DirectionMap map, string inner, out string swapped)
        {
            swapped = null;
            // 摘要括号可含多原子（"; " 分隔）：分隔符与各原子首尾空白原样保留，
            // 原子逐个精确交换；"15 Francisques" 这类"数字+复数标签"拆数换名。
            var parts = Regex.Split(inner, @"([;；]\s*)");
            var builder = new StringBuilder(inner.Length + 8);
            for (var i = 0; i < parts.Length; i++)
            {
                var piece = parts[i];
                if (i % 2 == 1 || piece.Trim().Length == 0)
                {
                    builder.Append(piece);
                    continue;
                }
                var leadLength = piece.Length - piece.TrimStart().Length;
                var trailLength = piece.Length - piece.TrimEnd().Length;
                var atom = piece.Substring(leadLength, piece.Length - leadLength - trailLength);
                var quantity = QuantityPrefixPattern.Match(atom);
                string swappedAtom = null;
                if (quantity.Success &&
                    map.Exact.TryGetValue(quantity.Groups[2].Value, out var countedLabel))
                {
                    swappedAtom = quantity.Groups[1].Value + countedLabel;
                }
                else if (map.Exact.TryGetValue(atom, out var exactAtom))
                {
                    swappedAtom = exactAtom;
                }
                if (swappedAtom == null)
                {
                    return false;
                }
                builder.Append(piece.Substring(0, leadLength));
                builder.Append(swappedAtom);
                builder.Append(piece.Substring(piece.Length - trailLength));
            }
            swapped = builder.ToString();
            return true;
        }

        private static readonly Regex OptionLeadingTagRun = new Regex(
            @"^(?:<sprite=[^>]+>|<space=[^>]+>)+", RegexOptions.Compiled);
        private static readonly Regex OptionPercentPattern = new Regex(
            @"^[+-]?\d+(?:\.\d+)?%$", RegexOptions.Compiled);
        private static readonly Regex QuantityPrefixPattern = new Regex(
            @"^(\d+\s+)(.+)$", RegexOptions.Compiled);

        // [q=<id>:words] 数字词的模板捕获转换（v2.7.1）：游戏渲染时按当前语言
        // 产数字词（中文态经 NumberToWordsPatch 产中文数词），缓冲里已渲染的
        // 行做模板交换时捕获组只是裸数词、不是映射键——在此按数词互转，
        // 如 "一共是四十弗朗西斯克。" ↔ "That comes to forty francisques."。
        // 只对整组都是数词的捕获生效，普通文本不受影响。
        private static bool TrySwapNumberWords(string captured, out string swapped)
        {
            swapped = null;
            if (string.IsNullOrWhiteSpace(captured) || captured.Length > 40)
            {
                return false;
            }
            var trimmed = captured.Trim();
            if (ChineseNumberWords.TryParse(trimmed, out var cnValue))
            {
                swapped = EnglishNumberWords.Format(cnValue);
                return true;
            }
            if (EnglishNumberWords.TryParse(trimmed, out var enValue))
            {
                swapped = ChineseNumberWords.ToWords(enValue);
                return true;
            }
            return false;
        }

        // 中文数字词：零/一…九、十百千万节级；覆盖账单等实际数值范围。
        internal static class ChineseNumberWords
        {
            private static readonly char[] Digits = { '零', '一', '二', '三', '四', '五', '六', '七', '八', '九' };

            internal static string ToWords(int n)
            {
                if (n == 0)
                {
                    return "零";
                }
                if (n < 0)
                {
                    return "负" + ToWordsPositive(-(long)n);
                }
                return ToWordsPositive(n);
            }

            private static string ToWordsPositive(long n)
            {
                // 四位一节（万/亿），从高到低拼：高节存在时，低节为 0 跳过但记零待补，
                // 低节非 0 且（前面跳过节或本节小于 1000）则补一个零。
                var chunks = new System.Collections.Generic.List<int>();
                for (var temp = n; temp > 0; temp /= 10000)
                {
                    chunks.Add((int)(temp % 10000));
                }
                var builder = new StringBuilder();
                var zeroPending = false;
                for (var i = chunks.Count - 1; i >= 0; i--)
                {
                    var chunk = chunks[i];
                    if (chunk == 0)
                    {
                        if (builder.Length > 0)
                        {
                            zeroPending = true;
                        }
                        continue;
                    }
                    if (builder.Length > 0 && (zeroPending || chunk < 1000))
                    {
                        builder.Append('零');
                    }
                    zeroPending = false;
                    builder.Append(SectionToWords(chunk));
                    builder.Append(i == 1 ? "万" : i == 2 ? "亿" : "");
                }
                return builder.ToString();
            }

            private static string SectionToWords(int chunk)
            {
                var builder = new StringBuilder();
                var zeroPending = false;
                for (var divisor = 1000; divisor > 0; divisor /= 10)
                {
                    var digit = chunk / divisor % 10;
                    if (digit == 0)
                    {
                        if (builder.Length > 0)
                        {
                            zeroPending = true;
                        }
                        continue;
                    }
                    if (zeroPending)
                    {
                        builder.Append('零');
                        zeroPending = false;
                    }
                    builder.Append(Digits[digit]);
                    if (divisor == 1000)
                    {
                        builder.Append('千');
                    }
                    else if (divisor == 100)
                    {
                        builder.Append('百');
                    }
                    else if (divisor == 10)
                    {
                        builder.Append('十');
                    }
                }
                var result = builder.ToString();
                // 口语惯例：一十→十（"十五"而非"一十五"）。
                if (result.StartsWith("一十", StringComparison.Ordinal))
                {
                    result = result.Substring(1);
                }
                return result;
            }

            internal static bool TryParse(string text, out int value)
            {
                value = 0;
                if (string.IsNullOrEmpty(text))
                {
                    return false;
                }
                var rest = text;
                var negative = false;
                if (rest.StartsWith("负", StringComparison.Ordinal))
                {
                    negative = true;
                    rest = rest.Substring(1);
                }
                long total = 0;
                long section = 0;
                var number = 0;
                var consumed = 0;
                foreach (var c in rest)
                {
                    var digit = Array.IndexOf(Digits, c);
                    if (digit >= 0)
                    {
                        number = digit;
                        consumed++;
                        continue;
                    }
                    int sectionUnit;
                    switch (c)
                    {
                        case '十': sectionUnit = 10; break;
                        case '百': sectionUnit = 100; break;
                        case '千': sectionUnit = 1000; break;
                        default: sectionUnit = 0; break;
                    }
                    if (sectionUnit > 0)
                    {
                        section += (number == 0 ? 1 : number) * sectionUnit;
                        number = 0;
                        consumed++;
                        continue;
                    }
                    if (c == '万' || c == '亿')
                    {
                        var bigUnit = c == '万' ? 10000 : 100000000;
                        section = (section + number) * bigUnit;
                        total += section;
                        section = 0;
                        number = 0;
                        consumed++;
                        continue;
                    }
                    return false;
                }
                if (consumed == 0)
                {
                    return false;
                }
                var parsed = total + section + number;
                if (parsed > int.MaxValue)
                {
                    return false;
                }
                value = (int)(negative ? -parsed : parsed);
                return true;
            }
        }

        // 英文数字词：与 TravellingUtility.NumberToWords 的格式逐字节一致
        // （"one hundred and five"、"twenty-one"、"minus"），供捕获组互换。
        internal static class EnglishNumberWords
        {
            private static readonly string[] UnitsAndTeens =
            {
                "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
                "seventeen", "eighteen", "nineteen"
            };
            private static readonly string[] Tens =
                { "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety" };

            internal static string Format(int n)
            {
                if (n == 0)
                {
                    return "zero";
                }
                if (n < 0)
                {
                    return "minus " + FormatPositive(-(long)n);
                }
                return FormatPositive(n);
            }

            private static string FormatPositive(long n)
            {
                if (n == 0L)
                {
                    return "";
                }
                var builder = new StringBuilder();
                AppendGroup(builder, n / 1000000000, "billion");
                AppendGroup(builder, n / 1000000 % 1000, "million");
                AppendGroup(builder, n / 1000 % 1000, "thousand");
                var remainder = n % 1000;
                if (remainder > 0)
                {
                    if (builder.Length > 0)
                    {
                        builder.Append(remainder < 100 ? " and " : " ");
                    }
                    builder.Append(SpellUnderThousand(remainder));
                }
                return builder.ToString();
            }

            private static void AppendGroup(StringBuilder builder, long groupValue, string suffix)
            {
                if (groupValue == 0L)
                {
                    return;
                }
                if (builder.Length > 0)
                {
                    builder.Append(' ');
                }
                builder.Append(SpellUnderThousand(groupValue));
                builder.Append(' ').Append(suffix);
            }

            private static string SpellUnderThousand(long n)
            {
                var builder = new StringBuilder();
                var hundreds = n / 100;
                var remainder = n % 100;
                if (hundreds > 0)
                {
                    builder.Append(UnitsAndTeens[hundreds]).Append(" hundred");
                    if (remainder > 0)
                    {
                        builder.Append(" and ");
                    }
                }
                if (remainder > 0)
                {
                    if (remainder < 20)
                    {
                        builder.Append(UnitsAndTeens[remainder]);
                    }
                    else
                    {
                        builder.Append(Tens[remainder / 10]);
                        if (remainder % 10 > 0)
                        {
                            builder.Append('-').Append(UnitsAndTeens[remainder % 10]);
                        }
                    }
                }
                return builder.ToString();
            }

            internal static bool TryParse(string text, out int value)
            {
                value = 0;
                if (string.IsNullOrEmpty(text) ||
                    !System.Text.RegularExpressions.Regex.IsMatch(text, @"^[A-Za-z\- ]+$"))
                {
                    return false;
                }
                var tokens = text.ToLowerInvariant()
                    .Replace('-', ' ')
                    .Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
                var negative = false;
                long total = 0;
                long current = 0;
                var recognized = 0;
                foreach (var token in tokens)
                {
                    if (token == "and")
                    {
                        continue;
                    }
                    if (token == "minus")
                    {
                        negative = true;
                        recognized++;
                        continue;
                    }
                    var unitIndex = Array.IndexOf(UnitsAndTeens, token);
                    if (unitIndex >= 0)
                    {
                        current += unitIndex;
                        recognized++;
                        continue;
                    }
                    var tensIndex = Array.IndexOf(Tens, token);
                    if (tensIndex > 1)
                    {
                        current += tensIndex * 10;
                        recognized++;
                        continue;
                    }
                    if (token == "hundred" && current > 0)
                    {
                        current *= 100;
                        recognized++;
                        continue;
                    }
                    long multiplier = token switch
                    {
                        "thousand" => 1000L,
                        "million" => 1000000L,
                        "billion" => 1000000000L,
                        _ => 0L,
                    };
                    if (multiplier > 0 && current > 0)
                    {
                        total += current * multiplier;
                        current = 0;
                        recognized++;
                        continue;
                    }
                    return false;
                }
                if (recognized == 0)
                {
                    return false;
                }
                var parsed = total + current;
                if (parsed > int.MaxValue)
                {
                    return false;
                }
                value = (int)(negative ? -parsed : parsed);
                return true;
            }
        }
    }
}
