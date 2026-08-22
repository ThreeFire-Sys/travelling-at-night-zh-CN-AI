// 夜游漫记简体中文补丁 —— 资产烘焙版（v2.x）配套插件。
//
// 译文自 v2.0 起直接烘进游戏序列化资产，游戏以自己的管线渲染原生中文。
// 本插件只负责三件不改变文本内容的事：
//   1. 挂载 Noto Sans CJK 动态字体 fallback（游戏字体没有中文字形）；
//   2. 可选的中文字号倍率；
//   3. Skill.RawLabel 补丁：技能标签已烘成中文，但技能检定图标用 RawLabel
//      拼 <sprite="SmolSkillImages" name="...">， sprite 图集键必须保持英文，
//      否则 TMP 会把整个标签原样打到屏幕上。映射表 raw_labels.json 由烘焙
//      工具生成（中文标签 → 英文原标签）。
// 另有一个可选的 F9 中英文即时切换模块（LanguageSwap.cs）：只在内存里按
// lang_swap.json 精确映射改写数据对象的字符串字段，不拦截渲染管线。
//
// 绝对不要在这里加任何文本改写/缓存/反向逻辑：v2.0.1 已证实启动巡检会把
// 场景占位文本（"MUNUMUNUM"/"— FOO"）缓存为"原文"并在数秒后回写，覆盖
// 游戏随后赋入的真实内容。运行时拦截时代的完整实现存档于
// legacy/RuntimePatchPlugin.cs.txt。

using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using HarmonyLib;
using Newtonsoft.Json;
using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TextCore.LowLevel;

namespace TravellingCN
{
    [BepInPlugin(PluginGuid, PluginName, PluginVersion)]
    public class Plugin : BaseUnityPlugin
    {
        public const string PluginGuid = "cn.nyctodromy.travelling.zhcn";
        public const string PluginName = "夜游漫记简体中文补丁";
        public const string PluginVersion = "2.6.2";

        private static ManualLogSource Log;
        private static TMP_FontAsset ChineseFont;
        private static string PluginDirectory;
        private static bool GlobalFallbackInstalled;
        private static float ChineseFontScale = 1.00f;
        private static readonly Dictionary<string, string> RawLabelByChineseLabel =
            new Dictionary<string, string>(StringComparer.Ordinal);
        private static readonly Dictionary<object, float> OriginalFontSizes =
            new Dictionary<object, float>();

        private ConfigEntry<float> _fontScale;
        private ConfigEntry<bool> _autoProbeSearch;
        private ConfigEntry<bool> _autoProbeSwap;
        private ConfigEntry<bool> _autoProbeSoak;
        private ConfigEntry<bool> _autoProbeNewGame;
        private Harmony _harmony;

        private void Awake()
        {
            Log = Logger;
            PluginDirectory = Path.GetDirectoryName(Info.Location) ?? Paths.PluginPath;
            _fontScale = Config.Bind(
                "Typography",
                "ChineseFontScale",
                1.00f,
                "中文固定字号倍率；建议保持在 1.00–1.10。自动字号文本不放大。");
            if (Mathf.Abs(_fontScale.Value - 1.04f) < 0.0001f)
            {
                // v1.0 的全局 1.04 默认值会把固定布局文本挤进相邻区块，迁移到安全值。
                _fontScale.Value = 1.00f;
            }
            ChineseFontScale = Mathf.Clamp(_fontScale.Value, 1f, 1.10f);
            InstallChineseFont();
            LoadRawLabelMap();
            LanguageSwap.Initialize(Config, Log, PluginDirectory);

            _harmony = new Harmony(PluginGuid);
            try
            {
                var patched = _harmony.CreateClassProcessor(typeof(SkillRawLabelPatch)).Patch();
                if (patched == null || patched.Count == 0)
                {
                    Log.LogError("SkillRawLabelPatch 未解析到目标方法。");
                }
            }
            catch (Exception exception)
            {
                Log.LogError($"安装 SkillRawLabelPatch 失败：{exception}");
            }
            try
            {
                var patched = _harmony.CreateClassProcessor(typeof(WorldPopupComposeWrappedPatch)).Patch();
                if (patched == null || patched.Count == 0)
                {
                    Log.LogError("WorldPopupComposeWrappedPatch 未解析到目标方法。");
                }
            }
            catch (Exception exception)
            {
                Log.LogError($"安装 WorldPopupComposeWrappedPatch 失败：{exception}");
            }
            try
            {
                var patched = _harmony.CreateClassProcessor(typeof(SearchResultLabelProbePatch)).Patch();
                if (patched == null || patched.Count == 0)
                {
                    Log.LogError("SearchResultLabelProbePatch 未解析到目标方法。");
                }
            }
            catch (Exception exception)
            {
                Log.LogError($"安装 SearchResultLabelProbePatch 失败：{exception}");
            }

            RefreshFonts("awake");
            SceneManager.sceneLoaded += OnSceneLoaded;
            StartCoroutine(FontRefreshLoop());
            _autoProbeSearch = Config.Bind(
                "Diagnostics",
                "AutoProbeSearch",
                false,
                "诊断：启动后自动读档并打开脚注搜索页采集渲染数据（仅排障用）。");
            _autoProbeSwap = Config.Bind(
                "Diagnostics",
                "AutoProbeSwap",
                false,
                "诊断：启动后自动读档并在物品栏/任务栏间做 F9 场景复现（仅排障用）。");
            if (_autoProbeSearch.Value)
            {
                StartCoroutine(AutoProbeSearchRoutine());
            }
            if (_autoProbeSwap.Value)
            {
                StartCoroutine(AutoProbeSwapRoutine());
            }
            _autoProbeSoak = Config.Bind(
                "Diagnostics",
                "AutoProbeSoak",
                false,
                "诊断：启动后自动读档并做面板×语言切换矩阵巡测（仅排障用）。");
            if (_autoProbeSoak.Value)
            {
                StartCoroutine(AutoProbeSoakRoutine());
            }
            _autoProbeNewGame = Config.Bind(
                "Diagnostics",
                "AutoProbeNewGame",
                false,
                "诊断：启动后自动开新游戏，驱动捏人并沿途做语言切换检查（仅排障用）。");
            if (_autoProbeNewGame.Value)
            {
                StartCoroutine(AutoProbeNewGameRoutine());
            }
            Log.LogInfo(
                $"资产烘焙版字体插件已载入；RawLabel 映射 {RawLabelByChineseLabel.Count} 条。");
        }

        private void OnDestroy()
        {
            SceneManager.sceneLoaded -= OnSceneLoaded;
            LanguageSwap.Shutdown();
            _harmony?.UnpatchSelf();
        }

        private void Update()
        {
            LanguageSwap.Tick();
            if (UnityEngine.Input.GetKeyDown(KeyCode.F12))
            {
                DumpFontDiagnostics();
            }
        }





        private static string GetIntField(object instance, string fieldName)
        {
            try
            {
                for (var type = instance.GetType(); type != null; type = type.BaseType)
                {
                    var field = type.GetField(fieldName, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                    if (field != null)
                    {
                        return field.GetValue(instance)?.ToString() ?? "null";
                    }
                }
            }
            catch (Exception)
            {
                // 读取失败按 ? 处理
            }
            return "?";
        }






        private static string MeshVertexSummary(TMP_Text text)
        {
            try
            {
                var info = text.textInfo;
                if (info == null)
                {
                    return "?";
                }
                var total = 0;
                for (var i = 0; i < info.meshInfo.Length; i++)
                {
                    total += info.meshInfo[i].vertexCount;
                }
                return $"{total}/{info.meshInfo.Length}sub";
            }
            catch (Exception)
            {
                return "?";
            }
        }

        // 自动交换排障（Diagnostics.AutoProbeSwap 门控）：读档 → 开物品栏 →
        // 切英文 → 关物品栏开任务栏 → 转储。复现"物品栏开着时 F9，任务栏文本不换"。
        private IEnumerator AutoProbeSwapRoutine()
        {
            Log.LogInfo("[autoswap] 等待启动……");
            yield return new WaitForSecondsRealtime(12f);
            try
            {
                Travelling.Infrastructure.TravellingPersistenceManager.LoadMostRecentSave();
                Log.LogInfo("[autoswap] 已调用 LoadMostRecentSave");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[autoswap] 读档失败：{exception.Message}");
            }
            for (var i = 0; i < 45 && FindObjectByTypeName("Journal") == null; i++)
            {
                yield return new WaitForSecondsRealtime(2f);
            }
            yield return new WaitForSecondsRealtime(3f);
            Exception driveError = null;
            try
            {
                CallUiAction("ToggleJournal");
                Log.LogInfo("[autoswap] 任务栏先开一次（组合出 CN 内容）");
            }
            catch (Exception exception)
            {
                driveError = exception;
            }
            yield return new WaitForSecondsRealtime(3f);
            try
            {
                CallUiAction("ToggleJournal");
                CallUiAction("ToggleInventory");
                Log.LogInfo("[autoswap] 关任务栏、开物品栏");
            }
            catch (Exception exception)
            {
                driveError = exception;
            }
            yield return new WaitForSecondsRealtime(2f);
            // 交换前先在 CN 态强制建起 curator 惰性缓存（模拟用户长时间
            // 中文游玩后的真实会话：缓存按 CN 标签建键）——否则探针只能
            // 覆盖"缓存从未建过"的幸运路径（v2.4.12 链接失效回归教训）。
            PreBuildLinkCaches();
            // 中文态基线转储（v2.4.14 链接变色排障）：任何 F9 之前的解析状态。
            DumpLinkResolutionState();
            DumpAudioListingNames();
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2f);
            try
            {
                CallUiAction("ToggleInventory");
                CallUiAction("ToggleJournal");
                Log.LogInfo("[autoswap] 已关物品栏、开任务栏");
            }
            catch (Exception exception)
            {
                driveError = exception;
            }
            if (driveError != null)
            {
                Log.LogWarning($"[autoswap] 驱动失败：{driveError.Message}");
            }
            yield return new WaitForSecondsRealtime(3f);
            try
            {
                DumpAxisQualityState();
                DumpLinkResolutionState();
                DumpAudioListingNames();
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[autoswap] 数据核查失败：{exception.Message}");
            }
            DumpFontDiagnostics();
            yield return StartCoroutine(ProbeToastRoundTrip());
            // 往返结束（已切回 CN）后再核一次音效条目名：en2zh 方向也不许碰。
            DumpAudioListingNames();
            DumpRegressionSummary("autoswap");
            Log.LogInfo("[autoswap] 完成");
        }

