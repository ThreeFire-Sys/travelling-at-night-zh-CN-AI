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
        public const string PluginVersion = "2.4.8";

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
            if (_autoProbeSearch.Value)
            {
                StartCoroutine(AutoProbeSearchRoutine());
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
                    if (!LanguageSwap.TryGetEnglishLabel(footnote.label, out var english) ||
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
