# Ported from kiwidude68/calibre_plugins find_duplicates (GPL-3), copyright
# 2011 Grant Drake, for the CalibreQuarry plugin host. The matcher ladder
# (identical / similar / soundex / fuzzy / ignore per field), the
# EPUB-free grouping pipeline (shrink, subset-clean, sort, the exemption
# partition with its don't-repartition subtlety), the three search types,
# and the exemption schema (bookExemptions / authorExemptions) are
# upstream's, carried verbatim per the parity crosswalk
# (docs/crosswalk.md). Recorded substitutions: calibre's get_udc() decode
# becomes a local NFKD-strip approximation; the soundex implementation is
# upstream's Jorgensen public-domain port; per-library exemption storage
# moves from the library database's namespaced preferences to the plugin's
# own config (keyed by the absolute library path), so the GUI plugin's and
# this plugin's exemption sets are independent; the tags soundex length
# quirk (upstream's tags matcher reading the publisher length) is the
# recorded deliberate correction. Provenance: README.md and spec.md.

"""The find_duplicates plugin: duplicate books across the matcher ladder,
byte-identical formats, and identifiers.

Verbs (dry-run safe; the actions land in the Phase 2 actions release):

  search  --type titleauthor|binary|identifier  [--title-match M]
          [--author-match M]  [--identifier-type isbn]
          [--soundex-title N] [--soundex-author N]  [--include-languages]
          [--ids ID,...]  [--search QUERY]  [--sort title|count]
          [--format json]  [--against PATH]
  exempt  --books ID,ID... | --authors A[,A...] | --list | --remove INDEX
          | --clear

Group reports replace upstream's marked-book highlighting; exemptions
persist in this plugin's config keyed per library, where upstream uses
the library database's namespaced preferences.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TITLE_SOUNDEX = 6
DEFAULT_AUTHOR_SOUNDEX = 8
DEFAULT_TAGS_SOUNDEX = 4
DEFAULT_IDENTIFIER_TYPE = "isbn"
MATCHERS = ("identical", "similar", "soundex", "fuzzy", "ignore")
FORMAT_PREFERENCE = (
    "EPUB",
    "AZW3",
    "MOBI",
    "LIT",
    "PRC",
    "FB2",
    "HTML",
    "HTM",
    "XHTM",
    "SHTML",
    "XHTML",
    "ZIP",
    "DOCX",
    "ODT",
    "RTF",
    "PDF",
    "TXT",
)


def _decode_ascii(text: str) -> str:
    """The get_udc() substitution: an NFKD strip to plain ASCII."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


# ------------------------------------------------------- matcher ladder

IGNORE_AUTHOR_WORDS = frozenset(
    ["von", "van", "jr", "sr", "i", "ii", "iii", "second", "third", "md", "phd"]
)


