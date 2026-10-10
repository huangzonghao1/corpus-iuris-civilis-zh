#!/usr/bin/env python3
"""Normalize the preserved web transcription into a navigable Latin EPUB 3."""
from __future__ import annotations

import hashlib
import html
import argparse
import json
import re
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "source_original"
OUT = ROOT / "Codex_Iustinianus_Krueger_Latin_source.epub"
NAV_FILES = ["codjust.htm", "Componendo.htm", "Confirmando.htm", "Emendatio.htm"] + [f"CJ{i}.htm" for i in range(1, 13)]
LATIN_ONLY_NAV_FILES = ["Componendo.htm", "Confirmando.htm", "Emendatio.htm"] + [f"CJ{i}.htm" for i in range(1, 13)]
OUT_NAMES = {name: Path(name).with_suffix(".xhtml").name for name in NAV_FILES}
ENGLISH_GREEK_NOTE = "[Here there is a Greek text. Sorry, it is not yet in the Library.]"
LATIN_GREEK_NOTE = "[Textus Graecus hic adesse dicitur; in Bibliotheca nondum continetur.]"
ENGLISH_KRUEGER_NOTE = "Based upon the Latin text of Krueger's edition"
LATIN_KRUEGER_NOTE = "Ex textu Latino editionis Kruegerianae"


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"head", "script", "style", "title"}:
            self.hidden += 1
        elif self.hidden == 0 and tag in {"p", "div", "br", "li", "tr", "td", "hr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"head", "script", "style", "title"} and self.hidden:
            self.hidden -= 1
        elif self.hidden == 0 and tag in {"p", "div", "br", "li", "tr", "td", "hr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.hidden == 0:
            self.parts.append(data)


class XHTMLNormalizer(HTMLParser):
    """Keep text, anchors, links and editorial emphasis; linearize legacy layout tables."""
    BLOCK = {"p": "p", "div": "div", "table": "div", "tr": "div", "td": "div", "ul": "ul", "ol": "ol", "li": "li", "blockquote": "blockquote", "h1": "h1", "h2": "h2", "h3": "h3", "h4": "h4", "h5": "h5", "h6": "h6"}
    INLINE = {"a": "a", "strong": "strong", "b": "strong", "i": "em", "em": "em", "span": "span", "sup": "sup", "sub": "sub", "cite": "cite", "q": "q", "code": "code"}
    VOID = {"br", "hr"}
    SKIP = {"head", "title", "style", "script", "meta", "link", "base"}

    def __init__(self, source_name: str, latin_only: bool = False):
        super().__init__(convert_charrefs=True)
        self.source_name = source_name
        self.latin_only = latin_only
        self.parts: list[str] = []
        self.stack: list[tuple[str, str | None]] = []
        self.skip_stack: list[str] = []

    def _mapped(self, tag: str) -> str | None:
        return self.BLOCK.get(tag) or self.INLINE.get(tag)

    def _attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        d = {k.lower(): v for k, v in attrs if v is not None}
        keep: list[tuple[str, str]] = []
        if tag == "a":
            name = d.get("name") or d.get("id")
            if name:
                keep.append(("id", name))
            href = d.get("href")
            if href:
                href = self._rewrite_href(href)
                keep.append(("href", href))
            if d.get("title"):
                keep.append(("title", d["title"]))
        if tag == "span" and d.get("lang"):
            # The source site marks nearly all Latin legal text as EN-GB/NL/DE.
            # In the Latin-only reading edition the surrounding corpus language
            # is the correct value; English lacuna notices are translated below.
            lang = "la" if self.latin_only else d["lang"]
            keep.extend([("lang", lang), ("xml:lang", lang)])
        if tag in {"div", "p", "li", "blockquote"}:
            cls = "legacy-layout" if tag == "div" else "source-paragraph"
            keep.append(("class", cls))
        if tag == "hr":
            keep.append(("class", "source-separator"))
        return "".join(f" {k}={quoteattr(v)}" for k, v in keep)

    def _rewrite_href(self, href: str) -> str:
        parts = urlsplit(href)
        path = parts.path
        if self.source_name == "CJ1.htm":
            # The web page retains three stale Word-era TOC targets. The raw source is untouched.
            if href == "#3":
                return "#1.3"
            if href == "#27":
                return "#1.27"
            if Path(path).name == "01_57.htm" and parts.fragment == "22":
                return "#1.22"
        if path:
            base = Path(path).name
            if base in OUT_NAMES:
                path = str(Path(path).with_suffix(".xhtml"))
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self.skip_stack:
            if tag in {"head", "script", "style", "title"}:
                self.skip_stack.append(tag)
            return
        if tag in self.SKIP:
            if tag in {"head", "script", "style", "title"}:
                self.skip_stack.append(tag)
            return
        if tag in {"html", "body"}:
            self.stack.append((tag, None)); return
        if tag == "p" and any(src == "p" for src, _ in self.stack):
            self._close_source("p")
        if tag == "br":
            self.parts.append("<br />"); return
        if tag == "hr":
            self.parts.append(f"<hr{self._attrs(tag, attrs)} />"); return
        if tag in {"img", "input", "area", "wbr"}:
            return
        mapped = self._mapped(tag)
        if mapped:
            self.parts.append(f"<{mapped}{self._attrs(tag, attrs)}>")
        self.stack.append((tag, mapped))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID:
            self.handle_endtag(tag)

    def _close_source(self, tag: str) -> None:
        found = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                found = i; break
        if found is None:
            return
        for src, mapped in reversed(self.stack[found:]):
            if mapped:
                self.parts.append(f"</{mapped}>")
        del self.stack[found:]

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip_stack:
            if tag in self.skip_stack:
                pos = len(self.skip_stack) - 1 - self.skip_stack[::-1].index(tag)
                del self.skip_stack[pos:]
            return
        if tag in self.SKIP:
            return
        self._close_source(tag)

    def handle_data(self, data: str) -> None:
        if not self.skip_stack:
            # XML 1.0 disallows a small set of control characters.
            data = "".join(ch for ch in data if ch in "\t\n\r" or ord(ch) >= 32)
            self.parts.append(escape(data))

    def handle_entityref(self, name: str) -> None:
        if not self.skip_stack:
            self.parts.append(escape(html.unescape(f"&{name};")))

    def handle_charref(self, name: str) -> None:
        if not self.skip_stack:
            self.parts.append(escape(html.unescape(f"&#{name};")))

    def finish(self) -> str:
        for src, mapped in reversed(self.stack):
            if mapped:
                self.parts.append(f"</{mapped}>")
        self.stack.clear()
        return "".join(self.parts)


def xml_text(source: bytes, filename: str, latin_only: bool = False) -> tuple[str, str]:
    text = source.decode("iso-8859-1", errors="strict")
    parser = XHTMLNormalizer(filename, latin_only=latin_only)
    parser.feed(text)
    body = parser.finish()
    if latin_only:
        body = re.sub(r"\[Here\s+there is a Greek text\. Sorry, it is not yet in the Library\.\]",
                      LATIN_GREEK_NOTE, body)
        body = body.replace(ENGLISH_KRUEGER_NOTE, LATIN_KRUEGER_NOTE)
    source_title = re.search(r"<title[^>]*>(.*?)</title\s*>", text, re.I | re.S)
    title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", source_title.group(1)))).strip() if source_title else filename
    return title, body


def xhtml_document(title: str, content: str, lang: str = "la", css_href: str = "../styles.css") -> bytes:
    doc = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" xml:lang="{lang}">
<head><title>{escape(title)}</title><meta charset="utf-8" /><link rel="stylesheet" type="text/css" href="{escape(css_href)}" /></head>
<body><main><h1>{escape(title)}</h1>{content}</main></body></html>'''
    return doc.encode("utf-8")


def title_entries(filename: str, source: bytes) -> list[tuple[str, str]]:
    text = source.decode("iso-8859-1", errors="strict")
    result: list[tuple[str, str]] = []
    seen = set()
    for m in re.finditer(r"<a\b([^>]*)>", text, re.I | re.S):
        attrs = m.group(1)
        n = re.search(r"\bname\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", attrs, re.I)
        if not n:
            continue
        anchor = next(g for g in n.groups() if g is not None)
        if not re.fullmatch(r"\d+\.\d+", anchor) or anchor in seen:
            continue
        seen.add(anchor)
        end = text.find("</p", m.end())
        if end < 0:
            end = min(len(text), m.end() + 800)
        fragment = text[m.start():end]
        vis = TextOnly(); vis.feed(fragment)
        label = re.sub(r"\s+", " ", "".join(vis.parts)).strip()
        if label:
            result.append((anchor, label))
    return result


def make_nav(chapter_info: list[tuple[str, str, str]], latin_only: bool = False) -> bytes:
    lines = ['<ol>']
    for fname, title, source_page in chapter_info:
        if source_page.startswith("CJ"):
            book = re.search(r"\d+", source_page).group()
            label = f"Liber {book} — {title}"
            anchors = title_entries(source_page, (RAW / source_page).read_bytes())
            lines.append(f'<li><a href="text/{fname}">{escape(label)}</a>')
            if anchors:
                lines.append("<ol>")
                for anchor, section_title in anchors:
                    lines.append(f'<li><a href="text/{fname}#{escape(anchor)}">{escape(section_title)}</a></li>')
                lines.append("</ol>")
            lines.append("</li>")
        else:
            lines.append(f'<li><a href="text/{fname}">{escape(title)}</a></li>')
    lines.append('</ol>')
    title = "Index" if latin_only else "Contents"
    return xhtml_document(title, f'<nav epub:type="toc" id="toc"><h1>{title}</h1>' + "".join(lines) + '</nav>', css_href="styles.css")


def make_opf(items: list[tuple[str, str, str]], modified: str, latin_only: bool = False) -> bytes:
    manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="css" href="styles.css" media-type="text/css"/>']
    spine = []
    for idx, (fname, title, source_name) in enumerate(items, 1):
        manifest.append(f'<item id="c{idx}" href="text/{escape(fname)}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="c{idx}"/>')
    title = "Codex Iustinianus — transcriptio Latina" if latin_only else "Codex Iustinianus — Latin source transcription"
    creator = "Paulus Krueger" if latin_only else "Text edition attributed on source index to Paulus Krueger"
    description = (
        "Textus Latinus ex transcriptione paginarum fontis. Notae Anglicae de locis ubi textus Graecus deest in Latinum redditae sunt; index Anglice scriptus omissus est. Haec transscriptio novam editionem criticam non constituit."
        if latin_only else
        "Latin source-only reading edition based on the pages linked from the source index. It is not a Chinese translation or a newly collated critical edition."
    )
    opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="la">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid">urn:sha256:{hashlib.sha256((ROOT / 'source_manifest.json').read_bytes()).hexdigest()}</dc:identifier>
<dc:title>{escape(title)}</dc:title><dc:language>la</dc:language>
<dc:creator>{escape(creator)}</dc:creator>
<dc:source>https://droitromain.univ-grenoble-alpes.fr/Corpus/codjust.htm</dc:source>
<dc:description>{escape(description)}</dc:description>
<meta property="dcterms:modified">{modified}</meta>
</metadata><manifest>{''.join(manifest)}</manifest><spine page-progression-direction="ltr">{''.join(spine)}</spine></package>'''
    return opf.encode("utf-8")


def main() -> None:
    cli = argparse.ArgumentParser(description="Build Latin source and Latin-only reading EPUB editions.")
    cli.add_argument("--latin-only", action="store_true", help="Exclude the English web index, Latinize the source's English Greek-lacuna notices, and normalize misclassified source language spans.")
    cli.add_argument("--output", type=Path, default=OUT)
    args = cli.parse_args()

    records = json.loads((ROOT / "source_manifest.json").read_text(encoding="utf-8"))["records"]
    by_name = {Path(r["local_path"]).name: r for r in records}
    chapter_info: list[tuple[str, str, str]] = []
    xhtml_pages: dict[str, bytes] = {}
    if args.latin_only:
        intro = '''<p>Recognovit et retractavit Paulus Krueger.</p>
<p>Corpus Iuris Civilis, volumen II.</p>
<p>Notae Anglicae de locis ubi textus Graecus deest Latine redditae sunt; index Anglice scriptus omissus est.</p>
<p>Haec transscriptio novam editionem criticam non constituit.</p>
<p><a href="https://droitromain.univ-grenoble-alpes.fr/Corpus/codjust.htm">Fons textus interretialis</a></p>'''
        title_page = xhtml_document("Codex Iustinianus", intro)
        from xml.etree import ElementTree as ET
        ET.fromstring(title_page)
        xhtml_pages["titulus.xhtml"] = title_page
        chapter_info.append(("titulus.xhtml", "Codex Iustinianus", "title"))

    selected_files = LATIN_ONLY_NAV_FILES if args.latin_only else NAV_FILES
    for source_name in selected_files:
        raw = (RAW / source_name).read_bytes()
        expected = by_name[source_name]["sha256"]
        if hashlib.sha256(raw).hexdigest() != expected:
            raise SystemExit(f"source checksum mismatch: {source_name}")
        title, body = xml_text(raw, source_name, latin_only=args.latin_only)
        dest_name = OUT_NAMES[source_name]
        doc = xhtml_document(title, body)
        # Ensure each normalized document parses as XML before packaging.
        from xml.etree import ElementTree as ET
        ET.fromstring(doc)
        plain_src = TextOnly(); plain_src.feed(raw.decode("iso-8859-1"))
        plain_dst = TextOnly(); plain_dst.feed(doc.decode("utf-8"))
        normalize = lambda s: " ".join("".join(s.parts).split())
        expected_text = normalize(plain_src)
        if args.latin_only:
            expected_text = expected_text.replace(ENGLISH_GREEK_NOTE, LATIN_GREEK_NOTE)
            expected_text = expected_text.replace(ENGLISH_KRUEGER_NOTE, LATIN_KRUEGER_NOTE)
        if expected_text != normalize(plain_dst):
            # Added generated H1 must be removed before comparing visible source strings.
            actual_text = normalize(plain_dst)
            if not actual_text.endswith(expected_text) and expected_text not in actual_text:
                raise SystemExit(f"visible text mismatch during XHTML conversion: {source_name}")
        xhtml_pages[dest_name] = doc
        chapter_info.append((dest_name, title, source_name))

    css = b'''@charset "utf-8";
body { margin: 5%; line-height: 1.42; font-family: "Times New Roman", "Noto Serif CJK SC", "Songti SC", serif; }
h1 { font-size: 1.45em; text-align: center; margin: 1.8em 0 1.2em; page-break-before: always; }
nav h1 { page-break-before: auto; }
p { margin: 0.25em 0 0.75em; text-indent: 1em; }
p.source-paragraph { text-indent: 1em; }
.legacy-layout { display: block; margin: 0; padding: 0; border: 0; }
a[id] { color: inherit; text-decoration: none; }
a[href] { color: inherit; }
em { font-style: italic; }
strong { font-weight: bold; }
hr.source-separator { margin: 1.2em auto; width: 30%; }
li { margin: 0.2em 0; }
'''
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    opf = make_opf(chapter_info, modified, latin_only=args.latin_only)
    nav = make_nav(chapter_info, latin_only=args.latin_only)
    container = b'''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w") as z:
        z.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("EPUB/package.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("EPUB/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("EPUB/styles.css", css, compress_type=zipfile.ZIP_DEFLATED)
        for fname, data in xhtml_pages.items():
            z.writestr(f"EPUB/text/{fname}", data, compress_type=zipfile.ZIP_DEFLATED)
    print(f"created {args.output} ({args.output.stat().st_size} bytes), {len(xhtml_pages)} content pages")


if __name__ == "__main__":
    main()
