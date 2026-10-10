#!/usr/bin/env python3
"""Verify the publication snapshot; write a report only after all gates pass."""
from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path
from validation import ROOT, WORKS, source_check, epub_check, translation_check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    sources, editions = {}, []
    for work, files in WORKS.items():
        base = root / "works" / work
        source_base = base / "学说汇纂_下载与EPUB_2026-09-26" if work == "digesta" else base
        sources[work] = source_check(source_base)
        for file in files:
            result = epub_check(base / file)
            result["work"] = work
            result["path"] = (base / file).relative_to(root).as_posix()
            editions.append(result)
    report = {"status": "PASS", "source_validation": sources, "epub_validation": editions,
              "translation_validation": translation_check(root),
              "epubcheck": "NOT RUN: not installed" if shutil.which("epubcheck") is None else "NOT RUN: separate validator required",
              "professional_translation_review": "Not independently certified"}
    output = args.report or root / "reports/validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "editions": len(editions),
                      "source_files": sum(x["source_records"] for x in sources.values()),
                      "report": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
