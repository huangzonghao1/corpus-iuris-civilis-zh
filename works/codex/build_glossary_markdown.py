#!/usr/bin/env python3
"""Render the maintained glossary CSV as an EPUB-ready Markdown appendix."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "glossary.csv"
TARGET = ROOT / "translation" / "术语表.md"


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    lines = [
        "# 术语表", "",
        "本表汇集本书拉丁法学术语的暂定译名及适用说明。不同语境下可能需要细分；首次出现处保留拉丁术语或于条文后说明。", "",
        "| 拉丁术语 | 统一译名 | 语境说明 |", "| --- | --- | --- |",
    ]
    for row in rows:
        cells = [row["latin_term"], row["preferred_chinese"], row["context_note"]]
        lines.append("| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in cells) + " |")
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(ROOT)} with {len(rows)} terms")


if __name__ == "__main__":
    main()
