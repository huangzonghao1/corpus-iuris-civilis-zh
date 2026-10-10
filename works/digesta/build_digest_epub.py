#!/usr/bin/env python3
"""Download the Grenoble-Alpes Digesta pages and build a navigable EPUB 3."""
from __future__ import annotations

import concurrent.futures
from collections import Counter
import datetime as dt
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "学说汇纂_下载与EPUB_2026-09-26"
SOURCE = "https://droitromain.univ-grenoble-alpes.fr/Corpus/"
PAGES = ["digest.htm", "compositio.htm", "omnem.htm", "confirmatio.htm", "tituli.htm"] + [f"d-{n:02d}.htm" for n in range(1, 51)]
NAV_LABELS = {
    "intro.xhtml": "版本说明",
    "compositio.htm": "Constitutio Deo auctore",
    "omnem.htm": "Constitutio Omnem",
    "confirmatio.htm": "Constitutio Tanta",
    "tituli.xhtml": "Index titulorum",
}
CONSTITUTIONS = [
    ("compositio.htm", "deo-auctore.xhtml", "Constitutio Deo auctore", "De conceptione digestorum"),
    ("omnem.htm", "omnem.xhtml", "Constitutio Omnem", "Promulgatio ad antecessores"),
    ("confirmatio.htm", "tanta.xhtml", "Constitutio Tanta", "De confirmatione digestorum"),
]


class Node:
    def __init__(self, tag: str, attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children: list[Node | str] = []


class TolerantParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        # These legacy pages occasionally omit optional HTML end tags. Apply
        # HTML's implicit-close rules for common list and table elements.
        if tag in {"li", "p", "td", "th", "tr"}:
            for index in range(len(self.stack) - 1, 0, -1):
                if self.stack[index].tag == tag:
                    del self.stack[index:]
                    break
        node = Node(tag.lower(), attrs)
        self.stack[-1].children.append(node)
        if node.tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag.lower(), attrs))

    def handle_endtag(self, tag):
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def text_of(node: Node | str) -> str:
    if isinstance(node, str):
        return node
    return "".join(text_of(child) for child in node.children)


def descendants(node: Node | str, tag: str | None = None):
    if isinstance(node, str):
        return
    if tag is None or node.tag == tag:
        yield node
    for child in node.children:
        yield from descendants(child, tag)


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def escaped_text(s: str) -> str:
    # Keep whitespace at text-node boundaries: it often separates words wrapped
    # in <i>, <b>, or <a> tags in the original pages.
    return html.escape(re.sub(r"\s+", " ", s.replace("\xa0", " ")), quote=False)


def source_filename_from_href(href: str) -> str | None:
    name = href.split("?", 1)[0].split("#", 1)[0].rsplit("/", 1)[-1].lower()
    if re.fullmatch(r"d-\d{1,2}\.htm", name):
        n = int(re.search(r"\d+", name).group())
        return f"book-{n:02d}.xhtml"
    if name == "tituli.htm":
        return "tituli.xhtml"
    if name == "digest.htm":
        return "intro.xhtml"
    return None


def rewrite_href(href: str) -> str:
    if href.startswith("#"):
        return href
    target = source_filename_from_href(href)
    if target:
        fragment = ("#" + href.split("#", 1)[1]) if "#" in href else ""
        return target + fragment
    if not urllib.parse.urlsplit(href).scheme and re.search(r"\.html?$", href.split("#", 1)[0], re.I):
        return urllib.parse.urljoin(SOURCE, href)
    return href


INLINE = {"a", "b", "strong", "i", "em", "u", "sup", "sub", "span", "cite", "q", "small"}
BLOCKS = {"p", "li", "ul", "ol", "blockquote", "hr", "br"}


