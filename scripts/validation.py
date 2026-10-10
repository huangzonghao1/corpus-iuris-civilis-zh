"""Offline source, EPUB, and rebuild checks using the Python standard library."""
from __future__ import annotations

import csv
import hashlib
import json
import posixpath
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
WORKS = {
    "institutiones": ["Justinian_Institutes_Krueger.epub"],
    "digesta": [
        "学说汇纂_下载与EPUB_2026-09-26/Digesta_Iustiniani_Mommsen_Krueger.epub",
        "学说汇纂_下载与EPUB_2026-09-26/Digesta_Iustiniani_学说汇纂_中文全译本.epub",
    ],
    "codex": [
        "Codex_Iustinianus_Krueger_Latin_source.epub",
        "Codex_Iustinianus_Krueger_Latin.epub",
        "Codex_Iustinianus_Krueger_Chinese.epub",
        "Codex_Iustinianus_Krueger_bilingual.epub",
    ],
    "novellae": [
        "Novellae_Schoell_Kroll_Latin.epub",
        "Novellae_Schoell_Kroll_Chinese.epub",
        "Novellae_Schoell_Kroll_Chinese_Bilingual.epub",
    ],
}
NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container",
      "o": "http://www.idpf.org/2007/opf", "x": "http://www.w3.org/1999/xhtml"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def source_check(base: Path) -> dict:
    manifest = base / "source_manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    records = data.get("files", data.get("records", []))
    records += data.get("linked_assets", []) + data.get("linked_pages", [])
    if not records:
        raise ValueError(f"No source records: {manifest}")
    for row in records:
        name = next((row[k] for k in ["local_path", "file", "name"] if row.get(k)), None)
        if not name or not row.get("sha256"):
            raise ValueError(f"Incomplete source record: {manifest}")
        candidates = [base / name, base / "source_original" / name, base / "source_html" / name]
        path = next((p for p in candidates if p.is_file()), None)
        if path is None or not path.resolve().is_relative_to(base.resolve()):
            raise ValueError(f"Missing or out-of-tree source: {name}")
        if sha256(path) != row["sha256"] or path.stat().st_size != row["bytes"]:
            raise ValueError(f"Source hash/size mismatch: {name}")
    return {"source_records": len(records), "hash_and_size": "PASS"}


def resolved(document: str, url: str) -> tuple[str, str] | None:
    parts = urlsplit(url)
    if parts.scheme or parts.netloc:
        return None
    target = posixpath.normpath(posixpath.join(posixpath.dirname(document), unquote(parts.path))) if parts.path else document
    return target, unquote(parts.fragment)


def document_signature(doc: ET.Element) -> dict:
    body = doc.find("x:body", NS)
    if body is None:
        body = doc
    text = normalize("".join(body.itertext()))
    identifiers = [e.get("id") for e in body.iter() if e.get("id")]
    links = [(e.tag.rsplit("}", 1)[-1], k, e.get(k)) for e in doc.iter() for k in ["href", "src"] if e.get(k)]
    headings = [(e.tag.rsplit("}", 1)[-1], normalize("".join(e.itertext()))) for e in body.iter() if re.fullmatch(r"h[1-6]", e.tag.rsplit("}", 1)[-1])]
    values = {"text": text, "identifiers": identifiers, "links": links, "headings": headings}
    return {k: hashlib.sha256(json.dumps(v, ensure_ascii=False).encode()).hexdigest() for k, v in values.items()}