        // 巡测电池（v2.4.13，Diagnostics.AutoProbeSoak 门控）：读档后对所有可
        // 切换面板做"开状态切换 + 关状态切换"双路径语言交换，每步转储可见
        // TMP 的残留嫌疑（EN 态含 CJK；CN 态整串命中 en2zh 精确键）。
        private static readonly string[] SoakPanelActions =        {
            "ToggleJournal",
            "ToggleInventory",
            "ToggleFootnoteSearch",
            "ToggleCharacterSheet",
            "ToggleMap",
            "ToggleCrafting",
        };

        private IEnumerator AutoProbeSoakRoutine()
        {
            Log.LogInfo("[soak] 等待启动……");
            yield return new WaitForSecondsRealtime(12f);
            try
            {
                Travelling.Infrastructure.TravellingPersistenceManager.LoadMostRecentSave();
                Log.LogInfo("[soak] 已调用 LoadMostRecentSave");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[soak] 读档失败：{exception.Message}");
            }
            for (var i = 0; i < 45 && FindObjectByTypeName("Journal") == null; i++)
            {
                yield return new WaitForSecondsRealtime(2f);
            }
            yield return new WaitForSecondsRealtime(3f);
            PreBuildLinkCaches();
            // 路径 A：面板开着切。逐面板：开 → 切EN → 转储 → 切CN → 转储 → 关。
            foreach (var action in SoakPanelActions)
            {
                yield return StartCoroutine(SoakOnePanelOpenSwap(action));
            }
            // 路径 B：面板关着切。全部关好切 EN，再逐面板开看重组结果。
            yield return StartCoroutine(SoakClosedSwapThenOpen());
            // 路径 C：详情弹窗（脚注/心念——用户报链接失效的现场表面）与 Esc 菜单。
            yield return StartCoroutine(SoakInfoWindow("Footnotes", "性相池"));
            yield return StartCoroutine(SoakInfoWindow("Passions", "愤怒"));
            yield return StartCoroutine(SoakEscapeMenu());
            DumpRegressionSummary("soak");
            Log.LogInfo("[soak] 完成");
        }

        // 详情弹窗巡测：经 InfoWindowManager.Show 打开指定 curator 集合里
        // 主标签匹配的元素（如 性相池 脚注 / 愤怒 心念），开着弹窗做 EN/CN
        // 往返并转储残留+青链。
        private IEnumerator SoakInfoWindow(string curatorCollectionProperty, string cnLabel)
        {
            object detailable = null;
            try
            {
                detailable = FindDetailableForInfoWindow(curatorCollectionProperty, cnLabel);
                if (detailable == null)
                {
                    Log.LogWarning($"[soak] 未找到弹窗对象 {curatorCollectionProperty}/{cnLabel}");
                    yield break;
                }
                var manager = FindObjectByTypeName("InfoWindowManager");
                var hasAspectsType = FindTypeByName("IHasAspects");
                var hasSkillModifiersType = FindTypeByName("IHasSkillModifiers");
                var show = manager.GetType().GetMethod(
                    "Show", new[] { FindTypeByName("IDetailable"), hasAspectsType, hasSkillModifiersType });
                // 与原生调用一致：不实现对应接口就传 null（脚注不传 IHasAspects 等）。
                show.Invoke(manager, new[] {
                    detailable,
                    hasAspectsType.IsInstanceOfType(detailable) ? detailable : null,
                    hasSkillModifiersType.IsInstanceOfType(detailable) ? detailable : null });
                Log.LogInfo($"[soak] 已开详情弹窗 {cnLabel}");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[soak] 开详情弹窗失败 {cnLabel}：{exception.Message}");
                yield break;
            }
            yield return new WaitForSecondsRealtime(2f);
            DumpVisibleResidue($"弹窗{cnLabel} CN态");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpVisibleResidue($"弹窗{cnLabel} 开切EN");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpVisibleResidue($"弹窗{cnLabel} 开切回CN");
            try
            {
                var manager = FindObjectByTypeName("InfoWindowManager");
                manager.GetType().GetMethod("ExplicitlyCloseCurrentInfoWindow").Invoke(manager, null);
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[soak] 关详情弹窗失败：{exception.Message}");
            }
            yield return new WaitForSecondsRealtime(1.5f);
        }

        private static object FindDetailableForInfoWindow(string collectionProperty, string cnLabel)
        {
            var curatorType = FindTypeByName("ScriptablesCurator");
            var curator = Resources.FindObjectsOfTypeAll(curatorType).FirstOrDefault();
            if (curator == null)
            {
                return null;
            }
            var collection = (curatorType.GetProperty(collectionProperty)?.GetValue(curator) ??
                              curatorType.GetField(collectionProperty, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)?.GetValue(curator)) as System.Collections.IEnumerable;
            if (collection == null)
            {
                return null;
            }
            foreach (var item in collection)
            {
                if (item == null)
                {
                    continue;
                }
                // ILabelledEntityWithId.Label 是属性；Footnote 是公开字段
                // label；Quality 的存储字段是 _label。三种形态都试。
                var type = item.GetType();
                var label = type.GetProperty("Label")?.GetValue(item) as string ??
                            type.GetField("label", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)?.GetValue(item) as string ??
                            type.GetField("_label", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)?.GetValue(item) as string;
                if (label == cnLabel)
                {
                    return item;
                }
            }
            return null;
        }

        private IEnumerator SoakEscapeMenu()
        {
            try
            {
                CallUiAction("CloseMenusThenToggleEscapeMenu");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[soak] 开 Esc 菜单失败：{exception.Message}");
                yield break;
            }
            yield return new WaitForSecondsRealtime(2f);
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpVisibleResidue("Esc菜单 开切EN");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpVisibleResidue("Esc菜单 开切回CN");
            try
            {
                CallUiAction("EscapeMenuRequestsClose");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[soak] 关 Esc 菜单失败：{exception.Message}");
            }
            yield return new WaitForSecondsRealtime(1.5f);
        }

        // 新游戏流程巡测（v2.4.13，Diagnostics.AutoProbeNewGame 门控）：
        // 主菜单 NewGame → 捏人（选职业/心念/完成）→ 进入游戏场景，
        // 沿途每步做 EN/CN 往返并转储残留+青链。FadeToNewSceneWithoutSave
        // 不落盘；进场景后若触发自动保存会占一个新槽位（测试后清理）。
        private IEnumerator AutoProbeNewGameRoutine()
        {
            Log.LogInfo("[newgame] 等待主菜单……");
            object menuController = null;
            for (var i = 0; i < 45 && menuController == null; i++)
            {
                yield return new WaitForSecondsRealtime(2f);
                menuController = FindObjectByTypeName("MainMenuController");
                // 启动序列 _Startup→_Logo→_Quote 停在引文页等按键：反射 Advance
                // （第一次按恢复不透明度、第二次按淡出、第三次直接载菜单场景）。
                var quote = FindObjectByTypeName("QuoteSceneController");
                if (quote != null)
                {
                    try
                    {
                        quote.GetType().GetMethod("Advance", BindingFlags.Instance | BindingFlags.NonPublic)?.Invoke(quote, null);
                        Log.LogInfo("[newgame] 引文页已按 Advance");
                    }
                    catch (Exception)
                    {
                        // 淡出途中失败就等下一轮再按。
                    }
                }
            }
            DumpVisibleResidue("主菜单 CN态");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpVisibleResidue("主菜单 切EN");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpVisibleResidue("主菜单 切回CN");
            if (menuController == null)
            {
                Log.LogWarning("[newgame] 未找到 MainMenuController");
                yield break;
            }
            try
            {
                menuController.GetType().GetMethod("NewGame").Invoke(menuController, null);
                Log.LogInfo("[newgame] 已调用 NewGame");
                // 捏人会触发 AutosaveMonitor 的存档节拍——探针不许可任何落盘，
                // 直接禁用组件（上次没禁用就把用户 102 号存档覆盖了，靠备份恢复）。
                var autosave = FindObjectByTypeName("AutosaveMonitor") as Behaviour;
                if (autosave != null)
                {
                    autosave.enabled = false;
                    Log.LogInfo("[newgame] 已禁用 AutosaveMonitor（探针不落盘）");
                }
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[newgame] NewGame 失败：{exception.Message}");
                yield break;
            }
            // 等捏人场景就绪。
            object chargen = null;
            for (var i = 0; i < 45 && chargen == null; i++)
            {
                yield return new WaitForSecondsRealtime(2f);
                chargen = FindObjectByTypeName("CharacterGenerationMenuController");
            }
            if (chargen == null)
            {
                Log.LogWarning("[newgame] 捏人场景未就绪");
                yield break;
            }
            yield return new WaitForSecondsRealtime(3f);
            Log.LogInfo("[newgame] 捏人已就绪");
            // 详情弹窗往返（v2.5.0 排障）：捏人界面打开"心念"脚注详情 → F9 往返
            // → 转储原始富文本。复现"中文链接正常、英文裸文本"（用户实测）。
            yield return StartCoroutine(ProbeChargenFootnotePopup());
            DumpVisibleResidue("捏人 CN态");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpVisibleResidue("捏人 切EN");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpVisibleResidue("捏人 切回CN");
            // 选第一个职业 → 第一个可选心念 → 完成捏人。
            var chargenType = chargen.GetType();
            try
            {
                var curatorType = FindTypeByName("ScriptablesCurator");
                var curator = Resources.FindObjectsOfTypeAll(curatorType).FirstOrDefault();
                var careers = curatorType.GetField("CareerChoices", BindingFlags.Instance | BindingFlags.Public)?.GetValue(curator) as System.Collections.IList;
                var career = careers?.Count > 0 ? careers[0] : null;
                chargenType.GetMethod("CareerChoiceSelected").Invoke(chargen, new[] { career });
                Log.LogInfo($"[newgame] 已选职业：{career}");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[newgame] 选职业失败：{exception.Message}");
            }
            yield return new WaitForSecondsRealtime(3f);
            DumpVisibleResidue("捏人选职业后 CN态");
            try
            {
                var curatorType = FindTypeByName("ScriptablesCurator");
                var curator = Resources.FindObjectsOfTypeAll(curatorType).FirstOrDefault();
                var passions = curatorType.GetField("Passions", BindingFlags.Instance | BindingFlags.Public)?.GetValue(curator) as System.Collections.IList;
                var passion = passions?.Count > 0 ? passions[0] : null;
                chargenType.GetMethod("ChoosePassion").Invoke(chargen, new[] { passion });
                Log.LogInfo($"[newgame] 已选心念：{passion}");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[newgame] 选心念失败：{exception.Message}");
            }
            yield return new WaitForSecondsRealtime(2.5f);
            DumpVisibleResidue("捏人选心念后 CN态");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpVisibleResidue("捏人定稿前 切EN");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            try
            {
                chargenType.GetMethod("FinishCharacterCreation").Invoke(chargen, null);
                Log.LogInfo("[newgame] 已完成捏人");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[newgame] FinishCharacterCreation 失败：{exception.Message}");
                yield break;
            }
            // 等游戏场景（Journal 就绪），再观察教程泡与 HUD 一段时间。
            for (var i = 0; i < 60 && FindObjectByTypeName("Journal") == null; i++)
            {
                yield return new WaitForSecondsRealtime(2f);
            }
            yield return new WaitForSecondsRealtime(5f);
            Log.LogInfo("[newgame] 已进入游戏场景");
            DumpVisibleResidue("进场景 CN态");
            // 纯中文新游戏态基线：任何 F9 之前的链接解析状态（v2.4.14 青链排障）。
            DumpLinkResolutionState();
            DumpRawLinkMarkup("进场景 CN态");
            RenderProbeAdvice();
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(3f);
            DumpVisibleResidue("进场景 切EN");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(3f);
            DumpVisibleResidue("进场景 切回CN");
            // 留 40 秒让开场教程泡陆续弹出，期间再抽查两轮。
            yield return new WaitForSecondsRealtime(20f);
            DumpVisibleResidue("开场驻留20s CN态");
            DumpLinkResolutionState();
            DumpRawLinkMarkup("开场驻留20s CN态");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(3f);
            DumpVisibleResidue("开场驻留 切EN");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(17f);
            DumpVisibleResidue("开场驻留 切回CN");
            yield return StartCoroutine(ProbeConversation());
            DumpRegressionSummary("newgame");
            Log.LogInfo("[newgame] 完成");
        }

