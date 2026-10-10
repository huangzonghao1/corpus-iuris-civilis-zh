#!/usr/bin/env python3
"""Mark source units that have both Latin/web witness text and a Chinese translation."""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from audit_translation_sources import SourceAnchorExtractor, markdown_unit_sources, normalize

ROOT = Path(__file__).resolve().parent
STATUS = ROOT / "translation_status.csv"
TRANS = ROOT / "translation"
RAW = ROOT / "source_original"

UNIT_HEADING = re.compile(
    r"^#{2,6}\s+(\d+\.\d+\.\d+)(?:\.(?:pr\.|\d+[a-z]?|[a-z]))?(?:\s|$)"
)
SOURCE_LABEL = re.compile(r"\*\*[^*]*(?:拉丁原文|网页原文编辑标记|网页编者说明|网页原文说明|原文编辑说明)[^*]*\*\*")


def collect_units():
    found = {}
    duplicates = {}
    for path in sorted(TRANS.glob("*.md")):
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        current = None
        body = []
        def save():
            if current:
                if current in found:
                    filename, previous = found[current]
                    if filename == path.name:
                        found[current] = (filename, previous + "\n" + "\n".join(body))
                    else:
                        duplicates.setdefault(current, [filename]).append(path.name)
                else:
                    found[current] = (path.name, "\n".join(body))
        for line in lines:
            match = UNIT_HEADING.match(line)
            if match:
                save()
                current = match.group(1)
                body = []
            elif current:
                body.append(line)
        save()
    if duplicates:
        raise SystemExit("Duplicate numeric translation headings: " + ", ".join(duplicates))
    return found


def main():
    found = collect_units()
    draft_sources = {}
    draft_files = {}
    for path in sorted(TRANS.glob("*.md")):
        for unit, content in markdown_unit_sources(path).items():
            if unit in draft_sources:
                raise SystemExit(f"duplicate Latin quotation for {unit}")
            draft_sources[unit] = content
            draft_files[unit] = path.name

    manual_pages = {
        "index": "index.md",
        "Componendo": "Componendo.md",
        "Confirmando": "Confirmando.md",
        "Emendatio": "Emendatio.md",
    }
    with STATUS.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0])

    legal_rows = [r for r in rows if re.fullmatch(r"\d+\.\d+\.\d+", r["unit_id"])]
    units_by_page = defaultdict(list)
    for row in legal_rows:
        units_by_page[row["source_page"]].append(row["unit_id"])
    source_texts = {}
    for page, ids in units_by_page.items():
        parser = SourceAnchorExtractor(set(ids))
        parser.feed((RAW / page).read_bytes().decode("iso-8859-1"))
        source_texts.update(parser.texts())

    marked = 0
    in_progress = 0
    unmarked_with_heading = []
    for row in rows:
        unit = row["unit_id"]
        if unit in manual_pages or re.fullmatch(r"CJ\d+_frontmatter", unit):
            filename = manual_pages.get(unit, unit + ".md")
            path = TRANS / filename
            content = path.read_text(encoding="utf-8-sig") if path.exists() else ""
            has_cn = "中文" in content and ("译文" in content or "翻译" in content)
            if path.exists() and has_cn:
                row["translation_status"] = "translated"
                row["translation_file"] = f"translation/{path.name}"
                marked += 1
            continue
        if not re.fullmatch(r"\d+\.\d+\.\d+", unit):
            continue
        item = found.get(unit)
        if not item:
            continue
        filename, content = item
        has_cn = "**中文译文**" in content
        has_source_or_editorial = bool(SOURCE_LABEL.search(content))
        if has_cn and has_source_or_editorial:
            source = source_texts.get(unit, "")
            draft = draft_sources.get(unit, "")
            row["translation_file"] = f"translation/{filename}"
            if source and draft and normalize(source) == normalize(draft):
                row["translation_status"] = "translated"
                marked += 1
            else:
                row["translation_status"] = "in_progress"
                in_progress += 1
                unmarked_with_heading.append(unit)
        else:
            unmarked_with_heading.append(unit)

    with STATUS.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Source-aligned translated legal units: {marked}")
    print(f"Numeric translation headings found: {len(found)}")
    print(f"In progress or mismatched sections: {in_progress}")
    print(f"Headings missing source/editorial or Chinese labels: {len(unmarked_with_heading) - in_progress}")
    for unit in unmarked_with_heading[:30]: print("INCOMPLETE SECTION:", unit)


if __name__ == "__main__":
    main()
