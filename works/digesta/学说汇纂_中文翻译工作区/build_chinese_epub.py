#!/usr/bin/env python3
"""Build and validate a Chinese EPUB from the completed scholarly translation."""
from __future__ import annotations

from collections import defaultdict
import datetime as dt
import html
import json
import re
import uuid
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile
import xml.etree.ElementTree as ET


WORK = Path(__file__).resolve().parent
SOURCE_DIR = WORK.parent / "学说汇纂_下载与EPUB_2026-09-26"
SOURCE_EPUB = SOURCE_DIR / "Digesta_Iustiniani_Mommsen_Krueger.epub"
OUTPUT = SOURCE_DIR / "Digesta_Iustiniani_学说汇纂_中文全译本.epub"
OUTDIR = WORK / "epub_build"
SOURCE_BASE = "https://droitromain.univ-grenoble-alpes.fr/Corpus/"
XHTML_NS = "http://www.w3.org/1999/xhtml"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"


def load_progress():
    return json.loads((WORK / "翻译进度.json").read_text(encoding="utf-8"))


def unit_file_map(progress):
    by_book: dict[int, list[Path]] = defaultdict(list)
    by_locator: dict[str, list[Path]] = defaultdict(list)
    units = sorted(
        progress["completed_units"],
        key=lambda unit: tuple(
            int(part) for part in re.fullmatch(r"D\.(\d+)\.(\d+)", unit.get("locator", "")).groups()
        ) if re.fullmatch(r"D\.(\d+)\.(\d+)", unit.get("locator", "")) else (10**9, 10**9),
    )
    for unit in units:
        match = re.fullmatch(r"D\.(\d+)\.(\d+)", unit.get("locator", ""))
        if not match:
            continue
        book = int(match.group(1))
        relative = unit.get("files", [unit.get("file")])
        files = [WORK / item for item in relative if item]
        starts = []
        for file in files:
            source = file.read_text(encoding="utf-8") if file.exists() else ""
            marker = re.search(r"<!--\s*source-p\s*[:#]?\s*0*(\d+)", source)
            starts.append(int(marker.group(1)) if marker else None)
        if files and all(start is not None for start in starts):
            files = [file for _, file in sorted(zip(starts, files), key=lambda item: item[0])]
        for file in files:
            if file not in by_book[book]:
                by_book[book].append(file)
            if file not in by_locator[unit["locator"]]:
                by_locator[unit["locator"]].append(file)
    return by_book, by_locator


def title_map(progress):
    result = {}
    for unit in progress["completed_units"]:
        locator = unit.get("locator")
        title = unit.get("title", "")
        if locator and title:
            result[locator] = title.rsplit(" / ", 1)[-1].strip()
    return result


def index_lines(progress):
    path = WORK / "译稿" / "前置材料" / "标题索引.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    translations = title_map(progress)
    entries = []
    pattern = re.compile(
        r"-\s+<a href=\"book-(\d{2})\.xhtml#([^\"]+)\">D\.(\d+)\.(\d+)</a>(.*)"
    )
    for line in lines:
        entry = pattern.match(line)
        if not entry:
            continue
        book, anchor, major, minor = entry.groups()[:4]
        locator = f"D.{major}.{minor}"
        rest = entry.group(5)
        if "【待译】" in rest:
            translated = translations.get(locator)
            if not translated:
                raise ValueError(f"No translated title for {locator}")
            rest = rest.replace("【待译】", html.escape(translated))
        href = f"book-{int(book):02d}.xhtml#{html.escape(anchor, quote=True)}"
        entries.append(
            {
                "book": int(book),
                "anchor": anchor,
                "locator": locator,
                "href": href,
                "line": f'<a href="{href}">{html.escape(locator)}</a>{md_inline(rest)}',
            }
        )
    return entries


def protect_tokens(text, pattern, namespace):
    tokens = []
    def replace(match):
        tokens.append(match.group(0))
        return f"ZZZ{namespace}{len(tokens)-1}ZZZ"
    return re.sub(pattern, replace, text), tokens