def serialize(node: Node | str) -> str:
    if isinstance(node, str):
        return escaped_text(node)
    tag = node.tag
    if tag in {"script", "style", "head", "img", "noscript"}:
        return ""
    children = "".join(serialize(c) for c in node.children)
    if tag == "br":
        return "<br/>"
    if tag == "hr":
        return "<hr/>"
    if tag == "a":
        attrs = []
        href = node.attrs.get("href")
        if href and not href.lower().startswith("javascript:"):
            attrs.append(f'href="{html.escape(rewrite_href(href), quote=True)}"')
        ident = node.attrs.get("id") or node.attrs.get("name")
        if ident:
            attrs.append(f'id="{html.escape(ident, quote=True)}"')
        return f"<a {' '.join(attrs)}>{children}</a>"
    if tag == "p":
        align = node.attrs.get("align", "").lower()
        content_text = normalize(text_of(node))
        cls = "digest-title" if re.match(r"^\d+\.\d+\.0\.?\s+\S", content_text) else "fragment" if re.fullmatch(r"\d+(?:\.\d+){1,3}\.?", content_text) else "source-paragraph"
        return f'<p class="{cls}" data-align="{align}">{children}</p>'
    if tag in {"b", "strong"}:
        # The source site wraps most full prose paragraphs in <strong> for
        # display; do not carry that website-wide weight into the book edition.
        return children
    if tag in {"i", "em"}:
        return f"<em>{children}</em>"
    if tag in INLINE or tag in BLOCKS:
        if tag in {"ul", "ol", "li", "blockquote"}:
            return f"<{tag}>{children}</{tag}>"
        if tag == "span":
            ident = node.attrs.get("id") or node.attrs.get("name")
            return f'<span id="{html.escape(ident, quote=True)}">{children}</span>' if ident else children
    # Strip legacy layout elements (font/table/div) while keeping all textual descendants.
    return children


def xhtml(title: str, body: str, stylesheet="../styles/book.css", lang="la") -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE html>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" lang="{lang}" xml:lang="{lang}">\n'
            '<head><meta charset="utf-8"/>\n'
            f'<title>{html.escape(title)}</title>\n'
            f'<link rel="stylesheet" type="text/css" href="{stylesheet}"/>\n'
            '</head><body>\n' + body + '\n</body></html>\n')


def fetch_page(name: str):
    url = SOURCE + name
    error = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; CorpusIurisEPUB/1.0)"})
            with urllib.request.urlopen(req, timeout=60) as response:
                payload = response.read()
                content_type = response.headers.get("Content-Type", "")
                if response.status != 200 or b"<html" not in payload[:500].lower():
                    raise ValueError(f"Unexpected response {response.status} {content_type}")
                return name, payload, content_type, response.geturl()
        except Exception as exc:
            error = exc
            if attempt < 3:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Could not download {url}: {error}")


def parse_file(directory: Path, name: str) -> Node:
    raw = (directory / name).read_bytes()
    # The server declares UTF-8 in HTTP headers; that correctly preserves its Greek text.
    return TolerantParser(raw.decode("utf-8", errors="replace")).root


def body_nodes(root: Node):
    body = next(descendants(root, "body"), None)
    return list(body.children) if body else list(root.children)


def make_intro() -> str:
    body = '''<main>
<h1>Digesta Iustiniani</h1>
<p class="subtitle">Corpus Iuris Civilis · Volumen I</p>
<p>学说汇纂（Digesta / Pandectae）拉丁文电子版。正文依据格勒诺布尔-阿尔卑斯大学 Roman Law 网站发布的 Mommsen 版文本页面整理；未作翻译或删节。</p>
<p>本书收录网页所列的《学说汇纂》五十卷、标题索引，以及《Deo auctore》《Omnem》《Tanta》三篇相关敕令。各卷目录可跳转至正文对应标题，书内锚点和段落编号来自原网页。</p>
<p>原始网页及本地保存的 HTML 均见随附来源目录。网页称文本依据 Mommsen 版；此电子排版仅整理 HTML 结构与阅读样式，不代表校勘或版本审定。</p>
<p class="source-note">来源：<a href="https://droitromain.univ-grenoble-alpes.fr/Corpus/digest.htm">Iustiniani Digesta (Mommsen &amp; Krueger)</a>。抓取日期：2026-09-26。</p>
</main>'''
    return xhtml("Digesta Iustiniani — 版本说明", body, "../styles/book.css", "zh-CN")


