#!/usr/bin/env python3
"""Static contract test for the slim (asset-bake era) TravellingCN plugin.

The baked build's plugin must never rewrite text: v2.0.1 proved that any
startup-sweep write can restore stale placeholders over game-assigned content.
This test locks the slim profile's surface: font-only refresh, the Skill
RawLabel remap, and the absence of every text-interception construct."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = (ROOT / "src" / "TravellingCN" / "Plugin.cs").read_text(encoding="utf-8")
LANGUAGE_SWAP = (ROOT / "src" / "TravellingCN" / "LanguageSwap.cs").read_text(encoding="utf-8")
ALL_SOURCES = PLUGIN + "\n" + LANGUAGE_SWAP


def main() -> int:
    errors: list[str] = []
    checks = 0

    def require(name: str, condition: bool) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(name)

    version_match = re.search(r'PluginVersion = "([^"]+)"', PLUGIN)
    require(
        "plugin version is a BepInEx-parseable System.Version",
        bool(version_match) and
        bool(re.fullmatch(r"\d+(\.\d+){1,3}", version_match.group(1))),
    )
    require("plugin guid stable", 'PluginGuid = "cn.nyctodromy.travelling.zhcn"' in PLUGIN)
    require("dynamic CJK font install", "NotoSansCJKsc-Regular.otf" in PLUGIN)
    require("global fallback install", "TMP_Settings.fallbackFontAssets" in PLUGIN)
    require("per-font fallback attach", "fallbackFontAssetTable" in PLUGIN)
    require("font scale clamp", "Mathf.Clamp(_fontScale.Value, 1f, 1.10f)" in PLUGIN)
    require("skill rawlabel patch", "get_RawLabel" in PLUGIN)
    require("raw label map file", "raw_labels.json" in PLUGIN)
    require("scene-load font refresh", "SceneManager.sceneLoaded" in PLUGIN)

    forbidden = {
        "TMP text setter patch": "TmpTextSetterPatch",
        "TMP SetText patch": "TmpSetTextMethodPatch",
        "typewriter input patch": "DialogueTypewriterInputPatch",
        "subtitle buffer patch": "SubtitleBufferSourcePatch",
        "original text cache": "OriginalTextValues",
        "composite relocalizer": "RelocalizeCompositeText",
        "buffer line pipeline": "LocalizeDialogueBufferChinese",
        "language toggle": "ToggleLanguage",
        "catalog load": "catalog.zh-CN.json",
        "diag logging": "DiagRecord",
    }
    for name, needle in forbidden.items():
        require(f"slim plugin must not contain {name}", needle not in PLUGIN)
        require(f"language swap must not contain {name}", needle not in LANGUAGE_SWAP)

    # LanguageSwap: in-memory string-field swap only — no new Harmony patches,
    # no render-pipeline interception, no asset writes.
    require("swap map file load", "lang_swap.json" in LANGUAGE_SWAP)
    require("swap scans all loaded objects", "FindObjectsOfTypeAll" in LANGUAGE_SWAP)
    require("swap resweeps on scene load", "SceneManager.sceneLoaded" in LANGUAGE_SWAP)
    require("swap handles TMP text", "TMP_Text" in LANGUAGE_SWAP)
    require("swap reflects game data fields", "GetFields(" in LANGUAGE_SWAP)
    require("swap gated by config", '"LanguageSwap"' in LANGUAGE_SWAP)
    require("plugin wires language swap", "LanguageSwap.Initialize" in PLUGIN)
    require("plugin ticks language swap", "LanguageSwap.Tick" in PLUGIN)
    require("language swap adds no harmony patch", "HarmonyPatch" not in LANGUAGE_SWAP)
    require("language swap adds no harmony lib", "HarmonyLib" not in LANGUAGE_SWAP)

    # LanguageSwap tiered display swap: template tier (compiled anchored regex,
    # manual segment reassembly) and substring tier (safe-key filter, first-char
    # buckets, longest-first, rich-text tags skipped, single left-to-right pass).
    require("template placeholder detection", "PlaceholderPattern" in LANGUAGE_SWAP)
    require("template regex escape", "Regex.Escape" in LANGUAGE_SWAP)
    require("template anchored fullmatch", '"^"' in LANGUAGE_SWAP and '"$"' in LANGUAGE_SWAP)
    require("template literal prefilter", "FirstLiteral" in LANGUAGE_SWAP)
    require("template longest-literal-first sort", "LiteralLength" in LANGUAGE_SWAP)
    require("template capture recursion depth cap", "MaxSwapDepth" in LANGUAGE_SWAP)
    require("substring cjk threshold", "MinCjkCharsForSubstring = 2" in LANGUAGE_SWAP)
    require("substring latin threshold", "MinLatinLengthForSubstring = 4" in LANGUAGE_SWAP)
    require("substring latin word boundary", "NeedsWordBoundary" in LANGUAGE_SWAP)
    require("substring latin letter check", "IsLatinLetter" in LANGUAGE_SWAP)
    require("substring first-char buckets", "SubstringBuckets" in LANGUAGE_SWAP)
    require("substring skips rich text tags", "IndexOf('>'" in LANGUAGE_SWAP)
    require("per-tier swap counters", "SwapCounters" in LANGUAGE_SWAP)
    require("field swap stays exact-only", "map.Exact" in LANGUAGE_SWAP)

    # DialogueSystem Field guard (v2.1.3 crash fix): only the value field of a
    # whitelisted-text-title Field may be swapped; structural titles like
    # "Name" must never be rewritten (LookupValue("Name") null -> crash).
    require("field type guard by full name", '"PixelCrushers.DialogueSystem.Field"' in LANGUAGE_SWAP)
    require("field title whitelist", "DialogueTextFieldTitles" in LANGUAGE_SWAP)
    require("field whitelist core titles", '"Dialogue Text"' in LANGUAGE_SWAP and '"Menu Text"' in LANGUAGE_SWAP)
    require("skillcheck description title regex", r"^SkillCheckModifier_\d+_Description$" in LANGUAGE_SWAP)
    require("field narrowed to title/value", '"title"' in LANGUAGE_SWAP and '"value"' in LANGUAGE_SWAP)
    require("field narrow path", "SwapDialogueFieldValue" in LANGUAGE_SWAP)

    # Display pipeline: tagless exact tier, text-segment exact tier, plain-text
    # substring scan with original-index mapping; Settle re-decorates [[Y]] via
    # the game's native link colourizer (v2.1.5) so link colours follow the
    # live read/unread state instead of frozen copied wrappers.
    require("tagless exact tier", "TaglessExact" in LANGUAGE_SWAP)
    require("strip tags helper", "StripTags" in LANGUAGE_SWAP)
    require("text segment exact tier", "SegmentExact" in LANGUAGE_SWAP)
    require("segment swap method", "SwapTextSegmentsExact" in LANGUAGE_SWAP)
    require("plain text index mapping", "indexMap" in LANGUAGE_SWAP)
    require("plain substring scan method", "SwapPlainTextSubstrings" in LANGUAGE_SWAP)
    require("settle step", "SettleLinks" in LANGUAGE_SWAP)
    require("bracket link pattern", r"\[\[([^\[\]]+)\]\]" in LANGUAGE_SWAP)
    require("native link decoration", "ResolveQualityTokensAndColourizeLinks" in LANGUAGE_SWAP)
    require("native link style", "LinkStyle.Default" in LANGUAGE_SWAP)
    require("visited links kept", "hideVisitedLinks: false" in LANGUAGE_SWAP)
    require("native decoration failure logged once", "_nativeDecorateFailed" in LANGUAGE_SWAP)
    # Removed with the native-decoration switch (v2.1.5): wrapper extraction,
    # wrapper rebuild, link span expansion, link id rewrite.
    for gone in ("LinkWrapperPattern", "RebuildWrapper", "ExpandLinkWrapper", "LinkIdPattern"):
        require(f"obsolete wrapper mechanism removed: {gone}", gone not in LANGUAGE_SWAP)

    # v2.1.6: template-substring tier (unanchored template regex on plain text,
    # spans take priority over key-bucket scan) and accumulatedText routing
    # (subtitle panel history blob goes through the display-tier pipeline).
    require("template unanchored substring pattern", "SubstringPattern" in LANGUAGE_SWAP)
    require("template substring counter", "TemplateSubstring" in LANGUAGE_SWAP)
    require("template assembly shared", "AssembleTemplateSwap" in LANGUAGE_SWAP)
    require("template span overlap guard", "OverlapsTemplateSpan" in LANGUAGE_SWAP)
    require("plain to original mapping apply",
            "cursorOrig" in LANGUAGE_SWAP and "indexMap[span[0]]" in LANGUAGE_SWAP)
    require("trailing placeholder greedy", '"(.+)"' in LANGUAGE_SWAP)
    require("accumulatedText display-tier routing", '"accumulatedText"' in LANGUAGE_SWAP)
    require("accumulatedText routed to display swap",
            "SwapBufferByLines(stringValue, map, counters)" in LANGUAGE_SWAP and
            "TrySwapDisplayText(map, restCore, counters, 1" in LANGUAGE_SWAP)

    # v2.1.8: m_accumulatedText backing-field routing (subtitle panel history is
    # a property backed by m_accumulatedText) and string-keyed dictionary rebuild
    # (ScriptablesCurator ByLabel dictionaries must follow the current language).
    require("m_accumulatedText backing field routing", '"m_accumulatedText"' in LANGUAGE_SWAP)
    require("dictionary key rebuild", "IDictionary" in LANGUAGE_SWAP)
    require("dictionary rebuild method", "SwapDictionaryKeys" in LANGUAGE_SWAP)
    require("dictionary conflict counter", "DictionaryKeyConflict" in LANGUAGE_SWAP)
    require("dictionary collect-then-apply", "DictionaryEntry" in LANGUAGE_SWAP)
    require("dictionary conflict skip", "dictionary.Contains(newKey)" in LANGUAGE_SWAP)

    # v2.1.9: typewriter guard, two-phase swap pass, panel link colour
    # inheritance, DebugLog diagnostics.
    require("typewriter guard", "IsTypewriterPlaying" in LANGUAGE_SWAP)
    require("typewriter component name", '"TravellingTypewriter"' in LANGUAGE_SWAP)
    require("typewriter isPlaying reflection", '"isPlaying"' in LANGUAGE_SWAP)
    require("typewriter check cache", "TypewriterCheckInterval" in LANGUAGE_SWAP)
    require("two phase swap pass", "阶段一" in LANGUAGE_SWAP and "阶段二" in LANGUAGE_SWAP)
    require("link color inheritance", "TryExtractLinkColor" in LANGUAGE_SWAP)
    require("link color regex", "LinkColorPattern" in LANGUAGE_SWAP)
    require("html color parse", "ColorUtility.TryParseHtmlString" in LANGUAGE_SWAP)
    require("default style colors cached", "TryGetDefaultStyleColors" in LANGUAGE_SWAP)
    require("viewed link color field", '"viewedLinkColor"' in LANGUAGE_SWAP)
    require("broken link color field", '"brokenLinkColor"' in LANGUAGE_SWAP)
    require("settle passes source text", "SettleLinks(exactValue, text)" in LANGUAGE_SWAP)
    require("debug log config", '"DebugLog"' in LANGUAGE_SWAP)
    require("mixed language detector", "IsMixedLanguage" in LANGUAGE_SWAP)
    require("log truncation helper", "TruncateForLog" in LANGUAGE_SWAP)

    # v2.1.10: read-only stale-field detector pass (DebugLog only) that reports
    # values still matching the forward direction's keys after a swap.
    require("stale detector method", "ReportStaleFields" in LANGUAGE_SWAP)
    require("stale inspector", "InspectStaleFields" in LANGUAGE_SWAP)
    require("stale report cap", "MaxStaleReports = 30" in LANGUAGE_SWAP)
    require("stale report log", "陈旧文本" in LANGUAGE_SWAP)
    require("stale detector gated by debug log",
            "if (_debugLog.Value)" in LANGUAGE_SWAP and "ReportStaleFields(map, reason)" in LANGUAGE_SWAP)

    # v2.1.11: speaker-name three-layer cache fix — dictionary value recursion
    # (CharacterInfo cache), <sprite=N> prefix tolerance, Lua snapshot sync.
    require("dictionary value recursion", "SwapDictionaryKeys(dictionary, map, counters, seen)" in LANGUAGE_SWAP)
    require("dictionary nested values list", "nestedValues" in LANGUAGE_SWAP)
    require("sprite prefix strip", "TryStripSpritePrefix" in LANGUAGE_SWAP)
    require("sprite prefix marker", '"<sprite="' in LANGUAGE_SWAP)
    require("lua sync method", "SyncLuaActorDisplayNames" in LANGUAGE_SWAP)
    require("lua sync call in pass", "SyncLuaActorDisplayNames();" in LANGUAGE_SWAP)
    require("lua master database", "DialogueManager.masterDatabase" in LANGUAGE_SWAP)
    require("lua set actor field", "DialogueLua.SetActorField(" in LANGUAGE_SWAP)
    require("lua display name field", '"Display Name"' in LANGUAGE_SWAP)
    require("lua name key via lookup", 'Field.LookupValue(actor.fields, "Name")' in LANGUAGE_SWAP)

    print(json.dumps({"checks": checks, "errors": errors, "error_count": len(errors)}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
