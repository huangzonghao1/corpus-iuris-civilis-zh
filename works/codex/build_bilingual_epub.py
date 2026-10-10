#!/usr/bin/env python3
"""Build a source-aligned scholarly Latin–Chinese EPUB 3 from translation drafts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from audit_translation_sources import SourceAnchorExtractor, markdown_unit_sources, normalize
from build_latin_epub import RAW, title_entries

ROOT = Path(__file__).resolve().parent
TRANS = ROOT / "translation"
STATUS = ROOT / "translation_status.csv"
OUTPUT = ROOT / "Codex_Iustinianus_Krueger_bilingual.epub"
INDEX_PAGE = "codjust.htm"
PREFACES = ["Componendo", "Confirmando", "Emendatio"]

NUMERIC_HEADING = re.compile(r"^(\d+\.\d+\.\d+(?:\.(?:pr\.?|\d+[a-z]?|[a-z]))?)(?:\s+.*)?$")
# Topic headings occur both with and without an explicit ``.0`` in the
# translation corpus (for example ``2.7`` and ``2.7.0``). Article headings
# have a third, non-zero component and therefore do not match this pattern.
TOPIC_HEADING = re.compile(r"^(\d+\.\d+)(?:\.0)?(?:\.)?(?:\s|$)")
SOURCE_LABEL = re.compile(r"(?m)^\*\*[^*]*(?:拉丁原文|拉丁题名|拉丁文题名|拉丁文|网页原文编辑标记|网页编者说明|网页原文说明|原文编辑说明|原文)[^*]*\*\*\s*(.*)$")
CN_LABEL = re.compile(r"^\*\*(?:中文译文|译文)(?:：|:)?\*\*\s*(.*)$")
CN_TOPIC_LABEL = re.compile(r"^\*\*(?:题名译文|中文题名|中文)(?:：|:)?\*\*(?:：|:)?\s*(.*)$")
NOTE_LABEL = re.compile(r"^\*\*(?:译者校记|译者说明|校记)(?:：|:)?\*\*[:：]?\s*(.*)$")
EN_LABEL = re.compile(r"^\*\*(?:[^*]*英文[^*]*|网页编者说明)\*\*\s*(.*)$")
FR_LABEL = re.compile(r"^\*\*法文原文\*\*\s*(.*)$")
CHINESE_ONLY_EXTRA_SOURCE_LABEL = re.compile(
    r"^\*\*(?:网页所标日期|网页编辑说明|(?:本题原题|本题题名)(?:（[^*]*）)?|题名(?:（网页[^*]*）)?)(?:：|:)?\*\*\s*(.*)$"
)

CHINESE_ONLY_H1 = {
    "titlepage.md": "《查士丁尼法典》",
    "index.md": "《查士丁尼法典》— 索引页说明译文",
    "Componendo.md": "关于编纂新法典",
    "CJ1_1.2.1-1.2.25.md": "《查士丁尼法典》第一卷第2题",
}

CHINESE_PREFACE_TITLES = {
    "Componendo": "关于编纂新法典",
    "Confirmando": "关于确认《查士丁尼法典》",
    "Emendatio": "关于校订《查士丁尼法典》及其第二版",
}


def read_rows():
    with STATUS.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def markdown_sections(path: Path):
    """Yield (heading level, heading text, body lines) for Markdown sections."""
    current_level = 0
    current_heading = ""
    body: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match:
            if current_heading or body:
                yield current_level, current_heading, body
            current_level = len(match.group(1))
            current_heading = match.group(2).strip()
            body = []
        else:
            body.append(line)
    if current_heading or body:
        yield current_level, current_heading, body


def chinese_only_body_lines(lines: list[str]) -> list[str]:
    """Remove explicitly labeled source-language blocks, preserving Chinese text.

    The translation corpus uses a small number of historical marker variants;
    these are handled as source labels here rather than deleting by Latin-letter
    frequency, which would remove legal terms retained in the Chinese prose.
    """
    result: list[str] = []
    dropping_source = False
    extra_keep = re.compile(r"^\*\*(?:译注|术语说明)(?:：|:)?\*\*\s*(.*)$")
    mixed_topic_title = re.compile(r"^\*\*题名(?:：|:)\*\*\s*(.*)$")
    for raw in lines:
        line = raw.strip()
        mixed_title = mixed_topic_title.match(line)
        if mixed_title:
            chinese_titles = re.findall(r"[（(]([^（）()]*)[）)]", mixed_title.group(1))
            chinese_title = next((t.strip() for t in chinese_titles if re.search(r"[\u4e00-\u9fff]", t)), "")
            if chinese_title:
                dropping_source = False
                result.append(f"**中文题名：** {chinese_title}")
            else:
                dropping_source = True
            continue
        source = (SOURCE_LABEL.match(line) or EN_LABEL.match(line)
                  or FR_LABEL.match(line) or CHINESE_ONLY_EXTRA_SOURCE_LABEL.match(line))
        chinese = (CN_LABEL.match(line) or CN_TOPIC_LABEL.match(line) or NOTE_LABEL.match(line)
                   or extra_keep.match(line))
        if source:
            dropping_source = True
            continue
        if chinese:
            dropping_source = False
            result.append(translate_english_lacuna_note(raw))
            continue
        if not dropping_source:
            result.append(translate_english_lacuna_note(raw))
    return result


def translate_english_lacuna_note(line: str) -> str:
    """Keep the source's missing-Greek notice in Chinese without its English wording."""
    line = re.sub(
        r"［网页编者说明（原文）：Here there is a Greek text\. Sorry, it is not yet in the Library\.］中文：［([^］]*)］",
        r"［网页编者说明：\1］",
        line,
    )
    return line.replace(
        "Here there is a Greek text. Sorry, it is not yet in the Library.",
        "此处有一段希腊文。抱歉，目前本网站图书馆尚未收录。",
    )