        // 会话巡测：优先真实开场对话 antibes/intro（含 [[心念]]/[[性相池]] 链接
        // 的教学 Advice，v2.4.14 青链排障目标），退化到开发冒烟会话（标题含
        // test/smoke/delay）。启动后自动推进：有响应就选第一项，否则按继续，
        // 每步转储字幕里含 <link 的原始富文本。AutosaveMonitor 已被本探针禁用，
        // 进程结束即弃，不会落盘。
        private IEnumerator ProbeConversation()
        {
            string conversationTitle = null;
            try
            {
                var database = PixelCrushers.DialogueSystem.DialogueManager.masterDatabase;
                foreach (var conversation in database.conversations)
                {
                    var title = conversation.Title;
                    if (string.IsNullOrEmpty(title))
                    {
                        continue;
                    }
                    if (title == "antibes/intro")
                    {
                        conversationTitle = title;
                        break;
                    }
                    if (conversationTitle == null &&
                        (title.IndexOf("test", StringComparison.OrdinalIgnoreCase) >= 0 ||
                        title.IndexOf("smoke", StringComparison.OrdinalIgnoreCase) >= 0 ||
                        title.IndexOf("delay", StringComparison.OrdinalIgnoreCase) >= 0))
                    {
                        conversationTitle = title;
                    }
                }
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[newgame] 枚举会话失败：{exception.Message}");
            }
            if (conversationTitle == null)
            {
                Log.LogWarning("[newgame] 未找到巡测会话，跳过会话巡测");
                yield break;
            }
            var player = FindObjectByTypeName("PlayerCharacter") as Component;
            if (player == null)
            {
                Log.LogWarning("[newgame] 未找到 PlayerCharacter，跳过会话巡测");
                yield break;
            }
            try
            {
                PixelCrushers.DialogueSystem.DialogueManager.StartConversation(
                    conversationTitle, player.transform, null);
                Log.LogInfo($"[newgame] 已启动会话：{conversationTitle}");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[newgame] 启动会话失败：{exception.Message}");
                yield break;
            }
            // 自动推进：打字机/节拍期间第一次"继续"先快进完成当前字幕，
            // 第二次才跳下一条；响应菜单出现时选第一项。上限 30 步防死循环。
            for (var step = 0; step < 30; step++)
            {
                yield return new WaitForSecondsRealtime(2f);
                var sawPassionLink = DumpConversationLinkMarkup($"会话步{step}");
                // 一次性一致性验证（v2.4.14）：教学链接出现后，把"心念"标记
                // 已读（等价点击打开详情的记录效果；已渲染文本不刷新是原版
                // 机制），随后 F9 往返——交换后链接应保持交换前的显示色与
                // 链接形态，不因已读状态变化而变淡/剥除。
                if (!_viewedSwapTestDone && sawPassionLink)
                {
                    _viewedSwapTestDone = true;
                    yield return StartCoroutine(ProbeViewedLinkConsistency());
                }
                object dialogueUI;
                try
                {
                    dialogueUI = FindObjectByTypeName("TravellingDialogueUI");
                }
                catch (Exception)
                {
                    dialogueUI = null;
                }
                if (dialogueUI == null)
                {
                    continue;
                }
                try
                {
                    var state = PixelCrushers.DialogueSystem.DialogueManager.instance?.currentConversationState;
                    if (state == null)
                    {
                        Log.LogInfo("[newgame] 会话状态为空（已结束）");
                        break;
                    }
                    var responses = state.pcResponses;
                    if (responses != null && responses.Length > 0)
                    {
                        dialogueUI.GetType().GetMethod("OnClick")?.Invoke(dialogueUI, new object[] { responses[0] });
                        Log.LogInfo($"[newgame] 步{step} 已选响应：{responses[0].formattedText?.text}");
                    }
                    else
                    {
                        dialogueUI.GetType().GetMethod("OnContinueConversation")?.Invoke(dialogueUI, null);
                        Log.LogInfo($"[newgame] 步{step} 已按继续");
                    }
                }
                catch (Exception exception)
                {
                    Log.LogWarning($"[newgame] 步{step} 推进失败：{exception.Message}");
                }
            }
            try
            {
                PixelCrushers.DialogueSystem.DialogueManager.StopConversation();
            }
            catch (Exception)
            {
                // 关不掉就随进程结束。
            }
            // 剥除继承单元验证（v2.5.2）：构造源串——"心念"裸文本（已读剥除
            // 形态）+"性相池"带色链接；切英文语义下 Passion 应剥除成裸文本、
            // Aspect Pool 应继承 #BA4802。（v2.4.14 顺序配对在剥除占位缺失时
            // 错位：Passion 错继承性相池颜色——用户实测回归。）
            try
            {
                LanguageSwap.DebugToggleNow(); // 切英文语义（reverse=en2zh）
                var srcText = "[下一项选择会动用一种 心念。选择你已有 的心念，可恢复 <link=\"性相池\"><color=#BA4802><b>性相池</b></color></link> 中的点数。]";
                var targetValue = "[The next choice acts with a [[Passion]]. Choose a Passion you possess to refresh pips in your [[Aspect Pool]].]";
                var decorate = typeof(LanguageSwap).GetMethod(
                    "DecorateLinksPreservingDisplayedState", BindingFlags.Static | BindingFlags.NonPublic);
                var output = decorate?.Invoke(null, new object[] { targetValue, srcText, true }) as string;
                ProbeAssert(output != null &&
                    !output.Contains("<link=\"Passion\"") &&
                    output.Contains("<link=\"Aspect Pool\"><color=#BA4802"),
                    "剥除继承：已读裸文本不复活、未读链接保持");
                Log.LogInfo($"[convlink] 剥除继承验证=【{output}】");
                LanguageSwap.DebugToggleNow(); // 切回中文
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[convlink] 剥除继承验证失败：{exception.Message}");
            }
        }

        // 转储当前对话 UI 里所有含 <link 的 TMP 原始富文本片段（含颜色 hex）。
        // 返回是否看到教学"心念"链接（一致性验证的触发信号）。
        private static bool _introScreenshotTaken;
        private static bool _viewedSwapTestDone;

        // 一致性验证（v2.4.14）：标记心念已读 → F9 往返 → 转储字幕链接。
        private IEnumerator ProbeViewedLinkConsistency()
        {
            try
            {
                foreach (var fn in Resources.FindObjectsOfTypeAll<Travelling.Infrastructure.Footnotes.Footnote>())
                {
                    if (fn != null && fn.id == "passion")
                    {
                        // LogInteraction 的参数接口在 travelling.core（未引用），反射调用。
                        var qc = Travelling.PCQualities.QHelper.GetQC();
                        qc?.GetType().GetMethod("LogInteraction")?.Invoke(qc, new object[] { fn });
                        Log.LogInfo("[convlink] 已标记心念为已读（模拟点击查看）");
                        break;
                    }
                }
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[convlink] 标记已读失败：{exception.Message}");
            }
            DumpConversationLinkMarkup("已读后F9前");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpConversationLinkMarkup("已读切EN");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpConversationLinkMarkup("已读切回CN");
        }

