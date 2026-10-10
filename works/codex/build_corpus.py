#!/usr/bin/env python3
"""Build the offline source set and translation inventory for the Codex project."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import posixpath
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "source_original"
WEB = ROOT / "web"


class VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "head", "title"}:
            self.skip.append(tag)
        elif not self.skip and tag in {"p", "div", "br", "li", "tr", "td", "hr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.skip:
            # HTMLParser is forgiving; close the matching skipped element and anything nested in it.
            pos = len(self.skip) - 1 - self.skip[::-1].index(tag)
            self.skip = self.skip[:pos]
        elif not self.skip and tag in {"p", "div", "br", "li", "tr", "td", "hr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def text_of(source: bytes, encoding: str = "iso-8859-1") -> str:
    parser = VisibleText()
    parser.feed(source.decode(encoding, errors="replace"))
    return re.sub(r"[\t\r\f\v ]+", " ", "".join(parser.parts)).strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text, flags=re.UNICODE))


def page_order(records: list[dict]) -> list[dict]:
    order = {"codjust.htm": 0, "Componendo.htm": 1, "Confirmando.htm": 2, "Emendatio.htm": 3}
    def key(rec: dict) -> int:
        name = Path(rec["local_path"]).name
        if name in order:
            return order[name]
        match = re.search(r"\d+", Path(rec["local_path"]).stem)
        return 4 + int(match.group()) if match else 100
    return sorted(records, key=key)


def offline_asset_href(source_page: str, asset_path: Path) -> str:
    """Return a path from a flattened Corpus page or preserved subdirectory."""
    page_dir = "Francogallica" if source_page.startswith("Francogallica/") else "."
    asset_rel = asset_path.relative_to(WEB).as_posix()
    return posixpath.relpath(asset_rel, page_dir)


def rewrite_background(raw: bytes, source_page: str, asset_path: Path, audit: list[dict[str, str]]) -> bytes:
    """Keep decorative backgrounds available in the offline copy and log each use."""
    original = b"../Images/marbre2.jpg"
    if original not in raw:
        return raw
    offline = offline_asset_href(source_page, asset_path)
    raw = raw.replace(original, offline.encode("ascii"))
    audit.append({
        "source_page": source_page,
        "original_href": original.decode("ascii"),
        "source_target_status": "archived locally; HTTP 200",
        "offline_target": offline,
        "treatment": "Rebased the background image path in the derived offline copy; raw source preserved.",
    })
    return raw


def rewrite_asset_sources(raw: bytes, source_page: str, assets: dict[str, Path], audit: list[dict[str, str]]) -> bytes:
    """Rebase image paths whose source assets have been archived."""
    def replace(match: re.Match[bytes]) -> bytes:
        quote, href = match.group(1), match.group(2)
        href_text = href.decode("latin-1")
        asset_path = assets.get(href_text)
        if asset_path is None:
            return match.group(0)
        offline = offline_asset_href(source_page, asset_path)
        audit.append({
            "source_page": source_page,
            "original_href": href_text,
            "source_target_status": "archived locally; HTTP 200",
            "offline_target": offline,
            "treatment": "Rebased the image path in the derived offline copy; raw source preserved.",
        })
        return match.group(0).replace(href, offline.encode("ascii"))
    return re.sub(rb'\bsrc\s*=\s*(["\'])([^"\']+)\1', replace, raw, flags=re.I)


def rewrite_preface_popups(raw: bytes, source_page: str, audit: list[dict[str, str]]) -> bytes:
    """Turn JavaScript popup links into ordinary local links for offline browsing."""
    def replace(match: re.Match[bytes]) -> bytes:
        tag = match.group(0)
        target_match = re.search(rb"MM_openBrWindow\(\s*['\"]([^'\"]+)['\"]", tag, re.I)
        if not target_match:
            return tag
        original = target_match.group(1).decode("latin-1")
        basename = Path(original).name
        offline = f"Francogallica/{basename}"
        audit.append({
            "source_page": source_page,
            "original_href": original,
            "source_target_status": "archived locally; HTTP 200",
            "offline_target": offline,
            "treatment": "Replaced the JavaScript popup with a direct local link; raw source preserved.",
        })
        tag = re.sub(rb'\bhref\s*=\s*(["\'])[^"\']*\1', b'href="' + offline.encode("ascii") + b'"', tag, count=1, flags=re.I)
        tag = re.sub(rb'\s+onClick\s*=\s*(?:"[^"]*"|\'[^\']*\')', b"", tag, flags=re.I)
        return tag
    return re.sub(rb'<a\b[^>]*>', replace, raw, flags=re.I | re.S)


def main() -> None:
    manifest_path = ROOT / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = page_order(manifest["records"])
    WEB.mkdir(parents=True, exist_ok=True)
    asset_paths: dict[str, Path] = {}
    for asset in manifest.get("linked_assets", []):
        raw_asset = ROOT / asset["local_path"]
        if hashlib.sha256(raw_asset.read_bytes()).hexdigest() != asset["sha256"]:
            raise SystemExit(f"linked asset hash mismatch: {asset['local_path']}")
        web_asset = WEB / Path(asset["local_path"]).relative_to("source_original")
        web_asset.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(raw_asset, web_asset)
        asset_paths[asset["source_href"]] = web_asset

    link_audit: list[dict[str, str]] = []
    audit_path = ROOT / "source_link_audit.csv"
    if audit_path.exists():
        with audit_path.open(newline="", encoding="utf-8-sig") as f:
            # Preserve live checks of external edition links across rebuilds.
            link_audit.extend(
                row for row in csv.DictReader(f)
                if row.get("source_target_status", "").startswith("checked ")
            )

    inventory: list[dict[str, str | int]] = []
    status: list[dict[str, str | int]] = []
    metadata_links: list[dict[str, str]] = []
    status_path = ROOT / "translation_status.csv"
    prior_status = {}
    if status_path.exists():
        with status_path.open(newline="", encoding="utf-8-sig") as f:
            prior_status = {r["unit_id"]: r for r in csv.DictReader(f)}
    corpus_words = 0

    for rec in records:
        rel = Path(rec["local_path"])
        raw_path = ROOT / rel
        body = raw_path.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        if digest != rec["sha256"]:
            raise SystemExit(f"source hash mismatch: {rel}")
        decoded = body.decode("iso-8859-1", errors="replace")
        meta = re.search(r"<meta\b[^>]*\bcharset\s*=\s*['\"]?([^\s\"'>;]+)", decoded, re.I)
        meta_enc = meta.group(1).lower() if meta else "not-declared"
        old_http = rec.get("detected_encoding", "unknown")
        rec["http_charset"] = old_http
        rec["html_meta_charset"] = meta_enc
        rec["detected_encoding"] = "iso-8859-1" if meta_enc in {"iso-8859-1", "latin1", "latin-1"} else old_http
        rec["decoding_note"] = (
            "HTML meta declaration used; response charset differs"
            if old_http.lower() != rec["detected_encoding"].lower()
            else "HTML meta and response charset agree"
        )

        web_path = WEB / rel.name
        web_bytes = body
        for target in re.findall(rb'<link\b[^>]*\bhref\s*=\s*["\']([^"\']*editdata\.mso)["\'][^>]*>', body, re.I):
            metadata_links.append({"source_page": rel.name, "original_href": target.decode("latin-1"),
                                   "source_target_status": "legacy Word metadata; not required for reading", "offline_target": "", 
                                   "treatment": "Removed from derived offline copy; exact source preserved."})
        web_bytes = re.sub(rb'<link\b(?=[^>]*\brel\s*=\s*["\']?Edit-Time-Data)[^>]*>', b"", web_bytes, flags=re.I)
        # Core Corpus pages are flattened into web/; audit their offline name, not source_original/.
        source_page = rel.name
        background_path = next((p for href, p in asset_paths.items() if href.endswith("marbre2.jpg")), None)
        if background_path:
            web_bytes = rewrite_background(web_bytes, source_page, background_path, link_audit)
        web_bytes = rewrite_asset_sources(web_bytes, source_page, asset_paths, link_audit)
        if rel.name in {"Componendo.htm", "Confirmando.htm", "Emendatio.htm"}:
            web_bytes = rewrite_preface_popups(web_bytes, source_page, link_audit)
        for script_match in re.finditer(rb'<script\b[^>]*\bsrc\s*=\s*["\']([^"\']*urchin\.js)[^>]*>.*?</script\s*>', body, re.I | re.S):
            link_audit.append({
                "source_page": source_page,
                "original_href": script_match.group(1).decode("latin-1"),
                "source_target_status": "external legacy analytics script",
                "offline_target": "",
                "treatment": "Removed analytics script from derived offline copy; raw source preserved.",
            })
        web_bytes = re.sub(rb'<script\b[^>]*\bsrc\s*=\s*["\'][^"\']*urchin\.js[^>]*>.*?</script\s*>', b"", web_bytes, flags=re.I | re.S)
        if rel.name == "CJ1.htm":
            # Repair obsolete MS Word navigation targets in this derived offline copy only.
            web_bytes = web_bytes.replace(b'href="#3"', b'href="#1.3"')
            web_bytes = web_bytes.replace(b'href="#27"', b'href="#1.27"')
            web_bytes = web_bytes.replace(b'href="01_57.htm#22"', b'href="#1.22"')
        web_path.write_bytes(web_bytes)

        visible = text_of(body)
        wc = word_count(visible)
        corpus_words += wc
        parser = VisibleText()
        parser.feed(decoded)
        # Capture named anchors in source order, including nonstandard/special labels.
        anchors = []
        for m in re.finditer(r"<a\b([^>]*)>", decoded, re.I | re.S):
            attrs = m.group(1)
            name_m = re.search(r"\b(?:name|id)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", attrs, re.I)
            if name_m:
                anchors.append(next(g for g in name_m.groups() if g is not None))

        file_name = rel.name
        if file_name == "codjust.htm":
            kind = "index_and_editorial_note"
            unit = "index"
            status.append({"unit_id": unit, "source_page": file_name, "source_anchor": "", "source_words": wc,
                           "translation_status": "not_started", "review_status": "not_started", "translation_file": "", "notes": "Translate English site description and page-level credits; retain Latin title/metadata."})
        elif file_name in {"Componendo.htm", "Confirmando.htm", "Emendatio.htm"}:
            kind = "prefatory_latin_text"
            unit = Path(file_name).stem
            status.append({"unit_id": unit, "source_page": file_name, "source_anchor": "", "source_words": wc,
                           "translation_status": "not_started", "review_status": "not_started", "translation_file": "", "notes": "Translate complete prefatory Latin text; preserve headings, editor notes, and paragraph structure."})
        else:
            kind = "book"
            unit = Path(file_name).stem
            # Front matter and editor's English note before the first numbered title.
            status.append({"unit_id": f"{unit}_frontmatter", "source_page": file_name, "source_anchor": "", "source_words": "",
                           "translation_status": "not_started", "review_status": "not_started", "translation_file": "", "notes": "Translate page title and English editorial note; Latin title text remains in source."})
            # Numeric anchors with exactly book.title.constitution identify constitutions.
            constitutions = []
            for m in re.finditer(r"<a\b([^>]*)>", decoded, re.I | re.S):
                attrs = m.group(1)
                n = re.search(r"\bname\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", attrs, re.I)
                if not n:
                    continue
                anchor = next(g for g in n.groups() if g is not None)
                if re.fullmatch(r"\d+\.\d+\.\d+", anchor):
                    constitutions.append((m.start(), anchor))
            for idx, (start, anchor) in enumerate(constitutions):
                end = constitutions[idx + 1][0] if idx + 1 < len(constitutions) else len(decoded)
                seg = decoded[start:end].encode("iso-8859-1", errors="replace")
                wc_unit = word_count(text_of(seg))
                status.append({"unit_id": anchor, "source_page": file_name, "source_anchor": anchor, "source_words": wc_unit,
                               "translation_status": "not_started", "review_status": "not_started", "translation_file": "", "notes": ""})

        inventory.append({"source_page": file_name, "kind": kind, "sha256": digest, "bytes": len(body),
                          "words_visible_estimate": wc, "anchor_count": len(anchors),
                          "anchors_semicolon_separated": ";".join(anchors)})

    for linked_page in manifest.get("linked_pages", []):
        rel = Path(linked_page["local_path"]).relative_to("source_original")
        linked_page.setdefault("source_href", f"../{rel.as_posix()}")
        raw_path = ROOT / linked_page["local_path"]
        body = raw_path.read_bytes()
        if hashlib.sha256(body).hexdigest() != linked_page["sha256"]:
            raise SystemExit(f"linked page hash mismatch: {linked_page['local_path']}")
        web_path = WEB / rel
        web_path.parent.mkdir(parents=True, exist_ok=True)
        web_bytes = body
        background_path = next((p for href, p in asset_paths.items() if href.endswith("marbre2.jpg")), None)
        if background_path:
            web_bytes = rewrite_background(web_bytes, rel.as_posix(), background_path, link_audit)
        for script_match in re.finditer(rb'<script\b[^>]*\bsrc\s*=\s*["\']([^"\']*urchin\.js)[^>]*>.*?</script\s*>', body, re.I | re.S):
            link_audit.append({
                "source_page": rel.as_posix(),
                "original_href": script_match.group(1).decode("latin-1"),
                "source_target_status": "external legacy analytics script",
                "offline_target": "",
                "treatment": "Removed analytics script from derived offline copy; raw source preserved.",
            })
        web_bytes = re.sub(rb'<script\b[^>]*\bsrc\s*=\s*["\'][^"\']*urchin\.js[^>]*>.*?</script\s*>', b"", web_bytes, flags=re.I | re.S)
        web_path.write_bytes(web_bytes)

    manifest["records"] = records
    manifest["encoding_policy"] = "Raw bytes are preserved. The HTML meta charset is recorded per page and used for source decoding; any response-header mismatch is flagged."
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with (ROOT / "source_inventory.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(inventory[0]))
        w.writeheader(); w.writerows(inventory)
    for row in status:
        prev = prior_status.get(str(row["unit_id"]))
        if prev:
            for field in ("translation_status", "review_status", "translation_file"):
                row[field] = prev.get(field, row[field]) or row[field]
            if prev.get("notes") and prev["notes"] != "":
                row["notes"] = prev["notes"]
    with status_path.open("w", newline="", encoding="utf-8-sig") as f:
        cols = ["unit_id", "source_page", "source_anchor", "source_words", "translation_status", "review_status", "translation_file", "notes"]
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(status)

    with (ROOT / "source_link_audit.csv").open("w", newline="", encoding="utf-8-sig") as f:
        cols = ["source_page", "original_href", "source_target_status", "offline_target", "treatment"]
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        w.writerows([
            {"source_page": "CJ1.htm", "original_href": "#3", "source_target_status": "missing anchor in original page", "offline_target": "#1.3", "treatment": "Mapped stale TOC target to the extant title anchor; raw source unchanged."},
            {"source_page": "CJ1.htm", "original_href": "#27", "source_target_status": "missing anchor in original page", "offline_target": "#1.27", "treatment": "Mapped stale TOC target to the extant title anchor; raw source unchanged."},
            {"source_page": "CJ1.htm", "original_href": "01_57.htm#22", "source_target_status": "HTTP 404 at linked URL", "offline_target": "#1.22", "treatment": "Mapped stale TOC target to the extant title anchor; raw source unchanged."},
        ] + metadata_links + link_audit)
    (WEB / "README.md").write_text(
        "# 离线网页副本\n\n"
        "本目录包含索引页、三篇前置文本、Libri I–XII、三篇辅助法文参照页及所需图片。派生副本修复了 `CJ1.htm` 的三处失效旧导航目标，重写了图片与前言法译页的离线路径，并移除了旧 Word 元数据链接和法文参照页中的统计脚本；处理清单见项目根目录 `source_link_audit.csv`。原始服务器字节仅保存在 `source_original/`，不得用本目录副本替代。辅助法文页面仅供离线参阅，不纳入中文双语 EPUB 的翻译范围。\n",
        encoding="utf-8",
    )
    for filename, header in [
        ("translation_issues.csv", ["issue_id", "source_location", "issue_type", "description", "proposed_handling", "status"]),
        ("glossary.csv", ["latin_term", "preferred_chinese", "context_note", "status"]),
    ]:
        path = ROOT / filename
        if not path.exists():
            with path.open("w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow(header)
    glossary = ROOT / "glossary.csv"
    with glossary.open(newline="", encoding="utf-8-sig") as f:
        glossary_rows = list(csv.DictReader(f))
    if not glossary_rows:
        with glossary.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["latin_term", "preferred_chinese", "context_note", "status"])
            w.writeheader()
            w.writerows([
                {"latin_term": "Codex Iustinianus", "preferred_chinese": "《查士丁尼法典》", "context_note": "全书书名；拉丁题名首次并列保留。", "status": "provisional"},
                {"latin_term": "Corpus Iuris Civilis", "preferred_chinese": "《民法大全》", "context_note": "丛书名；首次并列保留拉丁题名。", "status": "provisional"},
                {"latin_term": "liber", "preferred_chinese": "卷", "context_note": "全书层级；必要时保留 Liber I 等原编号。", "status": "provisional"},
                {"latin_term": "titulus", "preferred_chinese": "题", "context_note": "卷内层级；题名保留原编号。", "status": "provisional"},
                {"latin_term": "constitutio", "preferred_chinese": "敕令", "context_note": "皇帝立法文本的泛称；依具体文本功能细分。", "status": "provisional"},
                {"latin_term": "imperator", "preferred_chinese": "皇帝", "context_note": "罗马皇帝；不与现代国家元首制度作等同。", "status": "provisional"},
            ])
    readme = ROOT / "README.md"
    readme.write_text(
        "# Codex Iustinianus — 学术双语 EPUB 工作目录\n\n"
        "来源索引：<https://droitromain.univ-grenoble-alpes.fr/Corpus/codjust.htm>\n\n"
        "## 来源与范围\n\n"
        "索引页、三篇前置文本和 Libri I–XII 共 16 个核心页面已抓取；另存三篇由前言图标链接的法文辅助参照页及三项图片资源，仅用于离线网页导航，不纳入中文双语 EPUB 的翻译范围。`source_original/` 逐字节保留服务器响应；`source_manifest.json` 记录 URL、SHA-256、字符编码和页面标题。网页 HTTP 声明与 HTML 内部 `meta` 编码标签有冲突，原始文件未改，依据文件内 ISO-8859-1 声明解码，并在 manifest 中记录冲突。\n\n"
        "`web/` 是可离线浏览副本。三处失效旧目录链接映射、图片与法译链接修复、遗留 Word 元数据处理及法文参照页统计脚本移除情况见 `source_link_audit.csv`；原始页面不作修订。\n\n"
        "## 当前产物与翻译进度\n\n"
        "`Codex_Iustinianus_Krueger_Latin_source.epub` 是完整拉丁文阅读版；`Codex_Iustinianus_Krueger_bilingual.epub` 是完成中译与二校的拉丁文—中文双语阅读版，保留可导航的卷、题与法条层级。`translation_status.csv` 记录 4,683 个翻译单元的进度。\n\n"
        "`build_corpus.py` 重建离线副本与台账；`build_latin_epub.py` 重建拉丁文 EPUB。\n",
        encoding="utf-8",
    )

    print(f"pages={len(records)} visible_word_estimate={corpus_words} translation_units={len(status)}")
    print("per-page estimates:")
    for r in inventory:
        print(f"  {r['source_page']}: {r['words_visible_estimate']} words, {r['anchor_count']} anchors")


if __name__ == "__main__":
    main()