def md_inline(text):
    # Keep explicit anchors and raw index links; escape all other angle brackets,
    # including Latin editorial supplements, so the XHTML remains well-formed.
    text, protected = protect_tokens(text, r"<a\b[^>]*>.*?</a>|<a\b[^>]*/>", "HTML")
    link_pattern = r"\[([^\]]+)\]\((https?://[^)\s]+|[^)\s]+)\)"
    text, links = protect_tokens(text, link_pattern, "LINK")
    text = html.escape(text, quote=False)
    bt = chr(96)
    text = re.sub(bt + r"([^" + bt + r"]+)" + bt, r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", text)
    for index, value in enumerate(links):
        match = re.fullmatch(link_pattern, value)
        if match:
            label = html.escape(match.group(1), quote=False)
            href = html.escape(match.group(2), quote=True)
            replacement = f'<a href="{href}">{label}</a>'
        else:
            replacement = value
        text = text.replace(f"ZZZLINK{index}ZZZ", replacement)
    for index, value in enumerate(protected):
        text = text.replace(f"ZZZHTML{index}ZZZ", value)
    return text


def strip_comments(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def render_markdown_blocks(markdown, *, book_mode=False):
    source = strip_comments(markdown).splitlines()
    blocks = []
    para = []
    quote = []
    list_items = []

    def flush_para():
        if para:
            text = " ".join(part.strip() for part in para if part.strip())
            if text:
                blocks.append(f"<p>{md_inline(text)}</p>")
            para.clear()

    def flush_quote():
        if quote:
            content = " ".join(part.strip() for part in quote if part.strip())
            if content:
                blocks.append(f"<blockquote><p>{md_inline(content)}</p></blockquote>")
            quote.clear()

    def flush_list():
        if list_items:
            body = "".join(f"<li>{md_inline(item)}</li>" for item in list_items)
            blocks.append(f"<ul>{body}</ul>")
            list_items.clear()

    for line in source:
        raw = line.strip()
        if not raw:
            flush_para()
            flush_quote()
            flush_list()
            continue
        if raw.startswith(">"):
            flush_para()
            flush_list()
            content = raw[1:].strip()
            if re.match(r"(?:\*\*)?底本(?:范围|：| )", content):
                flush_quote()
                continue
            quote.append(content)
            continue
        if raw.startswith("- ") or raw.startswith("* "):
            flush_para()
            flush_quote()
            list_items.append(raw[2:].strip())
            continue
        flush_quote()
        flush_list()
        heading = re.match(r"^(#{1,6})\s+(.+)$", raw)
        if heading:
            flush_para()
            level = len(heading.group(1))
            title = heading.group(2)
            if book_mode and level == 1 and re.fullmatch(r"第[一二三四五六七八九十百〇零两\d]+卷", title):
                continue
            target = min(3, max(2, level))
            blocks.append(f"<h{target}>{md_inline(title)}</h{target}>")
            continue
        if re.fullmatch(r'(?:<a\b[^>]*>.*?</a>\s*)+', raw):
            flush_para()
            blocks.append(raw)
            continue
        para.append(raw)
    flush_para()
    flush_quote()
    flush_list()
    return "\n".join(blocks)


def clean_file_content(path):
    return render_markdown_blocks(path.read_text(encoding="utf-8"), book_mode=True)


def validate_complete_scope(progress, by_book):
    if len(by_book) != 50 or any(n not in by_book or not by_book[n] for n in range(1, 51)):
        missing = [n for n in range(1, 51) if n not in by_book or not by_book[n]]
        raise ValueError(f"Books without translated files: {missing}")
    pending = progress.get("in_progress_units", [])
    if pending:
        raise ValueError(f"Translation progress still has active units: {len(pending)}")
    index_path = WORK / "译稿" / "前置材料" / "标题索引.md"
    placeholders = sum(1 for line in index_path.read_text(encoding="utf-8").splitlines() if "【待译】" in line)
    if placeholders:
        raise ValueError(f"Title index still has {placeholders} untranslated entries")
    for filename in ("Deo-auctore-中文译稿.md", "Omnem-中文译稿.md", "Tanta-中文译稿.md"):
        if not (WORK / "译稿" / "前置材料" / filename).exists():
            raise ValueError(f"Missing constitution translation: {filename}")


def validate_source_alignment(progress, by_book):
    """Check translated source anchors and paragraph inventories against the source EPUB."""
    allowed_extras = defaultdict(list)
    for item in progress.get("source_unanchored_passages", []):
        allowed_extras[int(item["locator"].split(".")[1])].append(item["anchor"])

    with ZipFile(SOURCE_EPUB) as source:
        for book in range(1, 51):
            source_name = f"EPUB/text/book-{book:02d}.xhtml"
            root = ET.fromstring(source.read(source_name))
            source_ids = [element.attrib["id"] for element in root.iter() if "id" in element.attrib]
            source_p_count = sum(1 for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "p")

            translated_ids = []
            source_ps = []
            for path in by_book[book]:
                content = path.read_text(encoding="utf-8")
                translated_ids.extend(re.findall(r'<a\s+id=["\']([^"\']+)["\']', content))
                source_ps.extend(int(number) for number in re.findall(r"<!--\s*source-p\s*[:#]?\s*0*(\d+)\s*-->", content))

            if len(translated_ids) != len(set(translated_ids)):
                raise ValueError(f"Duplicate translated source anchors in Book {book}")
            extras = [ident for ident in translated_ids if ident not in set(source_ids)]
            if extras != allowed_extras.get(book, []):
                raise ValueError(f"Unexpected source-anchor supplements in Book {book}: {extras}")
            filtered_ids = [ident for ident in translated_ids if ident not in set(extras)]
            if filtered_ids != source_ids:
                mismatch = next(
                    (index for index, pair in enumerate(zip(filtered_ids, source_ids)) if pair[0] != pair[1]),
                    min(len(filtered_ids), len(source_ids)),
                )
                raise ValueError(
                    f"Book {book} anchor sequence differs at item {mismatch + 1}: "
                    f"translated={filtered_ids[mismatch:mismatch + 3]}, source={source_ids[mismatch:mismatch + 3]}"
                )

            # Books 1–29 do not all carry per-paragraph source markers, so their
            # recorded per-title inventory is checked against the normalized EPUB.
            recorded_p_count = sum(
                unit.get("source_content_paragraphs", 0)
                for unit in progress["completed_units"]
                if re.match(fr"^D\.{book}\.\d+$", unit.get("locator", ""))
            )
            if book < 30:
                if recorded_p_count != source_p_count:
                    raise ValueError(
                        f"Book {book} paragraph inventory differs: metadata={recorded_p_count}, source={source_p_count}"
                    )

            # Books 30–50 include a source-p marker on every captured source
            # paragraph. Check the whole sequence, including the earlier volumes.
            # Book 30 has one documented empty terminal paragraph in the archived
            # HTML that the normalized EPUB omits; its translation marks that slot.
            if book >= 30:
                if not source_ps:
                    raise ValueError(f"Book {book} has no source-p coverage markers")
                expected_count = recorded_p_count
                if book == 30:
                    exception = next(
                        (item for item in progress.get("source_paragraph_exceptions", [])
                         if item.get("book") == 30),
                        None,
                    )
                    if (
                        not exception
                        or exception.get("normalized_epub_paragraphs") != source_p_count
                        or exception.get("archived_html_paragraphs") != recorded_p_count
                        or recorded_p_count != source_p_count + 1
                        or not re.search(
                            r"<!--\s*source-p\s*[:#]?\s*0*647\s*-->\s*〔底本空段〕",
                            "\n".join(path.read_text(encoding="utf-8") for path in by_book[book]),
                        )
                    ):
                        raise ValueError("Book 30's documented empty terminal paragraph no longer matches source")
                elif recorded_p_count != source_p_count:
                    raise ValueError(
                        f"Book {book} paragraph inventory differs: metadata={recorded_p_count}, source={source_p_count}"
                    )
                expected = list(range(1, expected_count + 1))
                if source_ps != expected:
                    mismatch = next(
                        (index for index, pair in enumerate(zip(source_ps, expected)) if pair[0] != pair[1]),
                        min(len(source_ps), len(expected)),
                    )
                    raise ValueError(
                        f"Book {book} source-p sequence differs at item {mismatch + 1}: "
                        f"translated={source_ps[mismatch:mismatch + 4]}, source={expected[mismatch:mismatch + 4]}"
                    )


def xhtml(title, body, *, lang="zh-CN", stylesheet="../styles/book.css"):
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        f'<html xmlns="{XHTML_NS}" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" xml:lang="{lang}">'
        f'<head><meta charset="utf-8"/><title>{html.escape(title)}</title>'
        f'<link rel="stylesheet" type="text/css" href="{stylesheet}"/></head>'
        f'<body>{body}</body></html>\n'
    )


CSS = """
html { font-family: "Noto Serif CJK SC", "Songti SC", "STSong", "Noto Serif", serif; line-height: 1.72; }
body { margin: 5%; color: #171717; font-weight: 400; font-size: 1em; }
h1 { text-align: center; font-size: 1.55em; font-weight: 600; margin: 1.4em 0 .9em; }
h2 { font-size: 1.22em; font-weight: 600; margin: 1.7em 0 .65em; page-break-after: avoid; }
h3 { font-size: 1.05em; font-weight: 600; margin: 1.25em 0 .45em; page-break-after: avoid; }
p { text-align: justify; text-indent: 1.15em; margin: .55em 0; font-weight: 400; }
blockquote { margin: .8em 1.3em; font-size: .97em; }
blockquote p { text-indent: 0; }
code { font-family: "Noto Serif", "Songti SC", serif; }
.subtitle { text-align: center; text-indent: 0; font-style: italic; }
.local-toc { border-bottom: 1px solid #888; margin: 1em 0 2em; padding: .4em 0 1em; }
.local-toc h2 { font-size: 1.05em; }
.local-toc ol { padding-left: 1.7em; }
.local-toc li { margin: .25em 0; }
.title-index ol { padding-left: 1.65em; }
.title-index li { margin: .25em 0; }
.inscription { text-align: center; text-indent: 0; font-weight: 600; }
a { color: #174f76; text-decoration: none; }
"""


def make_title_index(entries):
    by_book = defaultdict(list)
    for entry in entries:
        by_book[entry["book"]].append(entry["line"])
    chunks = ['<main class="title-index"><h1>标题索引</h1><p class="subtitle">Index titulorum</p>']
    for book in range(1, 51):
        lines = by_book.get(book, [])
        if book in (30, 31, 32) and not lines:
            lines = [f'<a href="book-{book:02d}.xhtml#1">D.{book}.0</a>　论遗赠与遗嘱信托（<em>De legatis et fideicommissis</em>）']
        if not lines:
            continue
        chunks.append(f'<section><h2>第{book}卷（Liber {book}）</h2><ol>')
        chunks.extend(f"<li>{line}</li>" for line in lines)
        chunks.append("</ol></section>")
    chunks.append("</main>")
    return xhtml("标题索引", "\n".join(chunks))


def make_local_toc(book, entries):
    lines = [e["line"] for e in entries if e["book"] == book]
    if not lines:
        return ""
    return '<section class="local-toc"><h2>本卷标题</h2><ol>' + "".join(f"<li>{line}</li>" for line in lines) + "</ol></section>"


def make_book(book, files, entries):
    content = [f'<main class="book"><h1>第{book}卷</h1>', make_local_toc(book, entries), '<section class="book-text">']
    for path in files:
        content.append(clean_file_content(path))
    content.append("</section></main>")
    return xhtml(f"学说汇纂·第{book}卷", "\n".join(content))


def make_nav(entries):
    chunks = ['<nav epub:type="toc" id="toc"><h1>目录</h1><ol>',
              '<li><a href="text/intro.xhtml">版本说明</a></li>',
              '<li><span>敕令</span><ol>']
    for filename, label in [
        ("deo-auctore.xhtml", "Deo auctore：关于《学说汇纂》的编纂"),
        ("omnem.xhtml", "Omnem：致法学教授"),
        ("tanta.xhtml", "Tanta：关于确认《学说汇纂》"),
    ]:
        chunks.append(f'<li><a href="text/{filename}">{html.escape(label)}</a></li>')
    chunks.extend(['</ol></li>', '<li><a href="text/tituli.xhtml">标题索引</a></li>', '<li><span>正文</span><ol>'])
    for book in range(1, 51):
        chunks.append(f'<li><a href="text/book-{book:02d}.xhtml">第{book}卷</a>')
        titles = [e for e in entries if e["book"] == book]
        if titles:
            chunks.append("<ol>")
            chunks.extend(f'<li><a href="text/{e["href"]}">{html.escape(e["locator"])}</a></li>' for e in titles)
            chunks.append("</ol>")
        chunks.append("</li>")
    chunks.extend(["</ol></li>", "</ol></nav>"])
    return xhtml("目录", "".join(chunks), stylesheet="styles/book.css")


def build_package(spine):
    ET.register_namespace("", OPF_NS)
    ET.register_namespace("dc", DC_NS)
    package = ET.Element(f"{{{OPF_NS}}}package", {
        "version": "3.0",
        "unique-identifier": "pub-id",
        "prefix": "dcterms: http://purl.org/dc/terms/",
        f"{{http://www.w3.org/XML/1998/namespace}}lang": "zh-Hans",
    })
    meta = ET.SubElement(package, f"{{{OPF_NS}}}metadata")
    ET.SubElement(meta, f"{{{DC_NS}}}identifier", {"id": "pub-id"}).text = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, SOURCE_BASE + "digest.htm#zh"))
    ET.SubElement(meta, f"{{{DC_NS}}}title").text = "学说汇纂（Digesta Iustiniani）中文全译本"
    ET.SubElement(meta, f"{{{DC_NS}}}creator").text = "查士丁尼"
    ET.SubElement(meta, f"{{{DC_NS}}}contributor").text = "Theodor Mommsen; Paul Krueger（底本文本）"
    ET.SubElement(meta, f"{{{DC_NS}}}language").text = "zh-Hans"
    ET.SubElement(meta, f"{{{DC_NS}}}publisher").text = "依据格勒诺布尔-阿尔卑斯大学罗马法网站所载 Mommsen 文本翻译"
    ET.SubElement(meta, f"{{{DC_NS}}}source").text = SOURCE_BASE + "digest.htm"
    ET.SubElement(meta, f"{{{OPF_NS}}}meta", {"property": "dcterms:modified"}).text = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    manifest = ET.SubElement(package, f"{{{OPF_NS}}}manifest")
    ET.SubElement(manifest, f"{{{OPF_NS}}}item", {"id": "nav", "href": "nav.xhtml", "media-type": "application/xhtml+xml", "properties": "nav"})
    ET.SubElement(manifest, f"{{{OPF_NS}}}item", {"id": "css", "href": "styles/book.css", "media-type": "text/css"})
    for name in spine:
        ET.SubElement(manifest, f"{{{OPF_NS}}}item", {"id": Path(name).stem, "href": "text/" + name, "media-type": "application/xhtml+xml"})
    sp = ET.SubElement(package, f"{{{OPF_NS}}}spine", {"page-progression-direction": "ltr"})
    for name in spine:
        ET.SubElement(sp, f"{{{OPF_NS}}}itemref", {"idref": Path(name).stem})
    return ET.tostring(package, encoding="utf-8", xml_declaration=True)