def chinese_only_heading(path: Path, heading: str, level: int, topic_titles: dict[str, str]) -> str:
    if level == 1:
        if path.name in CHINESE_ONLY_H1:
            return CHINESE_ONLY_H1[path.name]
        heading = heading.replace("《Codex Iustinianus》", "《查士丁尼法典》")
        heading = heading.replace("Codex Iustinianus", "《查士丁尼法典》")
        heading = re.sub(r"《+查士丁尼法典》+", "《查士丁尼法典》", heading)
        heading = heading.replace("De novo codice componendo", "关于编纂新法典")
        heading = re.sub(r"\s*拉丁文[—–-]中文对照", "", heading)
        return heading
    topic = TOPIC_HEADING.match(heading)
    if topic:
        number = topic.group(1)
        title = topic_titles.get(number, "")
        if title:
            return f"{number}.0 {title}"
    return heading


def markdown_inline(text: str) -> str:
    """Convert the limited inline Markdown used in the scholarly drafts."""
    text = escape(text)
    code_spans: list[str] = []

    def protect_code(match: re.Match[str]) -> str:
        code_spans.append(f"<code>{match.group(1)}</code>")
        return f"\ue000CODE{len(code_spans) - 1}\ue001"

    text = re.sub(r"`([^`]+)`", protect_code, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', text)
    for index, code in enumerate(code_spans):
        text = text.replace(f"\ue000CODE{index}\ue001", code)
    return text


def markdown_latin_inline(text: str) -> str:
    """Render structural bold markers without consuming source editorial asterisks."""
    text = escape(text)
    code_spans: list[str] = []

    def protect_code(match: re.Match[str]) -> str:
        code_spans.append(f"<code>{match.group(1)}</code>")
        return f"\ue000CODE{len(code_spans) - 1}\ue001"

    text = re.sub(r"`([^`]+)`", protect_code, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    for index, code in enumerate(code_spans):
        text = text.replace(f"\ue000CODE{index}\ue001", code)
    return text


def heading_id(level: int, text: str) -> str:
    topic = TOPIC_HEADING.match(text)
    if topic:
        return topic.group(1)
    numeric = NUMERIC_HEADING.match(text)
    if numeric:
        return numeric.group(1).rstrip(".")
    slug = re.sub(r"[^\w-]+", "-", text, flags=re.UNICODE).strip("-").lower()
    return (slug or f"heading-{level}")[:100]


def file_unit_topics(path: Path):
    topics: list[tuple[str, str]] = []
    units: list[tuple[str, str]] = []
    for level, heading, _body in markdown_sections(path):
        if level < 1:
            continue
        topic_match = TOPIC_HEADING.match(heading)
        if topic_match:
            topics.append((topic_match.group(1), heading))
            continue
        match = NUMERIC_HEADING.match(heading)
        if match:
            raw = match.group(1).rstrip(".")
            pieces = raw.split(".")
            if len(pieces) >= 3 and pieces[2].isdigit() and pieces[2] != "0":
                units.append((".".join(pieces[:3]), raw))
    explicit = {topic for topic, _heading in topics}
    for unit, _raw in units:
        topic = ".".join(unit.split(".")[:2])
        if topic not in explicit:
            topics.append((topic, topic))
            explicit.add(topic)
    return topics, units


def topic_title_from_lines(lines: list[str]) -> str:
    """Extract a translated topic title from the labels used across drafts."""
    label = re.compile(r"^\*\*(?:题名译文|中文题名|中文)(?:：|:)?\*\*(?:：|:)?\s*(.*)$")
    for index, line in enumerate(lines):
        match = label.match(line.strip())
        if not match:
            continue
        value = match.group(1).strip()
        if value:
            return re.sub(r"^>\s?", "", value).strip()
        for following in lines[index + 1:]:
            candidate = following.strip()
            if not candidate:
                continue
            if candidate.startswith("**") or candidate.startswith("#") or candidate.startswith("```"):
                break
            return re.sub(r"^>\s?", "", candidate).strip()
    return ""


def has_nonempty_translation(lines: list[str]) -> bool:
    """Require actual Chinese prose after a translation label."""
    for index, line in enumerate(lines):
        match = CN_LABEL.match(line.strip())
        if not match:
            continue
        if match.group(1).strip():
            return True
        for following in lines[index + 1:]:
            candidate = following.strip()
            if not candidate or candidate.startswith("```"):
                continue
            if (SOURCE_LABEL.match(candidate) or EN_LABEL.match(candidate)
                    or CN_LABEL.match(candidate) or CN_TOPIC_LABEL.match(candidate)
                    or NOTE_LABEL.match(candidate)):
                break
            return True
    return False


def render_body(lines: list[str], initial_mode: str = "zh") -> str:
    out: list[str] = []
    mode = initial_mode
    paragraph: list[str] = []
    list_kind: str | None = None
    table_rows: list[list[str]] = []
    in_code = False
    code_lines: list[str] = []

    def close_list():
        nonlocal list_kind
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None

    def flush_para():
        if not paragraph:
            return
        text = " ".join(part.strip() for part in paragraph).strip()
        paragraph.clear()
        if not text:
            return
        if mode == "la":
            out.append(f'<p class="latin" lang="la" xml:lang="la">{markdown_latin_inline(text)}</p>')
        elif mode == "fr":
            out.append(f'<p class="french" lang="fr" xml:lang="fr">{markdown_inline(text)}</p>')
        elif mode == "en":
            out.append(f'<p class="english" lang="en" xml:lang="en">{markdown_inline(text)}</p>')
        else:
            cls = "editorial-note" if mode == "note" else "chinese"
            out.append(f'<p class="{cls}" lang="zh-CN" xml:lang="zh-CN">{markdown_inline(text)}</p>')

    def flush_table():
        nonlocal table_rows
        if not table_rows:
            return
        out.append('<table class="scholarly-table">')
        for row_index, cells in enumerate(table_rows):
            if not cells or all(re.fullmatch(r"[-: ]+", c or "") for c in cells):
                continue
            tag = "th" if row_index == 0 else "td"
            out.append("<tr>" + "".join(f"<{tag}>{markdown_inline(c.strip())}</{tag}>" for c in cells) + "</tr>")
        out.append("</table>")
        table_rows = []

    for raw in lines:
        line = raw.strip()
        if line.startswith("```"):
            flush_para(); flush_table(); close_list()
            if in_code:
                code_text = escape("\n".join(code_lines))
                lang = {"la": "la", "en": "en", "fr": "fr"}.get(mode, "zh-CN")
                out.append(f'<pre lang="{lang}" xml:lang="{lang}"><code>{code_text}</code></pre>')
                code_lines.clear()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(raw)
            continue

        source = SOURCE_LABEL.match(line)
        chinese = CN_LABEL.match(line)
        chinese_title = CN_TOPIC_LABEL.match(line)
        note = NOTE_LABEL.match(line)
        english = EN_LABEL.match(line)
        french = FR_LABEL.match(line)
        if source or chinese or chinese_title or note or english or french:
            flush_para(); flush_table(); close_list()
            if english:
                mode = "en"
                label, remainder = "网页英文说明", english.group(1)
            elif french:
                mode = "fr"
                label, remainder = "法文原文", french.group(1)
            elif chinese_title:
                mode = "zh"
                label_match = re.match(r"^\*\*(.*?)\*\*", line)
                label = label_match.group(1) if label_match else "中文题名"
                remainder = chinese_title.group(1)
            elif source:
                source_label = re.match(r"^\*\*(.*?)\*\*", line)
                source_name = source_label.group(1) if source_label else "拉丁原文"
                english_editorial = any(term in source_name for term in (
                    "网页原文编辑标记", "网页编者说明", "网页原文说明", "原文编辑说明"
                ))
                mode = "en" if mode == "en" or english_editorial else "la"
                label = source_name
                remainder = source.group(1)
            elif chinese:
                mode = "zh"
                label, remainder = "中文译文", chinese.group(1)
            else:
                mode = "note"
                label, remainder = "译者校记", note.group(1)
            out.append(f'<p class="section-label" lang="zh-CN" xml:lang="zh-CN">{label}</p>')
            if remainder.strip():
                paragraph.append(remainder.strip())
            continue

        if not line:
            flush_para(); flush_table(); close_list()
            continue
        if line.startswith("|") and line.endswith("|"):
            flush_para(); close_list()
            table_rows.append([c.strip() for c in line.strip("|").split("|")])
            continue
        flush_table()
        if re.match(r"^[-*+]\s+", line) or re.match(r"^\d+[.)]\s+", line):
            flush_para()
            ordered = bool(re.match(r"^\d+[.)]\s+", line))
            needed = "ol" if ordered else "ul"
            if list_kind != needed:
                close_list(); out.append(f"<{needed}>"); list_kind = needed
            item = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+)", "", line)
            lang_value = {"la": "la", "en": "en", "fr": "fr"}.get(mode, "zh-CN")
            lang = f' lang="{lang_value}" xml:lang="{lang_value}"'
            out.append(f"<li{lang}>{escape(item) if mode == 'la' else markdown_inline(item)}</li>")
            continue
        if line.startswith(">"):
            flush_para()
            quoted = re.sub(r"^>\s?", "", line)
            lang_value = {"la": "la", "en": "en", "fr": "fr"}.get(mode, "zh-CN")
            lang = f' lang="{lang_value}" xml:lang="{lang_value}"'
            cls = {"la": "latin", "en": "english-quotation", "fr": "french"}.get(mode, "chinese-quotation")
            rendered_quote = markdown_latin_inline(quoted) if mode == "la" else markdown_inline(quoted)
            out.append(f'<blockquote class="{cls}"{lang}><p>{rendered_quote}</p></blockquote>')
            continue
        if re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", line):
            flush_para(); flush_table(); close_list()
            out.append("<hr />")
            continue
        paragraph.append(line)
    flush_para(); flush_table(); close_list()
    if in_code:
        code_text = escape("\n".join(code_lines))
        lang = "la" if mode == "la" else "en" if mode == "en" else "zh-CN"
        out.append(f'<pre lang="{lang}" xml:lang="{lang}"><code>{code_text}</code></pre>')
    return "\n".join(out)


def build_xhtml(path: Path, href: str, *, chinese_only: bool = False,
                topic_titles: dict[str, str] | None = None) -> tuple[str, str]:
    sections = list(markdown_sections(path))
    topic_titles = topic_titles or {}
    if chinese_only:
        sections = [
            (level, chinese_only_heading(path, heading, level, topic_titles), chinese_only_body_lines(lines))
            for level, heading, lines in sections
        ]
    title = sections[0][1] if sections and sections[0][0] == 1 else path.stem
    body: list[str] = []
    seen_unit_ids: set[str] = set()
    emitted_ids: set[str] = set()
    explicit_topic_ids = {
        match.group(1)
        for level, heading, _lines in sections
        if level >= 1 and (match := TOPIC_HEADING.match(heading))
    }
    explicit_base_ids = set()
    for level, heading, _lines in sections:
        match = NUMERIC_HEADING.match(heading) if level >= 1 else None
        if not match:
            continue
        raw = match.group(1).rstrip(".")
        pieces = raw.split(".")
        if len(pieces) >= 3 and pieces[2].isdigit() and pieces[2] != "0" and raw == ".".join(pieces[:3]):
            explicit_base_ids.add(raw)
    doc_title_assigned = False
    mode = "zh"
    for level, heading, lines in sections:
        if level:
            if heading.startswith(("网页英文", "英文")):
                mode = "en"
            elif heading.startswith("法文"):
                mode = "fr"
            elif heading.strip() in {"拉丁书名", "拉丁原文", "拉丁文原文", "拉丁题名", "拉丁文题名"}:
                mode = "la"
            else:
                mode = "zh"
            match = NUMERIC_HEADING.match(heading) if level >= 1 else None
            topic_match = TOPIC_HEADING.match(heading) if level >= 1 else None
            raw = match.group(1).rstrip(".") if match else ""
            parts = raw.split(".") if raw else []
            is_article_heading = len(parts) >= 3 and parts[2].isdigit() and parts[2] != "0"

            # Keep the work-level link available even when an early manuscript
            # begins with a numbered article heading rather than a title.
            if level == 1 and not doc_title_assigned:
                if is_article_heading or topic_match:
                    body.append('<span id="doc-title"></span>')
                    emitted_ids.add("doc-title")
                    hid = topic_match.group(1) if topic_match else heading_id(level, heading)
                else:
                    hid = "doc-title"
                doc_title_assigned = True
            elif topic_match:
                hid = topic_match.group(1)
            else:
                hid = heading_id(level, heading)

            if match:
                if is_article_heading:
                    topic = ".".join(parts[:2])
                    if topic not in explicit_topic_ids and topic not in emitted_ids:
                        body.append(f'<span id={quoteattr(topic)}></span>')
                        emitted_ids.add(topic)
                    base = ".".join(parts[:3])
                    if raw != base and base not in explicit_base_ids and base not in emitted_ids:
                        body.append(f'<span id={quoteattr(base)}></span>')
                        emitted_ids.add(base)
                    if raw in seen_unit_ids:
                        raise SystemExit(f"duplicate article heading ID {raw} in {path}")
                    seen_unit_ids.add(raw)
            if hid in emitted_ids:
                if is_article_heading:
                    raise SystemExit(f"duplicate numbered heading ID {hid} in {path}")
                base = hid
                suffix = 2
                while f"{base}-{suffix}" in emitted_ids:
                    suffix += 1
                hid = f"{base}-{suffix}"
            emitted_ids.add(hid)
            if level == 1 and not doc_title_assigned:
                doc_title_assigned = True
            tag = f"h{level}"
            attrs = f" id={quoteattr(hid)}"
            body.append(f"<{tag}{attrs}>{markdown_inline(heading)}</{tag}>")
        rendered = render_body(lines, mode)
        if rendered:
            body.append(rendered)
    css_href = "../styles.css"
    rendered_body = "\n".join(body)
    document = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN" xml:lang="zh-CN">
<head><title>{escape(title)}</title><meta charset="utf-8" /><link rel="stylesheet" type="text/css" href="{css_href}" /></head>
<body><main>{rendered_body}</main></body></html>'''
    return title, document


def slug(path: Path) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "-", path.stem).strip("-")
    return value or "translation"


def get_language_page_items(paths: list[Path]):
    docs = []
    for path in paths:
        if path.name == "titlepage.md":
            kind, book = "title", 0
        elif path.name == "index.md":
            kind, book = "index", 0
        elif path.stem in PREFACES:
            kind, book = "preface", 0
        elif re.match(r"^CJ\d+_", path.stem):
            kind, book = "legal", int(re.match(r"^CJ(\d+)_", path.stem).group(1))
        elif path.name in {"版本与翻译说明.md", "术语表.md", "文本问题表.md", "书目与数字版本来源.md"}:
            kind, book = "apparatus", 99
        else:
            # Only project translation manuscripts are included.
            continue
        topics, units = file_unit_topics(path)
        first_unit = min((u for u, _ in units), key=lambda s: tuple(int(p) for p in s.split(".")[:3]), default="")
        docs.append({"path": path, "kind": kind, "book": book, "topics": topics, "units": units, "first_unit": first_unit})
    order = {"title": 0, "index": 1, "preface": 2, "legal": 3, "apparatus": 4}
    docs.sort(key=lambda d: (order[d["kind"]], d["book"],
                             tuple(int(p) for p in d["first_unit"].split(".")[:3]) if d["first_unit"] else (0,), d["path"].name))
    for i, doc in enumerate(docs, 1):
        doc["href"] = f"text/{i:04d}-{slug(doc['path'])}.xhtml"
    return docs


def check_coverage(rows, docs, allow_incomplete: bool):
    legal_rows = [r for r in rows if re.fullmatch(r"\d+\.\d+\.\d+", r["unit_id"])]
    by_page: dict[str, list[str]] = defaultdict(list)
    for row in legal_rows:
        by_page[row["source_page"]].append(row["unit_id"])
    sources = {}
    for page, units in by_page.items():
        parser = SourceAnchorExtractor(set(units))
        parser.feed((RAW / page).read_bytes().decode("iso-8859-1"))
        sources.update(parser.texts())

    draft: dict[str, str] = {}
    source_file: dict[str, str] = {}
    for doc in docs:
        path = doc["path"]
        for unit, quote in markdown_unit_sources(path).items():
            # Ignore topic-number headings, which are not legal units.
            if not re.fullmatch(r"\d+\.\d+\.[1-9]\d*", unit):
                continue
            if unit in draft:
                raise SystemExit(f"duplicate Latin quotation for {unit} in {source_file[unit]} and {path.name}")
            draft[unit] = quote
            source_file[unit] = path.name

    units_to_doc: dict[str, str] = {}
    topics_to_doc: dict[str, str] = {}
    topic_titles: dict[str, str] = {}
    for doc in docs:
        sections = list(markdown_sections(doc["path"]))
        for topic, heading in doc["topics"]:
            topics_to_doc.setdefault(topic, doc["href"])
            topic_section_index = None
            for section_index, (level, head, body) in enumerate(sections):
                match = TOPIC_HEADING.match(head) if level >= 1 else None
                if match and match.group(1) == topic:
                    topic_section_index = section_index
                    title = topic_title_from_lines(body)
                    if title:
                        topic_titles.setdefault(topic, title)
                    break

            # Some older files put the title in a separate ``### 题名``
            # section immediately after the numbered topic heading.
            if topic not in topic_titles and topic_section_index is not None:
                for level, head, body in sections[topic_section_index + 1:]:
                    if TOPIC_HEADING.match(head) or NUMERIC_HEADING.match(head):
                        break
                    if "题名" in head:
                        title = topic_title_from_lines(body)
                        if title:
                            topic_titles.setdefault(topic, title)
                            break

        # A small set of earlier drafts stores the topic number and its
        # Chinese title in the file's introductory metadata instead of a
        # dedicated topic-heading section.
        lines = doc["path"].read_text(encoding="utf-8-sig").splitlines()
        for index, line in enumerate(lines):
            if not any(token in line for token in ("题名", "原题")):
                continue
            number = re.search(r"(\d+\.\d+\.0)", line)
            if not number:
                continue
            topic = number.group(1)[:-2]
            title = topic_title_from_lines(lines[index + 1:index + 10])
            if title:
                topic_titles.setdefault(topic, title)
        # One early draft uses a plain Chinese h2 for its topic title rather
        # than a numbered topic heading or a title label.
        for topic, _heading in doc["topics"]:
            if topic in topic_titles:
                continue
            for level, heading, _body in sections:
                if level < 2 or TOPIC_HEADING.match(heading):
                    continue
                match = NUMERIC_HEADING.match(heading)
                if match:
                    pieces = match.group(1).rstrip(".").split(".")
                    if len(pieces) >= 3 and ".".join(pieces[:2]) == topic:
                        break
                    continue
                if re.search(r"[\u4e00-\u9fff]", heading):
                    topic_titles.setdefault(topic, heading.strip())
                    break
        for unit, _raw in doc["units"]:
            units_to_doc.setdefault(unit, doc["href"])

    missing_source = []
    missing_quote = []
    mismatched = []
    missing_translation = []
    missing_review = [r["unit_id"] for r in rows if r.get("review_status") != "ai_second_pass"]
    for row in legal_rows:
        unit = row["unit_id"]
        if unit not in sources:
            missing_source.append(unit)
            continue
        if unit not in draft:
            missing_quote.append(unit)
            continue
        if normalize(sources[unit]) != normalize(draft[unit]):
            mismatched.append(unit)
        docs_for_unit = [d for d in docs if unit in {u for u, _ in d["units"]}]
        path = docs_for_unit[0]["path"] if docs_for_unit else None
        if not docs_for_unit:
            missing_translation.append(unit)
        else:
            has_translation = False
            for _level, heading, body in markdown_sections(path):
                match = NUMERIC_HEADING.match(heading)
                if not match:
                    continue
                pieces = match.group(1).rstrip(".").split(".")
                if len(pieces) >= 3 and ".".join(pieces[:3]) == unit:
                    has_source = any(
                        SOURCE_LABEL.match(line.strip()) or EN_LABEL.match(line.strip())
                        for line in body
                    )
                    if has_nonempty_translation(body) and has_source:
                        has_translation = True
                        break
            if not has_translation:
                missing_translation.append(unit)

    expected_topics = {a for page in [f"CJ{i}.htm" for i in range(1, 13)] for a, _ in title_entries(page, (RAW / page).read_bytes())}
    missing_topics = sorted(expected_topics - set(topics_to_doc))
    missing_topic_titles = sorted(expected_topics - set(topic_titles))
    doc_by_name = {d["path"].name: d["path"] for d in docs}
    manual_units = {"index": "index.md", "Componendo": "Componendo.md",
                    "Confirmando": "Confirmando.md", "Emendatio": "Emendatio.md"}
    missing_nonlegal = []
    for row in rows:
        unit = row["unit_id"]
        if unit in manual_units:
            filename = manual_units[unit]
        elif re.fullmatch(r"CJ\d+_frontmatter", unit):
            filename = unit + ".md"
        else:
            continue
        path = doc_by_name.get(filename)
        if not path:
            missing_nonlegal.append(unit)
            continue
        text = path.read_text(encoding="utf-8-sig")
        if "中文" not in text or ("译文" not in text and "翻译" not in text):
            missing_nonlegal.append(unit)
    problems = {"missing_source": missing_source, "missing_quote": missing_quote, "mismatched": mismatched,
                "missing_translation": missing_translation, "missing_topics": missing_topics,
                "missing_topic_titles": missing_topic_titles, "missing_nonlegal": missing_nonlegal,
                "missing_review": missing_review}
    counts = {k: len(v) for k, v in problems.items()}
    print("Bilingual coverage:", len(legal_rows), "tracked legal units;", len(draft), "draft quotations;", counts)
    if any(counts.values()) and not allow_incomplete:
        for key, values in problems.items():
            if values:
                print(key + ":", ", ".join(values[:25]))
        raise SystemExit("Refusing to label an incomplete, unreviewed, or source-mismatched draft as the complete bilingual EPUB.")
    return units_to_doc, topics_to_doc, topic_titles


def xhtml(title: str, body: str, css: str = "styles.css", lang: str = "zh-CN") -> bytes:
    doc = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" xml:lang="{lang}">
<head><title>{escape(title)}</title><meta charset="utf-8" /><link rel="stylesheet" type="text/css" href="{escape(css)}" /></head>
<body><main>{body}</main></body></html>'''
    return doc.encode("utf-8")


def build_nav(rows, docs, units_to_doc, topics_to_doc, topic_titles, *, chinese_only: bool = False):
    page_by_book = {}
    for doc in docs:
        if doc["kind"] == "legal":
            page_by_book.setdefault(doc["book"], doc["href"])
    # Lexical filenames can put CJ10_10-* before CJ10_frontmatter. The volume
    # entry must point to its front matter, regardless of manuscript sort order.
    for doc in docs:
        if re.fullmatch(r"CJ\d+_frontmatter", doc["path"].stem):
            page_by_book[doc["book"]] = doc["href"]
    lines = ['<nav epub:type="toc" id="toc"><h1>目录</h1><ol>']
    title_doc = next((d for d in docs if d["kind"] == "title"), None)
    if title_doc:
        lines.append(f'<li><a href="{escape(title_doc["href"])}#doc-title">书名页</a></li>')
    index_doc = next((d for d in docs if d["kind"] == "index"), None)
    if index_doc:
        lines.append(f'<li><a href="{escape(index_doc["href"])}#doc-title">索引与版本说明</a><ol>')
        for name in PREFACES:
            doc = next((d for d in docs if d["path"].stem == name), None)
            if doc:
                label = CHINESE_PREFACE_TITLES.get(name, name) if chinese_only else name
                lines.append(f'<li><a href="{escape(doc["href"])}#doc-title">{escape(label)}</a></li>')
        lines.append('</ol></li>')

    by_topic = defaultdict(list)
    for row in rows:
        if re.fullmatch(r"\d+\.\d+\.\d+", row["unit_id"]):
            topic = ".".join(row["unit_id"].split(".")[:2])
            by_topic[topic].append(row["unit_id"])
    for book in range(1, 13):
        book_topics = [(a, label) for a, label in title_entries(f"CJ{book}.htm", (RAW / f"CJ{book}.htm").read_bytes())]
        if not book_topics:
            continue
        first = page_by_book.get(book)
        if not first:
            continue
        lines.append(f'<li><a href="{escape(first)}#doc-title">第{book}卷</a><ol>')
        for topic, latin_title in book_topics:
            canonical_topic = topic
            href = topics_to_doc.get(canonical_topic)
            if not href:
                continue
            anchor = "#" + canonical_topic
            zh = topic_titles.get(canonical_topic, "")
            if chinese_only:
                label = f"{canonical_topic}.0 {zh}" if zh else f"{canonical_topic}.0"
            else:
                label = f"{latin_title} — {zh}" if zh else latin_title
            lines.append(f'<li><a href="{escape(href + anchor)}">{markdown_inline(label)}</a>')
            law_units = by_topic.get(canonical_topic, [])
            if law_units:
                lines.append('<ol>')
                for unit in law_units:
                    law_href = units_to_doc.get(unit)
                    if law_href:
                        lines.append(f'<li><a href="{escape(law_href + "#" + unit)}">{escape(unit)}</a></li>')
                lines.append('</ol>')
            lines.append('</li>')
        lines.append('</ol></li>')
    apparatus = [d for d in docs if d["kind"] == "apparatus"]
    if apparatus:
        lines.append('<li>编辑附录<ol>')
        for doc in apparatus:
            label = doc["path"].stem
            lines.append(f'<li><a href="{escape(doc["href"])}#doc-title">{escape(label)}</a></li>')
        lines.append('</ol></li>')
    lines.append('</ol></nav>')
    return xhtml("目录", "".join(lines)).replace(b'href="styles.css"', b'href="styles.css"')


def opf(items, modified: str, identifier: str, *, chinese_only: bool = False) -> bytes:
    manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="css" href="styles.css" media-type="text/css"/>']
    spine = []
    for idx, (href, _title, _content) in enumerate(items, 1):
        manifest.append(f'<item id="c{idx}" href="{escape(href)}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="c{idx}"/>')
    title = "《查士丁尼法典》：Krueger 网页转录中文译本" if chinese_only else "《查士丁尼法典》：Krueger 1877 拉丁文底本与中文译本"
    languages = "<dc:language>zh-CN</dc:language>" if chinese_only else "<dc:language>zh-CN</dc:language><dc:language>la</dc:language>"
    collection = "《民法大全》第二卷" if chinese_only else "Corpus Iuris Civilis, vol. II"
    description = (
        "据格勒诺布尔—阿尔卑斯大学网页所载 Krueger 拉丁文转录翻译。此中文单语阅读本省略连续拉丁原文，保留法条编号、必要拉丁术语、引证标识和译者校记。网页链接至 1877 年版影印本作为版本线索；本书不宣称已逐页校勘该印本。"
        if chinese_only else
        "据格勒诺布尔—阿尔卑斯大学网页所载 Krueger 拉丁文转录配以中文译文。网页链接至 1877 年版影印本作为版本线索；本书不宣称已逐页校勘该印本。"
    )
    value = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="zh-CN">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid">urn:sha256:{identifier}</dc:identifier>
<dc:title>{escape(title)}</dc:title>
{languages}
<dc:contributor>Paulus Krueger（网页署名的拉丁文校订者）</dc:contributor>
<dc:source>https://droitromain.univ-grenoble-alpes.fr/Corpus/codjust.htm</dc:source>
<dc:relation>https://archive.org/stream/codexiustinianu00kruegoog#page/n8/mode/2up</dc:relation>
<meta property="belongs-to-collection" id="series">{escape(collection)}</meta>
<meta refines="#series" property="collection-type">series</meta>
<dc:description>{escape(description)}</dc:description>
<meta property="dcterms:modified">{modified}</meta>
</metadata><manifest>{''.join(manifest)}</manifest><spine page-progression-direction="ltr">{''.join(spine)}</spine></package>'''
    return value.encode("utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-incomplete", action="store_true", help="Build a review preview even if translation coverage is incomplete.")
    parser.add_argument("--chinese-only", action="store_true", help="Build a Chinese-only reading edition from the reviewed Chinese translation manuscripts.")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = args.output or (ROOT / "Codex_Iustinianus_Krueger_Chinese.epub" if args.chinese_only else OUTPUT)

    rows = read_rows()
    paths = sorted(TRANS.glob("*.md"))
    docs = get_language_page_items(paths)
    units_to_doc, topics_to_doc, topic_titles = check_coverage(rows, docs, args.allow_incomplete)
    content_items = []
    content_docs = []
    for doc in docs:
        title, body = build_xhtml(doc["path"], doc["href"], chinese_only=args.chinese_only,
                                  topic_titles=topic_titles)
        content_items.append((doc["href"], title, body))
        content_docs.append((doc["href"], title, body.encode("utf-8")))

    nav_bytes = build_nav(rows, docs, units_to_doc, topics_to_doc, topic_titles,
                          chinese_only=args.chinese_only)
    css = '''@charset "utf-8";
body { margin: 5%; font-family: "Noto Serif CJK SC", "Songti SC", "Noto Serif", serif; line-height: 1.55; }
main { max-width: 48em; margin: 0 auto; }
h1, h2, h3, h4 { line-height: 1.3; break-after: avoid; }
h1 { font-size: 1.55em; margin: 1.6em 0 1em; }
h2 { font-size: 1.28em; margin: 1.8em 0 .8em; border-bottom: .05em solid #777; padding-bottom: .2em; }
h3 { font-size: 1.08em; margin: 1.35em 0 .55em; }
p { margin: .45em 0; orphans: 2; widows: 2; }
p.chinese { text-indent: 2em; }
p.latin { font-family: "Noto Serif", "Times New Roman", serif; text-indent: 0; }
p.french { font-family: "Noto Serif", "Times New Roman", serif; text-indent: 0; }
.section-label { font-size: .88em; font-weight: bold; margin-top: .85em; text-indent: 0; }
.editorial-note { margin: .4em 1.5em; font-size: .92em; text-indent: 0; }
blockquote { margin: .35em 1.25em; }
blockquote.chinese-quotation, blockquote.english-quotation { border-left: .15em solid #aaa; padding-left: .7em; }
p.english { font-family: "Noto Serif", "Times New Roman", serif; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
td, th { border: .05em solid #999; padding: .35em; vertical-align: top; }
li { margin: .2em 0; }
hr { border: 0; border-top: .05em solid #999; width: 35%; margin: 1.2em auto; }
code { font-family: monospace; }
'''
    manifest_bytes = (ROOT / "source_manifest.json").read_bytes()
    id_hash = hashlib.sha256(manifest_bytes + (ROOT / "translation_status.csv").read_bytes()).hexdigest()
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    package = opf(content_items, modified, id_hash, chinese_only=args.chinese_only)

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", '''<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>''', compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("EPUB/styles.css", css, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("EPUB/nav.xhtml", nav_bytes, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("EPUB/package.opf", package, compress_type=zipfile.ZIP_DEFLATED)
        for href, _title, content in content_docs:
            archive.writestr("EPUB/" + href, content, compress_type=zipfile.ZIP_DEFLATED)
    print(f"Wrote {output}")
    print(f"XHTML content documents: {len(content_docs)}")
    legal_count = sum(1 for r in rows if re.fullmatch(r"\d+\.\d+\.\d+", r["unit_id"]))
    print(f"Tracked legal units: {legal_count}")


if __name__ == "__main__":
    main()
