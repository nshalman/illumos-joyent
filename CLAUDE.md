# Notes for agents working on this repo

This repo generates a branch; the branch is the product, and the repo is
expected to be thrown away eventually.  Humans read `README.md`,
`branch-log.txt` and `FINDINGS.md`; this file is for working on the
tooling itself.

## Ground rules

- The acceptance check is that the generated branch's tree is
  byte-identical to `JOYENT` (`build.py --branch` checks and refuses
  otherwise).  Bugs are carried, not fixed, in the generated commits.
- Changes to classification must not change the tree; when a change is
  meant to be purely structural, compare `data/assign.json` before and
  after (0 paths changed) and the generated messages against the
  branch's.
- Record bugs and decisions in `FINDINGS.md`, as a current-state
  document, not a log.  Verify every bug against the source before
  recording it; review agents have been wrong (e.g. "no cross-zone
  leak" in B2).
- Rebuild the branch after changing classification, messages or
  `mailmap`, so `branch-log.txt` stays current, and commit it with the
  change.

## Traps

- Nahum's git uses difftastic as its external diff: always pass
  `--no-ext-diff` to `git diff`/`git show`/`git log -p`.
- zsh treats `$var:u` as a modifier: write `"${sha}:path"`.
- Path-limited `git log -- path` simplifies history and drops joyent
  commits on merged side branches: use `--full-history`.
- Plain `git blame` over-credits joyent (on a merge it tries the joyent
  parent first): count only lines that differ from BASE.
- Python dict literals silently drop repeated keys; classification
  tables are lists of pairs for that reason.
- macOS has no `timeout(1)`.
- Use the scratchpad, not `/tmp`, for temporary files.

## Files

| File | Role |
|------|------|
| `collect.sh` | Gathers the delta, commit list, attribution and residue list into `data/` |
| `blame-file.sh` | Per-file diff-restricted blame (called by `collect.sh`) |
| `deletions.py` | Credits commits for lines they removed that are still gone (called by `collect.sh`) |
| `copyright_only.py` | Lists files that differ from upstream only in copyright/comment noise (called by `collect.sh`) |
| `omnios.py` | Attribution for the OmniOS-based lx commits (called by `collect.sh`) |
| `classify.py` | Assigns every delta path to a bucket |
| `overrides.py` | Hand placement for files the path rules don't cover |
| `buckets.py` | Commit order, subjects and descriptions; `FILE_NOTES` for undocumented divergences |
| `mailmap` | Identity fixes for co-author credit (git-mailmap format) |
| `build.py` | Writes commit messages and builds the branch |
| `report.py` | Reports over the classification (`./report.py help`) |
| `merge_lines.py` | Shows a file's lines written during merge resolution, or by one commit |

## How files are placed

In order of precedence (see the header of `classify.py`):

1. **Copyright residue.**  Files whose diff is only copyright lines,
   blank comment lines or whitespace go to `copyright-residue`.
2. **Overrides** (`overrides.py`): hand placement for generic files that
   several features touch, decided with `./report.py why <path>`.
3. **Path rules** (`RULES` in `classify.py`), first match wins.
4. **Hub files.**  A Makefile, mapfile or package manifest that lives in
   one feature's directory follows that feature rather than
   `integration`; hubs shared between features stay in `integration`.
5. **Ticket vote** for anything left: each ticket learns the bucket
   where most of its path-placed lines live (sweep tickets spread across
   buckets stay neutral), and a file goes where its lines' tickets
   point.  If the biggest share belongs to an unplaced ticket, the file
   goes to `misc`.

## lx on top of OmniOS

The lx files that OmniOS also carries are committed first exactly as
OmniOS has them (`lx-omnios`, pinned by `OMNIOS` in `data/refs`), and
the `lx` commit then brings them to joyent's versions and adds the lx
files OmniOS lacks.  So the `lx` commit is precisely how illumos-joyent's
lx differs from OmniOS's.  Credit for `lx-omnios` comes from blaming
OmniOS's versions; credit for those files in `lx` comes from blaming
joyent's lines that differ from OmniOS.  Generic kernel hooks for lx
stay in the brand-* commits.

## Commit messages

Each commit message has the bucket's description, its feature tickets
with subjects, the IDs of fix tickets, any `FILE_NOTES`, and a
`Co-authored-by` trailer for everyone whose surviving or removed lines
are in the commit.  The `integration` message also groups its changes
by the feature commit each ticket belongs to.  Commits are authored by
Claude and committed by whoever runs the build.

Co-author identities are collapsed when they share a name or an email,
credited under the newest one, then corrected by `mailmap`.  Bot
identities (`BOTS` in `build.py`) are not credited.

## Attribution

`collect.sh` blames `BASE..JOYENT` but counts only lines that are `+`
relative to BASE.  Plain blame over-credits joyent: on a merge, blame
tries the first (joyent) parent first, so a line identical in both
parents is credited to the joyent commit.  For example, KPTI (OS-6547)
was upstreamed, yet plain blame credits it with ~1,800 lines; restricted
to real differences it is ~22.

Blame cannot see removed lines, so `deletions.py` matches each joyent
commit's removed lines against the lines still missing from `JOYENT`.
It uses `git log --full-history`, because path-limited log otherwise
prunes joyent commits on merged side branches.  The match is by text,
so it over-counts repeated removals; it is used only for author credit.

Two by-products of attribution are bug leads (see `FINDINGS.md`):

- `+` lines blamed to `BOUNDARY` are lines joyent carries from an
  *older* upstream version (`./report.py boundary`).
- `+` lines blamed to merge commits were written during conflict
  resolution (`./report.py merge-lines`, `./merge_lines.py <path>`).
