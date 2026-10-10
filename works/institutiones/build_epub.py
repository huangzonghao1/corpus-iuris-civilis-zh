#!/usr/bin/env python3
"""Package the editable Institutiones edition, without using the finished EPUB.

edition/ contains the normalized reading text, navigation, CSS and package metadata
exported from the existing edition. Exact website bytes remain in source_original/.
This is a packaging entry point, not a new transcription or textual recension.
"""
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent


def main():
    edition = ROOT / "edition"
    with ZipFile(ROOT / "Justinian_Institutes_Krueger.epub", "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip", compress_type=ZIP_STORED)
        for path in sorted(edition.rglob("*")):
            if path.is_file() and path.name != "mimetype":
                archive.write(path, path.relative_to(edition).as_posix(), compress_type=ZIP_DEFLATED)
    print("Institutiones: packaged editable XHTML edition")


if __name__ == "__main__":
    main()
