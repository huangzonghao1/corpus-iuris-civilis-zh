from pathlib import Path
import hashlib
import json
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
EPUB = ROOT / 'Novellae_Schoell_Kroll_Chinese_Bilingual.epub'
REPORT = ROOT / 'epub_validation.json'
XHTML = '{http://www.w3.org/1999/xhtml}'
OPF = '{http://www.idpf.org/2007/opf}'

def body_text(root):
    body = root.find(XHTML + 'body')
    return ''.join(body.itertext()) if body is not None else ''

zip_errors = []
xml_errors = []
missing_hrefs = []
missing_fragments = []
all_ids = {}
with zipfile.ZipFile(EPUB) as zf:
    names = zf.namelist()
    assert names[0] == 'mimetype'
    assert zf.getinfo('mimetype').compress_type == zipfile.ZIP_STORED
    assert zf.testzip() is None
    for name in names:
        if name.endswith(('.xhtml', '.opf', '.xml')):
            try:
                root = ET.fromstring(zf.read(name))
            except ET.ParseError as exc:
                xml_errors.append({'file': name, 'error': str(exc)})
                continue
            if name.endswith('.xhtml'):
                all_ids[name] = {node.attrib['id'] for node in root.iter() if 'id' in node.attrib}
    present = set(names)
    for name in names:
        if not name.endswith('.xhtml'):
            continue
        root = ET.fromstring(zf.read(name))
        for node in root.iter():
            href = node.attrib.get('href')
            if not href:
                continue
            url = urlsplit(href)
            if url.scheme or url.netloc:
                continue
            if not url.path and not url.fragment:
                continue
            target = (Path(name).parent / url.path).as_posix() if url.path else name
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
                missing_hrefs.append({'from': name, 'href': href, 'target': target})
            elif url.fragment and url.fragment not in all_ids.get(target, set()):
                missing_fragments.append({'from': name, 'href': href, 'target': target, 'fragment': url.fragment})

    nav_name = 'nav.xhtml'
    nav_root = ET.fromstring(zf.read(nav_name))
    nav_hrefs = {node.attrib['href'] for node in nav_root.iter()
                 if node.tag == XHTML + 'a' and 'href' in node.attrib}
    opf_root = ET.fromstring(zf.read('package.opf'))
    nav_manifest_items = [node for node in opf_root.iter(OPF + 'item')
                          if 'nav' in node.attrib.get('properties', '').split()]
    assert len(nav_manifest_items) == 1 and nav_manifest_items[0].attrib['href'] == nav_name

    translated_heading_ids = 0
    translated_heading_nav_missing = []
    for name in names:
        if not name.startswith('translations/translation-') or not name.endswith('.xhtml'):
            continue
        root = ET.fromstring(zf.read(name))
        for node in root.iter():
            if node.tag in {XHTML + f'h{i}' for i in range(2, 7)} and node.attrib.get('id'):
                translated_heading_ids += 1
                expected = name + '#' + node.attrib['id']
                if expected not in nav_hrefs:
                    translated_heading_nav_missing.append(expected)

    source_documents_embedded = [name for name in names if re.fullmatch(
        r'text/(?:Novellae|Nov\d+|Ed\d+|App\d+|epitome_julien_\d+)\.xhtml', name)]
    assert not source_documents_embedded, source_documents_embedded
    assert 'index_latinus.xhtml' not in names

    samples = []
    sample_names = [
        'translations/translation-Novellae_001-056_Chinese.xhtml',
        'translations/translation-Novellae_057-112_Chinese.xhtml',
        'translations/translation-Novellae_113-168_Chinese.xhtml',
        'translations/translation-Edicta_001-012_Chinese.xhtml',
        'translations/translation-Appendix_001-009_Chinese.xhtml',
        'translations/translation-Epitome_Juliani_081-124_Chinese.xhtml',
    ]
    for name in sample_names:
        root = ET.fromstring(zf.read(name))
        text = body_text(root)
        samples.append({
            'file': name,
            'xhtml_valid': True,
            'replacement_character': '\ufffd' in text,
            'greek_characters': len(re.findall(r'[\u0370-\u03ff]', text)),
            'chinese_characters': len(re.findall(r'[\u3400-\u9fff]', text)),
            'text_characters': len(text),
        })

    first_pair = body_text(ET.fromstring(zf.read(
        'translations/translation-Novellae_001-056_Chinese.xhtml')))
    paired_checks = {
        'latin_passage_present': 'Occupatis nobis circa totius' in first_pair,
        'chinese_translation_present': '我们既然为整个国家' in first_pair,
        'original_marker_present': '原文（拉丁文）' in first_pair,
        'translation_marker_present': '中文译文' in first_pair,
    }

report = {
    'epub': str(EPUB),
    'zip_test': 'passed',
    'mimetype_first_uncompressed': True,
    'xhtml_xml_parse': 'passed' if not xml_errors else 'failed',
    'xml_errors': xml_errors,
    'internal_href_missing': missing_hrefs,
    'missing_fragments': missing_fragments,
    'layout': 'paired original/Chinese translation passages; standalone source pages omitted',
    'source_pages_embedded': len(source_documents_embedded),
    'navigation_spot_check': {
        'nav_manifest_item_present': len(nav_manifest_items) == 1,
        'toc_nav_count': len([node for node in nav_root.iter(XHTML + 'nav')
                              if 'toc' in node.attrib.get('{http://www.idpf.org/2007/ops}type', '').split()]),
        'toc_language': nav_root.attrib.get('{http://www.w3.org/XML/1998/namespace}lang'),
        'navigation_link_count': len(nav_hrefs),
        'translated_heading_ids': translated_heading_ids,
        'translated_heading_nav_missing': translated_heading_nav_missing,
    },
    'paired_passage_spot_check': paired_checks,
    'spot_checks': samples,
    'sha256': hashlib.sha256(EPUB.read_bytes()).hexdigest(),
    'epubcheck': 'available' if shutil.which('epubcheck') else 'not available on PATH',
}
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
assert not xml_errors, xml_errors[:5]
assert not missing_hrefs, missing_hrefs[:5]
assert not missing_fragments, missing_fragments[:5]
assert not translated_heading_nav_missing, translated_heading_nav_missing[:5]
assert len(nav_manifest_items) == 1
assert nav_root.attrib.get('{http://www.w3.org/XML/1998/namespace}lang') == 'zh-Hans'
assert translated_heading_ids == len([href for href in nav_hrefs if '#' in href])
assert all(not sample['replacement_character'] for sample in samples)
assert samples[2]['greek_characters'] > 0
assert all(paired_checks.values())
print(json.dumps({
    'epub': str(EPUB), 'zip': report['zip_test'], 'xml': report['xhtml_xml_parse'],
    'missing_hrefs': len(missing_hrefs), 'missing_fragments': len(missing_fragments),
    'embedded_standalone_source_pages': len(source_documents_embedded),
    'translated_nav_heading_targets': translated_heading_ids,
    'paired_passage_spot_check': paired_checks, 'sha256': report['sha256'],
}, ensure_ascii=False, indent=2))