def validate_epub(path):
    with ZipFile(path) as zf:
        names = zf.namelist()
        if not names or names[0] != "mimetype" or zf.getinfo("mimetype").compress_type != ZIP_STORED:
            raise ValueError("EPUB mimetype is not the first uncompressed ZIP entry")
        bad = zf.testzip()
        if bad:
            raise ValueError(f"ZIP CRC failure: {bad}")
        docs = {}
        ids = {}
        for name in names:
            if name.endswith((".xhtml", ".opf", ".xml")):
                root = ET.fromstring(zf.read(name))
                docs[name] = root
                all_ids = [e.attrib["id"] for e in root.iter() if "id" in e.attrib]
                repeated = sorted({ident for ident in all_ids if all_ids.count(ident) > 1})
                if repeated:
                    raise ValueError(f"Duplicate ids in {name}: {repeated[:20]}")
                ids[name] = set(all_ids)
        broken = []
        for name, root in docs.items():
            if not name.endswith(".xhtml"):
                continue
            for anchor in root.iter(f"{{{XHTML_NS}}}a"):
                href = anchor.attrib.get("href", "")
                if not href or re.match(r"^(?:https?:|mailto:|tel:)", href, re.I):
                    continue
                target, _, fragment = href.partition("#")
                target_path = (PurePosixPath(name).parent / target).as_posix() if target else name
                target_path = str(PurePosixPath(target_path))
                if target_path not in docs:
                    broken.append((name, href, "missing file"))
                elif fragment and fragment not in ids[target_path]:
                    broken.append((name, href, "missing anchor"))
        if broken:
            raise ValueError(f"Broken internal links: {broken[:25]}")
        return {
            "files": len(names),
            "xhtml": sum(1 for name in names if name.endswith(".xhtml")),
            "links_checked": sum(1 for root in docs.values() for _ in root.iter(f"{{{XHTML_NS}}}a")),
        }