def make_book(root: Node, book: int) -> tuple[str, list[str]]:
    content = []
    all_nodes = []
    for item in body_nodes(root):
        all_nodes.extend(descendants(item))
    toc_items = [n for n in all_nodes if n.tag == "li" and normalize(text_of(n))]
    # The source's list of title links precedes the text. Avoid including accidental nested duplicates.
    # Each original li is a direct list item; its children contain no further li elements.
    if toc_items:
        content.append('<section class="book-toc"><h2>Index titulorum — huius libri</h2><ol>')
        for item in toc_items:
            content.append(f"<li>{''.join(serialize(c) for c in item.children)}</li>")
        content.append("</ol></section>")
    content.append('<section class="digest-text"><h2>Textus</h2>')

    # Some books place the numeric table-of-contents anchors in standalone spans
    # just before each title paragraph, while others place them inside <p>.
    # Preserve those standalone IDs in document order so every source link works.
    events: list[tuple[str, Node | str]] = []
    def collect(node: Node | str):
        if isinstance(node, str):
            return
        if node.tag == "li":
            return
        if node.tag == "p":
            if normalize(text_of(node)):
                events.append(("paragraph", node))
            return
        if node.tag == "a":
            alias = node.attrs.get("id") or node.attrs.get("name")
            if alias and re.fullmatch(r"\d+", alias):
                events.append(("alias", alias))
                return
        for child in node.children:
            collect(child)
    for item in body_nodes(root):
        collect(item)
    for kind, value in events:
        if kind == "paragraph":
            content.append(serialize(value))
        else:
            content.append(f'<span id="{html.escape(str(value), quote=True)}"></span>')
    content.append("</section>")
    # The headings in the EPUB navigation are per book; this inner title list retains all chapter links.
    title = f"Digesta — Liber {book}"
    label = f"Liber {book}"
    page = f'<main class="book"><h1>{label}</h1>' + "\n".join(content) + "</main>"
    ids = Counter(re.findall(r'\bid="([^"]+)"', page))
    duplicates = sorted(v for v, count in ids.items() if count > 1)
    return xhtml(title, page), duplicates


def make_constitution(root: Node, page: str, title: str, subtitle: str) -> str:
    cells = [n for n in descendants(root, "td") if normalize(text_of(n))]
    chunks = []
    # First non-empty cell is the page title; second is the source/editor note.
    for cell in cells[2:]:
        cell_text = normalize(text_of(cell))
        if not cell_text or "Justinien par Charles Meynier" in cell_text:
            continue
        inner = "".join(serialize(c) for c in cell.children).strip()
        if not inner:
            continue
        cls = "inscription" if cell_text.startswith("IMPERATOR CAESAR") or cell_text.startswith("IN NOMINE DOMINI") else "source-paragraph"
        chunks.append(f'<p class="{cls}">{inner}</p>')
    body = f'<main class="constitution"><h1>{html.escape(title)}</h1><p class="subtitle">{html.escape(subtitle)}</p>' + "\n".join(chunks) + "</main>"
    return xhtml(title, body)


def make_title_index(root: Node) -> tuple[str, int]:
    cells = [n for n in descendants(root, "td") if normalize(text_of(n))]
    groups: dict[int, list[str]] = {}
    current = None
    for cell in cells[2:]:
        cell_text = normalize(text_of(cell))
        m = re.fullmatch(r"Liber\s+([IVXLCDM]+)", cell_text, re.I)
        if m:
            roman = m.group(1).upper()
            num = roman_to_int(roman)
            current = num
            groups.setdefault(num, [])
            continue
        if current is None:
            continue
        for anchor in descendants(cell, "a"):
            href = anchor.attrs.get("href", "")
            m = re.search(r"d-(\d{1,2})\.htm#([^\s]+)", href, re.I)
            if m:
                inner = "".join(serialize(child) for child in anchor.children).strip()
                groups[current].append(f'<li><a href="book-{int(m.group(1)):02d}.xhtml#{html.escape(m.group(2), quote=True)}">{inner}</a></li>')
    body = ['<main class="title-index"><h1>Index titulorum</h1><p class="subtitle">Iustiniani Digesta</p>']
    total = 0
    for book in sorted(groups):
        items = groups[book]
        total += len(items)
        body.append(f'<section><h2>Liber {book}</h2><ol>{"".join(items)}</ol></section>')
    body.append("</main>")
    return xhtml("Index titulorum", "\n".join(body)), total


