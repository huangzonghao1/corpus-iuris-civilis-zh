#!/usr/bin/env python3
"""Build standalone Latin and Chinese EPUBs and validate all three EPUB TOCs."""
from __future__ import annotations

from pathlib import Path
from html import escape, unescape
import json
import re
import runpy
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, date
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent

# Reuse the project's established source parser, anchor normalization, Markdown
# converter, and navigation tree builders. The bilingual edition contains
# paired original/Chinese passages only; the full source pages live in the
# standalone Latin edition and the adjacent source archive.
ctx = runpy.run_path(str(ROOT / 'build_epub.py'))

files = ctx['files']
parsed = ctx['parsed']
serialize = ctx['serialize']
link_map = ctx['link_map']
titles = ctx['titles']
xhtml = ctx['xhtml']
css = ctx['css']
md_convert = ctx['md_convert']
TRANS = ctx['TRANS']
OUT_BI = ctx['OUT']
BASE = ctx['BASE']
translation_meta = ctx['translation_meta']
translation_docs = ctx['translation_docs']
glossary_content = ctx['glossary_content']
glossary_doc = ctx['glossary_doc']
coverage = ctx['coverage']
group_items = ctx['group_items']
latin_source_page_entry = ctx['latin_source_page_entry']
render_nav_item = ctx['render_nav_item']
translation_nav_entry = ctx['translation_nav_entry']
chinese_doc_title = ctx['chinese_doc_title']
source_anchor_tree = ctx['source_anchor_tree']
latin_page_label = ctx['latin_page_label']

OUT_LA = ROOT / 'Novellae_Schoell_Kroll_Latin.epub'
OUT_ZH = ROOT / 'Novellae_Schoell_Kroll_Chinese.epub'
EDITABLE_ZH = ROOT / 'translations_chinese_only'

def nav_doc(title: str, lang: str, groups_html: str, front_label: str,
            front_href: str = 'front.xhtml') -> str:
    body = (
        '<nav epub:type="toc" id="toc" xml:lang="' + escape(lang, quote=True) +
        '" lang="' + escape(lang, quote=True) + '"><h1>' + escape(title) +
        '</h1><ol><li><a href="' + escape(front_href, quote=True) + '">' +
        escape(front_label) + '</a></li>' + groups_html + '</ol></nav>'
    )
    return xhtml(title, body, lang, 'styles/book.css')

def latin_groups_html() -> str:
    specs = [
        (r'Novellae\.htm', 'Index fontis'),
        (r'Nov\d+\.htm', 'Iustiniani Novellae'),
        (r'Ed\d+\.htm', 'Iustiniani XIII Edicta'),
        (r'App\d+\.htm', 'Appendix constitutionum dispersarum'),
        (r'epitome_julien_\d+\.htm', 'Iuliani Epitome Latina Novellarum Iustiniani'),
    ]
    groups = []
    for pattern, label in specs:
        members = [latin_source_page_entry(p) for p in files if re.fullmatch(pattern, p.name)]
        if members:
            groups.append(group_items(members, label))
    return ''.join(groups)

latin_groups = latin_groups_html()

