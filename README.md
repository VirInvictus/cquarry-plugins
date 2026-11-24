# cquarry-plugins

GPL-3 plugins for the [CalibreQuarry](https://github.com/VirInvictus/CalibreQuarry)
plugin system. This repository holds the proof-of-concept ports that prove the
system: **extract_isbn**, **find_duplicates**, and **quality_check**, each a 1:1
port of the same-named plugin from
[kiwidude68/calibre_plugins](https://github.com/kiwidude68/calibre_plugins)
(Grant Drake's calibre plugin collection, GPL-3).

## The licensing shape

CalibreQuarry (the host) is MIT and never imports a byte of this repository.
These plugins are GPL-3, derived from upstream GPL-3 code with attribution
carried per plugin (see each plugin's README). The import boundary is one-way:
plugins depend on the host's plugin API; the host depends on nothing here.

## Status

Skeleton. The plugin system host ships in CalibreQuarry itself (Phase 21 of its
roadmap); until it does, the manifests in this repository are the live contract
and the code is placeholders. Each plugin directory carries a
`cquarry-plugin.toml` declaring its capabilities and its minimum supported
cquarry and calibrequarry versions.

## Install (once the host ships)

```
cquarry plugin add https://github.com/VirInvictus/cquarry-plugins
```

The host classifies this repository by discovery (three manifests, one per
plugin directory, so a multi-plugin source), reports what it found, and gates
the write-capable plugins behind its verify-and-approve harness.

## Layout

- `extract_isbn/`, `find_duplicates/`, `quality_check/`: one plugin each.
- `docs/crosswalk.md`: the parity ledger; every upstream check, matcher,
  option, and fix mapped to its CLI twin.
- `docs/upstream-sync.md`: dated upstream windows against kiwidude68.

## License

GPL-3.0-only; see [LICENSE](LICENSE). Upstream attribution per plugin in each
plugin's README.