def roman_to_int(s: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for i, ch in enumerate(s):
        v = vals[ch]
        total += -v if i + 1 < len(s) and v < vals[s[i + 1]] else v
    return total


def make_nav(book_count=50) -> str:
    links = ['<li><a href="text/intro.xhtml">版本说明</a></li>', '<li><span>Constitutiones</span><ol>']
    for _, out, title, _ in CONSTITUTIONS:
        links.append(f'<li><a href="text/{out}">{html.escape(title)}</a></li>')
    links.append('</ol></li><li><span>Digesta</span><ol>')
    for n in range(1, book_count + 1):
        links.append(f'<li><a href="text/book-{n:02d}.xhtml">Liber {n}</a></li>')
    links.append('</ol></li><li><a href="text/tituli.xhtml">Index titulorum</a></li>')
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="la" xml:lang="la">'
            '<head><meta charset="utf-8"/><title>Contents</title><link rel="stylesheet" type="text/css" href="styles/book.css"/></head>'
            '<body><nav epub:type="toc" id="toc"><h1>Contents</h1><ol>' + "".join(links) + '</ol></nav></body></html>\n')


CSS = '''
html { font-family: "Noto Serif", "EB Garamond", "Palatino Linotype", Georgia, serif; line-height: 1.5; }
body { margin: 5%; color: #171717; font-weight: 400; }
h1 { text-align: center; font-size: 1.55em; margin: 1.4em 0 0.4em; }
h2 { font-size: 1.12em; margin: 1.5em 0 .6em; page-break-after: avoid; }
.subtitle { text-align: center; font-style: italic; margin: 0 0 2em; }
.book-toc { border-bottom: 1px solid #888; margin-bottom: 2em; padding-bottom: 1em; }
.book-toc ol, .title-index ol { padding-left: 1.7em; }
.book-toc li, .title-index li { margin: 0 0 .36em; }
.digest-text p, .constitution p { text-align: justify; text-indent: 1.15em; margin: .45em 0; }
p.digest-title { text-align: left; text-indent: 0; font-weight: 600; margin: 1.4em 0 .55em; page-break-after: avoid; }
p.fragment { text-align: left; text-indent: 0; font-weight: 600; margin: 1em 0 .2em; }
.inscription { text-align: center !important; font-weight: bold; text-indent: 0 !important; margin: 1.25em 0 !important; }
.source-note { margin-top: 3em; font-size: .88em; }
a { color: #174f76; text-decoration: none; }
hr { border: 0; border-top: 1px solid #999; margin: 1em 0; }
'''