def package_epub(output: Path, opf: str, items: list[tuple[str, str, str, str | bytes]]) -> None:
    container = ('<?xml version="1.0" encoding="utf-8"?>'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="package.opf" '
                 'media-type="application/oebps-package+xml"/></rootfiles></container>')
    with zipfile.ZipFile(output, 'w') as z:
        z.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        z.writestr('META-INF/container.xml', container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr('package.opf', opf, compress_type=zipfile.ZIP_DEFLATED)
        for ident, href, media, content in items:
            data = content.encode('utf-8') if isinstance(content, str) else content
            z.writestr(href, data, compress_type=zipfile.ZIP_DEFLATED)

def make_package(output: Path, title: str, languages: list[str], description: str,
                 items: list[tuple[str, str, str]]) -> None:
    manifest = []
    spine = []
    for i, (href, media, content) in enumerate(items):
        props = ' properties="nav"' if href == 'nav.xhtml' else ''
        manifest.append(f'<item id="item{i}" href="{escape(href, quote=True)}" '
                        f'media-type="{media}"{props}/>')
        if media == 'application/xhtml+xml':
            linear = ' linear="no"' if href == 'nav.xhtml' else ''
            spine.append(f'<itemref idref="item{i}"{linear}/>')
    langs = ''.join(f'<dc:language>{escape(value)}</dc:language>' for value in languages)
    modified = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id" xml:lang="{escape(languages[0])}">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="pub-id">urn:uuid:{uuid.uuid4()}</dc:identifier><dc:title>{escape(title)}</dc:title><dc:creator>Rudolfus Schoell; Guilelmus Kroll (edition credits as reported by source)</dc:creator><dc:publisher>Local scholarly research edition</dc:publisher>{langs}<dc:date>{date.today().isoformat()}</dc:date><dc:description>{escape(description)}</dc:description><meta property="dcterms:modified">{modified}</meta></metadata>
<manifest>{''.join(manifest)}</manifest><spine>{''.join(spine)}</spine></package>'''
    packed = [(href, media, content) for href, media, content in items]
    tuple_items = [(href, href, media, content) for href, media, content in packed]
    package_epub(output, opf, tuple_items)

def build_latin() -> dict:
    front_body = f'''<h1>Iustiniani Novellae</h1>
<p><em>Corpus Iuris Civilis</em>, volumen III. Pagina fontis editionem a Rudolfo Schoell curatam, Guilielmo Kroll continuatam indicat.</p>
<p>Haec editio textus Latinos e paginis fontis collegit, ordinem, titulos, paragraphos, signa editorum et fragmenta Graeca servans. Textus a fonte absentes non supplentur.</p>
<p><a href="nav.xhtml">Index et navigatio capitum</a> · <a href="text/Novellae.xhtml">Index in pagina fontis</a></p>
<h2>Amplitudo et lacunae</h2>
<p>In hac editione reperiuntur 165 Novellae paginae (I–CXXXV, CXXXVIII–CLXII, CLXIV–CLXVIII), X paginae Edictorum (I–VI, VIII, X–XII), IX Appendices, atque II volumina Epitomes Iuliani, quae Constitutiones I–CXXIV continent. Paginae non connexae aut absentes: Novellae CXXXVI, CXXXVII, CLXIII; Edicta VII, IX, XIII. In paginis Edictorum I, V et VI verba “Unknown text” leguntur; nullus textus supplendus est. In fonte quoque kp. 531 deest.</p>
<h2>Fons et iura</h2>
<p>Fons principalis: <a href="{escape(BASE, quote=True)}">{escape(BASE)}</a>. HTML originalia, URLs, codices et summas SHA-256 in catalogo locali, in directorio <code>source_original/</code> et in <code>source_manifest.json</code> reperies. Paginae fontis notam iuris Alexandr Koptev exhibent; licentia reutilizationis manifesta non reperta est. Haec compilatio ad usum investigationis localem pertinet.</p>
<p>Submissor paginarum qui a fonte nominantur in singulis paginis servatur; eum a curatoribus editionis typis impressae distingue.</p>'''
    front = xhtml('Praefatio editionis Latinae', front_body, 'la', 'styles/book.css')
    nav = nav_doc('Index Latinus', 'la', latin_groups, 'Praefatio editionis')
    items: list[tuple[str, str, str]] = [
        ('front.xhtml', 'application/xhtml+xml', front),
        ('nav.xhtml', 'application/xhtml+xml', nav),
        ('styles/book.css', 'text/css', css),
    ]
    for p in files:
        body = serialize(parsed[p.name], p.name)
        title = titles[p.name]
        url = 'https://droitromain.univ-grenoble-alpes.fr/Corpus/' + p.name
        note = (f'<aside class="source-note"><p>Textus e pagina fontis hic loci editus. '
                f'Fasciculus HTML originalis: <code>source_original/{escape(p.name)}</code> '
                f'(in archivo locali adiuncto). Fons: <a href="{escape(url, quote=True)}">pagina originaria</a>.</p></aside>')
        page = xhtml(title, '<h1 class="source-page-title">' + escape(title) + '</h1>' + note + body,
                     'la', '../styles/book.css')
        items.append(('text/' + link_map[p.name], 'application/xhtml+xml', page))
    make_package(OUT_LA, 'Iustiniani Novellae: textus Latinus e fonte', ['la', 'grc'],
                 'Textus fontis sine translatione Sinica; fragmenta Graeca a fonte servata sunt.', items)
    return {'output': str(OUT_LA), 'source_documents': len(files), 'language': 'la (fragmenta grc servata)'}

SOURCE_MARKER = re.compile(r'^\*\*原文(?:（[^*]+）)?\*\*$')
TRANSLATION_MARKER = re.compile(r'^\*\*中文译文\*\*$')

def chinese_only_markdown(text: str, filename: str) -> tuple[str, dict]:
    result = []
    skipping = False
    starts = closes = orphan_closes = 0
    for line_no, line in enumerate(text.splitlines(), start=1):
        plain = line.strip()
        if SOURCE_MARKER.fullmatch(plain):
            if skipping:
                raise ValueError(f'{filename}:{line_no}: nested original-text marker')
            skipping = True
            starts += 1
            continue
        if TRANSLATION_MARKER.fullmatch(plain):
            if skipping:
                skipping = False
                closes += 1
            else:
                orphan_closes += 1
            result.append(line)
            continue
        if not skipping:
            result.append(line)
    if skipping:
        raise ValueError(f'{filename}: source-text block has no following Chinese-translation marker')
    return '\n'.join(result) + '\n', {
        'original_blocks_removed': starts,
        'translation_markers_following_removed_blocks': closes,
        'translation_markers_without_source_block': orphan_closes,
    }

def chinese_front(trans_docs: list[tuple[str, str]], metas: list[dict]) -> str:
    entries = ''.join(
        '<li><a href="' + escape('translations/' + doc, quote=True) + '">' +
        escape(ctx['chinese_doc_title'](meta['file'], meta['title'])) + '</a></li>'
        for doc, _ in trans_docs for meta in metas if meta['doc'] == doc
    )
    body = f'''<h1>查士丁尼《新律》中文译本</h1>
<p><em>Iustiniani Novellae</em> 及目录中所列相关组成部分。</p>
<p>据网页版本说明：Rudolfus Schoell 校订；Guilelmus Kroll 完成未竟工作，<em>Corpus Iuris Civilis</em>, vol. III。具体版本信息、录入者、来源说明与校勘标记依各来源页分别保留。</p>
<p>本册提供逐段中文译文；移除了对读稿中的逐段拉丁原文，保留原文标题、敕令程式、法律术语、篇章定位、来源引证和译者注。译文由 OpenAI Codex 及并行代理分批生成、整理，属于机器辅助工作译稿，尚未经古典法学专业译者终审，不应作为定本。</p>
<p><a href="nav.xhtml">打开完整中文导航目录</a> · <a href="terminology.xhtml">术语表（工作版）</a></p>
<h2>收录范围与缺失</h2>{coverage}
<p>原始网页以拉丁文为主，另保留网页中的希腊文片段。未链接的新律第136、137、163篇及敕令第7、9、13篇不作补译；敕令I、V、VI页面标作 “Unknown text.”，无正文可译。尤利安摘要的 kp.531 在来源中缺失。本译本仅翻译网页实际提供的正文，卷首所列完成范围及缺译状态依原译稿保留。</p>
<h2>来源与权利</h2>
<p>来源目录：<a href="{escape(BASE, quote=True)}">{escape(BASE)}</a>；下载日期为2026年9月27日。原始 HTML、来源 URL、编码及 SHA-256 见随附项目目录中的 <code>source_original/</code> 和 <code>source_manifest.json</code>。网站标注 Alexandr Koptev 的版权归属；未发现明确再利用许可。本册供本地研究使用，不构成公开传播授权。</p>
<ul>{entries}</ul>'''
    return xhtml('版本说明与收录范围', body, 'zh-Hans', 'styles/book.css')

def build_chinese() -> tuple[dict, list[tuple[str, str]]]:
    EDITABLE_ZH.mkdir(exist_ok=True)
    out_docs: list[tuple[str, str]] = []
    metas = []
    for meta in translation_meta:
        source = TRANS / meta['file']
        original = source.read_text(encoding='utf-8')
        clean_md, audit = chinese_only_markdown(original, meta['file'])
        editable_path = EDITABLE_ZH / meta['file']
        editable_path.write_text(clean_md, encoding='utf-8')
        title = meta['title']
        doc = 'translation-' + Path(meta['file']).stem + '.xhtml'
        intro = ('<section class="source-note"><p>本卷保留原译稿的完成范围、版本说明、篇章编号、原文标题、法律术语、来源引证和译者注；逐段拉丁原文已单独收入拉丁文版及中拉对照版。</p></section>')
        content = xhtml(title, intro + md_convert(clean_md), 'zh-Hans')
        out_docs.append((doc, content))
        metas.append({**meta, 'doc': doc, 'clean_markdown': str(editable_path), 'strip_audit': audit})

    groups = []
    by_doc = {doc: content for doc, content in out_docs}
    for prefix, label in [
        ('Novellae_', '查士丁尼新律中文译文'),
        ('Edicta_', '查士丁尼十三篇敕令中文译文'),
        ('Appendix_', '散见宪令附录中文译文'),
        ('Epitome_Juliani_', '尤利安新律拉丁摘要中文译文'),
    ]:
        entries = []
        for meta in metas:
            if meta['file'].startswith(prefix):
                doc = meta['doc']
                entries.append(translation_nav_entry(doc, meta, by_doc[doc]))
        if entries:
            groups.append(group_items(entries, label))
    if glossary_content:
        groups.append('<li><a href="terminology.xhtml">术语表（工作版）</a></li>')
    nav = nav_doc('目录（中文）', 'zh-Hans', ''.join(groups), '版本与收录范围')
    front = chinese_front(out_docs, metas)
    items: list[tuple[str, str, str]] = [
        ('front.xhtml', 'application/xhtml+xml', front),
        ('nav.xhtml', 'application/xhtml+xml', nav),
        ('styles/book.css', 'text/css', css),
    ]
    items.extend(('translations/' + doc, 'application/xhtml+xml', content) for doc, content in out_docs)
    if glossary_content and glossary_doc:
        items.append((glossary_doc, 'application/xhtml+xml', glossary_content))
    make_package(OUT_ZH, '查士丁尼《新律》中文译本（Schoell–Kroll 底本）', ['zh-Hans'],
                 '依据网站所载 Schoell–Kroll 版文本制作的中文工作译本；卷首说明译稿范围和状态。', items)
    info = {'output': str(OUT_ZH), 'translation_documents': len(out_docs),
            'editable_markdown_directory': str(EDITABLE_ZH),
            'removed_original_blocks': sum(m['strip_audit']['original_blocks_removed'] for m in metas),
            'unmatched_source_blocks': sum(m['strip_audit']['original_blocks_removed'] - m['strip_audit']['translation_markers_following_removed_blocks'] for m in metas),
            'orphan_translation_markers_retained': sum(m['strip_audit']['translation_markers_without_source_block'] for m in metas),
            'per_file': metas}
    return info, out_docs

def validate_epub(path: Path, expected_nav_lang: str, expected_nav_targets: set[str] | None = None) -> dict:
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        names = z.namelist()
        assert names[0] == 'mimetype'
        assert z.getinfo('mimetype').compress_type == zipfile.ZIP_STORED
        present = set(names)
        xml_docs = {}
        for name in names:
            if name.endswith(('.xhtml', '.opf', '.xml')):
                xml_docs[name] = ET.fromstring(z.read(name))
        assert 'nav.xhtml' in xml_docs
        opf = xml_docs['package.opf']
        ns_opf = {'o': 'http://www.idpf.org/2007/opf'}
        nav_items = [e for e in opf.findall('.//o:manifest/o:item', ns_opf)
                     if 'nav' in e.attrib.get('properties', '').split()]
        assert len(nav_items) == 1, (path, len(nav_items))
        nav_root = xml_docs['nav.xhtml']
        lang = nav_root.attrib.get('{http://www.w3.org/XML/1998/namespace}lang')
        assert lang == expected_nav_lang, (path, lang, expected_nav_lang)
        known_ids = {}
        for name, root in xml_docs.items():
            if name.endswith('.xhtml'):
                known_ids[name] = {e.attrib['id'] for e in root.iter() if 'id' in e.attrib}
        missing = []
        bad_fragments = []
        for name, root in xml_docs.items():
            if not name.endswith('.xhtml'):
                continue
            for element in root.iter():
                href = element.attrib.get('href')
                if not href:
                    continue
                url = urlsplit(href)
                if url.scheme or url.netloc:
                    continue
                if not url.path and not url.fragment:
                    continue
                target = str((Path(name).parent / url.path).as_posix()) if url.path else name
                parts = []
                for part in target.split('/'):
                    if part in ('', '.'):
                        continue
                    if part == '..':
                        if parts:
                            parts.pop()
                    else:
                        parts.append(part)
                target = '/'.join(parts)
                if target not in present:
                    missing.append((name, href))
                elif url.fragment and target in known_ids and url.fragment not in known_ids[target]:
                    bad_fragments.append((name, href))
        assert not missing, (path, missing[:8])
        assert not bad_fragments, (path, bad_fragments[:8])
        nav_links = [e.attrib.get('href', '') for e in nav_root.iter()
                     if e.tag.endswith('}a') and e.attrib.get('href')]
        nav_link_set = set(nav_links)
        nav_targets_missing = sorted((expected_nav_targets or set()) - nav_link_set)
        assert not nav_targets_missing, (path, nav_targets_missing[:12])
        nav_fragment_count = sum(1 for href in nav_links if '#' in href)
        return {
            'epub': str(path), 'zip_test': 'passed', 'mimetype_first_uncompressed': True,
            'xml_parse': 'passed', 'single_nav_item': len(nav_items) == 1,
            'navigation_language': lang, 'internal_href_missing': missing,
            'missing_fragments': bad_fragments, 'navigation_links': len(nav_links),
            'expected_navigation_targets': len(expected_nav_targets or set()),
            'navigation_targets_missing': nav_targets_missing,
            'navigation_fragment_links': nav_fragment_count, 'size_bytes': path.stat().st_size,
        }

def all_translation_heading_targets(docs: list[tuple[str, str]]) -> set[str]:
    targets = set()
    ns = '{http://www.w3.org/1999/xhtml}'
    for doc, content in docs:
        root = ET.fromstring(content)
        for element in root.iter():
            if re.fullmatch(re.escape(ns) + r'h[2-6]', element.tag) and element.attrib.get('id'):
                targets.add('translations/' + doc + '#' + element.attrib['id'])
    return targets

latin_info = build_latin()
chinese_info, chinese_docs = build_chinese()

# Assert all named source anchors and every translation heading are in the
# corresponding reader-facing EPUB navigation document.
def flatten_nav_items(items: list[dict]) -> set[str]:
    targets = set()
    for item in items:
        targets.add(item['href'])
        targets.update(flatten_nav_items(item['children']))
    return targets

source_targets = set()
for p in files:
    source_targets.update(flatten_nav_items(source_anchor_tree(p)))
zh_targets = all_translation_heading_targets(chinese_docs)
report = {
    'bilingual': validate_epub(OUT_BI, 'zh-Hans', zh_targets),
    'latin': validate_epub(OUT_LA, 'la', source_targets),
    'chinese': validate_epub(OUT_ZH, 'zh-Hans', zh_targets),
    'coverage': {
        'source_documents_in_latin_edition': len(files),
        'source_navigation_anchor_targets': len(source_targets),
        'translation_heading_targets': len(zh_targets),
        'removed_original_blocks': chinese_info['removed_original_blocks'],
        'unmatched_source_blocks': chinese_info['unmatched_source_blocks'],
        'orphan_translation_markers_retained': chinese_info['orphan_translation_markers_retained'],
    },
    'latin_edition': latin_info,
    'chinese_edition': chinese_info,
    'bilingual_layout': 'paired original/Chinese passages only; standalone source pages are in the Latin edition',
    'epubcheck': 'not available on PATH; XML, ZIP and link checks are recorded here; Calibre conversion is recorded after build',
}
assert chinese_info['unmatched_source_blocks'] == 0
report_path = ROOT / 'three_editions_validation.json'
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
