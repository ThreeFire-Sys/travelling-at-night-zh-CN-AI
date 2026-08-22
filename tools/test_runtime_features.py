#!/usr/bin/env python3
"""Static regression checks for runtime localisation features.

These checks intentionally cover behavioural source contracts, rather than
only looking for feature names anywhere in Plugin.cs.  The live smoke test is
still authoritative for rendered output, but this file prevents the known F9
and character-generation regressions from reaching that stage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = (ROOT / "src" / "TravellingCN" / "Plugin.cs").read_text(encoding="utf-8-sig")
CSPROJ = (ROOT / "src" / "TravellingCN" / "TravellingCN.csproj").read_text(
    encoding="utf-8-sig"
)
SEND_KEY = (ROOT / "tools" / "send_key_to_travelling.ps1").read_text(
    encoding="utf-8-sig"
)
COSMETIC_MARKUP_RE = re.compile(
    r"<(?P<close>/)?(?P<name>i|b|u|s|em)(?:\s+[^>]*)?>", re.IGNORECASE
)
WIKI_LINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
TMP_TAG_RE = re.compile(r"<[^>]*>")


def load_translations(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for chunk in sorted(path.glob("chunk_*.jsonl")):
        for line in chunk.read_text(encoding="utf-8-sig").splitlines():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def extract_method_body(source: str, signature: str) -> str:
    """Return a C# method body using balanced braces.

    This is deliberately small, but unlike split()/substring assertions it
    cannot be satisfied by a similarly named method or a token elsewhere in
    the file.
    """

    start = source.find(signature)
    if start < 0:
        raise ValueError(f"method signature not found: {signature}")
    opening = source.find("{", start + len(signature))
    if opening < 0:
        raise ValueError(f"method body not found: {signature}")
    depth = 0
    for index in range(opening, len(source)):
        character = source[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index]
    raise ValueError(f"unterminated method body: {signature}")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_lookup_text(value: str) -> str:
    value = WIKI_LINK_RE.sub(lambda match: match.group(1), value)
    value = COSMETIC_MARKUP_RE.sub("", value)
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ").strip()


def canonicalize_cosmetic_markup(value: str) -> str:
    return COSMETIC_MARKUP_RE.sub(
        lambda match: "\ue100"
        + ("/" if match.group("close") else "")
        + match.group("name").lower()
        + "\ue101",
        value,
    )


def restore_cosmetic_markup(value: str) -> str:
    return re.sub(
        r"\ue100(?P<close>/)?(?P<name>i|b|u|s|em)\ue101",
        lambda match: "<"
        + ("/" if match.group("close") else "")
        + match.group("name").lower()
        + ">",
        value,
        flags=re.IGNORECASE,
    )


def replace_standalone_visible_token(value: str, token: str, replacement: str) -> str:
    pattern = re.compile(rf"(?<![^\W_]){re.escape(token)}(?![^\W_])", re.UNICODE)
    return pattern.sub(replacement, value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translations", type=Path, default=ROOT / "translations_k97")
    parser.add_argument(
        "--catalog", type=Path, default=ROOT / "build/merged_k97/catalog.zh-CN.json"
    )
    args = parser.parse_args()
    # The pre-bake interceptor profile was retired in v2.0.  Keep this legacy
    # entry point callable, but route the current asset-bake plugin to its
    # authoritative 119-check contract instead of asserting removed patches.
    if "OriginalTextValues" not in PLUGIN:
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools/test_slim_plugin.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        print(result.stdout.strip())
        if result.stderr.strip():
            print(result.stderr.strip())
        if result.returncode:
            raise SystemExit(result.returncode)
        print(json.dumps({"profile": "asset-bake", "delegated_to": "test_slim_plugin.py"}))
        return
    errors: list[str] = []
    checks = 0

    def require(name: str, condition: bool) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(name)

    required = {
        "plugin version 2.6.2": 'PluginVersion = "2.6.2"',
        "F9 default shortcut": "new KeyboardShortcut(KeyCode.F9)",
        "toggle update loop": "_toggleShortcut.Value.IsDown()",
        "English restore": "RestoreOriginalValues();",
        "member originals": "OriginalMemberValues",
        "list originals": "OriginalListValues",
        "text originals": "OriginalTextValues",
        "font size originals": "OriginalFontSizes",
        "bounded font scale": "Mathf.Clamp(_fontScale.Value, 1f, 1.10f)",
        "static regular font": "NotoSansCJKsc-Regular.otf",
        "rendered link canonicalisation": "CanonicalizeRenderedLinks",
        "isolated Harmony patch installation": "CreateClassProcessor(patchType).Patch()",
        "quality-link terminal-overload compatibility": "parameters.Length >= 6",
        "standalone dialogue speaker localisation": "StandaloneMeRegex.Replace(result, translatedMe)",
        "world-popup language reflow": "RefreshVisibleWorldPopups();",
        "conversation Description patch": '"Dialogue Text", "Menu Text", "Description"',
        "InputLegacy reference": "UnityEngine.InputLegacyModule",
        "IMGUI reference": "UnityEngine.IMGUIModule",
        "suppressed internal text writes": "TextWriteSuppressionDepth",
        "TMP SetText overload patch": "TmpSetTextMethodPatch",
        "cached language application": "ApplyCachedLanguageValues(true);",
        "tracked curator refresh": "GetLiveTrackedCurators()",
        "toggle timing evidence": "同步应用耗时",
        "decorated splice lookup": "TrySpliceDecoratedTranslation",
        "query pattern matcher": "TryMatchTranslationPattern",
        "query pattern catalog load": "patterns.zh-CN.json",
        "stripped composite variants": "AppendStrippedCompositePairs",
        "stripped reverse disambiguation": "AppendStrippedReverseCompositePairs",
        "dynamic argument localisation": "TranslateDynamicValue",
        "chance-prefix trim": r'@"^\s*\[\d{1,3}%\]\s*"',
        "ascii word-boundary composite guard": "ReplaceRespectingAsciiWordBoundaries",
        "wiki label prefix trim": "LeadingWikiLabelRegex",
        "tolerant reverse source fallback": "TryGetAnyKnownSource",
        "content-level reverse chain": "TryRestoreContentEnglish",
        "spliced label prefix translation": "TranslateSplicedLabelPrefix",
    }
    for name, needle in required.items():
        require(name, needle in PLUGIN or needle in CSPROJ)
    version_match = re.search(r'PluginVersion = "([^"]+)"', PLUGIN)
    # BepInEx silently skips a plugin whose version string cannot be parsed as
    # System.Version; suffixes like "-diag" must never reach a build.
    require(
        "plugin version is a BepInEx-parseable System.Version",
        bool(version_match) and
        bool(re.fullmatch(r"\d+(\.\d+){1,3}", version_match.group(1))),
    )
    require(
        "one changed Harmony target must not abort all runtime patches",
        ".PatchAll(" not in PLUGIN,
    )
    require(
        "every runtime patch class must resolve at least one target or fail explicitly",
        "patchedMethods == null || patchedMethods.Count == 0" in PLUGIN
        and "failedPatchClasses++;" in PLUGIN
        and "未解析到任何目标方法" in PLUGIN,
    )
    require(
        "plugin still loads the thin-default variable font",
        re.search(r"NotoSansSC-VF\.ttf", PLUGIN) is None,
    )
    rows = load_translations(args.translations)
    runtime_catalog_path = args.catalog
    runtime_catalog = json.loads(runtime_catalog_path.read_text(encoding="utf-8-sig"))

    # Exercise the two concrete strings from the reported screenshots. These
    # are behavioural model checks over the real j.66 catalogue, not merely
    # token-presence checks against Plugin.cs.
    normalized_targets: dict[str, str] = {}
    ambiguous_normalized: set[str] = set()
    for row in rows.values():
        source = row.get("source", "")
        target = runtime_catalog.get(sha256_text(source))
        if not source or not target:
            continue
        key = normalize_lookup_text(source)
        existing = normalized_targets.get(key)
        if existing is None and key not in ambiguous_normalized:
            normalized_targets[key] = target
        elif existing is not None and normalize_lookup_text(existing) != normalize_lookup_text(target):
            normalized_targets.pop(key, None)
            ambiguous_normalized.add(key)

    papers = rows.get("TAN-10C6A32F2D49")
    require("missing Leon papers screenshot fixture", papers is not None)
    if papers is not None:
        plain_papers = COSMETIC_MARKUP_RE.sub("", papers["source"])
        require(
            "response text with stripped italics must still resolve its Chinese translation",
            normalized_targets.get(normalize_lookup_text(plain_papers))
            == runtime_catalog.get(sha256_text(papers["source"])),
        )
        numbered_response = "2.  " + papers["source"]
        composite_response = canonicalize_cosmetic_markup(numbered_response).replace(
            canonicalize_cosmetic_markup(papers["source"]),
            runtime_catalog[sha256_text(papers["source"])],
        )
        composite_response = restore_cosmetic_markup(composite_response)
        require(
            "numbered response with inline italics must translate inside its composite button label",
            composite_response.startswith("2.  哦，我没有<i>证件</i>。")
            and "Oh, I don't have" not in composite_response,
        )

    dignify = rows.get("TAN-FC7ABFDB1FF0")
    require("missing Dignify description screenshot fixture", dignify is not None)
    if dignify is not None:
        authored = dignify["source"]
        localized = runtime_catalog.get(sha256_text(authored), "")
        require(
            "Dignify description must translate as a complete sentence before link resolution",
            localized.startswith("我会摆出一副威严而体面的模样")
            and "[[世俗技艺]]" in localized,
        )
        authored_links = WIKI_LINK_RE.findall(authored)
        link_index = 0

        def restore_authored_link(_: re.Match[str]) -> str:
            nonlocal link_index
            link = authored_links[link_index]
            link_index += 1
            return f"[[{link}]]"

        working = WIKI_LINK_RE.sub(restore_authored_link, localized)
        rendered = WIKI_LINK_RE.sub(
            lambda match: f'<color=#D33><link="{match.group(1)}">{match.group(1)}</link></color>',
            working,
        )
        localized_labels = WIKI_LINK_RE.findall(localized)
        for authored_label, localized_label in zip(authored_links, localized_labels):
            rendered = rendered.replace(
                f'>{authored_label}</link>', f'>{localized_label}</link>', 1
            )
        require(
            "Dignify description link must retain authored ID, red style and Chinese visible label",
            '<color=#D33><link="Worldly Skill">世俗技艺</link></color>' in rendered,
        )

    old_line = rows.get("TAN-30394FAB9660")
    short_line = rows.get("TAN-A4949E2C96DE")
    require("missing accumulated dialogue regression fixtures", old_line is not None and short_line is not None)
    if old_line is not None and short_line is not None:
        rendered_buffer = (
            f'<color=#888>{old_line["translation"]}</color>\n'
            f'<color=#FFF>{short_line["translation"]}</color>\n'
        )
        protected_tags: list[str] = []

        def protect_tag(match: re.Match[str]) -> str:
            marker = f"\ue002TAG{len(protected_tags)}\ue003"
            protected_tags.append(match.group(0))
            return marker

        reversed_buffer = TMP_TAG_RE.sub(protect_tag, rendered_buffer)
        unique_by_target: dict[str, list[str]] = {}
        for row in rows.values():
            unique_by_target.setdefault(row.get("translation", ""), []).append(row.get("source", ""))
        for target, sources in sorted(unique_by_target.items(), key=lambda pair: len(pair[0]), reverse=True):
            if len(target) >= 4 and len(sources) == 1:
                reversed_buffer = reversed_buffer.replace(target, sources[0])
        require(
            "legacy accumulated-buffer reversal fixture must expose the short-line failure",
            short_line["translation"] in reversed_buffer,
        )
        for target, sources in sorted(unique_by_target.items(), key=lambda pair: len(pair[0]), reverse=True):
            if 0 < len(target) < 4 and len(sources) == 1 and re.search(r"[\u3400-\u9fff]", target):
                reversed_buffer = replace_standalone_visible_token(reversed_buffer, target, sources[0])
        for index, tag in enumerate(protected_tags):
            reversed_buffer = reversed_buffer.replace(f"\ue002TAG{index}\ue003", tag)
        require(
            "short final dialogue line must survive best-effort accumulated-buffer reversal",
            old_line["source"] in reversed_buffer and short_line["source"] in reversed_buffer,
        )
    require(
        "runtime skill-check alias Dignify must render as 尊严",
        re.search(r'\{\s*"Dignify"\s*,\s*"尊严"\s*\}', PLUGIN) is not None,
    )

    # Skill-check previews can format internal English tokens into a template
    # that has already been localised by Loc.  The TMP and legacy setters must
    # still translate known tokens inside that mixed-language rendered value,
    # while declining to cache the mixed string as an English source.
    try:
        tmp_assignment_body = extract_method_body(
            PLUGIN, "private static void LocalizeTmpAssignment(TMP_Text instance, ref string value)"
        )
        legacy_patch_body = extract_method_body(
            PLUGIN, "private static class LegacyTextSetterPatch"
        )
    except ValueError as exception:
        errors.append(str(exception))
        tmp_assignment_body = legacy_patch_body = ""
    mixed_fixture = "Dignify 检定失败将增加 Trace。"
    required_runtime_tokens = {
        "Dignify": "尊严",
        "Trace": "痕迹",
    }
    for source, target in required_runtime_tokens.items():
        if source == "Dignify":
            condition = target in PLUGIN
        else:
            row = rows.get("TAN-7E14C3D7DD12")
            condition = row is not None and (
                row.get("source") == source and row.get("translation") == target
            )
        require(f"mixed skill-check fixture lacks {source} -> {target}", condition)
    require(
        f"TMP setter must continue localising mixed rendered text: {mixed_fixture}",
        "mixedReplacement = RelocalizeCompositeText(source, true)" in tmp_assignment_body,
    )
    require(
        f"legacy setter must continue localising mixed rendered text: {mixed_fixture}",
        "value = RelocalizeCompositeText(source, true)" in legacy_patch_body,
    )
    require(
        "formatted Loc output must localise the template and dynamic skill-check tokens before TMP display",
        "LocFormattedTemplatePatch" in PLUGIN
        and 'method.Name == "ForCurrentCulture"' in PLUGIN
        and "method.GetParameters()[1].ParameterType == typeof(string[])" in PLUGIN
        and "TryLookupTranslation(template, out var translatedTemplate)" in PLUGIN
        and "private static string LocalizeFormattedArgument(string argument)" in PLUGIN
        and "LocalizeWikiLinkLabels(argument)" in PLUGIN
        and ".Select(LocalizeFormattedArgument)" in PLUGIN
        and "string.Format(translatedTemplate, translatedArguments)" in PLUGIN,
    )
    require(
        "formatted Loc output must register an exact reversible pair for open-panel F9",
        "TrackOriginalLocTemplates(root);" in PLUGIN
        and 'EnumerateMember(locData, "entries")' in PLUGIN
        and "OriginalLocTemplatesByKey.TryGetValue(__0, out var template)" in PLUGIN
        and "RegisterKnownLocalizationPair(renderedValue, replacement);" in PLUGIN
        and "many-to-one" in PLUGIN,
    )
    try:
        resolved_link_body = extract_method_body(
            PLUGIN, "private static class ResolvedQualityLinkLocalizationPatch"
        )
    except ValueError as exception:
        errors.append(str(exception))
        resolved_link_body = ""
    require(
        "resolved skill-advice links must restore authored IDs before quality resolution",
        "ResolveQualityTokensAndColourizeLinks" in resolved_link_body
        and "PrepareRichLinkInput(ref __0)" in resolved_link_body
        and "FinishRichLinkLocalization(" in resolved_link_body
        and "QSpecEnv" in resolved_link_body,
    )
    require(
        "translated bracket links must retain authored IDs and link colours",
        "private static string RestoreAuthoredLinkStyles(" in PLUGIN
        and "RenderedLinkVisibleTextRegex.Replace(authoredMarkup" in PLUGIN
        and 'localizedLabels[linkIndex].Groups["id"].Value' in PLUGIN,
    )
    require(
        "translated wiki labels must be replaced by authored link targets before resolution",
        "private static string RestoreAuthoredWikiLinkTargets(" in PLUGIN
        and "private static string LocalizeWikiLinkLabels(string input)" in PLUGIN
        and "TryLookupTranslation(authoredInput, out var exactTranslation)" in PLUGIN
        and "localizedInput = LocalizeWikiLinkLabels(localizedInput);" in PLUGIN
        and "authoredLinks[linkIndex++]" in PLUGIN
        and "input = workingInput;" in PLUGIN,
    )
    require(
        "link-style restoration failure must preserve the game-resolved text",
        "private static void FinishRichLinkLocalization(" in PLUGIN
        and "catch (Exception exception)" in PLUGIN
        and "RegisterKnownLocalizationPair(authoredResult, result);" in PLUGIN,
    )
    try:
        finish_link_body = extract_method_body(
            PLUGIN, "private static void FinishRichLinkLocalization("
        )
    except ValueError as exception:
        errors.append(str(exception))
        finish_link_body = ""
    require(
        "Harmony link postfix must not re-enter its own patched original method",
        finish_link_body != ""
        and ".Invoke(" not in finish_link_body
        and "var authoredResult = result;" in finish_link_body,
    )

    # The general input helper is what scripted smoke tests use.  Validate the
    # accepted key and its Windows virtual-key value independently so an F7/F9
    # copy-paste error cannot silently turn the language test into a scene load.
    validate_set = re.search(r"\[ValidateSet\((.*?)\)\]", SEND_KEY, re.DOTALL)
    require(
        "send_key_to_travelling.ps1 does not accept F9",
        validate_set is not None and re.search(r"['\"]F9['\"]", validate_set.group(1)) is not None,
    )
    require(
        "send_key_to_travelling.ps1 must map F9 to VK_F9 (0x78)",
        re.search(r"\bF9\s*=\s*0x78\b", SEND_KEY, re.IGNORECASE) is not None,
    )
    standalone_f9 = ROOT / "tools" / "send_f9_to_travelling.ps1"
    if standalone_f9.exists():
        standalone_source = standalone_f9.read_text(encoding="utf-8-sig")
        require(
            "send_f9_to_travelling.ps1 must send VK_F9 (0x78)",
            re.search(r"keybd_event\(0x78\b", standalone_source, re.IGNORECASE) is not None,
        )

    try:
        toggle_body = extract_method_body(PLUGIN, "private void ToggleLanguage()")
    except ValueError as exception:
        errors.append(str(exception))
        toggle_body = ""
    require(
        "F9 hot path must not call RefreshAll",
        toggle_body != "" and re.search(r"\bRefreshAll\s*\(", toggle_body) is None,
    )
    try:
        live_typewriter_body = extract_method_body(
            PLUGIN, "private static void RelocalizeVisibleTypewriters(bool toChinese)"
        )
        typewriter_input_body = extract_method_body(
            PLUGIN, "private static class DialogueTypewriterInputPatch"
        )
        subtitle_buffer_body = extract_method_body(
            PLUGIN, "private static class SubtitleBufferSourcePatch"
        )
        world_popup_body = extract_method_body(
            PLUGIN, "private static class WorldPopupSegmentsPatch"
        )
        skill_raw_label_body = extract_method_body(
            PLUGIN, "private static class SkillRawLabelPatch"
        )
    except ValueError as exception:
        errors.append(str(exception))
        live_typewriter_body = typewriter_input_body = subtitle_buffer_body = ""
        world_popup_body = skill_raw_label_body = ""
    require(
        "F9 must relocalise currently visible typewriter text in both directions",
        "RelocalizeVisibleTypewriters(true);" in toggle_body
        and "RelocalizeVisibleTypewriters(false);" in toggle_body,
    )
    require(
        "live typewriter relocalisation must preserve the current visible-character index",
        "text.maxVisibleCharacters" in live_typewriter_body
        and "RestartFromIndexPreservingState(replacement, visibleCharacters)" in live_typewriter_body,
    )
    require(
        "typewriter input must capture and localise the complete accumulated buffer before animation",
        all(name in typewriter_input_body for name in ("StartTyping", "PlayText", "RestartFromIndexPreservingState"))
        and "GetTypewriterTextComponent(__instance)" in typewriter_input_body
        and "OriginalTextValues[text] = source;" in typewriter_input_body
        and "RelocalizeDialogueBufferSource(source)" in typewriter_input_body
        and "__0 = replacement;" in typewriter_input_body,
    )
    require(
        "typewriter input must never replace a newer buffer with stale savedSource",
        "else if (savedSource != null)" not in typewriter_input_body
        and "Always advance the cache to the newest complete" in typewriter_input_body,
    )
    require(
        "dialogue must be localised before accumulated-glyph counting and typewriter startup",
        re.search(
            r'\[HarmonyPatch\(\s*typeof\(Travelling\.UI\.Dialogue\.TravellingSubtitlePanel\),\s*"SetSubtitleTextContent"\)\]\s*private static class SubtitleBufferSourcePatch',
            PLUGIN,
        ) is not None
        and "DialogueBufferBuildDepth++;" in subtitle_buffer_body
        and "RelocalizeSubtitle(subtitle, ChineseEnabled);" in subtitle_buffer_body
        and "RelocalizeSubtitle(subtitle, false);" not in subtitle_buffer_body
        and "DialogueBufferBuildDepth - 1" in subtitle_buffer_body
        and "Finalizer(Exception __exception)" in subtitle_buffer_body,
    )
    try:
        bracket_link_body = extract_method_body(
            PLUGIN, "private static class BracketLinkLocalizationPatch"
        )
    except ValueError as exception:
        errors.append(str(exception))
        bracket_link_body = ""
    require(
        "generic bracket links must preserve authored IDs for complete linked dialogue sentences",
        "BracketsToColourizedLinks" in bracket_link_body
        and "parameters.Length == 4 || parameters.Length == 6" in bracket_link_body
        and "PrepareRichLinkInput(ref __0)" in bracket_link_body
        and "FinishRichLinkLocalization(" in bracket_link_body,
    )
    require(
        "world popup segments must be localised before wrapping",
        "ComposeWrapped" in PLUGIN
        and "RelocalizeCompositeText(segment, ChineseEnabled)" in world_popup_body,
    )
    require(
        "skill sprite identifiers must retain the authored English RawLabel",
        '"get_RawLabel"' in PLUGIN
        and 'GetOriginalMemberValue(__instance, "_label", __result)' in skill_raw_label_body,
    )
    try:
        character_name_body = extract_method_body(
            PLUGIN, "private static class CharacterInfoDisplayNamePatch"
        )
    except ValueError as exception:
        errors.append(str(exception))
        character_name_body = ""
    require(
        "log/person display names must patch CharacterInfo.Name only",
        re.search(
            r'\[HarmonyPatch\(\s*typeof\(PixelCrushers\.DialogueSystem\.CharacterInfo\),\s*"get_Name"\)\]\s*private static class CharacterInfoDisplayNamePatch',
            PLUGIN,
        )
        is not None,
    )
    require(
        "all catalogued dynamic actor display names must translate while Chinese is enabled",
        "ChineseEnabled" in character_name_body
        and "TryLookupTranslation(__result, out var translated)" in character_name_body
        and "DialogueBufferBuildDepth == 0" in character_name_body,
    )
    require(
        "dynamic actor display-name patch must not remain hard-coded to Me",
        'string.Equals(__result, "Me"' not in character_name_body,
    )
    player_display_name = rows.get("TAN-D30AF076B0DC")
    require(
        "dynamic player display name catalog entry must remain Me -> 我",
        player_display_name is not None
        and player_display_name.get("source") == "Me"
        and player_display_name.get("translation") == "我",
    )
    require(
        "display-name patch must not mutate the internal actor database key",
        re.search(r"\bnameInDatabase\s*=", character_name_body) is None
        and 'SetMemberValue(__instance, "nameInDatabase"' not in character_name_body
        and "Actor.Asset" not in character_name_body,
    )
    require(
        "TMP composite localisation must protect complete rich-text tags",
        "TmpTagRegex.Replace(result" in PLUGIN
        and "protectedTags.Add(match.Value)" in PLUGIN,
    )
    require(
        "composite localisation must match authored text across cosmetic rich-text tags",
        "CanonicalizeCosmeticMarkup(pair.Key)" in PLUGIN
        and "var result = CanonicalizeCosmeticMarkup(value);" in PLUGIN
        and "RestoreCanonicalCosmeticMarkup(result)" in PLUGIN,
    )

    dynamic_message_expected = {
        "TAN-134FD5B013D2": "I agreed to Zèlia's request. I could fulfil it - or try to deceive her",
        "TAN-2E53BAAA4053": "A Plan in the Journal has hints on how to do this.",
    }
    for row_id, expected_source in dynamic_message_expected.items():
        row = rows.get(row_id)
        require(
            f"missing dynamic dialogue/log fixture {row_id}",
            row is not None
            and row.get("source") == expected_source
            and row.get("translation") != expected_source,
        )

    smoking = rows.get("TAN-792F429CD716")
    require(
        "Andrée smoking branch must retain its reviewed contextual translation",
        smoking is not None
        and smoking.get("source") == "Best not, then."
        and smoking.get("translation") == "那还是算了。",
    )

    # Role captions are scene-authored strings, not Career labels.  Lock both
    # the source and the reviewed single-line caption, then also check the
    # hashed runtime catalog actually shipped by build_release.ps1.
    career_expected = {
        "TAN-CC93F932FC0E": ("an exorcist", "一名驱灵师"),
        "TAN-D162B1023F37": ("a\nwriter", "一名作家"),
        "TAN-B4016B177A90": ("a\nconjurer", "一名魔术师"),
        "TAN-D1D49487AD4E": ("a\nphysician", "一名医生"),
    }
    for row_id, (expected_source, expected_target) in career_expected.items():
        row = rows.get(row_id)
        require(f"missing character-generation role row {row_id}", row is not None)
        if row is None:
            continue
        require(
            f"{row_id}: source must remain {expected_source!r}",
            row.get("source") == expected_source,
        )
        require(
            f"{row_id}: expected single-line {expected_target!r}, got {row.get('translation')!r}",
            row.get("translation") == expected_target and "\n" not in row.get("translation", ""),
        )
        require(
            f"runtime catalog does not contain {expected_source!r} -> {expected_target!r}",
            runtime_catalog.get(sha256_text(expected_source)) == expected_target,
        )

    # The catalog contains legitimate many-English-to-one-Chinese mappings.
    # English restoration must therefore be owner/source based; a global
    # Chinese-to-English reverse dictionary cannot choose the authored source.
    hashes_by_target: dict[str, list[str]] = {}
    for source_hash, target in runtime_catalog.items():
        hashes_by_target.setdefault(target, []).append(source_hash)
    duplicate_targets = {
        target: hashes
        for target, hashes in hashes_by_target.items()
        if len(hashes) > 1
    }
    require(
        "runtime catalog needs a duplicate-target fixture for owner restore coverage",
        bool(duplicate_targets),
    )

    try:
        restore_body = extract_method_body(PLUGIN, "private static void RestoreOriginalValues()")
        apply_cached_body = extract_method_body(
            PLUGIN, "private static void ApplyCachedLanguageValues(bool toChinese)"
        )
        relocalize_body = extract_method_body(
            PLUGIN, "private static void RelocalizeVisibleTextComponents(bool toChinese)"
        )
        typewriter_relocalize_body = extract_method_body(
            PLUGIN, "private static void RelocalizeVisibleTypewriters(bool toChinese)"
        )
        tmp_write_body = extract_method_body(
            PLUGIN, "private static void SetTextWithoutCapture(TMP_Text text, string value)"
        )
        legacy_write_body = extract_method_body(
            PLUGIN, "private static void SetTextWithoutCapture(Text text, string value)"
        )
    except ValueError as exception:
        errors.append(str(exception))
        restore_body = apply_cached_body = relocalize_body = typewriter_relocalize_body = ""
        tmp_write_body = legacy_write_body = ""

    require(
        "TMP English restore must write the owner's exact saved source",
        re.search(r"SetTextWithoutCapture\s*\(\s*tmp\s*,\s*entry\.Value\s*\)", restore_body)
        is not None,
    )
    require(
        "legacy Text English restore must write the owner's exact saved source",
        re.search(r"SetTextWithoutCapture\s*\(\s*legacy\s*,\s*entry\.Value\s*\)", restore_body)
        is not None,
    )
    require(
        "English owner restore must not depend on lossy reverse localisation",
        "RelocalizeCompositeText" not in restore_body and "TryGetUniqueSource" not in restore_body,
    )
    require(
        "visible TMP relocalisation must skip owner-cached text already applied from its exact source",
        re.search(
            r"OriginalTextValues\.ContainsKey\(text\).*?continue\s*;",
            relocalize_body,
            re.DOTALL,
        )
        is not None,
    )
    require(
        "F9 typewriter relocalisation must only inspect active subtitle panels",
        "FindObjectsOfTypeAll<Travelling.UI.Dialogue.TravellingSubtitlePanel>()"
        in typewriter_relocalize_body
        and "panel.isActiveAndEnabled" in typewriter_relocalize_body
        and "panel.gameObject.activeInHierarchy" in typewriter_relocalize_body
        and 'GetMemberValue(panel, "_typewriter")' in typewriter_relocalize_body,
    )
    require(
        "F9 typewriter relocalisation must deduplicate panel typewriters",
        "HashSet<Travelling.UI.Dialogue.TravellingTypewriter>" in typewriter_relocalize_body
        and "handled.Add(typewriter)" in typewriter_relocalize_body,
    )
    require(
        "F9 typewriter source must be the complete accumulated buffer, never currentSubtitle",
        "OriginalTextValues.TryGetValue(text, out var source)" in typewriter_relocalize_body
        and "RelocalizeDialogueBufferSource(current)" in typewriter_relocalize_body
        and 'GetMemberValue(panel, "currentSubtitle")' not in typewriter_relocalize_body
        and 'GetMemberValue(subtitle, "formattedText")' not in typewriter_relocalize_body,
    )
    require(
        "generic cache restore/apply must leave accumulated typewriter history to its state-preserving path",
        re.search(
            r"entry\.Key is TMP_Text tmp.*?IsDialogueTypewriterText\(tmp\).*?continue\s*;",
            restore_body,
            re.DOTALL,
        ) is not None
        and re.search(
            r"entry\.Key is TMP_Text tmp.*?IsDialogueTypewriterText\(tmp\).*?continue\s*;",
            apply_cached_body,
            re.DOTALL,
        ) is not None,
    )
    require(
        "F9 typewriter path must never rebuild or clear the dialogue panel",
        re.search(r"\b(?:SetContent|ClearText|HideSubtitle|ShowSubtitle)\s*\(", typewriter_relocalize_body)
        is None,
    )
    require(
        "only a playing typewriter may restart its coroutine during F9",
        re.search(
            r"if\s*\(wasPlaying\).*?RestartFromIndexPreservingState\s*\(",
            typewriter_relocalize_body,
            re.DOTALL,
        )
        is not None,
    )
    require(
        "stopped typewriter F9 must replace text without restarting and reveal it fully",
        re.search(
            r"else\s*\{.*?SetTextWithoutCapture\s*\(text\s*,\s*replacement\s*\)"
            r".*?ForceMeshUpdate\s*\(false\s*,\s*false\s*\)"
            r".*?maxVisibleCharacters\s*=\s*text\.textInfo\?\.characterCount",
            typewriter_relocalize_body,
            re.DOTALL,
        )
        is not None,
    )
    require(
        "playing typewriter F9 must clamp the TMP visible-character resume index",
        "Mathf.Clamp(" in typewriter_relocalize_body
        and "text.maxVisibleCharacters" in typewriter_relocalize_body
        and "oldVisibleCount" in typewriter_relocalize_body,
    )
    require(
        "visible TMP Chinese localisation must capture the component-specific English source before writing",
        re.search(
            r"if\s*\(toChinese\).*?OriginalTextValues\[text\]\s*=\s*current\s*;.*?SetTextWithoutCapture\s*\(text\s*,\s*replacement\s*\)",
            relocalize_body,
            re.DOTALL,
        )
        is not None,
    )
    try:
        loaded_text_body = extract_method_body(
            PLUGIN, "private static int PatchLoadedTextComponents()"
        )
    except ValueError as exception:
        errors.append(str(exception))
        loaded_text_body = ""
    require(
        "background text refresh must branch on ChineseEnabled instead of forcing Chinese after F9",
        "ChineseEnabled" in loaded_text_body
        and "RelocalizeCompositeText(source, true)" in loaded_text_body,
    )
    require(
        "background text refresh must avoid rewriting an already-correct rendered value",
        "string.Equals(text.text, replacement, StringComparison.Ordinal)" in loaded_text_body,
    )
    require(
        "release source must not contain the temporary F8 scene-skip QA hook",
        "TEMP_QA_ONLY" not in PLUGIN
        and "KeyCode.F8" not in PLUGIN
        and "LoadScene(4)" not in PLUGIN,
    )
    require(
        "owner restoration writes must suppress TMP recapture",
        "TextWriteSuppressionDepth++" in tmp_write_body
        and "TextWriteSuppressionDepth--" in tmp_write_body,
    )
    require(
        "owner restoration writes must suppress legacy Text recapture",
        "TextWriteSuppressionDepth++" in legacy_write_body
        and "TextWriteSuppressionDepth--" in legacy_write_body,
    )

    print({"checks": checks, "errors": errors, "error_count": len(errors)})
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