def _fuzzy_it(text: str) -> str:
    """The automerge strip: punctuation, leading article, separators."""
    text = text.strip().lower()
    text = re.sub(r"[\[\](){}<>'\";,:#]", "", text)
    text = re.sub(r"^(a|the|an)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[-._]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _soundex(name: str, length: int = 4) -> str:
    """Knuth-conforming soundex (Gregory Jorgensen's public-domain port,
    carried verbatim from upstream)."""
    digits = "01230120022455012623010202"
    sndx = ""
    fc = ""
    orda = ord("A")
    ordz = ord("Z")
    for c in name.upper():
        ordc = ord(c)
        if orda <= ordc <= ordz:
            if not fc:
                fc = c
            d = digits[ordc - orda]
            if not sndx or (d != sndx[-1]):
                sndx += d
    sndx = fc + sndx[1:]
    sndx = sndx.replace("0", "")
    return (sndx + (length * "0"))[:length]


def _get_title_tokens(title: str):
    """Fuzzy-title tokens: subtitle dropped, edition parens dropped,
    a/the dropped, lowercase (upstream's patterns verbatim)."""
    if not title:
        return
    subtitle = re.compile(r"([\(\[\{].*?[\)\]\}]|[/:\\].*$)")
    if len(subtitle.sub("", title)) > 1:
        title = subtitle.sub("", title)
    patterns = [
        (
            r"(?i)[({\[](\d{4}|omnibus|anthology|hardcover|paperback|mass\s*market|edition|ed\.)[\])}]",
            "",
        ),
        (r"(?i)[({\[].*?(edition|ed.).*?[\]})]", ""),
        (r"(\d+),(\d+)", r"\1\2"),
        (r"(\s-)", " "),
        (r"'(?!s)", ""),
        (r'[:,;+!@#$%^&*(){}.`~"\s\[\]/]', " "),
    ]
    for pat, repl in [(re.compile(p, re.IGNORECASE), r) for p, r in patterns]:
        title = pat.sub(repl, title)
    title = _decode_ascii(title)
    for token in title.split():
        token = token.strip()
        if token and token.lower() not in ("a", "the"):
            yield token.lower()


def identical_title_match(title, lang=None):
    return (lang or "") + title.lower()


def similar_title_match(title, lang=None):
    result = _fuzzy_it(_decode_ascii(title))
    return (lang or "") + result


def soundex_title_match(title, lang=None, length=DEFAULT_TITLE_SOUNDEX):
    result = _soundex(similar_title_match(title), length)
    return (lang or "") + result


def fuzzy_title_match(title, lang=None):
    tokens = list(_get_title_tokens(title))
    for i, tok in enumerate(tokens):
        if tok in ("&", "and", "or", "aka") and i > 0:
            tokens = tokens[:i]
            break
    result = "".join(tokens)
    return (lang or "") + result


def _get_author_tokens(author: str, strip_initials: bool = False):
    """Author tokens in first..last order (comma rotation), ignore words
    dropped, apostrophes kept for Irish names (upstream verbatim)."""
    if not author:
        return
    author = re.sub(r",([^\s])", ", \\1", author)
    au = re.sub(r"[-+.:;]", " ", author)
    au = _decode_ascii(au)
    parts = au.split()
    if "," in au:
        # ln, fn form: rotate the surname from the front to the end
        parts = parts[1:] + parts[:1]
    remove_pat = re.compile(r'[,!@#$%^&*(){}`~"\s\[\]/]')
    min_length = 1 if strip_initials else 0
    for tok in parts:
        tok = remove_pat.sub("", tok).strip()
        if len(tok) > min_length and tok.lower() not in IGNORE_AUTHOR_WORDS:
            yield tok.lower()


def identical_authors_match(author):
    return author.lower(), None


def similar_authors_match(author):
    tokens = list(_get_author_tokens(author, strip_initials=True))
    ahash = " ".join(tokens)
    rev_ahash = None
    if len(tokens) > 1:
        tokens = tokens[1:] + tokens[:1]
        rev_ahash = " ".join(tokens)
    return ahash, rev_ahash


def soundex_authors_match(author, length=DEFAULT_AUTHOR_SOUNDEX):
    tokens = list(_get_author_tokens(author))
    if len(tokens) <= 1:
        return _soundex("".join(tokens)), None
    # Surname fronted so the soundex focuses on it (upstream's rule).
    new_tokens = [tokens[-1]]
    new_tokens.extend(tokens[:-1])
    ahash = _soundex("".join(new_tokens), length)
    rev_ahash = None
    if len(tokens) > 1:
        rev_ahash = _soundex("".join(tokens), length)
    return ahash, rev_ahash


def fuzzy_authors_match(author):
    tokens = list(_get_author_tokens(author))
    if not tokens:
        return "", None
    if len(tokens) == 1:
        return tokens[0], None
    # Initial plus surname, no reversed permutation: A. Bronte is
    # "ABronte", never "BA" (upstream's comment, behavior is the point).
    return "".join([tokens[0][0], tokens[-1]]), None


TITLE_FNS = {
    "identical": identical_title_match,
    "similar": similar_title_match,
    "soundex": soundex_title_match,
    "fuzzy": fuzzy_title_match,
}
AUTHOR_FNS = {
    "identical": identical_authors_match,
    "similar": similar_authors_match,
    "soundex": soundex_authors_match,
    "fuzzy": fuzzy_authors_match,
}


# ------------------------------------------------------------- exemptions


class ExemptionMap:
    """Upstream's map: member -> the exemption sets containing it."""

    def __init__(self, exemptions) -> None:
        self._sets = [set(items) for items in exemptions]
        self._map: dict = defaultdict(list)
        for entry in self._sets:
            for key in entry:
                self._map[key].append(entry)

    def merge_sets(self, key):
        merged: set = set()
        for entry in self._map.get(key, ()):
            merged |= entry
        merged.discard(key)
        return merged


def _partition_using_exemptions(data_items, exemptions_map):
    """Upstream's partition: exempted pairs never co-occur; a partitioning
    item never re-partitions its own split (the subset subtlety its
    comment documents). Verbatim behavior over sorted items."""
    data_items = sorted(data_items)
    results = [set(data_items)]
    partitioning_ids = [None]
    for one_dup in data_items:
        if one_dup not in exemptions_map._map:
            continue
        ndm_entry = exemptions_map.merge_sets(one_dup)
        for i, res in enumerate(results):
            if one_dup in res:
                if one_dup == partitioning_ids[i]:
                    results[i] = (res - ndm_entry) | {one_dup}
                    continue
                results[i] = (res - ndm_entry) | {one_dup}
                for nd in ndm_entry:
                    if nd > one_dup and nd in res:
                        results.append((res - ndm_entry - {one_dup}) | {nd})
                        partitioning_ids.append(nd)
    out = [sorted(r) for r in results if len(r) > 1]
    out.sort()
    return out


def _clean_dup_groups(candidates_map):
    """Sets, smallest first, dropping any set that is a subset of another."""
    res = [set(d) for d in candidates_map.values()]
    res.sort(key=len)
    out = []
    for i, a in enumerate(res):
        for b in res[i + 1 :]:
            if a.issubset(b):
                break
        else:
            out.append(a)
    return out


def _shrink(candidates_map):
    for key in list(candidates_map.keys()):
        if len(candidates_map[key]) < 2:
            del candidates_map[key]


# ---------------------------------------------------------------- reading


def _book_authors(db, book_id) -> list[str]:
    book = db.get_book(book_id, include_comments=False)
    return list(book.get("authors") or []) if book else []


def _book_title(db, book_id) -> str:
    book = db.get_book(book_id, include_comments=False)
    return book.get("title", "") if book else ""


def _book_languages(db, book_id) -> str:
    book = db.get_book(book_id, include_comments=False)
    return "".join(sorted(book.get("languages") or [])) if book else ""


def _formats_of(context, book_id) -> dict:
    return context.format_paths(book_id)


def _sha_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# -------------------------------------------------------------- algorithms


class _Base:
    mode = "book"

    def __init__(self, book_exemptions, author_exemptions) -> None:
        self.book_exemptions = book_exemptions
        self.author_exemptions = author_exemptions

    def exemption_map(self):
        source = (
            self.author_exemptions if self.mode == "author" else self.book_exemptions
        )
        return ExemptionMap(source)

    def run(self, context, book_ids, include_languages=False, sort_by_title=True):
        candidates = defaultdict(set)
        extra = {}
        for book_id in book_ids:
            self.find_candidate(context, book_id, candidates, include_languages, extra)
        _shrink(candidates)
        return self.run_from_candidates(context, candidates, sort_by_title)

    def run_from_candidates(self, context, candidates, sort_by_title=True):
        candidates = self.sort_candidates(candidates, context, sort_by_title)
        candidates_list = _clean_dup_groups(candidates)
        emap = self.exemption_map()
        books_for_group: dict[int, list] = {}
        groups_for_book: dict = defaultdict(set)
        group_id = 0
        for members in candidates_list:
            partitions = _partition_using_exemptions(members, emap)
            if self.mode == "author":
                partitions = [
                    sorted(self.book_ids_for(partition)) for partition in partitions
                ]
                partitions = [p for p in partitions if len(p) > 1]
            for partition in partitions:
                if len(partition) > 1:
                    group_id += 1
                    books_for_group[group_id] = partition
                    for book_id in partition:
                        groups_for_book[book_id].add(group_id)
        return books_for_group, groups_for_book

    def sort_candidates(self, candidates, context, sort_by_title=True):
        """By the fuzzy key itself, or by group size then key descending."""
        if sort_by_title:
            keys = sorted(candidates.keys())
        else:
            keys = sorted(
                candidates.keys(),
                key=lambda k: "%04d%s" % (len(candidates[k]), str(k)),
                reverse=True,
            )
        return {k: candidates[k] for k in keys}


class TitleAuthorAlgorithm(_Base):
    def __init__(self, title_eval, author_eval, **kw) -> None:
        super().__init__(**kw)
        self.title_eval = title_eval
        self.author_eval = author_eval

    def find_candidate(self, context, book_id, candidates, include_languages, extra):
        db = context.db
        lang = _book_languages(db, book_id) if include_languages else None
        title_hash = self.title_eval(_book_title(db, book_id), lang)
        if self.author_eval:
            for author in _book_authors(db, book_id):
                author_hash, rev_hash = self.author_eval(author)
                candidates[title_hash + author_hash].add(book_id)
                if rev_hash and rev_hash != author_hash:
                    candidates[title_hash + rev_hash].add(book_id)
            return
        candidates[title_hash].add(book_id)


class AuthorOnlyAlgorithm(_Base):
    """Candidates keyed by author hash with author NAMES as members; the
    group's book ids come from the author->books map; exemptions are
    per author name (upstream's author search mode)."""

    mode = "author"

    def __init__(self, author_eval, **kw) -> None:
        super().__init__(**kw)
        self.author_eval = author_eval
        self.author_bookids: dict = defaultdict(set)

    def find_candidate(self, context, book_id, candidates, include_languages, extra):
        authors = _book_authors(context.db, book_id)
        if not authors:
            return
        for author in authors:
            self.author_bookids[author].add(book_id)
            author_hash, rev_hash = self.author_eval(author)
            candidates[author_hash].add(author)
            if rev_hash and rev_hash != author_hash:
                candidates[rev_hash].add(author)

    def book_ids_for(self, partition):
        ids: set = set()
        for author in partition:
            ids |= self.author_bookids.get(author, set())
        return ids

    def sort_candidates(self, candidates, context, sort_by_title=True):
        if sort_by_title:
            keys = sorted(candidates.keys())
        else:
            keys = sorted(
                candidates.keys(),
                key=lambda k: "%04d%s" % (len(candidates[k]), str(k)),
                reverse=True,
            )
        return {k: candidates[k] for k in keys}


class IdentifierAlgorithm(_Base):
    def __init__(self, identifier_type=DEFAULT_IDENTIFIER_TYPE, **kw) -> None:
        super().__init__(**kw)
        self.identifier_type = identifier_type

    def find_candidate(self, context, book_id, candidates, include_languages, extra):
        value = context.db.get_identifiers(book_id).get(self.identifier_type, "")
        if value:
            candidates[value].add(book_id)

    def sort_candidates(self, candidates, context, sort_by_title=True):
        def title_key(k):
            first = min(candidates[k])
            return _fuzzy_it(_book_title(context.db, first))

        if sort_by_title:
            keys = sorted(candidates.keys(), key=title_key)
        else:
            keys = sorted(
                candidates.keys(),
                key=lambda k: "%04d%s" % (len(candidates[k]), str(k)),
                reverse=True,
            )
        return {k: candidates[k] for k in keys}


class BinaryCompareAlgorithm(IdentifierAlgorithm):
    """Two passes: exact size collisions, then SHA over the survivors,
    with an mtime-keyed sha cache (upstream's two-pass shape; the cache
    lives in the plugin's config dir, not the library database)."""

    def run(self, context, book_ids, include_languages=False, sort_by_title=True):
        cache = context.load_config().get("shaCache", {})
        sizes: dict = defaultdict(set)
        for book_id in book_ids:
            for fmt, path in _formats_of(context, book_id).items():
                try:
                    stat = path.stat()
                except OSError:
                    continue
                sizes[stat.st_size].add((book_id, fmt, path, stat.st_mtime))
        _shrink(sizes)
        candidates: dict = defaultdict(set)
        for size, group in sizes.items():
            for book_id, fmt, path, mtime in group:
                key = f"{book_id}:{fmt}"
                cached = cache.get(key)
                if (
                    cached
                    and cached.get("mtime") == mtime
                    and cached.get("size") == size
                    and cached.get("path") == str(path)
                ):
                    sha = cached["sha"]
                else:
                    try:
                        sha = _sha_of(path)
                    except OSError:
                        continue
                    cache[key] = {
                        "path": str(path),
                        "mtime": mtime,
                        "size": size,
                        "sha": sha,
                    }
                candidates[(sha, size)].add(book_id)
        config = context.load_config()
        if config.get("shaCache") != cache:
            config["shaCache"] = cache
            context.save_config(config)
        return self.run_from_candidates(context, candidates, sort_by_title)


def _make_algorithm(args, context, config):
    """(algorithm, error): the error string is a usage refusal (exit 2)."""
    library_key = str(Path(context.db_path).resolve())
    lib_cfg = config.setdefault("libraries", {}).setdefault(
        library_key, {"bookExemptions": [], "authorExemptions": []}
    )
    book_ex = lib_cfg.setdefault("bookExemptions", [])
    author_ex = lib_cfg.setdefault("authorExemptions", [])
    search_type = args.type
    if search_type == "identifier":
        return IdentifierAlgorithm(
            args.identifier_type, book_exemptions=book_ex, author_exemptions=author_ex
        ), None
    if search_type == "binary":
        return BinaryCompareAlgorithm(
            book_exemptions=book_ex, author_exemptions=author_ex
        ), None
    title_match = args.title_match
    author_match = args.author_match
    if title_match == "ignore" and author_match == "ignore":
        return None, "--title-match ignore needs --author-match other than ignore"
    if title_match == "ignore" and author_match == "identical":
        return None, (
            "--title-match ignore with --author-match identical matches every "
            "book; pick a real author matcher (upstream's own refusal)"
        )

    def title_eval(title, lang=None):
        if title_match == "soundex":
            return soundex_title_match(title, lang, args.soundex_title)
        return TITLE_FNS[title_match](title, lang)

    if author_match == "ignore":
        return TitleAuthorAlgorithm(
            title_eval, None, book_exemptions=book_ex, author_exemptions=author_ex
        ), None

    if author_match == "soundex":

        def author_eval(author):
            return soundex_authors_match(author, args.soundex_author)

    else:
        author_eval = AUTHOR_FNS[author_match]

    if title_match == "ignore":
        return AuthorOnlyAlgorithm(
            author_eval, book_exemptions=book_ex, author_exemptions=author_ex
        ), None
    return TitleAuthorAlgorithm(
        title_eval, author_eval, book_exemptions=book_ex, author_exemptions=author_ex
    ), None


def _targets(context, args, db):
    if args.ids:
        return set(_parse_ids(args.ids))
    if args.search:
        return set(db.search(args.search))
    return set(db.all_ids())


def _parse_ids(raw: str) -> list[int]:
    return [int(p.strip()) for p in raw.split(",") if p.strip()]


def _describe_book(context, book_id) -> str:
    db = context.db
    book = db.get_book(book_id, include_comments=False)
    title = book.get("title", "") if book else f"book {book_id}"
    authors = ", ".join(book.get("authors") or []) if book else ""
    fmts = "/".join(sorted(_formats_of(context, book_id)))
    bits = [f"#{book_id} {title}"]
    if authors:
        bits.append(authors)
    if fmts:
        bits.append(f"[{fmts}]")
    return " | ".join(bits)


def search(context, argv: list[str]) -> int:
    """The duplicate search: groups rendered as the report (the recorded
    CLI twin of upstream's marked-book highlighting)."""
    args = _parse_search_args(argv)
    db = context.db
    config = context.load_config()
    algorithm, error = _make_algorithm(args, context, config)
    if error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    targets = _targets(context, args, db)
    if args.type == "identifier":
        targets = {
            b
            for b in targets
            if context.db.get_identifiers(b).get(args.identifier_type)
        }
    elif args.type == "binary":
        targets = {b for b in targets if _formats_of(context, b)}
    books_for_group, groups_for_book = algorithm.run(
        context,
        sorted(targets),
        include_languages=args.include_languages,
        sort_by_title=args.sort != "count",
    )

    if args.against:
        return _cross_library(context, args, db)

    if args.format == "json":
        payload = {
            "books_for_group": {str(g): ids for g, ids in books_for_group.items()},
            "entangled_groups_for_book": {
                str(b): sorted(g) for b, g in groups_for_book.items() if len(g) > 1
            },
            "library_uuid": None,
            "library_path": str(Path(context.db_path).resolve()),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        print(json.dumps(payload, indent=1, sort_keys=True))
        return 0
    lib_cfg = config.get("libraries", {}).get(str(Path(context.db_path).resolve()), {})
    lines = [
        f"search: {args.type}"
        + (
            f" ({args.title_match} title, {args.author_match} author)"
            if args.type == "titleauthor"
            else ""
        )
        + f"; scope: {len(targets)} book(s); exemptions: "
        + f"{len(lib_cfg.get('bookExemptions', []))} book set(s), "
        + f"{len(lib_cfg.get('authorExemptions', []))} author set(s)"
    ]
    for gid, ids in books_for_group.items():
        lines.append(f"group {gid} ({len(ids)} book(s)):")
        for book_id in ids:
            lines.append(f"  {_describe_book(context, book_id)}")
    entangled = sorted(b for b, g in groups_for_book.items() if len(g) > 1)
    if entangled:
        lines.append(
            "entangled: "
            + ", ".join(
                f"#{b} in {len(groups_for_book[b])} group(s)" for b in entangled
            )
        )
    covered = len({b for ids in books_for_group.values() for b in ids})
    lines.append(f"summary: {len(books_for_group)} group(s) covering {covered} book(s)")
    for line in lines:
        print(line)
    return 0


def _cross_library(context, args, db):
    """The recorded report-only comparison: the second library opens
    read-only, exemptions do not apply (upstream's own rule)."""
    from cquarry.db import CalibreDB

    against = CalibreDB(args.against)
    matched = 0
    print(f"cross-library: local vs {args.against}")
    if args.type == "identifier":
        for book_id in sorted(db.all_ids()):
            value = db.get_identifiers(book_id).get(args.identifier_type)
            if not value:
                continue
            for target_id in sorted(against.all_ids()):
                if (
                    against.get_identifiers(target_id).get(args.identifier_type)
                    == value
                ):
                    matched += 1
                    print(
                        f"  #{book_id} {_book_title(db, book_id)} == target #{target_id} {_book_title(against, target_id)} ({args.identifier_type} {value})"
                    )
    elif args.type == "binary":
        local_sizes: dict = defaultdict(set)
        target_sizes: dict = defaultdict(set)
        for book_id in db.all_ids():
            for fmt, path in _formats_of(context, book_id).items():
                try:
                    local_sizes[path.stat().st_size].add((book_id, fmt, path))
                except OSError:
                    pass
        for book_id in against.all_ids():
            for fmt, detail in against.get_formats(book_id).items():
                p = Path(detail["path"])
                try:
                    target_sizes[p.stat().st_size].add((book_id, fmt, p))
                except OSError:
                    pass
        shared = set(local_sizes) & set(target_sizes)
        local_hash: dict = {}
        target_hash: dict = {}
        for size in shared:
            for book_id, fmt, path in local_sizes[size]:
                local_hash[(book_id, fmt, _sha_of(path))] = size
            for target_id, fmt, path in target_sizes[size]:
                target_hash[(target_id, fmt, _sha_of(path))] = size
        for (book_id, fmt, sha), size in local_hash.items():
            for (target_id, tfmt, tsha), tsize in target_hash.items():
                if sha == tsha:
                    matched += 1
                    print(
                        f"  #{book_id} {_book_title(db, book_id)} [{fmt}] == target #{target_id} {_book_title(against, target_id)} [{tfmt}] (byte-identical, {size} bytes)"
                    )
    else:

        def _hash_map(a_db):
            title_fn = (
                (lambda title, lang=None: "")
                if args.title_match == "ignore"
                else TITLE_FNS.get(args.title_match, similar_title_match)
            )
            author_fn = AUTHOR_FNS.get(args.author_match, similar_authors_match)
            hashes: dict = defaultdict(set)
            for book_id in a_db.all_ids():
                lang = (
                    _book_languages(a_db, book_id) if args.include_languages else None
                )
                title_hash = title_fn(_book_title(a_db, book_id), lang)
                authors = _book_authors(a_db, book_id)
                if not authors and args.title_match != "ignore":
                    hashes[title_hash].add(book_id)
                for author in authors:
                    ahash, rev = author_fn(author)
                    hashes[title_hash + ahash].add(book_id)
                    if rev:
                        hashes[title_hash + rev].add(book_id)
            return hashes

        local_hashes = _hash_map(db)
        target_hashes = _hash_map(against)
        for key in sorted(set(local_hashes) & set(target_hashes)):
            for book_id in sorted(local_hashes[key]):
                for target_id in sorted(target_hashes[key]):
                    matched += 1
                    print(
                        f"  #{book_id} {_book_title(db, book_id)} == "
                        f"target #{target_id} {_book_title(against, target_id)}"
                    )
    print(f"summary: {matched} cross-library match(es)")
    return 0


def _parse_search_args(argv):
    parser = argparse.ArgumentParser(prog="find_duplicates search")
    parser.add_argument(
        "--type", default="titleauthor", choices=("titleauthor", "binary", "identifier")
    )
    parser.add_argument("--title-match", default="identical", choices=match_choices())
    parser.add_argument("--author-match", default="identical", choices=match_choices())
    parser.add_argument("--identifier-type", default=DEFAULT_IDENTIFIER_TYPE)
    parser.add_argument("--soundex-title", type=int, default=DEFAULT_TITLE_SOUNDEX)
    parser.add_argument("--soundex-author", type=int, default=DEFAULT_AUTHOR_SOUNDEX)
    parser.add_argument("--include-languages", action="store_true")
    parser.add_argument("--ids", default=None)
    parser.add_argument("--search", default=None)
    parser.add_argument("--sort", default="title", choices=("title", "count"))
    parser.add_argument("--format", default=None)
    parser.add_argument("--against", default=None)
    args, _unknown = parser.parse_known_args(argv)
    return args


def match_choices():
    return MATCHERS


def _library_config(context):
    config = context.load_config()
    key = str(Path(context.db_path).resolve())
    lib = config.setdefault("libraries", {}).setdefault(
        key, {"bookExemptions": [], "authorExemptions": []}
    )
    lib.setdefault("bookExemptions", [])
    lib.setdefault("authorExemptions", [])
    return config, lib


def exempt(context, argv: list[str]) -> int:
    """Record not-duplicate pairs (upstream's mark-as-exempt, stored per
    library in the plugin config)."""
    parser = argparse.ArgumentParser(prog="find_duplicates exempt")
    parser.add_argument(
        "--books", default=None, help="comma-separated book ids of one exempt set"
    )
    parser.add_argument(
        "--authors", default=None, help="comma-separated author names of one exempt set"
    )
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--remove", type=int, default=None, metavar="INDEX")
    parser.add_argument("--clear", action="store_true")
    args, _unknown = parser.parse_known_args(argv)
    config, lib = _library_config(context)
    if args.list or (
        args.books is None
        and args.authors is None
        and args.remove is None
        and not args.clear
    ):
        print("book exempt set(s):")
        for i, entry in enumerate(lib["bookExemptions"]):
            print(f"  [{i}] {', '.join('#' + str(b) for b in entry)}")
        print("author exempt set(s):")
        for i, entry in enumerate(lib["authorExemptions"]):
            print(f"  [{i}] {entry}")
        return 0
    if args.clear:
        lib["bookExemptions"] = []
        lib["authorExemptions"] = []
        context.save_config(config)
        print("exemptions cleared for this library")
        return 0
    if args.remove is not None:
        removed = False
        for key in ("bookExemptions", "authorExemptions"):
            if 0 <= args.remove < len(lib[key]):
                del lib[key][args.remove]
                removed = True
                break
        context.save_config(config)
        print(
            f"exempt set [{args.remove}] removed"
            if removed
            else f"no exempt set [{args.remove}]"
        )
        return 0 if removed else 1
    if args.books:
        entry = _parse_ids(args.books)
        if len(entry) < 2:
            print("ERROR: an exempt set needs at least two book ids", file=sys.stderr)
            return 2
        lib["bookExemptions"].append(entry)
    elif args.authors:
        entry = [a.strip() for a in args.authors.split(",") if a.strip()]
        if len(entry) < 2:
            print(
                "ERROR: an exempt set needs at least two author names",
                file=sys.stderr,
            )
            return 2
        lib["authorExemptions"].append(entry)
    context.save_config(config)
    print(f"exempt set recorded ({len(entry)} member(s))")
    return 0


# ----------------------------------------------------------------- actions

MERGEABLE_FIELDS = (
    "authors",
    "tags",
    "languages",
    "identifiers",
    "rating",
    "pubdate",
    "publisher",
    "comments",
)
#: calibre's merge keeps the keeper's title and series by default; the
#: ported default field set is everything else, fill-blanks plus unions.


def _book_row(db, book_id):
    return db.get_book(book_id, include_comments=True)


def _plan_merge(context, keeper, sources, fields):
    """The merge plan: (actions, plan_lines, file_copies).

    File copies happen outside the batch (files are not transactional);
    the actions cover the row-level mutations in one transaction."""
    db = context.db
    keeper_row = _book_row(db, keeper)
    keeper_formats = set(db.get_formats(keeper).keys())
    root = Path(context.db_path).parent
    keeper_dir = root / keeper_row["path"]
    actions: list = []
    lines: list[str] = [
        f"merge: keeper #{keeper} {keeper_row['title']!r}; "
        f"sources: {', '.join('#' + str(s) for s in sources)}"
    ]
    copies: list[tuple[Path, Path]] = []
    for source in sources:
        source_row = _book_row(db, source)
        if source_row is None:
            lines.append(f"  #{source}: MISSING BOOK, skipped")
            continue
        lines.append(f"  source #{source} {source_row['title']!r}:")
        source_formats = db.get_formats(source)
        for fmt, detail in source_formats.items():
            if fmt in keeper_formats:
                lines.append(f"    {fmt}: keeper already carries it, format stays")
                continue
            src_path = Path(detail["path"])
            if not src_path.exists():
                lines.append(f"    {fmt}: FILE MISSING ({src_path}), skipped")
                continue
            stem = f"merge{source}"
            size = src_path.stat().st_size
            dest = keeper_dir / f"{stem}.{fmt.lower()}"
            counter = 2
            while dest.exists():
                dest = keeper_dir / f"{stem}-{counter}.{fmt.lower()}"
                counter += 1
            copies.append((src_path, dest))
            actions.append(context.plan.plan_add_format(keeper, fmt, dest.stem, size))
            lines.append(
                f"    {fmt}: copy {src_path.name} -> {dest.name} "
                f"({size} bytes), register on keeper"
            )
            keeper_formats.add(fmt)
        for field in fields:
            keeper_value = keeper_row.get(field)
            source_value = source_row.get(field)
            if field in ("authors", "tags", "languages"):
                merged = list(
                    dict.fromkeys((keeper_value or []) + (source_value or []))
                )
                if merged != (keeper_value or []):
                    actions.append(_field_action(context, keeper, field, merged))
                    lines.append(f"    {field}: union -> {merged}")
            elif field == "identifiers":
                keep_ids = db.get_identifiers(keeper)
                src_ids = db.get_identifiers(source)
                for id_type, value in src_ids.items():
                    if id_type not in keep_ids:
                        actions.append(
                            context.plan.plan_identifier(keeper, id_type, value)
                        )
                        lines.append(f"    identifier {id_type}: adopt {value}")
                    elif keep_ids[id_type] != value:
                        lines.append(
                            f"    identifier {id_type}: CONFLICT "
                            f"({keep_ids[id_type]} vs {value}), keeper wins"
                        )
            elif not keeper_value and source_value:
                actions.append(_field_action(context, keeper, field, source_value))
                lines.append(f"    {field}: fill from source -> {source_value!r}")
        actions.append(context.plan.plan_remove_book(source))
        lines.append(f"    row: remove #{source} (the merge absorbs it)")
    return actions, lines, copies


def _field_action(context, book_id, field, value):
    """The writeops action for one mergeable field (the fill/union shape)."""
    import sys as _sys

    w = context.plan
    if field == "authors":
        return w.plan_set_authors(book_id, value)
    if field == "tags":
        return w.plan_add_tags(book_id, value)
    if field == "languages":
        return w.plan_set_languages(book_id, value)
    if field == "rating":
        return w.plan_set_rating(book_id, value)
    if field == "pubdate":
        return w.plan_set_pubdate(book_id, value)
    if field == "publisher":
        return w.plan_set_publisher(book_id, value)
    if field == "comments":
        return w.plan_set_comments(book_id, value)
    print(f"ERROR: field {field!r} is not mergeable", file=_sys.stderr)
    raise SystemExit(2)


def merge(context, argv: list[str]) -> int:
    """Calibre's merge behind the gates: formats move (files copied),
    chosen fields fill/union into the keeper, absorbed rows are removed.
    One transaction for the row mutations; the dry run is the prompt."""
    import argparse

    parser = argparse.ArgumentParser(prog="find_duplicates merge")
    parser.add_argument("--keeper", type=int, required=True)
    parser.add_argument("--ids", required=True, help="the absorbed book id(s)")
    parser.add_argument("--fields", default=",".join(MERGEABLE_FIELDS))
    args, _unknown = parser.parse_known_args(argv)
    fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    sources = [s for s in _parse_ids(args.ids) if s != args.keeper]
    if not sources:
        print(
            "ERROR: merge needs at least one source id (different from --keeper)",
            file=sys.stderr,
        )
        return 2
    actions, lines, copies = _plan_merge(context, args.keeper, sources, fields)
    lines.insert(
        0,
        "DRY RUN: merge plan (--apply executes)"
        if not context.can_write
        else "merge plan:",
    )
    for line in lines:
        print(line)
    if not context.can_write:
        print(f"plan: {len(actions)} action(s) in one transaction")
        return 0
    for src, dest in copies:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)
    code = context.write.apply(context.db_path, actions)
    print(
        f"merged {len(sources)} source book(s) into #{args.keeper}: "
        f"{len(actions)} action(s), {len(copies)} file copy(ies)"
    )
    return code


def remove_duplicate_formats(context, argv: list[str]) -> int:
    """Upstream's binary auto-removal: within the id set, keep the
    earliest-mtime copy of each byte-identical format, remove the rest."""
    import argparse

    parser = argparse.ArgumentParser(prog="find_duplicates remove-duplicate-formats")
    parser.add_argument("--ids", required=True)
    parser.add_argument("--format", default=None, help="restrict to one format")
    args, _unknown = parser.parse_known_args(argv)
    ids = _parse_ids(args.ids)
    entries: list[tuple[int, str, Path, float]] = []
    for book_id in ids:
        for fmt, path in _formats_of(context, book_id).items():
            if args.format and fmt != args.format:
                continue
            try:
                entries.append((book_id, fmt, path, path.stat().st_mtime))
            except OSError:
                continue
    by_sha: dict = defaultdict(list)
    for book_id, fmt, path, mtime in entries:
        by_sha[_sha_of(path)].append((mtime, book_id, fmt, path))
    actions: list = []
    lines: list[str] = []
    for sha, group in by_sha.items():
        if len(group) < 2:
            continue
        group.sort()
        keep_mtime, keep_book, keep_fmt, _keep_path = group[0]
        for mtime, book_id, fmt, path in group[1:]:
            actions.append(context.plan.plan_remove_format(book_id, fmt))
            lines.append(
                f"  {fmt} of #{book_id} ({path.name}, {datetime.fromtimestamp(mtime).date()})"
                f" duplicates #{keep_book}'s ({sha[:12]}); remove"
            )
    if not lines:
        print("no byte-identical format duplicates in the id set")
        return 0
    if not context.can_write:
        print("DRY RUN: duplicate-format removal plan (--apply executes)")
        for line in lines:
            print(line)
        print(f"plan: {len(actions)} format removal(s)")
        return 0
    code = context.write.apply(context.db_path, actions)
    print(f"removed {len(actions)} duplicate format(s)")
    return code


def delete_books(context, argv: list[str]) -> int:
    """Upstream's Delete key behind the gates: remove the named rows."""
    import argparse

    parser = argparse.ArgumentParser(prog="find_duplicates delete")
    parser.add_argument("--ids", required=True)
    args, _unknown = parser.parse_known_args(argv)
    ids = _parse_ids(args.ids)
    if not ids:
        print("ERROR: delete needs --ids", file=sys.stderr)
        return 2
    db = context.db
    actions = []
    lines = []
    for book_id in ids:
        book = _book_row(db, book_id)
        title = book["title"] if book else "<unknown>"
        actions.append(context.plan.plan_remove_book(book_id))
        lines.append(f"  #{book_id} {title!r}: remove")
    if not context.can_write:
        print("DRY RUN: deletion plan (--apply executes)")
        for line in lines:
            print(line)
        print(f"plan: {len(actions)} book removal(s)")
        return 0
    code = context.write.apply(context.db_path, actions)
    print(f"removed {len(ids)} book(s)")
    return code


# ------------------------------------------------------------- variations

VARIATION_ITEMS = ("authors", "series", "publishers", "tags")


def _unique_names(db, item):
    """Upstream's variation source: the unique names of one field."""
    column = {
        "authors": "authors",
        "series": "series",
        "publishers": "publisher",
        "tags": "tags",
    }[item]
    names: set = set()
    for book_id in db.all_ids():
        book = db.get_book(book_id, include_comments=False)
        value = book.get(column)
        if isinstance(value, list):
            names.update(value)
        elif value:
            names.add(value)
    return sorted(names)


def _variation_hash(name, item, match):
    if match == "similar":
        fns = {
            "authors": similar_authors_match,
            "series": lambda s: (_fuzzy_it(s), None),
            "publishers": lambda s: (_fuzzy_it(s), None),
            "tags": lambda s: (_fuzzy_it(s), None),
        }
        if item == "authors":
            return similar_authors_match(name)[0]
        return fns[item](name)[0]
    if match == "soundex":
        length = DEFAULT_TAGS_SOUNDEX if item == "tags" else DEFAULT_TITLE_SOUNDEX
        source = name
        if item == "authors":
            tokens = list(_get_author_tokens(name))
            source = (tokens[-1] + "".join(tokens[:-1])) if tokens else ""
        return _soundex(_fuzzy_it(source), length)
    # fuzzy
    if item == "authors":
        return fuzzy_authors_match(name)[0]
    tokens = list(_get_title_tokens(name))
    return tokens[0] if tokens else ""


def variations(context, argv: list[str]) -> int:
    """Upstream's variation report: clusters of one field's names that the
    chosen matcher considers the same (the rename verb's supply)."""
    import argparse

    parser = argparse.ArgumentParser(prog="find_duplicates variations")
    parser.add_argument("--item", default="authors", choices=VARIATION_ITEMS)
    parser.add_argument(
        "--match", default="similar", choices=("similar", "soundex", "fuzzy")
    )
    parser.add_argument("--format", default=None)
    args, _unknown = parser.parse_known_args(argv)
    db = context.db
    names = _unique_names(db, args.item)
    clusters: dict = defaultdict(set)
    for name in names:
        clusters[_variation_hash(name, args.item, args.match)].add(name)
    _shrink(clusters)
    import json as _json

    if args.format == "json":
        print(
            _json.dumps(
                {
                    "item": args.item,
                    "match": args.match,
                    "clusters": [sorted(c) for c in clusters.values()],
                },
                indent=1,
                sort_keys=True,
            )
        )
        return 0
    if not clusters:
        print(f"no {args.item} variations under {args.match}")
        return 0
    print(f"variations: {args.item} under {args.match}")
    for i, (key, cluster) in enumerate(sorted(clusters.items()), 1):
        print(f"  cluster {i}: {' | '.join(sorted(cluster))}")
    print(f"summary: {len(clusters)} cluster(s) over {len(names)} name(s)")
    return 0


def rename(context, argv: list[str]) -> int:
    """The entity rename behind the gate (the variations report's action)."""
    import argparse

    parser = argparse.ArgumentParser(prog="find_duplicates rename")
    parser.add_argument(
        "--kind", default="authors", choices=("authors", "series", "publishers", "tags")
    )
    parser.add_argument("--from", dest="from_name", required=True)
    parser.add_argument("--to", dest="to_name", required=True)
    args, _unknown = parser.parse_known_args(argv)
    action = context.plan.plan_rename_entity(args.kind, args.from_name, args.to_name)
    if not context.can_write:
        print("DRY RUN:", action[0])
        return 0
    code = context.write.apply(context.db_path, [action])
    print(f"renamed {args.kind} {args.from_name!r} -> {args.to_name!r}")
    return code


def register(context):
    return {
        "search": search,
        "exempt": exempt,
        "merge": merge,
        "remove-duplicate-formats": remove_duplicate_formats,
        "delete": delete_books,
        "variations": variations,
        "rename": rename,
    }