        private bool DumpConversationLinkMarkup(string tag)
        {
            var sawPassion = false;
            try
            {
                var dumped = 0;
                foreach (var text in Resources.FindObjectsOfTypeAll<TMP_Text>())
                {
                    if (text == null || !text.gameObject.activeInHierarchy || string.IsNullOrEmpty(text.text))
                    {
                        continue;
                    }
                    var idx = text.text.IndexOf("<link", StringComparison.Ordinal);
                    if (idx < 0)
                    {
                        continue;
                    }
                    if (text.text.Contains("link=\"心念\""))
                    {
                        sawPassion = true;
                    }
                    var start = Math.Max(0, idx - 30);
                    var len = Math.Min(text.text.Length - start, 300);
                    Log.LogInfo($"[convlink:{tag}] {text.gameObject.name}: …{text.text.Substring(start, len)}…");
                    // 含教学链接的字幕出现时截屏：用真实像素核对链接颜色
                    // （v2.4.14 用户实测"心念"呈亮蓝，但富文本里是 #BA4802）。
                    if (text.text.Contains("心念") && !_introScreenshotTaken)
                    {
                        _introScreenshotTaken = true;
                        var shot = Path.Combine(BepInEx.Paths.BepInExRootPath, "convlink_intro.png");
                        // ScreenCapture 在 UnityEngine.ScreenCaptureModule（未引用），反射调用。
                        Type.GetType("UnityEngine.ScreenCapture, UnityEngine.ScreenCaptureModule")
                            ?.GetMethod("CaptureScreenshot", BindingFlags.Static | BindingFlags.Public, null, new[] { typeof(string) }, null)
                            ?.Invoke(null, new object[] { shot });
                        Log.LogInfo($"[convlink:{tag}] 已截屏 {shot}");
                    }
                    if (++dumped >= 6)
                    {
                        break;
                    }
                }
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[convlink:{tag}] 失败：{exception.Message}");
            }
            return sawPassion;
        }

        // 捏人界面详情弹窗往返探针（v2.5.0）：打开"心念"脚注详情（InfoWindowManager
        // .Show 三参重载，参数接口在 travelling.core 故全反射），F9 往返逐态转储
        // 弹窗 TMP 的原始富文本（含 <link>/<color> 标签形态）。
        private IEnumerator ProbeChargenFootnotePopup()
        {
            object mgr = null;
            Travelling.Infrastructure.Footnotes.Footnote passion = null;
            try
            {
                mgr = FindObjectByTypeName("InfoWindowManager");
                foreach (var fn in Resources.FindObjectsOfTypeAll<Travelling.Infrastructure.Footnotes.Footnote>())
                {
                    if (fn != null && fn.id == "passion")
                    {
                        passion = fn;
                        break;
                    }
                }
                if (mgr == null || passion == null)
                {
                    Log.LogWarning("[popup] InfoWindowManager 或 passion 脚注未找到");
                    yield break;
                }
                var show = mgr.GetType().GetMethods().FirstOrDefault(
                    m => m.Name == "Show" && m.GetParameters().Length == 3);
                show?.Invoke(mgr, new object[] { passion, null, null });
                Log.LogInfo("[popup] 已打开心念详情");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[popup] 打开详情失败：{exception.Message}");
                yield break;
            }
            yield return new WaitForSecondsRealtime(1.5f);
            DumpRawLinkMarkup("弹窗 CN态");
            DumpPassionTextFull("弹窗 CN态");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpRawLinkMarkup("弹窗 切EN");
            DumpPassionTextFull("弹窗 切EN");
            // 原生 tooltip 渲染路径验证（带 CharGenLinkContext.ActivePermit 白
            // 名单）：F9 后白名单缓存若未失效，英文链接会被剥成裸文本。
            try
            {
                var ctxType = FindTypeByName("CharGenLinkContext");
                var permit = ctxType?.GetProperty("ActivePermit", BindingFlags.Static | BindingFlags.Public)?.GetValue(null);
                var render = typeof(Travelling.Utility.TravellingUtility)
                    .GetMethods(BindingFlags.Static | BindingFlags.Public)
                    .FirstOrDefault(m => m.Name == "ResolveQualityTokensAndColourizeLinks" &&
                        m.GetParameters().Length == 4 &&
                        m.GetParameters()[3].ParameterType.Name.StartsWith("Predicate"));
                var rendered = render?.Invoke(null, new object[] {
                    passion.Description, Travelling.UI.Info.LinkStyle.Default, false, permit }) as string;
                var linkCount = rendered == null ? -1 :
                    System.Text.RegularExpressions.Regex.Matches(rendered, "<link=").Count;
                ProbeAssert(linkCount > 0, "捏人白名单原生渲染链接存活（EN 态）");
                Log.LogInfo($"[popup] 原生渲染(EN,带白名单) 链接数={linkCount} 片段=【{(rendered ?? "null").Substring(0, Math.Min(300, (rendered ?? "").Length))}】");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[popup] 原生渲染验证失败：{exception.Message}");
            }
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpRawLinkMarkup("弹窗 切回CN");
            DumpPassionTextFull("弹窗 切回CN");
            try
            {
                mgr.GetType().GetMethod("ExplicitlyCloseCurrentInfoWindow")?.Invoke(mgr, null);
            }
            catch (Exception)
            {
                // 关不掉随它去。
            }
        }

        // 转储所有含目标词的 active TMP 全文（含标签形态），找链接渲染的真实载体。
        private void DumpPassionTextFull(string tag)
        {
            try
            {
                foreach (var text in Resources.FindObjectsOfTypeAll<TMP_Text>())
                {
                    if (text == null || !text.gameObject.activeInHierarchy || string.IsNullOrEmpty(text.text))
                    {
                        continue;
                    }
                    var t = text.text;
                    if (!t.Contains("性相池") && !t.Contains("Aspect Pool"))
                    {
                        continue;
                    }
                    Log.LogInfo($"[passdump:{tag}] {text.gameObject.name} 全文=【{t}】");
                }
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[passdump:{tag}] 失败：{exception.Message}");
            }
        }

        private IEnumerator SoakOnePanelOpenSwap(string action)
        {
            try
            {
                CallUiAction(action);
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[soak] 开面板失败 {action}：{exception.Message}");
                yield break;
            }
            yield return new WaitForSecondsRealtime(2f);
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpVisibleResidue($"{action} 开切EN");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            DumpVisibleResidue($"{action} 开切回CN");
            try
            {
                CallUiAction(action);
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[soak] 关面板失败 {action}：{exception.Message}");
            }
            yield return new WaitForSecondsRealtime(1.5f);
        }

        private IEnumerator SoakClosedSwapThenOpen()
        {
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            foreach (var action in SoakPanelActions)
            {
                try
                {
                    CallUiAction(action);
                }
                catch (Exception exception)
                {
                    Log.LogWarning($"[soak] 关切EN后开面板失败 {action}：{exception.Message}");
                    continue;
                }
                yield return new WaitForSecondsRealtime(2f);
                DumpVisibleResidue($"{action} 关切EN后开");
                try
                {
                    CallUiAction(action);
                }
                catch (Exception)
                {
                    // 关不上就继续下一个。
                }
                yield return new WaitForSecondsRealtime(1f);
            }
            // 收回中文再抽查一遍重组。
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2.5f);
            foreach (var action in SoakPanelActions)
            {
                try
                {
                    CallUiAction(action);
                }
                catch (Exception)
                {
                    continue;
                }
                yield return new WaitForSecondsRealtime(2f);
                DumpVisibleResidue($"{action} 关切回CN后开");
                try
                {
                    CallUiAction(action);
                }
                catch (Exception)
                {
                    // 同上。
                }
                yield return new WaitForSecondsRealtime(1f);
            }
        }

