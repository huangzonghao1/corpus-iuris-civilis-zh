#!/usr/bin/env python3
"""Rebuild archived editions offline in isolated directories and compare content."""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from validation import ROOT, WORKS, source_check, compare_epubs


def run(directory: Path, script: str, *arguments: str):
    result = subprocess.run([sys.executable, script, *arguments], cwd=directory, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"{script} failed:\n{result.stdout[-10000:]}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", choices=["all", *WORKS], default="all")
    parser.add_argument("--output-dir", type=Path, default=Path("build"))
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output == ROOT or ROOT.is_relative_to(output) or output.is_relative_to(ROOT / "works"):
        raise ValueError("Output must be separate from the publication sources")
    output.mkdir(parents=True, exist_ok=True)
    selected = list(WORKS) if args.work == "all" else [args.work]
    report = {"status": "PASS", "network": "Not used", "works": {}, "build_logs": {}}
    with tempfile.TemporaryDirectory(prefix="scratch-", dir=output) as temporary:
        for work in selected:
            source = ROOT / "works" / work
            copied = Path(temporary) / work
            shutil.copytree(source, copied, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
            source_base = copied / "学说汇纂_下载与EPUB_2026-09-26" if work == "digesta" else copied
            source_check(source_base)
            # Finished outputs are removed so every listed edition must be regenerated.
            for name in WORKS[work]:
                (copied / name).unlink()
            logs = []
            if work == "institutiones":
                logs.append(run(copied, "build_epub.py"))
            elif work == "digesta":
                logs.append(run(copied, "build_digest_epub.py"))
                logs.append(run(copied / "学说汇纂_中文翻译工作区", "build_chinese_epub.py"))
            elif work == "codex":
                logs.append(run(copied, "audit_translation_sources.py"))
                logs.append(run(copied, "build_latin_epub.py"))
                logs.append(run(copied, "build_latin_epub.py", "--latin-only", "--output", WORKS[work][1]))
                logs.append(run(copied, "build_bilingual_epub.py", "--chinese-only", "--output", WORKS[work][2]))
                logs.append(run(copied, "build_bilingual_epub.py", "--output", WORKS[work][3]))
            elif work == "novellae":
                logs.append(run(copied, "build_three_editions.py"))
                logs.append(run(copied, "verify_sources.py"))
                source_report = json.loads((copied / "source_integrity_report.json").read_text())
                for gate in ["source_sha_mismatches", "offline_mirror_mismatches", "epub_source_text_mismatches"]:
                    if source_report[gate]:
                        raise ValueError(f"Novellae source-integrity gate failed: {gate}")
            comparisons = []
            destination = output / work
            destination.mkdir(exist_ok=True)
            for name in WORKS[work]:
                comparisons.append(compare_epubs(source / name, copied / name))
                shutil.copy2(copied / name, destination / Path(name).name)
            report["works"][work] = comparisons
            report["build_logs"][work] = "\n".join(logs).replace(str(copied), f"works/{work}")
            print(f"{work}: {len(comparisons)} editions rebuilt and semantically matched", flush=True)
    (output / "rebuild_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {sum(len(v) for v in report['works'].values())} editions; report: {output / 'rebuild_validation.json'}")


if __name__ == "__main__":
    main()
