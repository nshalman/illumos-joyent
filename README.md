# illumos-joyent restructure

Tooling to re-express illumos-joyent `master` as a series of curated,
ticket-annotated commits on top of the illumos-gate commit it last merged,
such that the resulting tree is identical to `master`.

Each commit carries the *final* state of a group of files (a "bucket"),
not the history that produced it.  Whole files go to exactly one bucket.
Shared hub files that many features touch (`manifest`, top-level and
kernel Makefiles, package manifests, exception lists, driver tables) land
in a final `integration` commit.

## Running

    ./collect.sh            # ~30s; writes data/ (not committed)
    ./classify.py           # bucket summary; writes data/assign.json
    ./report.py ...         # see `./report.py help`

Environment: `ILLUMOS` (clone path, default `~/Workspace/illumos`),
`JOYENT` (ref, default `master`), `BASE` (default: upstream parent of the
newest `[illumos-gate merge]` on `JOYENT`).

## How files are placed

1. **Path rules** (`RULES` in `classify.py`), first match wins.
2. **Added hub files** (a new Makefile/mapfile/manifest in a feature's
   own directory) follow their feature rather than `integration`.
3. **Overrides** (`overrides.py`): hand placement for generic files that
   several features touch, decided from `./report.py why <path>`.
4. **Ticket vote** for anything left: each ticket learns the bucket where
   most of its path-placed lines live (sweep tickets that spread across
   buckets stay neutral), and a file goes where its lines' tickets point.
   If the biggest share belongs to an unplaced ticket the file goes to
   `misc` for review instead.

## Attribution: why diff-restricted blame

`collect.sh` blames `BASE..JOYENT` but counts only lines that are `+`
relative to `BASE`.  Plain blame over-credits joyent: on a merge, blame
tries the first (joyent) parent first, so a line identical in both
parents is credited to the joyent commit.  Example: KPTI (OS-6547) was
upstreamed, yet plain blame credits it with ~1,800 lines; restricted to
real differences it is ~22.

Two by-products are bug leads (see `FINDINGS.md`):

- `+` lines blamed to `BOUNDARY` are lines joyent carries from an
  *older* upstream version: possible stale merges.
- `+` lines blamed to merge commits were written during conflict
  resolution: possible mismerges.

Deleted lines are not attributed (blame cannot see them); files whose
delta is only deletions show up with no tickets.
