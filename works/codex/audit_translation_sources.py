#!/usr/bin/env python3
"""Compare Latin quotations in translation drafts with the preserved web transcription."""
from __future__ import annotations

import csv
import html
import re
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATUS = ROOT / "translation_status.csv"
RAW = ROOT / "source_original"
TRANSLATIONS = ROOT / "translation"


class SourceAnchorExtractor(HTMLParser):
    def __init__(self, known: set[str]):
        super().__init__(convert_charrefs=True)
        self.known = known
        self.current: str | None = None
        self.skip_anchor_text = False
        self.skip_depth = 0
        self.parts: dict[str, list[str]] = defaultdict(list)

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag.lower() == "a":
            attrs = dict(attrs)
            value = attrs.get("name") or attrs.get("id")
            if value in self.known:
                self.current = value
                self.skip_anchor_text = True
                return
            # A topic-heading anchor ends the preceding law even when no next
            # constitution paragraph has begun yet.
            if value and re.fullmatch(r"\d+\.\d+", value):
                self.current = None
                self.skip_anchor_text = True
                return
        if self.current and tag.lower() in {"p", "div", "br", "li", "tr", "td", "hr"}:
            self.parts[self.current].append(" ")

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag.lower() == "a":
            self.skip_anchor_text = False
        if self.current and tag.lower() in {"p", "div", "br", "li", "tr", "td", "hr"}:
            self.parts[self.current].append(" ")

    def handle_data(self, data):
        if self.current and not self.skip_anchor_text and not self.skip_depth:
            self.parts[self.current].append(data)

    def texts(self):
        return {k: normalize("".join(v)) for k, v in self.parts.items()}


def normalize(text: str) -> str:
    text = html.unescape(text).replace("\u00a0", " ").replace("\ufeff", "")
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"\*\s+(?=<)", "*", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"(?<=\*)\s+(?=[A-Z])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def markdown_unit_sources(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    units: dict[str, list[str]] = defaultdict(list)
    current_unit: str | None = None
    section_lines: list[str] = []
    # A constitution may be split into editor/source anchors such as
    # 1.3.22.pr., 1.3.22.1, or 1.3.25.1a. These are paragraphs within the
    # constitution, not separate status units; collect them under 1.3.22 etc.
    unit_header = re.compile(
        r"^#{2,6}\s+(\d+\.\d+\.\d+)(?:\.(?:pr\.|\d+[a-z]?|[a-z]))?(?:\s|$)"
    )

    def save():
        if current_unit:
            units[current_unit].extend(section_lines)

    topic_header = re.compile(r"^#{2,6}\s+\d+\.\d+\.0(?:\s|$)")
    for line in lines:
        if topic_header.match(line):
            save()
            current_unit = None
            section_lines = []
            continue
        match = unit_header.match(line)
        if match:
            save()
            current_unit = match.group(1)
            section_lines = []
        elif current_unit:
            section_lines.append(line)
    save()

    result: dict[str, str] = {}
    for unit, body in units.items():
        in_latin = False
        pieces: list[str] = []
        for line in body:
            stripped = line.strip()
            source_label = re.search(r"\*\*[^*]*(?:拉丁原文|网页原文编辑标记|网页编者说明|网页原文说明|原文编辑说明)[^*]*\*\*", stripped)
            if source_label:
                in_latin = True
                remainder = stripped[source_label.end():]
                if remainder.strip(): pieces.append(remainder)
                continue
            if re.search(r"\*\*中文译文\*\*", stripped):
                in_latin = False
                continue
            if in_latin:
                if stripped.startswith("```"):
                    continue
                stripped = re.sub(r"^>\s?", "", stripped)
                stripped = re.sub(r"^" + re.escape(unit) + r"(?:\s+.*)?$", "", stripped)
                stripped = re.sub(r"^text\s+", "", stripped)
                stripped = re.sub(r"`([^`]*)`", r"\1", stripped)
                stripped = stripped.replace("**", "")
                # Remove Markdown italic delimiters while preserving source *editorial marks*.
                stripped = re.sub(r"(?<!\*)\*(\S(?:[^*\n]*?\S)?)\*(?!\*)", r"\1", stripped)
                pieces.append(stripped)
        result[unit] = normalize(" ".join(pieces))
    return result


def main():
    with STATUS.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    legal_rows = [r for r in rows if re.fullmatch(r"\d+\.\d+\.\d+", r["unit_id"])]
    by_page: dict[str, list[str]] = defaultdict(list)
    for r in legal_rows:
        by_page[r["source_page"]].append(r["unit_id"])

    source_texts: dict[str, str] = {}
    for page, units in by_page.items():
        parser = SourceAnchorExtractor(set(units))
        parser.feed((RAW / page).read_bytes().decode("iso-8859-1"))
        source_texts.update(parser.texts())

    draft_texts: dict[str, str] = {}
    draft_files: dict[str, str] = {}
    for path in sorted(TRANSLATIONS.glob("*.md")):
        for unit, content in markdown_unit_sources(path).items():
            if unit in draft_texts:
                raise SystemExit(f"duplicate translated unit heading: {unit} in {path} and {draft_files[unit]}")
            draft_texts[unit] = content
            draft_files[unit] = str(path.relative_to(ROOT))

    missing_anchor = []
    missing_draft = []
    empty_latin = []
    mismatches = []
    aligned = 0
    tracked_with_draft = 0
    for row in legal_rows:
        unit = row["unit_id"]
        source = source_texts.get(unit)
        draft = draft_texts.get(unit)
        if source is None:
            missing_anchor.append(unit)
            continue
        if draft is None:
            missing_draft.append(unit)
            continue
        tracked_with_draft += 1
        if not draft:
            empty_latin.append(unit)
            continue
        if normalize(source) != normalize(draft):
            # Keep reports compact while making the first differing region inspectable.
            limit = min(len(source), len(draft))
            at = next((i for i in range(limit) if source[i] != draft[i]), limit)
            mismatches.append((unit, source[max(0, at-45):at+100], draft[max(0, at-45):at+100], len(source), len(draft)))
        else:
            aligned += 1

    print(f"Tracked legal units: {len(legal_rows)}")
    print(f"Source anchors found: {len(source_texts)}")
    print(f"Tracked units with draft quotation: {tracked_with_draft}")
    print(f"Tracked units source-aligned: {aligned}")
    print(f"All parsed quotation sections (including untracked heading variants): {len(draft_texts)}")
    print(f"Missing source anchors: {len(missing_anchor)}")
    print(f"Missing draft quotations: {len(missing_draft)}")
    print(f"Empty Latin quotations: {len(empty_latin)}")
    print(f"Latin text mismatches: {len(mismatches)}")
    for label, values in (("MISSING SOURCE", missing_anchor), ("MISSING DRAFT", missing_draft), ("EMPTY LATIN", empty_latin)):
        for unit in values[:30]: print(f"{label}: {unit}")
    for unit, source, draft, slen, dlen in mismatches[:50]:
        print(f"MISMATCH {unit}: source={slen}, draft={dlen}; source={source!r}; draft={draft!r}")

    # An incomplete translation corpus is expected while work is in progress.
    # Exit nonzero only for a source mismatch among draft units or missing source anchors.
    if mismatches or missing_anchor:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
