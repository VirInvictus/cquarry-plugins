# Ported from kiwidude68/calibre_plugins quality_check (GPL-3), copyright
# kiwidude/Grant Drake, for the CalibreQuarry plugin host. The ePub
# structure/style battery carries verbatim per the parity crosswalk
# (docs/crosswalk.md): the manifest-worthy filter, the DRM skip, the file
# class lists, and every check's trigger logic. The css_margins
# comparison reads no calibre page-setup prefs (the recorded
# substitution: the core margin patterns flag; the prefs comparison is
# the deferred tail). Provenance: README.md and spec.md.

"""The ePub structure/style battery: stdlib zip/XML parsing, one
evaluate(epub_path) -> bool | None per check (None = skipped, e.g. DRM)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

HTML_OVER_BYTES = 260 * 1024
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp"}
FONT_EXTS = {".otf", ".ttf"}
ITUNES_FILES = ("iTunesMetadata.plist", "iTunesArtwork")
TOLERATED_ARTIFACTS = (
    "itunesmetadata.plist",
    "itunesartwork",
    "calibre_bookmarks.txt",
    ".ds_store",
    "thumbs.db",
)
DRM_ALGORITHM_OK = "http://www.adobe.com/2006/pdf/enc#RC"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _is_drm_encrypted(archive) -> bool | None:
    try:
        data = archive.read("META-INF/encryption.xml")
    except KeyError:
        return False
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return True  # unparseable encryption.xml reads as DRM
    for el in root.iter():
        if _local(el.tag) == "EncryptionMethod":
            algo = el.get("Algorithm", "")
            if algo != DRM_ALGORITHM_OK:
                return True
    return False


class EpubBook:
    """One parsed ePub: names, OPF data, html/css contents."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.archive = zipfile.ZipFile(path)
        self.names = set(self.archive.namelist())
        self.manifest_hrefs: dict[str, str] = {}
        self.spine: list[str] = []
        self.guide: list[tuple[str, str]] = []
        self.opf_name = self._opf_name()
        self.opf_text = (
            self.archive.read(self.opf_name).decode("utf-8", "replace")
            if self.opf_name
            else ""
        )
        self._parse_opf()
        self.drm = _is_drm_encrypted(self.archive)

    def _opf_name(self) -> str | None:
        try:
            container = ET.fromstring(self.archive.read("META-INF/container.xml"))
        except KeyError, ET.ParseError:
            return None
        for el in container.iter():
            if _local(el.tag) == "rootfile" and el.get("full-path"):
                return el.get("full-path")
        return None

    def _parse_opf(self) -> None:
        if not self.opf_name:
            return
        try:
            opf = ET.fromstring(self.archive.read(self.opf_name))
        except ET.ParseError:
            return
        opf_dir = self.opf_name.rsplit("/", 1)[0] if "/" in self.opf_name else ""
        from urllib.parse import unquote

        for el in opf.iter():
            if _local(el.tag) == "item" and el.get("id") and el.get("href"):
                href = unquote(el.get("href").split("#", 1)[0])
                self.manifest_hrefs[el.get("id")] = (
                    f"{opf_dir}/{href}" if opf_dir else href
                )
            elif _local(el.tag) == "itemref" and el.get("idref"):
                self.spine.append(el.get("idref"))
            elif _local(el.tag) == "reference":
                self.guide.append((el.get("type", ""), el.get("href", "")))

    def close(self) -> None:
        self.archive.close()

    def __enter__(self) -> "EpubBook":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def spine_names(self) -> list[str]:
        out = []
        for idref in self.spine:
            href = self.manifest_hrefs.get(idref)
            if href:
                out.append(href)
        return out


def _manifest_worthy(name: str) -> bool:
    if name == "mimetype" or name.endswith("/"):
        return False
    base = name.rsplit("/", 1)[-1].lower()
    if base in ("content.opf",) or base.endswith(".opf"):
        return False
    if name.startswith("META-INF/"):
        return False
    if base == "pagemap.xml" or base == "display-options.xml":
        return False
    return True


# Each check: evaluate(book: EpubBook) -> bool (True = flagged).


def check_no_container(book: EpubBook) -> bool:
    return book.opf_name is None


