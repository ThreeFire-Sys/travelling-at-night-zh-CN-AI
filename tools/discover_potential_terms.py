#!/usr/bin/env python3
"""Discover terminology candidates from the complete current translation corpus.

This is deliberately an open-set pass.  The existing glossary is only one
signal; links, title-case lore phrases, all-caps labels, exact short labels and
translation notes that still contain provisional-review markers are scanned as
independent sources.  Human dispositions live in a separate audit ledger.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9]*(?:[’'][A-Za-zÀ-ÖØ-öø-ÿ0-9]+)*(?:-[A-Za-zÀ-ÖØ-öø-ÿ0-9]+(?:[’'][A-Za-zÀ-ÖØ-öø-ÿ0-9]+)*)*")
LINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
TAG_RE = re.compile(r"<[^>]+>|\[(?:q|if|set|img|IMG)=[^\]]+\]", re.IGNORECASE)
STALE_RE = re.compile(r"(?<!短)暂(?!时)|待.{0,20}(?:校|核|统一)|需.{0,20}(?:校|核|统一)")
CONNECTORS = {
    "a", "an", "at", "by", "d'", "de", "del", "della", "des", "du",
    "et", "for", "from", "in", "la", "le", "of", "on", "the", "to", "under",
    "with", "without", "who", "were", "was",
}
SINGLE_STOPWORDS = {
    "A", "An", "And", "Are", "As", "At", "Be", "Because", "But", "By", "Can",
    "Could", "Did", "Do", "Does", "Even", "For", "From", "Go", "Good", "Had",
    "Has", "Have", "He", "Her", "Here", "His", "How", "I", "If", "In", "Is",
    "It", "Its", "Let", "Like", "Look", "Maybe", "Me", "Much", "My", "No", "Not",
    "Now", "Of", "Oh", "On", "One", "Only", "Or", "Our", "Perhaps", "Please",
    "She", "So", "Some", "Still", "That", "The", "Their", "Then", "There", "These",
    "They", "This", "Those", "Though", "To", "Too", "Very", "Was", "We", "Well",
    "What", "When", "Where", "Which", "Who", "Why", "Will", "With", "Would", "Yes",
    "You", "Your",
}


LABEL_TAILS = {
    "_label", "label", "_displayname", "displayname", "_listingname", "_introlabel",
    "name", "title", "_source", "_author",
}


def load_rows(directory: Path, catalog_path: Path) -> list[dict]:
    catalog = {
        row["id"]: row
        for row in (
            json.loads(raw)
            for raw in catalog_path.read_text(encoding="utf-8-sig").splitlines()
            if raw
        )
    }
    rows: list[dict] = []
    for path in sorted(directory.glob("chunk_*.jsonl")):
        for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not raw:
                continue
            row = json.loads(raw)
            catalog_row = catalog.get(row["id"], {})
            row["_file"] = path.name
            row["_line"] = line_no
            row["_domain"] = catalog_row.get("domain", "")
            row["_label_context"] = any(
                (
                    str(context.get("field_path", "")).rsplit(".", 1)[-1].casefold()
                    in LABEL_TAILS
                )
                or str(context.get("field_path", "")).casefold().endswith(".label")
                or str(context.get("field_title", "")).casefold()
                in {"display name", "menu text"}
                for context in catalog_row.get("contexts", [])
            )
            rows.append(row)
    return rows


def load_baseline_notes(directory: Path, git_ref: str | None) -> dict[str, str]:
    if not git_ref:
        return {}
    notes = {}
    for path in sorted(directory.glob("chunk_*.jsonl")):
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
        result = subprocess.run(
            ["git", "show", f"{git_ref}:{relative}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        for raw in result.stdout.decode("utf-8-sig").splitlines():
            if raw:
                row = json.loads(raw)
                notes[row["id"]] = row.get("notes", "") or ""
    return notes


def norm(value: str) -> str:
    return " ".join(value.replace("’", "'").split()).casefold()


def is_title_word(word: str) -> bool:
    return bool(word) and word[0].isupper()


def is_sentence_initial(text: str, start: int) -> bool:
    prefix = text[:start].rstrip(" \t\r\n\"'“”‘’([{<")
    return not prefix or prefix[-1] in ".!?\n:"


def clean_link(value: str) -> str:
    # The current game uses plain [[Label]] links.  Keep a defensive display
    # split for future [[id|Label]] / [[id:Label]] forms.
    value = value.strip()
    if "|" in value:
        value = value.rsplit("|", 1)[-1]
    return value.strip()


def add_hit(store: dict, candidate: str, signal: str, row: dict, snippet: str | None = None) -> None:
    candidate = " ".join(candidate.split()).strip(" \t\r\n\"“”‘’.,;:!?()[]{}")
    if not candidate or len(candidate) > 120:
        return
    key = norm(candidate)
    if not key:
        return
    entry = store.setdefault(
        key,
        {
            "candidate": candidate,
            "forms": Counter(),
            "signals": set(),
            "row_ids": set(),
            "hits": [],
        },
    )
    entry["forms"][candidate] += 1
    entry["signals"].add(signal)
    entry["row_ids"].add(row["id"])
    if len(entry["hits"]) < 12:
        entry["hits"].append(
            {
                "id": row["id"],
                "source": snippet or row["source"],
                "translation": row.get("translation", ""),
                "domain": row.get("_domain", ""),
                "label_context": bool(row.get("_label_context")),
                "file": row["_file"],
                "line": row["_line"],
            }
        )


def note_ascii_candidates(note: str, source: str) -> set[str]:
    found: set[str] = set()
    for match in re.finditer(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9’'&./ -]{0,100}", note):
        run = " ".join(match.group(0).split()).strip(" ./-")
        for value in re.split(r"\s*/\s*", run):
            value = value.strip()
            if not value or value in SINGLE_STOPWORDS or len(value) < 2:
                continue
            if re.search(rf"(?<![A-Za-z]){re.escape(value)}(?![A-Za-z])", source, re.IGNORECASE):
                found.add(value)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translations", type=Path, default=ROOT / "translations_k97")
    parser.add_argument(
        "--catalog", type=Path, default=ROOT / "build/merged_k97/review_catalog.jsonl"
    )
    parser.add_argument(
        "--notes-baseline-ref",
        default=None,
        help="read provisional-note discovery signals from this Git ref while using current sources/targets",
    )
    parser.add_argument("--glossary", type=Path, default=ROOT / "glossary/glossary.csv")
    parser.add_argument("--links", type=Path, default=ROOT / "glossary/link_targets.csv")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "build/reviews/potential_term_candidates.json"
    )
    args = parser.parse_args()

    rows = load_rows(args.translations, args.catalog)
    baseline_notes = load_baseline_notes(args.translations, args.notes_baseline_ref)
    with args.glossary.open("r", encoding="utf-8-sig", newline="") as handle:
        glossary = {norm(row["source_en"]): row for row in csv.DictReader(handle)}
    with args.links.open("r", encoding="utf-8-sig", newline="") as handle:
        links = {norm(row["source_en"]): row for row in csv.DictReader(handle)}

    raw: dict[str, dict] = {}
    provisional_rows = []
    single_occurrences: dict[str, list[tuple[str, bool, dict]]] = defaultdict(list)

    for row in rows:
        source = row["source"]
        notes = baseline_notes.get(row["id"], row.get("notes", "") or "")
        stale = STALE_RE.search(notes)
        if stale:
            provisional_rows.append(
                {
                    "id": row["id"],
                    "source": source,
                    "translation": row.get("translation", ""),
                    "notes": notes,
                    "marker": stale.group(0),
                    "file": row["_file"],
                    "line": row["_line"],
                }
            )
            for value in note_ascii_candidates(notes, source):
                add_hit(raw, value, "provisional_note", row)

        for match in LINK_RE.finditer(source):
            add_hit(raw, clean_link(match.group(1)), "double_bracket_link", row)

        plain = TAG_RE.sub(" ", LINK_RE.sub(lambda m: clean_link(m.group(1)), source))
        tokens = list(WORD_RE.finditer(plain))
        for index, token in enumerate(tokens):
            word = token.group(0)
            title = is_title_word(word)
            if title:
                single_occurrences[norm(word)].append(
                    (word, is_sentence_initial(plain, token.start()), row)
                )
            if not title:
                continue
            if index > 0:
                previous = tokens[index - 1]
                between_previous = plain[previous.end() : token.start()]
                continues_previous = re.fullmatch(r"[\s\-–—'’]*", between_previous)
                if continues_previous and is_title_word(previous.group(0)):
                    continue
                if (
                    continues_previous
                    and previous.group(0).casefold() in CONNECTORS
                    and index > 1
                    and is_title_word(tokens[index - 2].group(0))
                ):
                    continue
            end = index
            title_count = 1
            while end + 1 < len(tokens) and end - index < 7:
                between = plain[tokens[end].end() : tokens[end + 1].start()]
                next_word = tokens[end + 1].group(0)
                if not re.fullmatch(r"[\s\-–—'’]*", between):
                    break
                if is_title_word(next_word):
                    title_count += 1
                    end += 1
                    continue
                if next_word.casefold() in CONNECTORS and end + 2 < len(tokens):
                    after_connector = plain[tokens[end + 1].end() : tokens[end + 2].start()]
                    if re.fullmatch(r"[\s\-–—'’]*", after_connector) and is_title_word(tokens[end + 2].group(0)):
                        end += 1
                        continue
                break
            if title_count >= 2 and end > index:
                phrase = plain[token.start() : tokens[end].end()]
                add_hit(raw, phrase, "title_phrase", row)
                if stale:
                    add_hit(raw, phrase, "provisional_context", row)
                if row["_label_context"]:
                    add_hit(raw, phrase, "label_context", row)
                if row["_domain"] == "lore":
                    add_hit(raw, phrase, "lore_context", row)

        source_words = list(WORD_RE.finditer(plain.strip()))
        if row["_label_context"] and source_words and len(source_words) <= 12:
            add_hit(raw, plain.strip(), "label_source", row)

    for key, occurrences in single_occurrences.items():
        forms = Counter(item[0] for item in occurrences)
        form = forms.most_common(1)[0][0]
        keep = (
            key in glossary
            or key in links
            or form.isupper()
            or "-" in form
            or any(not item[1] for item in occurrences)
            or any(STALE_RE.search(item[2].get("notes", "") or "") for item in occurrences)
        )
        if keep and (form not in SINGLE_STOPWORDS or key in glossary or key in links):
            for value, _initial, row in occurrences[:12]:
                add_hit(raw, value, "capitalized_token", row)
                if STALE_RE.search(row.get("notes", "") or ""):
                    add_hit(raw, value, "provisional_context", row)
                if row["_label_context"]:
                    add_hit(raw, value, "label_context", row)
                if row["_domain"] == "lore":
                    add_hit(raw, value, "lore_context", row)

    candidates = []
    for key, entry in raw.items():
        forms = entry.pop("forms")
        entry["candidate"] = forms.most_common(1)[0][0]
        entry["forms"] = [form for form, _count in forms.most_common()]
        entry["signals"] = sorted(entry["signals"])
        entry["row_ids"] = sorted(entry["row_ids"])
        entry["occurrence_count"] = len(entry["row_ids"])
        entry["existing_glossary"] = glossary.get(key)
        entry["existing_link_target"] = links.get(key)
        strong_signals = {
            "provisional_note", "provisional_context", "double_bracket_link", "label_source",
            "lore_context",
        }
        strong = bool(strong_signals & set(entry["signals"]))
        repeated = entry["occurrence_count"] >= 2
        all_caps = any(
            form.replace("-", "").replace("'", "").isupper()
            and any(char.isalpha() for char in form)
            for form in entry["forms"]
        )
        if not (
            entry["existing_glossary"]
            or entry["existing_link_target"]
            or strong
            or repeated
            or all_caps
        ):
            continue
        candidates.append(entry)
    candidates.sort(key=lambda row: (row["candidate"].casefold(), row["candidate"]))

    result = {
        "rows": len(rows),
        "candidate_count": len(candidates),
        "provisional_row_count": len(provisional_rows),
        "notes_baseline_ref": args.notes_baseline_ref,
        "covered_by_glossary": sum(row["existing_glossary"] is not None for row in candidates),
        "covered_by_link_targets": sum(
            row["existing_link_target"] is not None for row in candidates
        ),
        "candidates": candidates,
        "provisional_rows": provisional_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key not in {"candidates", "provisional_rows"}},
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