def epub_check(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        listed = archive.namelist()
        names = set(listed)
        if len(names) != len(listed) or any(n.startswith("/") or ".." in Path(n).parts for n in names):
            raise ValueError(f"Duplicate or unsafe ZIP members: {path.name}")
        first = archive.infolist()[0]
        if first.filename != "mimetype" or first.compress_type != zipfile.ZIP_STORED or archive.read("mimetype") != b"application/epub+zip":
            raise ValueError(f"Invalid mimetype: {path.name}")
        if archive.testzip() is not None:
            raise ValueError(f"ZIP CRC error: {path.name}")
        docs = {n: ET.fromstring(archive.read(n)) for n in listed if n.endswith((".xhtml", ".xml", ".opf", ".ncx"))}
        package_path = docs["META-INF/container.xml"].find(".//c:rootfile", NS).get("full-path")
        package = docs[package_path]
        items = {e.get("id"): e for e in package.find("o:manifest", NS)}
        spine = package.find("o:spine", NS)
        spine_paths = []
        for entry in spine:
            item = items.get(entry.get("idref"))
            if item is None:
                raise ValueError(f"Unknown spine resource: {path.name}")
            spine_paths.append(resolved(package_path, item.get("href"))[0])
        nav_items = [item for item in items.values() if "nav" in item.get("properties", "").split()]
        if len(nav_items) != 1:
            raise ValueError(f"Expected exactly one EPUB navigation document: {path.name}")
        nav_path = resolved(package_path, nav_items[0].get("href"))[0]
        ids = {}
        for name, doc in docs.items():
            values = [e.get("id") for e in doc.iter() if e.get("id")]
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate IDs: {path.name}/{name}")
            ids[name] = set(values) | {e.get("name") for e in doc.iter() if e.get("name")}
        checked = 0
        for name, doc in docs.items():
            for element in doc.iter():
                for attribute in ["href", "src"]:
                    if element.get(attribute) is None:
                        continue
                    target = resolved(name, element.get(attribute))
                    if target is None:
                        continue
                    checked += 1
                    file, fragment = target
                    if file not in names or (fragment and file in ids and fragment not in ids[file]):
                        raise ValueError(f"Broken link: {path.name}/{name}: {element.get(attribute)}")
        toc = next((e for e in docs[nav_path].iter() if "toc" in e.get("{http://www.idpf.org/2007/ops}type", "").split()), None)
        if toc is None:
            raise ValueError(f"Missing navigation TOC: {path.name}")
        toc_targets = [resolved(nav_path, e.get("href")) for e in toc.iter() if e.get("href")]
        nav_files = {t[0] for t in toc_targets if t is not None}
        # Some editions include the navigation document itself in the reading
        # order; a TOC is not required to contain a link back to itself.
        uncovered = set(spine_paths) - nav_files - {nav_path}
        if uncovered:
            raise ValueError(f"Spine documents absent from TOC: {path.name}: {sorted(uncovered)}")
        signatures = {n: document_signature(d) for n, d in docs.items() if n.endswith(".xhtml")}
        return {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path),
                "zip_xml_links_navigation": "PASS", "internal_links": checked,
                "spine_documents": len(spine_paths), "spine_order": spine_paths,
                "navigation_targets": len(toc_targets),
                "xhtml_signatures": signatures}


def compare_epubs(original: Path, rebuilt: Path) -> dict:
    old = epub_check(original)
    new = epub_check(rebuilt)
    if old["spine_order"] != new["spine_order"]:
        raise ValueError(f"Rebuild changed reading order: {original.name}")
    if old["xhtml_signatures"] != new["xhtml_signatures"]:
        before, after = old["xhtml_signatures"], new["xhtml_signatures"]
        changed = {n: [k for k in before.get(n, {}) if before[n][k] != after.get(n, {}).get(k)]
                   for n in set(before) | set(after) if before.get(n) != after.get(n)}
        raise ValueError(f"Rebuild changed content/anchors/navigation: {original.name}: {json.dumps(changed, ensure_ascii=False)}")
    return {"file": original.name, "semantic_match": "PASS", "original_sha256": old["sha256"],
            "rebuilt_sha256": new["sha256"], "xhtml_documents_compared": len(old["xhtml_signatures"])}


def translation_check(root: Path) -> dict:
    digesta = root / "works/digesta/学说汇纂_中文翻译工作区"
    progress = json.loads((digesta / "翻译进度.json").read_text(encoding="utf-8"))
    units = progress["completed_units"]
    books = set()
    for unit in units:
        locator = unit.get("locator", "")
        if re.fullmatch(r"D\.\d+\.\d+", locator):
            books.add(int(locator.split(".")[1]))
        for name in unit.get("files", [unit.get("file")]):
            if name and not (digesta / name).is_file():
                raise ValueError(f"Missing Digesta manuscript: {name}")
    if progress["status"] != "complete" or progress["in_progress_units"] or books != set(range(1, 51)) or len(units) != 432:
        raise ValueError("Digesta translation coverage/progress mismatch")
    with (root / "works/codex/translation_status.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 4683 or any(r["translation_status"] != "translated" for r in rows):
        raise ValueError("Codex translation coverage/progress mismatch")
    for row in rows:
        if not (root / "works/codex" / row["translation_file"]).is_file():
            raise ValueError(f"Missing Codex manuscript: {row['translation_file']}")
    return {"digesta_completed_units": len(units), "digesta_books": len(books),
            "codex_translated_units": len(rows), "codex_review_status": dict(Counter(r["review_status"] for r in rows)),
            "coverage_and_manuscript_paths": "PASS", "scholarly_review": "Not independently certified"}