def check_namespaces(book: EpubBook) -> bool:
    if "META-INF/container.xml" not in book.names:
        return True
    container = book.archive.read("META-INF/container.xml").decode("utf-8", "replace")
    if "urn:oasis:names:tc:opendocument:xmlns:container" not in container:
        return True
    return "http://www.idpf.org/2007/opf" not in book.opf_text


def check_non_dc_metadata(book: EpubBook) -> bool:
    try:
        opf = ET.fromstring(book.archive.read(book.opf_name))
    except KeyError, ET.ParseError:
        return False
    for el in opf.iter():
        if _local(el.tag) == "metadata":
            for child in el:
                tag = _local(child.tag)
                if tag.startswith("dc:") or tag == "meta":
                    if tag == "meta" and child.get("property") == "dcterms:modified":
                        continue
                    if tag == "meta":
                        continue
                elif tag.startswith("dc:"):
                    continue
                else:
                    return True
    return False


def check_opf_files_missing(book: EpubBook) -> bool:
    return any(h not in book.names for h in book.manifest_hrefs.values())


def check_unmanifested_files(book: EpubBook) -> bool:
    worthy = [n for n in book.names if _manifest_worthy(n)]
    referenced = set(book.manifest_hrefs.values())
    for name in worthy:
        base = name.rsplit("/", 1)[-1].lower()
        if base in TOLERATED_ARTIFACTS or any(
            name.endswith(a) for a in TOLERATED_ARTIFACTS
        ):
            continue
        if name not in referenced:
            return True
    return False


def _all_html(book: EpubBook) -> list[str]:
    return [
        n
        for n in book.names
        if n.lower().endswith((".htm", ".html", ".xhtml")) and _manifest_worthy(n)
    ]


def _all_css(book: EpubBook) -> list[str]:
    return [n for n in book.names if n.lower().endswith((".css", ".xpgt"))]


def check_unused_css(book: EpubBook) -> bool:
    if book.drm:
        return None
    html_text = ""
    for name in _all_html(book):
        try:
            html_text += book.archive.read(name).decode("utf-8", "replace")
        except KeyError:
            continue
    for name in book.names:
        if not name.lower().endswith(".css") or not _manifest_worthy(name):
            continue
        base = name.rsplit("/", 1)[-1]
        if base not in html_text and _re_quote(base) not in html_text:
            return True
    return False


def _re_quote(base: str) -> str:
    from urllib.parse import quote

    return quote(base)


def check_unused_images(book: EpubBook) -> bool:
    if book.drm:
        return None
    html_text = ""
    for name in _all_html(book) + _all_css(book):
        try:
            html_text += book.archive.read(name).decode("utf-8", "replace")
        except KeyError:
            continue
    cover_id = None
    cover_match = re.search(
        r'<meta[^>]*name=["\']cover["\'][^>]*content=["\']([^"\']+)', book.opf_text
    )
    if cover_match:
        cover_id = cover_match.group(1)
    images = [
        h for h in book.manifest_hrefs.values() if Path(h).suffix.lower() in IMAGE_EXTS
    ]
    for img in images:
        base = img.rsplit("/", 1)[-1]
        if base in html_text or _re_quote(base) in html_text:
            continue
        if cover_id and book.manifest_hrefs.get(cover_id) == img:
            continue
        if f"url({base})" in html_text or f"url('{base}')" in html_text:
            continue
        return True
    return False


def check_broken_image_links(book: EpubBook) -> bool:
    if book.drm:
        return None
    image_names = {
        n.rsplit("/", 1)[-1]: n
        for n in book.names
        if Path(n).suffix.lower() in IMAGE_EXTS
    }
    for name in _all_html(book):
        try:
            text = book.archive.read(name).decode("utf-8", "replace")
        except KeyError:
            continue
        for match in re.finditer(r"<(?:img|image)[^>]*>", text, re.IGNORECASE):
            src = re.search(r'(?:src|href)="([^"]+)"', match.group(0))
            if not src:
                continue
            target = src.group(1).split("#", 1)[0]
            base = target.rsplit("/", 1)[-1]
            if base and base not in image_names:
                return True
    return False


def check_itunes_files(book: EpubBook) -> bool:
    return any(n in book.names for n in ITUNES_FILES)


def check_bookmark_file(book: EpubBook) -> bool:
    return "META-INF/calibre_bookmarks.txt" in book.names


