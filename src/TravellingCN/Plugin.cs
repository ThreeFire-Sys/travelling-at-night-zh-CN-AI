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
        public const string PluginVersion = "2.3.0";

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

            RefreshFonts("awake");
            SceneManager.sceneLoaded += OnSceneLoaded;
            StartCoroutine(FontRefreshLoop());
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
        }

        private static void RefreshFonts(string reason)
        {
            try
            {
                if (!GlobalFallbackInstalled && EnsureGlobalChineseFallback())
                {
                    Log.LogInfo($"TMP 全局设置现已就绪（{reason}），已补装中文 fallback 字体。");
                }
                foreach (var text in Resources.FindObjectsOfTypeAll<TMP_Text>())
                {
                    if (text == null)
                    {
                        continue;
                    }
                    AttachChineseFallback(text.font);
                    ApplyChineseFontScale(text);
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
            catch
            {
                return false;
            }
        }

        private static void AttachChineseFallback(TMP_FontAsset font)
        {
            if (font == null || ChineseFont == null || font == ChineseFont)
            {
                return;
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
            }
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
    }
}
