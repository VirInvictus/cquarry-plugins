# Ported from kiwidude68/calibre_plugins quality_check (GPL-3), copyright
# kiwidude/Grant Drake, for the CalibreQuarry plugin host. The verb
# surface is the recorded CLI twin of upstream's GUI menus (the crosswalk
# rows name every mapping): the check runner replaces the marked-ids
# display, the fix verbs ride the host's WriteGate, the saved-regex
# content search carries upstream's scopes and options, and the
# exclusion lists persist in the plugin's contract-2 config per library
# (upstream's library-database prefs is the recorded storage
# substitution). Provenance: README.md and spec.md.

"""The quality_check plugin: the check battery, the gated fixes, and the
saved-regex ePub content search.

Verbs (all dry-run safe; fixes demand --apply):

  check [--family all|metadata|missing|covers|mobi|epub] [--ids/--search]
        [--max-tags N] [--soundex...] [--format json]
  fix --key swap-author-names|reformat-initials|ascii-authors|author-sort|
        title-sort [--ids ID,...] [--initials-mode A.B.]
  search-epub --pattern P [--scope html,css,opf,ncx,zip] [--ignore-case]
        [--all-matches] [--exclude-matches] [--ids ID,...]
  exclude --check KEY --add ID | --list [--check KEY] | --remove KEY ID
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from quality_check import checks_db, checks_epub
from quality_check.checks_db import MISSING_SEARCHES, DEFAULT_MAX_TAGS

#: The ePub battery: check_key -> evaluate(epub_book) -> bool|None.
EPUB_CHECKS = {
    "check_epub_no_container": checks_epub.check_no_container,
    "check_epub_namespaces": checks_epub.check_namespaces,
    "check_epub_non_dc_metadata": checks_epub.check_non_dc_metadata,
    "check_epub_files_missing": checks_epub.check_opf_files_missing,
    "check_epub_unmanifested_files": checks_epub.check_unmanifested_files,
    "check_epub_unused_css": checks_epub.check_unused_css,
    "check_epub_unused_images": checks_epub.check_unused_images,
    "check_epub_broken_images": checks_epub.check_broken_image_links,
    "check_epub_itunes": checks_epub.check_itunes_files,
    "check_epub_bookmark": checks_epub.check_bookmark_file,
    "check_epub_os_artifacts": checks_epub.check_os_artifacts,
    "check_epub_inside_epub": checks_epub.check_inside_epub,
    "check_epub_corrupt_zip": checks_epub.check_corrupt_zip_entry,
    "check_epub_toc_hierarchy": checks_epub.check_toc_hierarchical,
    "check_epub_toc_size": checks_epub.check_toc_size,
    "check_epub_toc_broken": checks_epub.check_toc_broken_links,
    "check_epub_guide_broken": checks_epub.check_guide_broken_links,
    "check_epub_repl_cover": checks_epub.check_replaceable_cover,
    "check_epub_svg_cover": checks_epub.check_calibre_svg_cover,
    "check_epub_converted": checks_epub.check_conversion,
    "check_epub_html_oversize": checks_epub.check_html_size,
    "check_epub_drm": checks_epub.check_drm,
    "check_epub_adobe_meta_tags": checks_epub.check_drm_meta,
    "check_epub_address_tags": checks_epub.check_address_tags,
    "check_epub_embedded_fonts": checks_epub.check_embedded_fonts,
    "check_epub_font_face": checks_epub.check_font_faces,
    "check_epub_xpgt_margins": checks_epub.check_xpgt_margins,
    "check_epub_inline_xpgt": checks_epub.check_inline_xpgt_links,
    "check_epub_css_justify": checks_epub.check_css_justify,
    "check_epub_css_margins": checks_epub.check_css_margins,
    "check_epub_css_no_margins": checks_epub.check_css_no_margins,
    "check_epub_inline_margins": checks_epub.check_inline_margins,
    "check_epub_javascript": checks_epub.check_javascript,
    "check_epub_smarten_punctuation": checks_epub.check_smarten_punctuation,
}

#: The metadata-quality family: check_key -> (fn(db, book_id, ...)).
METADATA_CHECKS = {
    "check_title_sort": lambda db, bid, **kw: checks_db.check_title_sort(db, bid),
    "check_author_sort": lambda db, bid, **kw: checks_db.check_author_sort(db, bid),
    "check_isbn": lambda db, bid, **kw: checks_db.check_isbn_checksum(db, bid),
    "check_pubdate": lambda db, bid, **kw: checks_db.check_pubdate_unchanged(db, bid),
    "check_excess_tags": lambda db, bid, **kw: checks_db.check_excess_tags(
        db, bid, kw.get("max_tags", DEFAULT_MAX_TAGS)
    ),
    "check_html_comments": lambda db, bid, **kw: checks_db.check_html_in_comments(
        db, bid
    ),
    "check_no_html_comments": lambda db, bid, **kw: checks_db.check_no_html_in_comments(
        db, bid
    ),
    "check_authors_commas": lambda db, bid, **kw: checks_db.check_authors_commas(
        db, bid
    ),
    "check_authors_no_commas": lambda db, bid, **kw: checks_db.check_authors_no_commas(
        db, bid
    ),
    "check_authors_case": lambda db, bid, **kw: checks_db.check_authors_case(db, bid),
    "check_authors_non_alphabetic": lambda db, bid, **kw: (
        checks_db.check_authors_non_alpha(db, bid)
    ),
    "check_authors_non_ascii": lambda db, bid, **kw: checks_db.check_authors_non_ascii(
        db, bid
    ),
    "check_authors_initials": lambda db, bid, **kw: checks_db.check_authors_initials(
        db, bid, kw.get("initials_mode", "A.B.")
    ),
    "check_titles_series": lambda db, bid, **kw: (
        checks_db.check_titles_with_series_info(db, bid)
    ),
    "check_title_case": lambda db, bid, **kw: checks_db.check_title_case(db, bid),
    "check_dup_isbn": lambda db, bid, **kw: False,
    "check_duplicate_series": lambda db, bid, **kw: False,
    "check_series_gaps": lambda db, bid, **kw: False,
}

MOBI_CHECKS = {
    "check_mobi_missing_ebok": lambda db, bid, **kw: checks_db.check_mobi_missing_ebok(
        db, bid
    ),
}

FAMILIES = {
    "metadata": METADATA_CHECKS,
    "missing": {},  # the saved-search family runs separately
    "covers": {},  # the cover checks run with their mode flags
    "mobi": MOBI_CHECKS,
    "epub": EPUB_CHECKS,
}


def _scope(context, args, db):
    db = context.db
    if getattr(args, "ids", None):
        return set(_parse_ids(args.ids))
    if getattr(args, "search", None):
        return set(db.search(args.search))
    return set(db.all_ids())


def _parse_ids(raw):
    return [int(p.strip()) for p in raw.split(",") if p.strip()]


def _exclusions_for(context, check_key):
    """Per-library exclusion list for one check (contract-2 config)."""
    config = context.load_config()
    key = str(Path(context.db_path).resolve())
    lib = config.get("libraries", {}).get(key, {})
    return set(lib.get("exclusionsByCheck", {}).get(check_key, []))


def check(context, argv: list[str]) -> int:
    """The battery: run the families, report flagged ids per check."""
    parser = argparse.ArgumentParser(prog="quality_check check")
    parser.add_argument(
        "--family",
        default="all",
        choices=("all", "metadata", "missing", "covers", "mobi", "epub"),
    )
    parser.add_argument("--ids", default=None)
    parser.add_argument("--search", default=None)
    parser.add_argument("--max-tags", type=int, default=DEFAULT_MAX_TAGS)
    parser.add_argument(
        "--initials-mode", default="A.B.", choices=("A.B.", "A. B.", "A B", "AB")
    )
    parser.add_argument("--format", default=None)
    args, _unknown = parser.parse_known_args(argv)
    db = context.db
    targets = _scope(context, args, db)
    results: dict[str, list[int]] = defaultdict(list)
    errors: list[str] = []

    # -- missing family: saved-search expressions carried verbatim --
    if args.family in ("all", "missing"):
        for key, expr in MISSING_SEARCHES:
            try:
                found = db.search(expr) & targets
            except Exception:
                found = set()
            if found:
                excluded = _exclusions_for(context, key)
                results[key] = sorted(found - excluded)

    # -- metadata family --
    if args.family in ("all", "metadata"):
        # duplicate-isbn groups once, then per-book predicate
        isbn_groups: dict = defaultdict(set)
        for book_id in targets:
            isbn = db.get_identifiers(book_id).get("isbn", "")
            if isbn:
                isbn_groups[isbn].add(book_id)
        series_groups: dict = defaultdict(set)
        series_ints: dict = defaultdict(set)
        for book_id in targets:
            book = db.get_book(book_id, include_comments=False)
            series = book.get("series") if book else None
            if series:
                idx = float(book.get("series_index") or 0)
                series_groups[(series, round(idx, 4))].add(book_id)
                series_ints[series].add(int(idx))
        kw = {"max_tags": args.max_tags, "initials_mode": args.initials_mode}
        for key, fn in METADATA_CHECKS.items():
            excluded = _exclusions_for(context, key)
            flagged = []
            for book_id in sorted(targets):
                try:
                    if key in ("check_dup_isbn", "check_duplicate_isbn"):
                        hit = checks_db.check_duplicate_isbn(db, book_id, isbn_groups)
                    elif key == "check_duplicate_series":
                        hit = checks_db.check_duplicate_series(
                            db, book_id, series_groups
                        )
                    elif key == "check_series_gaps":
                        hit = checks_db.check_series_gaps(db, book_id, series_ints)
                    else:
                        hit = fn(db, book_id, **kw)
                except Exception as exc:
                    errors.append(f"{key} #{book_id}: {exc!r}")
                    continue
                if hit and book_id not in excluded:
                    flagged.append(book_id)
            if flagged:
                results[key] = flagged

    # -- mobi family --
    if args.family in ("all", "mobi"):
        for key, fn in MOBI_CHECKS.items():
            excluded = _exclusions_for(context, key)
            flagged = [b for b in sorted(targets) if fn(db, b)]
            flagged = [b for b in flagged if b not in excluded]
            if flagged:
                results[key] = flagged

    # -- epub family --
    if args.family in ("all", "epub"):
        excluded_any = {}
        for key in EPUB_CHECKS:
            excluded_any[key] = _exclusions_for(context, key)
        for book_id in sorted(targets):
            formats = context.format_paths(book_id)
            epub = next((p for f, p in formats.items() if f.upper() == "EPUB"), None)
            if epub is None or not Path(epub).exists():
                continue
            try:
                book = checks_epub.EpubBook(Path(epub))
            except zipfile.BadZipFile, KeyError:
                results["check_epub_corrupt_zip"].append(book_id)
                continue
            with book:
                for key, fn in EPUB_CHECKS.items():
                    try:
                        hit = fn(book)
                    except Exception:
                        hit = False
                    if hit is True and book_id not in excluded_any[key]:
                        results[key].append(book_id)

    if args.format == "json":
        payload = {
            "results": {k: v for k, v in sorted(results.items())},
            "scope": len(targets),
            "checks_run": len(results),
        }
        print(json.dumps(payload, indent=1, sort_keys=True))
        return 1 if results else 0
    total = sum(len(v) for v in results.values())
    print(f"check: scope {len(targets)} book(s), {len(results)} check(s) with findings")
    for key in sorted(results):
        ids = ", ".join(f"#{b}" for b in results[key])
        print(f"  {key}: {len(results[key])} book(s) [{ids}]")
    print(f"summary: {total} finding(s)")
    if errors:
        print(
            f"check errors ({len(errors)}): the checks named below raised "
            "and are NOT counted as findings:"
        )
        for line in errors:
            print(f"  {line}")
    return 1 if results else 0


def fix(context, argv: list[str]) -> int:
    """The gated fixes (upstream's fix menus, CLI-mapped)."""
    parser = argparse.ArgumentParser(prog="quality_check fix")
    parser.add_argument(
        "--key",
        required=True,
        choices=(
            "fix_swap_author_names",
            "fix_reformat_initials",
            "fix_ascii_authors",
            "fix_author_sort",
            "fix_title_sort",
        ),
    )
    parser.add_argument("--ids", required=True)
    parser.add_argument(
        "--initials-mode", default="A.B.", choices=("A.B.", "A. B.", "A B", "AB")
    )
    args, _unknown = parser.parse_known_args(argv)
    ids = _parse_ids(args.ids)
    if not ids:
        print(
            "ERROR: fix needs --ids (upstream's selection-only scope)", file=sys.stderr
        )
        return 2
    db = context.db
    if not context.can_write:
        actions, lines = _plan_fix(context, args, ids, db)
        lines.insert(0, "DRY RUN: fix plan (--apply executes)")
        for line in lines:
            print(line)
        print(f"plan: {len(actions)} action(s)")
        return 0
    actions, lines = _plan_fix(context, args, ids, db)
    for line in lines:
        print(line)
    code = context.write.apply(context.db_path, actions)
    print(f"applied {len(actions)} fix action(s)")
    return code


def _plan_fix(context, args, ids, db):
    actions = []
    lines = []
    for book_id in ids:
        book = db.get_book(book_id, include_comments=False)
        authors = list(book.get("authors") or []) if book else []
        if args.key == "fix_swap_author_names":
            swapped = []
            for a in authors:
                if "," in a:
                    last, _sep, first = a.partition(",")
                    swapped.append(f"{first.strip()} {last.strip()}")
                else:
                    parts = a.rsplit(" ", 1)
                    swapped.append(f"{parts[1]}, {parts[0]}" if len(parts) == 2 else a)
            actions.append(context.plan.plan_set_authors(book_id, swapped))
            lines.append(f"  #{book_id}: authors swap -> {swapped}")
        elif args.key == "fix_reformat_initials":
            new_authors = [
                checks_db.formatted_author_initials(a, args.initials_mode)
                for a in authors
            ]
            actions.append(context.plan.plan_set_authors(book_id, new_authors))
            lines.append(f"  #{book_id}: initials -> {new_authors}")
        elif args.key == "fix_ascii_authors":
            new_authors = [checks_db._decode_ascii(a) for a in authors]
            actions.append(context.plan.plan_set_authors(book_id, new_authors))
            lines.append(f"  #{book_id}: ascii -> {new_authors}")
        elif args.key == "fix_author_sort":
            actions.append(
                context.plan.plan_set_author_sort(book_id, ", ".join(authors))
            )
            lines.append(f"  #{book_id}: author sort recomputed")
        elif args.key == "fix_title_sort":
            actions.append(
                context.plan.plan_set_title_sort(book_id, book.get("title", ""))
            )
            lines.append(f"  #{book_id}: title sort recomputed")
    return actions, lines


def search_epub(context, argv: list[str]) -> int:
    """Upstream's saved-regex content search: scopes, ignore-case,
    all-matches, and the does-not-contain flag (a book flags when the
    expression matched NOTHING)."""
    parser = argparse.ArgumentParser(prog="quality_check search-epub")
    parser.add_argument("--pattern", required=True)
    parser.add_argument(
        "--scope", default="html", help="comma list from html,plaintext,css,opf,ncx,zip"
    )
    parser.add_argument("--ignore-case", action="store_true", default=True)
    parser.add_argument("--case-sensitive", action="store_true")
    parser.add_argument("--all-matches", action="store_true")
    parser.add_argument(
        "--exclude-matches",
        action="store_true",
        help="flag books where the expression matched NOTHING",
    )
    parser.add_argument("--ids", default=None)
    args, _unknown = parser.parse_known_args(argv)
    db = context.db
    targets = set(_parse_ids(args.ids)) if args.ids else set(db.all_ids())
    flags = 0 if args.case_sensitive else re.IGNORECASE
    pattern = re.compile(args.pattern, flags)
    scopes = {s.strip().lower() for s in args.scope.split(",")}
    flagged: list[int] = []
    lines: list[str] = []
    for book_id in sorted(targets):
        formats = context.format_paths(book_id)
        epub = next((p for f, p in formats.items() if f.upper() == "EPUB"), None)
        if epub is None or not Path(epub).exists():
            continue
        try:
            archive = zipfile.ZipFile(epub)
        except zipfile.BadZipFile:
            continue
        with archive:
            matched = False
            for name in archive.namelist():
                lower = name.lower()
                if lower.endswith((".htm", ".html", ".xhtml")):
                    if not (scopes & {"html", "plaintext"}):
                        continue
                    text = archive.read(name).decode("utf-8", "replace")
                    if "plaintext" in scopes:
                        text = re.sub(r"<[^>]+>", "", text)
                elif lower.endswith((".css", ".xpgt")):
                    if "css" not in scopes:
                        continue
                    text = archive.read(name).decode("utf-8", "replace")
                elif lower.endswith(".opf"):
                    if "opf" not in scopes:
                        continue
                    text = archive.read(name).decode("utf-8", "replace")
                elif lower.endswith(".ncx"):
                    if "ncx" not in scopes:
                        continue
                    text = archive.read(name).decode("utf-8", "replace")
                else:
                    if "zip" not in scopes:
                        continue
                    text = name  # scope_zip searches entry NAMES
                if pattern.search(text):
                    matched = True
                    if not args.exclude_matches:
                        lines.append(f"  #{book_id} {name}: matched")
                        if not args.all_matches:
                            break
            hit = matched if not args.exclude_matches else not matched
            if hit:
                flagged.append(book_id)
                lines.append(
                    f"  #{book_id}: flagged ({'matched' if matched else 'no match'})"
                )
    print(
        f"search-epub: {args.pattern!r} scopes {sorted(scopes)}; "
        f"{len(flagged)} book(s) flagged"
    )
    for line in lines:
        print(line)
    print("changed ids: " + ",".join(str(b) for b in flagged) if flagged else "")
    return 0


def exclusions(context, argv: list[str]) -> int:
    """The per-check exclusion lists (the missing-data checks are NOT
    excludable, upstream's rule)."""
    parser = argparse.ArgumentParser(prog="quality_check exclude")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--check", default=None)
    parser.add_argument("--add", type=int, default=None)
    parser.add_argument("--remove", type=int, default=None, metavar="BOOK_ID")
    args, _unknown = parser.parse_known_args(argv)
    config = context.load_config()
    key = str(Path(context.db_path).resolve())
    lib = config.setdefault("libraries", {}).setdefault(key, {"exclusionsByCheck": {}})
    by_check = lib.setdefault("exclusionsByCheck", {})
    if args.list or (args.add is None and args.remove is None):
        for check_key, ids in sorted(by_check.items()):
            print(f"  {check_key}: {', '.join('#' + str(i) for i in ids)}")
        if not by_check:
            print("(no exclusions recorded for this library)")
        return 0
    if args.check is None:
        print("ERROR: --add/--remove need --check KEY", file=sys.stderr)
        return 2
    if args.check.startswith("check_missing_"):
        print(
            "ERROR: missing-data checks are not excludable (upstream's rule)",
            file=sys.stderr,
        )
        return 2
    entries = by_check.setdefault(args.check, [])
    if args.add is not None:
        if args.add not in entries:
            entries.append(args.add)
            print(f"excluded #{args.add} from {args.check}")
    elif args.remove is not None:
        if args.remove in entries:
            entries.remove(args.remove)
            print(f"removed #{args.remove} from {args.check}")
        else:
            print(f"#{args.remove} not excluded under {args.check}")
    context.save_config(config)
    return 0


def register(context):
    return {
        "check": check,
        "fix": fix,
        "search-epub": search_epub,
        "exclude": exclusions,
    }