def check_os_artifacts(book: EpubBook) -> bool:
    return any(
        n.rsplit("/", 1)[-1].lower() in (".ds_store", "thumbs.db") for n in book.names
    )


def check_inside_epub(book: EpubBook) -> bool:
    return any(n.lower().endswith(".epub") for n in book.names)


def check_corrupt_zip_entry(book: EpubBook) -> bool:
    for name in book.names:
        if not _manifest_worthy(name):
            continue
        try:
            book.archive.read(name)
        except zipfile.BadZipFile, RuntimeError, OSError:
            return True
    return False


def check_toc_hierarchical(book: EpubBook) -> bool:
    if book.drm:
        return None
    ncx = _ncx_name(book)
    if not ncx:
        return None
    try:
        ncx_root = ET.fromstring(book.archive.read(ncx))
    except ET.ParseError:
        return None
    for el in ncx_root.iter():
        if _local(el.tag) == "navpoint":
            for child in el:
                if _local(child.tag) == "navpoint":
                    return True
    return False


def check_toc_size(book: EpubBook) -> bool | None:
    if book.drm:
        return None
    ncx = _ncx_name(book)
    if not ncx:
        return True
    try:
        text = book.archive.read(ncx).decode("utf-8", "replace")
    except KeyError, UnicodeDecodeError:
        return True
    return text.count("<navLabel>") < 3


def check_toc_broken_links(book: EpubBook) -> bool:
    if book.drm:
        return None
    ncx = _ncx_name(book)
    if not ncx:
        return None
    try:
        ncx_root = ET.fromstring(book.archive.read(ncx))
    except ET.ParseError:
        return None
    html_names = {_local_name(n) for n in book.names}
    from urllib.parse import unquote

    ncx_dir = ncx.rsplit("/", 1)[0] if "/" in ncx else ""
    for el in ncx_root.iter():
        if _local(el.tag) != "content":
            continue
        src = el.get("src", "")
        target = unquote(src.split("#", 1)[0])
        full = f"{ncx_dir}/{target}" if ncx_dir else target
        if full not in html_names and target not in html_names:
            return True
    return False


def check_guide_broken_links(book: EpubBook) -> bool:
    if book.drm:
        return None
    for _type, href in book.guide:
        target = href.split("#", 1)[0]
        if target and target not in book.manifest_hrefs.values():
            return True
    return False


def check_replaceable_cover(book: EpubBook) -> bool:
    cover_match = re.search(
        r'<meta[^>]*name=["\']cover["\'][^>]*content=["\']([^"\']+)',
        book.opf_text,
    )
    if not cover_match:
        return None
    item = book.manifest_hrefs.get(cover_match.group(1))
    if not item:
        return False
    return Path(item).suffix.lower() in (".png", ".jpg", ".jpeg")


def check_calibre_svg_cover(book: EpubBook) -> bool:
    if book.drm:
        return None
    for gtype, href in book.guide:
        if gtype != "cover":
            continue
        base = href.split("#", 1)[0]
        full = _resolve(book.opf_name, base)
        if full not in book.names:
            continue
        text = book.archive.read(full).decode("utf-8", "replace")
        return 'name="calibre:cover"' in text and "<svg" in text.lower()
    return False


def check_conversion(book: EpubBook) -> bool:
    return 'name="calibre:timestamp"' in book.opf_text or (
        'opf:role="bkp"' in book.opf_text and ">calibre " in book.opf_text
    )


def check_html_size(book: EpubBook) -> bool:
    for name in book.names:
        if name.lower().endswith((".htm", ".html", ".xhtml")):
            info = book.archive.getinfo(name)
            if info.file_size > HTML_OVER_BYTES:
                return True
    return False


def check_drm(book: EpubBook) -> bool:
    return bool(book.drm)


def check_drm_meta(book: EpubBook) -> bool:
    for name in _all_html(book):
        try:
            text = book.archive.read(name).decode("utf-8", "replace")
        except KeyError:
            continue
        if re.search(
            r'<meta[^>]*?name="adept\.(?:expctd\.)*?resource"', text, re.IGNORECASE
        ):
            return True
    return False


def check_address_tags(book: EpubBook) -> bool:
    for name in _all_html(book):
        try:
            if b"</address>" in book.archive.read(name):
                return True
        except KeyError:
            continue
    return False