def main():
    progress = load_progress()
    by_book, _ = unit_file_map(progress)
    entries = index_lines(progress)
    validate_complete_scope(progress, by_book)
    validate_source_alignment(progress, by_book)
    if OUTDIR.exists():
        import shutil
        shutil.rmtree(OUTDIR)
    (OUTDIR / "EPUB" / "text").mkdir(parents=True)
    (OUTDIR / "EPUB" / "styles").mkdir(parents=True)

    front = WORK / "译稿" / "前置材料"
    spine = []
    front_files = [
        ("版本说明.md", "版本说明", "intro.xhtml"),
        ("Deo-auctore-中文译稿.md", "Deo auctore", "deo-auctore.xhtml"),
        ("Omnem-中文译稿.md", "Omnem", "omnem.xhtml"),
        ("Tanta-中文译稿.md", "Tanta", "tanta.xhtml"),
    ]
    for source, title, output in front_files:
        body = render_markdown_blocks((front / source).read_text(encoding="utf-8"))
        doc = xhtml(title, f'<main class="frontmatter"><h1>{html.escape(title)}</h1>{body}</main>')
        (OUTDIR / "EPUB" / "text" / output).write_text(doc, encoding="utf-8")
        spine.append(output)

    index_doc = make_title_index(entries)
    (OUTDIR / "EPUB" / "text" / "tituli.xhtml").write_text(index_doc, encoding="utf-8")
    spine.append("tituli.xhtml")

    for book in range(1, 51):
        doc = make_book(book, by_book[book], entries)
        (OUTDIR / "EPUB" / "text" / f"book-{book:02d}.xhtml").write_text(doc, encoding="utf-8")
        spine.append(f"book-{book:02d}.xhtml")
    (OUTDIR / "EPUB" / "nav.xhtml").write_text(make_nav(entries), encoding="utf-8")
    (OUTDIR / "EPUB" / "styles" / "book.css").write_text(CSS, encoding="utf-8")
    (OUTDIR / "EPUB" / "package.opf").write_bytes(build_package(spine))
    (OUTDIR / "META-INF").mkdir()
    (OUTDIR / "META-INF" / "container.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        encoding="utf-8",
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        zf.writestr("META-INF/container.xml", (OUTDIR / "META-INF" / "container.xml").read_bytes(), compress_type=ZIP_DEFLATED)
        for file in sorted((OUTDIR / "EPUB").rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(OUTDIR).as_posix(), compress_type=ZIP_DEFLATED)
    report = validate_epub(OUTPUT)
    print(json.dumps({"epub": str(OUTPUT), "size": OUTPUT.stat().st_size, "title_index_links": len(entries), **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
