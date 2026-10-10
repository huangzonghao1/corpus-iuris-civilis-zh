#!/usr/bin/env python3
"""Package validated snapshot EPUBs and publish their SHA-256 inventory."""
import json
import zipfile
from pathlib import Path
from validation import ROOT, WORKS, sha256

VERSION = "v2026.10.11"
ASSET_NAMES = {"Digesta_Iustiniani_学说汇纂_中文全译本.epub": "Digesta_Iustiniani_Chinese.epub"}


def main():
    verified = json.loads((ROOT / "reports/validation.json").read_text(encoding="utf-8"))
    rebuild = json.loads((ROOT / "reports/rebuild_validation.json").read_text(encoding="utf-8"))
    if verified["status"] != "PASS" or rebuild["status"] != "PASS" or set(rebuild["works"]) != set(WORKS):
        raise ValueError("All four works must pass verification and rebuilding before packaging")
    files = []
    inventory = []
    for entry in verified["epub_validation"]:
        path = ROOT / entry["path"]
        if sha256(path) != entry["sha256"]:
            raise ValueError(f"EPUB changed since validation: {path.name}")
        if not any(item["file"] == path.name and item["original_sha256"] == entry["sha256"]
                   and item["semantic_match"] == "PASS" for item in rebuild["works"][entry["work"]]):
            raise ValueError(f"EPUB has no current matching rebuild audit: {path.name}")
        files.append(path)
        inventory.append({"work": entry["work"], "path": entry["path"],
                          "asset": ASSET_NAMES.get(path.name, path.name),
                          "bytes": path.stat().st_size, "sha256": entry["sha256"]})
    if len(files) != 10 or len({p.name for p in files}) != 10:
        raise ValueError("Expected exactly ten unique EPUB assets")
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    bundle = dist / f"corpus-iuris-civilis-zh-{VERSION}-epub.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, entry in zip(files, inventory):
            archive.write(path, entry["asset"])
            (dist / entry["asset"]).write_bytes(path.read_bytes())
            if entry["asset"] != path.name:
                (dist / path.name).unlink(missing_ok=True)
        archive.write(ROOT / "README.md", "README.md")
        archive.write(ROOT / "reports/publication_changes.json", "publication_changes.json")
    (dist / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in
                [*[dist / entry["asset"] for entry in inventory], bundle]), encoding="utf-8")
    manifest = {"version": VERSION, "repository": "huangzonghao1/corpus-iuris-civilis-zh",
                "editions": inventory, "bundle": {"asset": bundle.name, "bytes": bundle.stat().st_size,
                                                  "sha256": sha256(bundle)}}
    (ROOT / "publication_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Packaged {len(files)} EPUBs, bundle, and SHA256SUMS in {dist}")


if __name__ == "__main__":
    main()