def check_embedded_fonts(book: EpubBook) -> bool:
    return any(Path(n).suffix.lower() in FONT_EXTS for n in book.names)


def check_font_faces(book: EpubBook) -> bool:
    for name in _all_html(book) + _all_css(book):
        try:
            if "@font-face" in book.archive.read(name).decode("utf-8", "replace"):
                return True
        except KeyError:
            continue
    return False


def check_xpgt_margins(book: EpubBook) -> bool:
    for name in book.names:
        if name.lower().endswith(".xpgt"):
            try:
                if (
                    "margin"
                    in book.archive.read(name).decode("utf-8", "replace").lower()
                ):
                    return True
            except KeyError:
                continue
    return False


def check_inline_xpgt_links(book: EpubBook) -> bool:
    for name in _all_html(book) + _all_css(book):
        try:
            text = book.archive.read(name).decode("utf-8", "replace")
        except KeyError:
            continue
        if (
            re.search(r"<link[^>]*\.xpgt", text)
            or "@import" in text
            and ".xpgt" in text
        ):
            return True
    return False


def check_css_justify(book: EpubBook) -> bool:
    if book.drm:
        return None
    for name in _all_css(book):
        if not name.lower().endswith(".css"):
            continue
        try:
            if re.search(
                r"text-align\s*:\s*justify",
                book.archive.read(name).decode("utf-8", "replace"),
            ):
                return False
        except KeyError:
            continue
    return True


def check_css_margins(book: EpubBook) -> bool:
    if book.drm:
        return None
    for name in _all_css(book):
        if not name.lower().endswith(".css"):
            continue
        try:
            text = book.archive.read(name).decode("utf-8", "replace")
        except KeyError:
            continue
        if re.search(r"(body|@page)\s*\{[^}]*margin", text):
            return True
    return False


def check_css_no_margins(book: EpubBook) -> bool:
    if book.drm:
        return None
    has_margins = False
    for name in _all_css(book):
        if not name.lower().endswith(".css"):
            continue
        try:
            text = book.archive.read(name).decode("utf-8", "replace")
        except KeyError:
            continue
        if re.search(r"(body|@page)\s*\{[^}]*margin", text):
            has_margins = True
    if has_margins:
        return False
    for name in _all_html(book):
        try:
            head = book.archive.read(name).decode("utf-8", "replace")[:1000]
        except KeyError:
            continue
        if re.search(r"(body|@page)\s*\{[^}]*margin", head):
            return False
    return True


def check_inline_margins(book: EpubBook) -> bool:
    if book.drm:
        return None
    for name in _all_html(book):
        if "title" in name.lower() or "cover" in name.lower():
            continue
        try:
            head = book.archive.read(name).decode("utf-8", "replace")[:1000]
        except KeyError:
            continue
        if re.search(r"(body|@page)\s*\{[^}]*margin", head):
            return True
    return False


def check_javascript(book: EpubBook) -> bool:
    if book.drm:
        return None
    if any(n.lower().endswith(".js") for n in book.names):
        return True
    for name in _all_html(book):
        try:
            if re.search(
                r"<script[^>]*text/javascript",
                book.archive.read(name).decode("utf-8", "replace"),
                re.IGNORECASE,
            ):
                return True
        except KeyError:
            continue
    return False


def check_smarten_punctuation(book: EpubBook) -> bool:
    if book.drm:
        return None
    for name in book.spine_names():
        try:
            text = book.archive.read(name).decode("utf-8", "replace")
        except KeyError:
            continue
        body = re.sub(r"<[^>]+>", "", text)
        if "'" in body or '"' in body:
            return True
    return False


# -- helpers the battery shares


def _ncx_name(book: EpubBook) -> str | None:
    toc_match = re.search(
        r'<item[^>]*media-type=["\']application/x-dtbncx\+xml["\'][^>]*id=["\']([^"\']+)',
        book.opf_text,
    )
    if toc_match:
        return book.manifest_hrefs.get(toc_match.group(1))
    return None


def _resolve(opf_name: str, href: str) -> str:
    from urllib.parse import unquote

    target = unquote(href.split("#", 1)[0])
    opf_dir = opf_name.rsplit("/", 1)[0] if "/" in opf_name else ""
    return f"{opf_dir}/{target}" if opf_dir else target


def _local_name(path: str) -> str:
    return path.rsplit("/", 1)[-1]