        // 残留嫌疑转储：EN 态下可见 TMP 含 CJK；CN 态下可见 TMP 剥净后整串
        // 命中 en2zh 精确键（= 有译文却没换的英文）。返回嫌疑条数。
        private static int DumpVisibleResidue(string phase)
        {
            var suspects = 0;
            foreach (var text in Resources.FindObjectsOfTypeAll<TMP_Text>())
            {
                if (text == null || !text.isActiveAndEnabled ||
                    !text.gameObject.activeInHierarchy)
                {
                    continue;
                }
                var content = text.text;
                if (string.IsNullOrWhiteSpace(content))
                {
                    continue;
                }
                var plain = StripMarkupForLog(content).Trim();
                if (plain.Length < 2)
                {
                    continue;
                }
                var hasCjk = HasCjk(plain);
                // 青链检测：BROKEN_LINK_COLOR = Color.cyan（#00FFFF）——链接目标
                // 在交换后的 curator 里解析失败才会被染成它。任何语言的可见文本
                // 里出现都算嫌疑（v2.4.13 用户实测 EN 态 Passion 青链）。
                if (content.IndexOf("<color=#00FFFF", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    suspects++;
                    Log.LogWarning($"[soak] 青链失效[{phase}]：{Truncate(plain, 90)}");
                    // 带标签原文：看清是哪个链接目标被判失效。
                    Log.LogWarning($"[soak] 青链原文[{phase}]={Truncate(content, 400)}");
                }
                if (LanguageSwap.IsEnglishMode)
                {
                    if (hasCjk)
                    {
                        suspects++;
                        Log.LogWarning($"[soak] EN态残留中文[{phase}]：{Truncate(plain, 90)}");
                    }
                }
                else if (!hasCjk && LanguageSwap.DebugIsExactEnKey(plain))
                {
                    suspects++;
                    Log.LogWarning($"[soak] CN态残留英文[{phase}]：{Truncate(plain, 90)}");
                }
            }
            Log.LogInfo($"[soak] {phase}：残留嫌疑 {suspects} 条");
            return suspects;
        }

        // 提示泡排障（v2.4.12）：弹出"制作：查看配方"教程泡，在泡保持打开
        // 的状态下 CN→EN→CN 往返切换，逐阶段转储泡文本。复现"切回中文时
        // 提示文本切不回来/正文英文链接名中文"。
        private IEnumerator ProbeToastRoundTrip()
        {
            // 先切回中文，让 TutorialQualityMessage 数据处于 CN。
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(2f);
            try
            {
                ShowCraftingTutorialToast();
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[autoswap] 弹提示泡失败：{exception.Message}");
                yield break;
            }
            yield return new WaitForSecondsRealtime(3f);
            DumpToastTutorialText("弹出后（CN）");
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(3f);
            DumpToastTutorialText("泡打开中切英文");
            DumpLinkResolutionState();
            LanguageSwap.DebugToggleNow();
            yield return new WaitForSecondsRealtime(3f);
            DumpToastTutorialText("泡打开中切回中文");
        }

        private static void ShowCraftingTutorialToast()
        {
            var tutorialType = FindTypeByName("TutorialQualityMessage");
            var serviceType = FindTypeByName("TutorialPopupService");
            if (tutorialType == null || serviceType == null)
            {
                Log.LogWarning("[autoswap] 未找到 TutorialQualityMessage/TutorialPopupService 类型");
                return;
            }
            var shown = 0;
            foreach (var tutorial in Resources.FindObjectsOfTypeAll(tutorialType))
            {
                if (tutorial == null)
                {
                    continue;
                }
                var text = tutorialType.GetField("_tutorialText", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)?.GetValue(tutorial) as string;
                if (string.IsNullOrEmpty(text) ||
                    (!text.Contains("adept") && !text.Contains("修习者") &&
                     !text.Contains("Expand a tooltip") && !text.Contains("展开工具提示")))
                {
                    continue;
                }
                var id = tutorialType.GetField("_id", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)?.GetValue(tutorial) as string;
                var label = tutorialType.GetField("_label", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)?.GetValue(tutorial) as string;
                serviceType.GetMethod("Show", BindingFlags.Public | BindingFlags.Static)
                    .Invoke(null, new object[] { id, label, text, null, null, null });
                Log.LogInfo($"[autoswap] 已弹出教程泡 id={id} label={Truncate(label, 12)}");
                shown++;
            }
            if (shown == 0)
            {
                Log.LogWarning("[autoswap] 未找到制作教程 TutorialQualityMessage");
            }
        }

        private static void DumpToastTutorialText(string phase)
        {
            foreach (var text in Resources.FindObjectsOfTypeAll<TMP_Text>())
            {
                if (text == null || string.IsNullOrEmpty(text.text))
                {
                    continue;
                }
                var content = text.text;
                if (!content.Contains("adept") && !content.Contains("修习者") &&
                    !content.Contains("斯宾塞") && !content.Contains("Spencer") &&
                    !content.Contains("Footnote") && !content.Contains("脚注") &&
                    !content.Contains("tooltip") && !content.Contains("工具提示"))
                {
                    continue;
                }
                Log.LogInfo(
                    $"[autoswap] 提示泡文本[{phase}] active={text.isActiveAndEnabled} " +
                    $"含CN={(HasCjk(content) ? "是" : "否")} 内容={Truncate(StripMarkupForLog(content), 120)}");
                if (content.Contains("展开工具提示") || content.Contains("Expand a tooltip"))
                {
                    // 该泡曾整颗失配滞留旧语言：记录带标签原文以核对键形态。
                    Log.LogInfo($"[autoswap] 提示泡原文[{phase}]={Truncate(content, 500)}");
                }
            }
        }

        private static bool HasCjk(string value)
        {
            foreach (var c in value)
            {
                if (c >= '一' && c <= '鿿')
                {
                    return true;
                }
            }
            return false;
        }

        private static string StripMarkupForLog(string value) =>
            System.Text.RegularExpressions.Regex.Replace(value, "<[^>]+>", "");

        // 交换前在 CN 态强制构建 curator 的惰性 ByLabel 字典与别名映射。
        private static void PreBuildLinkCaches()
        {
            var curatorType = FindTypeByName("ScriptablesCurator");
            if (curatorType == null)
            {
                return;
            }
            var curator = Resources.FindObjectsOfTypeAll(curatorType).FirstOrDefault();
            if (curator == null)
            {
                return;
            }
            var existsMethod = curatorType.GetMethod("DoesDetailableLabelExist", BindingFlags.Instance | BindingFlags.Public);
            existsMethod?.Invoke(curator, new object[] { "心念" });
            var altMethod = curatorType.GetMethod("GetAlternativeLabels", BindingFlags.Instance | BindingFlags.Public);
            altMethod?.Invoke(curator, new object[] { "心念" });
            Log.LogInfo("[autoswap] 已在 CN 态预建链接缓存");
        }

        // 链接解析排障（v2.4.12 回归调查）：切英文后链接被判定失效（青链/裸文本）。
        // 直接查 curator 的 ByLabel 字典与别名映射在交换后的实际内容。
        private static void DumpLinkResolutionState()
        {
            var curatorType = FindTypeByName("ScriptablesCurator");
            if (curatorType == null)
            {
                Log.LogWarning("[autoswap] 未找到 ScriptablesCurator 类型");
                return;
            }
            var curators = Resources.FindObjectsOfTypeAll(curatorType);
            Log.LogInfo($"[autoswap] curator 实例数={curators.Length}");
            foreach (var curator in curators)
            {
                if (curator == null)
                {
                    continue;
                }
                DumpCuratorDict(curator, "_passionsByLabel", "心念");
                DumpCuratorDict(curator, "_aspectsByLabel", "性相池");
                DumpCuratorDict(curator, "_footnotesByLabel", "心念");
                DumpCuratorDict(curator, "_footnotesByLabel", "性相池");
                var altMap = curatorType.GetField("_alternativeToPrimaryLabel", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)?.GetValue(curator) as System.Collections.IDictionary;
                if (altMap == null)
                {
                    Log.LogInfo("[autoswap] _alternativeToPrimaryLabel = null");
                }
                else
                {
                    var hasPassion = altMap.Contains("Passion") ? $"Passion→{altMap["Passion"]}" : "无Passion键";
                    var hasCn = altMap.Contains("心念") ? $"心念→{altMap["心念"]}" : "无心念键";
                    var hasPool = altMap.Contains("Aspect Pool") ? $"Aspect Pool→{altMap["Aspect Pool"]}" : "无AspectPool键";
                    var hasCnPool = altMap.Contains("性相池") ? $"性相池→{altMap["性相池"]}" : "无性相池键";
                    Log.LogInfo($"[autoswap] _alternativeToPrimaryLabel 共{altMap.Count}条：{hasPassion}；{hasCn}；{hasPool}；{hasCnPool}");
                }
                var existsMethod = curatorType.GetMethod("DoesDetailableLabelExist", BindingFlags.Instance | BindingFlags.Public);
                if (existsMethod != null)
                {
                    Log.LogInfo($"[autoswap] DoesDetailableLabelExist(Passion)={existsMethod.Invoke(curator, new object[] { "Passion" })} " +
                        $"DoesDetailableLabelExist(心念)={existsMethod.Invoke(curator, new object[] { "心念" })} " +
                        $"DoesDetailableLabelExist(Aspect Pool)={existsMethod.Invoke(curator, new object[] { "Aspect Pool" })} " +
                        $"DoesDetailableLabelExist(性相池)={existsMethod.Invoke(curator, new object[] { "性相池" })}");
                }
                var resolveMethod = curatorType.GetMethod("GetDetailedScriptableByLabel", BindingFlags.Instance | BindingFlags.Public);
                if (resolveMethod != null)
                {
                    foreach (var probe in new[] { "心念", "性相池", "Passion", "Aspect Pool" })
                    {
                        var resolved = resolveMethod.Invoke(curator, new object[] { probe });
                        var id = resolved?.GetType().GetProperty("Id")?.GetValue(resolved) ?? "(无Id)";
                        Log.LogInfo($"[autoswap] 解析 {probe} → {resolved?.GetType().Name} id={id}");
                    }
                }
                break; // 只看第一个非空实例
            }
            try
            {
                var qc = Travelling.PCQualities.QHelper.GetQC();
                var stateMethod = qc?.GetType().GetMethod("GetDetailableLabelState", BindingFlags.Instance | BindingFlags.Public);
                if (qc != null && stateMethod != null)
                {
                    Log.LogInfo($"[autoswap] LabelState(心念)={stateMethod.Invoke(qc, new object[] { "心念" })} " +
                        $"LabelState(性相池)={stateMethod.Invoke(qc, new object[] { "性相池" })} " +
                        $"LabelState(Passion)={stateMethod.Invoke(qc, new object[] { "Passion" })} " +
                        $"LabelState(Aspect Pool)={stateMethod.Invoke(qc, new object[] { "Aspect Pool" })}");
                }
                foreach (var fn in Resources.FindObjectsOfTypeAll<Travelling.Infrastructure.Footnotes.Footnote>())
                {
                    if (fn != null && (fn.id == "passion" || fn.id == "aspectpool"))
                    {
                        Log.LogInfo($"[autoswap] footnote {fn.id}: label={fn.label} alt=[{string.Join(",", fn.alternativeLabels)}]");
                    }
                }
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[autoswap] 深度链接诊断失败：{exception.Message}");
            }
        }

        private static void DumpCuratorDict(object curator, string fieldName, string probeKey)
        {
            var dict = curator.GetType().GetField(fieldName, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)?.GetValue(curator) as System.Collections.IDictionary;
            if (dict == null)
            {
                Log.LogInfo($"[autoswap] {fieldName} = null（尚未惰性构建）");
                return;
            }
            var sample = new System.Text.StringBuilder();
            var i = 0;
            foreach (System.Collections.DictionaryEntry entry in dict)
            {
                if (i++ >= 4)
                {
                    break;
                }
                sample.Append(entry.Key).Append(" | ");
            }
            var probe = probeKey == null ? "" :
                $" 含{probeKey}={dict.Contains(probeKey)}";
            Log.LogInfo($"[autoswap] {fieldName} 共{dict.Count}条{probe} 样例: {sample}");
        }

        // 转储所有可见 TMP 里含 <link 标签的原始富文本片段（含颜色 hex），
        // 用于确认对话渲染后链接 id 与上色结果（v2.4.14 青链排障）。
        private static void DumpRawLinkMarkup(string tag)
        {
            try
            {
                var dumped = 0;
                foreach (var text in Resources.FindObjectsOfTypeAll<TMP_Text>())
                {
                    if (text == null || !text.gameObject.activeInHierarchy || string.IsNullOrEmpty(text.text))
                    {
                        continue;
                    }
                    var t = text.text;
                    var idx = t.IndexOf("<link", StringComparison.Ordinal);
                    if (idx < 0)
                    {
                        continue;
                    }
                    var start = Math.Max(0, idx - 20);
                    var len = Math.Min(t.Length - start, 260);
                    Log.LogInfo($"[linkdump:{tag}] {text.gameObject.name}: …{t.Substring(start, len)}…");
                    if (++dumped >= 12)
                    {
                        break;
                    }
                }
                if (dumped == 0)
                {
                    Log.LogInfo($"[linkdump:{tag}] 无可见 <link 文本");
                }
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[linkdump:{tag}] 失败：{exception.Message}");
            }
        }

        // 直接调用游戏上色纯函数复现 Advice 链接渲染（v2.4.14 青链排障）：
        // 从对话数据库取 Until Antipolis 里含链接标记的运行时条目文本，
        // 过 BracketsToColourizedLinks 输出带颜色 hex 的渲染结果。
        private static void RenderProbeAdvice()
        {
            try
            {
                var db = PixelCrushers.DialogueSystem.DialogueManager.masterDatabase;
                string probeText = null;
                var titles = new System.Text.StringBuilder();
                foreach (var conv in db.conversations)
                {
                    if (titles.Length < 900)
                    {
                        titles.Append('[').Append(conv.Title).Append(']');
                    }
                    // 开场对话的内部标题是 antibes/intro（"直至安提波利斯"是
                    // Description 字段，不是 Title——v2.4.14 探针实测）。
                    var title = conv.Title ?? string.Empty;
                    if (title != "antibes/intro")
                    {
                        continue;
                    }
                    foreach (var entry in conv.dialogueEntries)
                    {
                        foreach (var field in entry.fields)
                        {
                            if (field?.value != null && field.value.Contains("[[") && field.value.Contains("心念"))
                            {
                                probeText = field.value;
                                break;
                            }
                        }
                        if (probeText != null)
                        {
                            break;
                        }
                    }
                    if (probeText != null)
                    {
                        break;
                    }
                }
                Log.LogInfo($"[renderprobe] 会话标题样例={titles}");
                if (probeText == null)
                {
                    Log.LogWarning("[renderprobe] 未找到 Until Antipolis 的链接条目");
                    return;
                }
                Log.LogInfo($"[renderprobe] 条目原文={probeText.Substring(0, Math.Min(140, probeText.Length))}…");
                var util = FindTypeByName("TravellingUtility");
                var linkify = util.GetMethods(BindingFlags.Static | BindingFlags.Public)
                    .FirstOrDefault(x => x.Name == "BracketsToColourizedLinks" &&
                        x.GetParameters().Length == 3 &&
                        x.GetParameters()[1].ParameterType == typeof(bool));
                if (linkify == null)
                {
                    Log.LogWarning("[renderprobe] 未找到 BracketsToColourizedLinks(string,bool,Predicate)");
                    return;
                }
                var result = linkify.Invoke(null, new object[] { probeText, false, null }) as string;
                Log.LogInfo($"[renderprobe] 上色结果={result}");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[renderprobe] 失败：{exception.Message}");
            }
        }

        // ---- 回归断言设施（v2.5.3）：探针从"打印给人看"升级为"断言+FAIL 汇总"，
        // 发版前跑一遍， FAIL 即不得发。每断言失败打 [FAIL] 行并计数。
        private static int _regressionFailures;

        private static void ProbeAssert(bool condition, string what)
        {
            if (!condition)
            {
                _regressionFailures++;
                Log.LogWarning($"[FAIL] {what}");
            }
            else
            {
                Log.LogInfo($"[pass] {what}");
            }
        }

        private static void DumpRegressionSummary(string probe)
        {
            if (_regressionFailures == 0)
            {
                Log.LogInfo($"[regression] {probe} 全绿（0 失败）");
            }
            else
            {
                Log.LogWarning($"[regression] {probe} 失败 {_regressionFailures} 项——发版前必须清零！");
            }
        }

        // 转储 UI 音效库的条目名（_name 是 UiSfx.Play 的查找键；被交换成中文
        // 后音效静默消失——v2.4.16 排障）。交换前后各 dump 一次对照；含 CJK
        // 即断言失败。
        private static void DumpAudioListingNames()
        {
            try
            {
                var curatorType = FindTypeByName("ScriptablesCurator");
                var curator = Resources.FindObjectsOfTypeAll(curatorType).FirstOrDefault();
                var lib = curatorType.GetField("uiAudioFXLibrary", BindingFlags.Instance | BindingFlags.NonPublic)?.GetValue(curator);
                if (lib == null)
                {
                    Log.LogInfo("[audio] uiAudioFXLibrary = null");
                    return;
                }
                var listings = lib.GetType().GetField("_listings", BindingFlags.Instance | BindingFlags.NonPublic)?.GetValue(lib) as System.Collections.IEnumerable;
                var names = new List<string>();
                foreach (var listing in listings)
                {
                    var nameField = listing.GetType().GetField("_name", BindingFlags.Instance | BindingFlags.NonPublic);
                    names.Add(nameField?.GetValue(listing) as string ?? "?");
                }
                Log.LogInfo($"[audio] UI 音效条目名=[{string.Join(",", names)}]");
                ProbeAssert(!names.Any(n => n.Any(c => c >= '一' && c <= '鿿')),
                    "音效条目名保持英文（逻辑查找键不得交换）");
                var request = curatorType.GetMethod("GetUIAudioFXRequest")?.Invoke(curator, new object[] { "Select" });
                ProbeAssert(request != null, "GetUIAudioFXRequest(Select) 解析非空");
                Log.LogInfo($"[audio] GetUIAudioFXRequest(Select)={(request == null ? "null" : "非空")}");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[audio] 转储失败：{exception.Message}");
            }
        }

        // 交换后核查 nina.prologue（内心所求？）的运行时数据语言。
        // AxisQuality 在 travelling.scripts.dll 的全局命名空间，只能按名反射。
        private static void DumpAxisQualityState()
        {
            var axisType = FindTypeByName("AxisQuality");
            if (axisType == null)
            {
                Log.LogWarning("[autoswap] 未找到 AxisQuality 类型");
                return;
            }
            foreach (var quality in Resources.FindObjectsOfTypeAll(axisType))
            {
                if (quality == null)
                {
                    continue;
                }
                var idField = quality.GetType().GetField("_id", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                var id = idField?.GetValue(quality) as string;
                if (id != "nina.prologue")
                {
                    continue;
                }
                var labelField = quality.GetType().GetField("_label", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                var descField = quality.GetType().GetField("_description", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                var label = labelField?.GetValue(quality) as string ?? "?";
                var desc = descField?.GetValue(quality) as string ?? "?";
                Log.LogInfo(
                    $"[autoswap] nina.prologue _label={Truncate(label, 12)} " +
                    $"_description={Truncate(desc, 24)}…");
                return;
            }
            Log.LogWarning("[autoswap] 未找到 nina.prologue");
        }

        private static string Truncate(string value, int limit) =>
            string.IsNullOrEmpty(value) ? value :
            value.Length <= limit ? value : value.Substring(0, limit);

        private static void CallUiAction(string methodName)
        {
            var handlerType = FindTypeByName("IUIActionHandler");
            var watchman = FindTypeByName("Watchman");
            var getter = watchman.GetMethods(BindingFlags.Public | BindingFlags.Static)
                .First(m => m.Name == "GetRegisteredInterface" && m.IsGenericMethodDefinition);
            var handler = getter.MakeGenericMethod(handlerType).Invoke(null, null);
            handlerType.GetMethod(methodName).Invoke(handler, null);
        }

        // 自动探针（v2.4.4 排障专用，Diagnostics.AutoProbeSearch 门控）：
        // 启动 → 读最近存档 → 打开脚注搜索页 → 转储渲染数据，全程无人值守。
        private IEnumerator AutoProbeSearchRoutine()
        {
            Log.LogInfo("[autoprobe] 等待启动……");
            yield return new WaitForSecondsRealtime(12f);
            try
            {
                Travelling.Infrastructure.TravellingPersistenceManager.LoadMostRecentSave();
                Log.LogInfo("[autoprobe] 已调用 LoadMostRecentSave");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[autoprobe] 读档失败：{exception.Message}");
            }
            object hud = null;
            for (var i = 0; i < 45 && hud == null; i++)
            {
                yield return new WaitForSecondsRealtime(2f);
                hud = FindObjectByTypeName("FootnoteSearchHUD");
            }
            Log.LogInfo($"[autoprobe] 搜索 HUD：{(hud == null ? "未找到" : "已找到")}");
            if (hud == null)
            {
                yield break;
            }
            yield return new WaitForSecondsRealtime(3f);
            try
            {
                var handlerType = FindTypeByName("IUIActionHandler");
                var watchman = FindTypeByName("Watchman");
                var getter = watchman.GetMethods(BindingFlags.Public | BindingFlags.Static)
                    .First(m => m.Name == "GetRegisteredInterface" && m.IsGenericMethodDefinition);
                var handler = getter.MakeGenericMethod(handlerType).Invoke(null, null);
                handlerType.GetMethod("ToggleFootnoteSearch").Invoke(handler, null);
                Log.LogInfo("[autoprobe] 已调用 ToggleFootnoteSearch");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[autoprobe] 打开搜索页失败：{exception.Message}");
            }
            yield return new WaitForSecondsRealtime(4f);
            DumpFontDiagnostics();
            Log.LogInfo("[autoprobe] 完成");
        }

        private static Type FindTypeByName(string simpleName)
        {
            foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type found = null;
                try
                {
                    found = assembly.GetTypes().FirstOrDefault(x => x.Name == simpleName);
                }
                catch (Exception)
                {
                    // 某些程序集类型枚举会抛异常，跳过。
                }
                if (found != null)
                {
                    return found;
                }
            }
            return null;
        }

        private static object FindObjectByTypeName(string simpleName)
        {
            var type = FindTypeByName(simpleName);
            if (type == null)
            {
                return null;
            }
            var found = Resources.FindObjectsOfTypeAll(type);
            return found != null && found.Length > 0 ? found[0] : null;
        }

        // F12 诊断（v2.3.6）：脚注搜索行中文空白（英文正常、全局与逐字体 fallback
        // 均已确认挂载、Player.log 无缺字告警）——静态排查到头，改为运行时转储
        // 现场：每个含 CJK 的 TMP 的字体/材质/矩形/激活状态与父链，外加全局
        // fallback 状态与全部已载字体资产清单。
        private static void DumpFontDiagnostics()
        {
            try
            {
                var fallbacks = TMP_Settings.fallbackFontAssets;
                Log.LogInfo(
                    $"[F12] 全局 fallback 列表：{(fallbacks == null ? "null" : string.Join(",", fallbacks.ConvertAll(f => f == null ? "null" : f.name)))}");
                var fontNames = new List<string>();
                foreach (var fontAsset in Resources.FindObjectsOfTypeAll<TMP_FontAsset>())
                {
                    fontNames.Add(fontAsset.name + (HasChineseFallback(fontAsset) ? "(+CN)" : "(无CN)"));
                }
                Log.LogInfo($"[F12] 已载字体资产 {fontNames.Count} 个：{string.Join(";", fontNames)}");
                var dumped = 0;
                foreach (var text in Resources.FindObjectsOfTypeAll<TMP_Text>())
                {
                    if (text == null || string.IsNullOrEmpty(text.text))
                    {
                        continue;
                    }
                    var hasCjk = false;
                    foreach (var c in text.text)
                    {
                        if (c >= '一' && c <= '鿿')
                        {
                            hasCjk = true;
                            break;
                        }
                    }
                    if (!hasCjk)
                    {
                        continue;
                    }
                    var font = text.font;
                    var chain = new List<string>();
                    Transform t = text.transform;
                    while (t != null && chain.Count < 6)
                    {
                        chain.Add(t.name);
                        t = t.parent;
                    }
                    var rect = text.rectTransform != null ? text.rectTransform.rect.ToString() : "?";
                    var charCount = -1;
                    try
                    {
                        charCount = text.textInfo.characterCount;
                    }
                    catch (Exception)
                    {
                        // textInfo 未就绪时记 -1。
                    }
                    Log.LogInfo(
                        $"[F12] CJK文本 \"{(text.text.Length <= 18 ? text.text : text.text.Substring(0, 18) + "…")}\" " +
                        $"font={(font == null ? "null" : font.name)} 已挂CN={HasChineseFallback(font)} " +
                        $"mat={(text.fontSharedMaterial == null ? "null" : text.fontSharedMaterial.name)} " +
                        $"size={text.fontSize} active={text.isActiveAndEnabled} rect={rect} " +
                        $"chars={charCount} verts={MeshVertexSummary(text)} " +
                        $"cull={(text.canvasRenderer == null ? "?" : text.canvasRenderer.cull.ToString())} 链={string.Join("<", chain)}");
                    dumped++;
                }
                Log.LogInfo($"[F12] CJK 文本转储完成，共 {dumped} 条。");
            }
            catch (Exception exception)
            {
                Log.LogWarning($"[F12] 诊断转储失败：{exception}");
            }
        }

        private static void OnSceneLoaded(Scene scene, LoadSceneMode mode)
        {
            RefreshFonts($"scene:{scene.name}");
            InjectAlternativeLabels($"scene:{scene.name}");
        }

        // v2.2.16：作者手写 <link="英文标签"> 的文本（如 <link="Mansus">太阳的居屋</link>）
        // 在中文界面依赖 alternativeLabels 备用通道解析（MatchFromAlternate）。烘焙器
        // 对 Footnote 等类型的别名推送因 TypeTreeGenerator 建模坑静默失效（其
        // alternativeLabels 被读成字符串）；v2.2.15 曾改原始布局写回，Unity 判定
        // resources.assets 损坏（启动崩溃），已回退。改为运行时注入：中文模式下为每个
        // 脚注补上英文原标签，注入后刷新 curator 的别名缓存。英文模式标签即英文，
        // 无需注入。
        private static bool _altLabelsInjected;
        private static bool _overflowFixLogged;

        // 搜索行字体直换（v2.4.2）：行标签含 CJK 时把 TMP 字体直接换成中文字体，
        // 无 CJK 时还原。绕过游戏动态字体字符表里的空字形对 fallback 的抢占。
        private static readonly ConditionalWeakTable<TMP_Text, OriginalFontHolder> OriginalFonts =
            new ConditionalWeakTable<TMP_Text, OriginalFontHolder>();

        private sealed class OriginalFontHolder
        {
            internal TMP_FontAsset Font;
        }

        // 交换后复注入：交换过程会按映射改写 alternativeLabels 列表内容，
        // 可能把注入的英文别名换掉；每趟交换结束重置标记并在中文态复注入。
        internal static void RequestAlternativeLabelsInjection()
        {
            _altLabelsInjected = false;
            InjectAlternativeLabels("swap");
        }

        // 交换开始时失效 curator 惰性缓存（ByLabel 字典/别名映射），让后续
        // 链接解析按当前语言重建。见 LanguageSwap.RunSwapPass 的 v2.4.12 注记。
        internal static void RequestCuratorCacheRefresh()
        {
            try
            {
                Travelling.PCQualities.QHelper.GetScriptablesCuratorSafe()?.ForceRefresh();
            }
            catch (Exception exception)
            {
                Log.LogWarning($"curator 缓存失效失败：{exception.Message}");
            }
        }

        // 捏人链接白名单（CharGenLinkWhitelist._labels）是惰性缓存：首次求值按
        // 当时语言的 label 建集合，F9 换语言后谓词拿新语言 label 去查旧集合必然
        // 失配，捏人界面 tooltip/详情的链接被剥成裸文本（v2.5.0 用户实测：心念
        // 说明里英文态 Experiences/Aspect 变裸文本）。交换完成后清空缓存，让
        // 下次求值按当前语言重建。
        internal static void ResetCharGenLinkWhitelistCache()
        {
            try
            {
                var whitelistType = FindTypeByName("CharGenLinkWhitelist");
                if (whitelistType == null)
                {
                    return;
                }
                var labelsField = whitelistType.GetField("_labels", BindingFlags.Instance | BindingFlags.NonPublic);
                if (labelsField == null)
                {
                    return;
                }
                var cleared = 0;
                foreach (var whitelist in Resources.FindObjectsOfTypeAll(whitelistType))
                {
                    if (whitelist != null && labelsField.GetValue(whitelist) != null)
                    {
                        labelsField.SetValue(whitelist, null);
                        cleared++;
                    }
                }
                if (cleared > 0)
                {
                    Log.LogInfo($"已失效 {cleared} 个捏人链接白名单缓存（按当前语言重建）。");
                }
            }
            catch (Exception exception)
            {
                Log.LogWarning($"捏人链接白名单缓存失效失败：{exception.Message}");
            }
        }

        private static void InjectAlternativeLabels(string reason)
        {
            if (_altLabelsInjected || LanguageSwap.IsEnglishMode)
            {
                return;
            }
            try
            {
                var added = 0;
                foreach (var footnote in Resources.FindObjectsOfTypeAll<Travelling.Infrastructure.Footnotes.Footnote>())
                {
                    if (footnote == null || string.IsNullOrEmpty(footnote.label))
                    {
                        continue;
                    }
                    // 列表卫生：去空、去重、去与主标签相同的自映射项。历史交换
                    // 曾把别名换成主标签同语副本并逐趟膨胀（v2.4.14），交换端
                    // 已改为不碰此字段，这里兜底清理存量。
                    footnote.alternativeLabels.RemoveAll(string.IsNullOrEmpty);
                    footnote.alternativeLabels.RemoveAll(a => a == footnote.label);
                    var seenAliases = new HashSet<string>(StringComparer.Ordinal);
                    footnote.alternativeLabels.RemoveAll(a => !seenAliases.Add(a));
                    if (!LanguageSwap.TryGetEnglishLabel(footnote.id, footnote.label, out var english) ||
                        string.IsNullOrEmpty(english) || english == footnote.label)
                    {
                        continue;
                    }
                    if (!footnote.alternativeLabels.Contains(english))
                    {
                        footnote.alternativeLabels.Add(english);
                        added++;
                    }
                }
                if (added > 0)
                {
                    Travelling.PCQualities.QHelper.GetScriptablesCuratorSafe()?.ForceRefresh();
                    Log.LogInfo($"已为 {added} 个脚注注入英文别名（{reason}）。");
                }
                _altLabelsInjected = true;
            }
            catch (Exception exception)
            {
                Log.LogWarning($"注入脚注英文别名失败（{reason}）：{exception.Message}");
            }
        }

        private IEnumerator FontRefreshLoop()
        {
            // 启动后的数十秒内 TMP 全局设置与各场景字体陆续就绪；只做字体挂载，
            // 不触碰任何文本内容。
            for (var attempt = 0; attempt < 20; attempt++)
            {
                yield return new WaitForSecondsRealtime(attempt < 5 ? 1f : 3f);
                RefreshFonts($"startup:{attempt + 1}");
                InjectAlternativeLabels($"startup:{attempt + 1}");
            }
            // 启动密集巡检后转入低频常驻巡检（v2.3.5）：运行时按需实例化的
            // 预制体（如脚注搜索结果行）其字体资产可能从未被启动窗口覆盖，
            // 中文因此渲染成空白——周期性补挂兜底。
            for (var steady = 1; ; steady++)
            {
                yield return new WaitForSecondsRealtime(15f);
                RefreshFonts($"steady:{steady}");
                InjectAlternativeLabels($"steady:{steady}");
            }
        }

        private static void RefreshFonts(string reason)
        {
            try
            {
                if (!GlobalFallbackInstalled && EnsureGlobalChineseFallback())
                {
                    Log.LogInfo($"TMP 全局设置现已就绪（{reason}），已补装中文 fallback 字体。");
                }
                // 直接扫描字体资产：仅被预制体引用的字体（如脚注搜索结果行）
                // 在 TMP 实例化前就可挂上中文 fallback，防止运行时新实例中文空白。
                var newlyCovered = 0;
                foreach (var fontAsset in Resources.FindObjectsOfTypeAll<TMP_FontAsset>())
                {
                    if (AttachChineseFallback(fontAsset))
                    {
                        newlyCovered++;
                    }
                }
                foreach (var text in Resources.FindObjectsOfTypeAll<TMP_Text>())
                {
                    if (text == null)
                    {
                        continue;
                    }
                    var had = HasChineseFallback(text.font);
                    AttachChineseFallback(text.font);
                    ApplyChineseFontScale(text);
                    if (!had && HasChineseFallback(text.font))
                    {
                        // 字体刚挂上 fallback：既有网格是按缺字形建的（渲染空白），
                        // 强制重解析重建（v2.3.5 实测：仅挂 fallback 不刷新网格，
                        // 脚注搜索结果行的中文仍不可见）。
                        try
                        {
                            text.ForceMeshUpdate(true, true);
                        }
                        catch (Exception)
                        {
                            // 单个文本刷新失败不影响整体。
                        }
                    }
                }
                if (newlyCovered > 0)
                {
                    Log.LogInfo($"字体巡检（{reason}）：新挂载 {newlyCovered} 个字体资产。");
                }
            }
            catch (Exception exception)
            {
                Log.LogWarning($"挂载中文字体时发生异常（{reason}）：{exception}");
            }
        }

        private static void InstallChineseFont()
        {
            try
            {
                var fontPath = Path.Combine(PluginDirectory, "font", "NotoSansCJKsc-Regular.otf");
                if (!File.Exists(fontPath))
                {
                    Log.LogError($"未找到中文字体：{fontPath}");
                    return;
                }
                ChineseFont = TMP_FontAsset.CreateFontAsset(
                    fontPath,
                    0,
                    48,
                    5,
                    GlyphRenderMode.SDFAA,
                    2048,
                    2048);
                if (ChineseFont == null)
                {
                    Log.LogError("TextMeshPro 无法创建中文字体资产。");
                    return;
                }
                ChineseFont.name = "Noto Sans CJK SC Regular Dynamic (TravellingCN)";
                ChineseFont.atlasPopulationMode = AtlasPopulationMode.Dynamic;
                ChineseFont.isMultiAtlasTexturesEnabled = true;
                UnityEngine.Object.DontDestroyOnLoad(ChineseFont);
                if (!EnsureGlobalChineseFallback())
                {
                    Log.LogWarning("TMP 全局设置尚未就绪；稍后将再次挂载中文 fallback 字体。");
                }
                Log.LogInfo("中文动态字体已安装。字符将在首次显示时按需生成。");
            }
            catch (Exception exception)
            {
                Log.LogError($"安装中文字体失败：{exception}");
            }
        }

        private static bool _globalFallbackFailureLogged;

        private static bool EnsureGlobalChineseFallback()
        {
            if (ChineseFont == null)
            {
                return false;
            }
            if (GlobalFallbackInstalled)
            {
                return true;
            }
            try
            {
                var fallbacks = TMP_Settings.fallbackFontAssets;
                if (fallbacks == null)
                {
                    fallbacks = new List<TMP_FontAsset>();
                    TMP_Settings.fallbackFontAssets = fallbacks;
                }
                if (!fallbacks.Contains(ChineseFont))
                {
                    fallbacks.Insert(0, ChineseFont);
                }
                GlobalFallbackInstalled = true;
                return true;
            }
            catch (Exception exception)
            {
                // v2.3.6：首次失败时记录原因（此前静默，排障无据）。
                if (!_globalFallbackFailureLogged)
                {
                    _globalFallbackFailureLogged = true;
                    Log.LogWarning($"TMP 全局 fallback 挂载失败（转为按字体逐个补挂）：{exception.Message}");
                }
                return false;
            }
        }

        private static bool HasChineseFallback(TMP_FontAsset font)
        {
            return font != null &&
                   font.fallbackFontAssetTable != null &&
                   font.fallbackFontAssetTable.Contains(ChineseFont);
        }

        // 返回是否为本次新挂载（供调用方强制重建已按缺字形渲染的空白网格）。
        private static bool AttachChineseFallback(TMP_FontAsset font)
        {
            if (font == null || ChineseFont == null || font == ChineseFont)
            {
                return false;
            }
            var fallbacks = font.fallbackFontAssetTable;
            if (fallbacks == null)
            {
                fallbacks = new List<TMP_FontAsset>();
                font.fallbackFontAssetTable = fallbacks;
            }
            if (!fallbacks.Contains(ChineseFont))
            {
                fallbacks.Insert(0, ChineseFont);
                return true;
            }
            return false;
        }

        private static void ApplyChineseFontScale(TMP_Text text)
        {
            if (text == null || ChineseFontScale <= 1f)
            {
                return;
            }
            if (!OriginalFontSizes.TryGetValue(text, out var original))
            {
                original = text.fontSize;
                OriginalFontSizes[text] = original;
            }
            // 自动字号已随可用矩形自适应，二次放大只会增加裁切风险。
            if (!text.enableAutoSizing)
            {
                text.fontSize = original * ChineseFontScale;
            }
        }

        private static void LoadRawLabelMap()
        {
            RawLabelByChineseLabel.Clear();
            var path = Path.Combine(PluginDirectory, "raw_labels.json");
            if (!File.Exists(path))
            {
                Log.LogWarning($"未找到 RawLabel 映射：{path}；技能检定图标可能显示异常。");
                return;
            }
            try
            {
                var loaded = JsonConvert.DeserializeObject<Dictionary<string, string>>(
                    File.ReadAllText(path));
                if (loaded != null)
                {
                    foreach (var pair in loaded)
                    {
                        if (!string.IsNullOrEmpty(pair.Key) && !string.IsNullOrEmpty(pair.Value))
                        {
                            RawLabelByChineseLabel[pair.Key] = pair.Value;
                        }
                    }
                }
            }
            catch (Exception exception)
            {
                Log.LogError($"RawLabel 映射无法解析：{exception}");
            }
        }

        [HarmonyPatch(
            typeof(Travelling.PCQualities.Skill),
            "get_RawLabel")]
        private static class SkillRawLabelPatch
        {
            private static void Postfix(Travelling.PCQualities.Skill __instance, ref string __result)
            {
                // RawLabel 是 sprite 图集的内部键。资产烘焙后 _label 已是中文，
                // 直接返回会让游戏拼出 <sprite name="口才"> 这类无效标签并被
                // TMP 原样显示；按烘焙时生成的映射还原英文键。
                if (__result != null &&
                    RawLabelByChineseLabel.TryGetValue(__result, out var english))
                {
                    __result = english;
                }
            }
        }

        // 场景浮签（WorldPopup）显示时由 ComposeWrapped 把 _authoredBaseText
        // （烘焙中文，Awake 捕获后不再变）等段按字符数断行。英文模式下在此把
        // 各段换回英文，游戏随后的断行与米纸条重建（RebuildLineStrips 按行量宽）
        // 就都作用在英文上——新弹出的浮签语言、换行、纸条底三者一致。
        // 已显示浮签的切换重排见 LanguageSwap.RefreshVisibleWorldPopups。
        [HarmonyPatch(
            typeof(Travelling.Interactables.WorldPopup),
            nameof(Travelling.Interactables.WorldPopup.ComposeWrapped))]
        private static class WorldPopupComposeWrappedPatch
        {
            private static void Prefix(ref IEnumerable<string> segments)
            {
                if (segments == null)
                {
                    return;
                }
                segments = segments.Select(LanguageSwap.SwapPopupSegment).ToArray();
            }
        }

        // v2.3.8 脚注搜索结果行中文空白探针：资产/字体/挂载全部正常但行标签渲染
        // 空白（英文正常；F9 重写文本后可见）。在 DetailableDisplay.PopulateWith
        // 之后对搜索行（父链含 fsr_/SearchResultsContainer）做网格级探针并强制
        // 重建网格——既取决定性数据（顶点数/cull 状态），也可能即时修复。
        [HarmonyPatch(
            typeof(Travelling.UI.DetailableDisplay),
            "PopulateWith")]
        private static class SearchResultLabelProbePatch
        {
            private static FieldInfo _labelTextField;

            private static void Postfix(Travelling.UI.DetailableDisplay __instance)
            {
                try
                {
                    if (__instance == null)
                    {
                        return;
                    }
                    var inSearchResults = false;
                    for (var t = __instance.transform; t != null; t = t.parent)
                    {
                        if (t.name.StartsWith("fsr_") || t.name.Contains("SearchResultsContainer"))
                        {
                            inSearchResults = true;
                            break;
                        }
                    }
                    if (!inSearchResults)
                    {
                        return;
                    }
                    if (_labelTextField == null)
                    {
                        _labelTextField = typeof(Travelling.UI.DetailableDisplay).GetField(
                            "_labelText", BindingFlags.Instance | BindingFlags.NonPublic);
                    }
                    if (_labelTextField?.GetValue(__instance) is not TMP_Text label || label == null)
                    {
                        return;
                    }
                    var rowText = label.text ?? string.Empty;
                    try
                    {
                        // v2.4.8 根治：搜索结果行 TMP 是 Ellipsis 截断 + 固定行高矩形；
                        // CJK 经后备字体渲染的行高溢出即被整行截掉（同面板 Overflow
                        // 模式的占位符不受影响）。改 Overflow 后网格正常生成。
                        if (label.overflowMode != TextOverflowModes.Overflow)
                        {
                            label.overflowMode = TextOverflowModes.Overflow;
                            label.SetText(rowText);
                            label.ForceMeshUpdate(true, true);
                            if (!_overflowFixLogged)
                            {
                                _overflowFixLogged = true;
                                Log.LogInfo("脚注搜索结果行：溢出模式已由截断改为 Overflow（修复 CJK 文本整行被截的空白问题）。");
                            }
                        }
                    }
                    catch (Exception exception)
                    {
                        Log.LogWarning($"[populate] 搜索行修复失败：{exception.Message}");
                    }
                }
                catch (Exception exception)
                {
                    Log.LogWarning($"[populate] 搜索行处理失败：{exception.Message}");
                }
            }
        }
    }
}