def build_epub(output: Path, title_index_count: int, book_duplicates: dict[int, list[str]]):
    epub_dir = output / "EPUB"
    text_dir = epub_dir / "text"
    styles_dir = epub_dir / "styles"
    for d in (text_dir, styles_dir):
        d.mkdir(parents=True, exist_ok=True)
    (text_dir / "intro.xhtml").write_text(make_intro(), encoding="utf-8")
    spine = ["intro.xhtml"]
    for source, out, title, subtitle in CONSTITUTIONS:
        parsed = parse_file(output / "source_html", source)
        (text_dir / out).write_text(make_constitution(parsed, out, title, subtitle), encoding="utf-8")
        spine.append(out)
    idx_root = parse_file(output / "source_html", "tituli.htm")
    index_doc, actual_count = make_title_index(idx_root)
    (text_dir / "tituli.xhtml").write_text(index_doc, encoding="utf-8")
    spine.append("tituli.xhtml")
    for n in range(1, 51):
        root = parse_file(output / "source_html", f"d-{n:02d}.htm")
        doc, duplicates = make_book(root, n)
        (text_dir / f"book-{n:02d}.xhtml").write_text(doc, encoding="utf-8")
        if duplicates:
            book_duplicates[n] = duplicates
        spine.append(f"book-{n:02d}.xhtml")
    (epub_dir / "nav.xhtml").write_text(make_nav(), encoding="utf-8")
    (styles_dir / "book.css").write_text(CSS, encoding="utf-8")

    ns = "http://www.idpf.org/2007/opf"
    dc = "http://purl.org/dc/elements/1.1/"
    ET.register_namespace("", ns)
    ET.register_namespace("dc", dc)
    package = ET.Element(f"{{{ns}}}package", {"version": "3.0", "unique-identifier": "pub-id", "xml:lang": "la", "prefix": "dcterms: http://purl.org/dc/terms/"})
    metadata = ET.SubElement(package, f"{{{ns}}}metadata")
    ET.SubElement(metadata, f"{{{dc}}}identifier", {"id": "pub-id"}).text = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, SOURCE + "digest.htm"))
    ET.SubElement(metadata, f"{{{dc}}}title").text = "Digesta Iustiniani (学说汇纂)"
    ET.SubElement(metadata, f"{{{dc}}}creator").text = "Iustinianus I"
    ET.SubElement(metadata, f"{{{dc}}}contributor").text = "Theodor Mommsen; Paul Krueger (edition)"
    ET.SubElement(metadata, f"{{{dc}}}language").text = "la"
    ET.SubElement(metadata, f"{{{dc}}}publisher").text = "Source transcription: Université Grenoble Alpes, Roman Law"
    ET.SubElement(metadata, f"{{{dc}}}date").text = "2026-09-26"
    ET.SubElement(metadata, f"{{{dc}}}source").text = SOURCE + "digest.htm"
    ET.SubElement(metadata, f"{{{ns}}}meta", {"property": "dcterms:modified"}).text = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    manifest = ET.SubElement(package, f"{{{ns}}}manifest")
    ET.SubElement(manifest, f"{{{ns}}}item", {"id": "nav", "href": "nav.xhtml", "media-type": "application/xhtml+xml", "properties": "nav"})
    ET.SubElement(manifest, f"{{{ns}}}item", {"id": "css", "href": "styles/book.css", "media-type": "text/css"})
    for name in spine:
        ET.SubElement(manifest, f"{{{ns}}}item", {"id": Path(name).stem, "href": "text/" + name, "media-type": "application/xhtml+xml"})
    sp = ET.SubElement(package, f"{{{ns}}}spine", {"page-progression-direction": "ltr"})
    for name in spine:
        ET.SubElement(sp, f"{{{ns}}}itemref", {"idref": Path(name).stem})
    (epub_dir / "package.opf").write_bytes(ET.tostring(package, encoding="utf-8", xml_declaration=True))

    epub_path = output / "Digesta_Iustiniani_Mommsen_Krueger.epub"
    with ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        zf.writestr("META-INF/container.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>', compress_type=ZIP_DEFLATED)
        for file in sorted(epub_dir.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(output).as_posix(), compress_type=ZIP_DEFLATED)
    return epub_path, actual_count


def main():
    """Build from hash-verified archived source pages without downloading."""
    records = json.loads((OUT / "source_manifest.json").read_text(encoding="utf-8"))["files"]
    if set(row["file"] for row in records) != set(PAGES):
        raise ValueError("Archived Digesta page inventory differs from expected scope")
    for row in records:
        data = (OUT / "source_html" / row["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("Source hash mismatch: " + row["file"])
    duplicate_ids = {}
    epub, index_count = build_epub(OUT, 0, duplicate_ids)
    if duplicate_ids:
        raise ValueError("Duplicate IDs: " + json.dumps(duplicate_ids))
    print(json.dumps({"epub": epub.name, "title_index_links": index_count, "network": "not used"}))


if __name__ == "__main__":
    main()
