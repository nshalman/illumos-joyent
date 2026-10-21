# Replay: release-20260903 to da512a7e2e6

Run 2026-10-21. Every one of the 15 master commits was reproduced tree
for tree, and the replayed features at the end have the same trees as
the 78 phase 1 features computed directly at da512a7e2e6.

## Setup

- Bootstrap: the phase 1 pipeline (meta/restructure f36dd83) rerun with
  JOYENT=feb8a55d8d3 (release-20260903's branch point), gate base
  a330f55b6c6, and OMNIOS=441c91326c0. That was meant to be the last
  omniosce/master commit before feb8a55d8d3, but `rev-list --before`
  without `--first-parent` picked a commit from a merged side branch.
  The first-parent pick, acb45c42696, has the same lx tree, so the
  results do not change; later runs use `--first-parent`. It produced the same 78 feature names as today's split,
  with no override changes, and their merge equals feb8a55d8d3.
- Tools: features/tooling 133822d2ddb (`feature-tools/replay.py`).
- Command:

      replay.py --repo <clone> --gate a330f55b6c6 --from feb8a55d8d3 \
          --to da512a7e2e6 --gate-ref refs/remotes/illumos/master

- `steps.txt` is the tool's output; `steps.jsonl` has one record per
  step.

## What a person would have done

13 gate merges and 2 joyent commits. Both joyent commits were routed
without help: the manifest change to integration-manifest, and the
ipmgmtd fix (Andy Fiddaman) to lx, the only feature touching that file.
Gate merges needed eight pieces of work beyond a plain rebase, all taken
from master's own merges:

| Master merge | Feature | Rebase conflict | What master did | Could tooling do it |
| --- | --- | --- | --- | --- |
| eab31c4851f | smartos-test | no | Ran header tests with `log_test .../bin/headertest`, following gate's 18295 | No: semantic, found only by running the tests |
| a2098682c51 | integration | yes, libc-tests Makefile | Added `aio_cancel` to `PROGS` | Yes: Makefile list resolver |
| a2098682c51 | integration-manifest | no | zoneinfo `h` entries became `f` | Yes: manifest sync from gate's pkg manifests |
| 0c4fef4daef | integration-manifest | no | Added `userattr.1` | Yes: manifest sync |
| 3d97d1d7245 | zones-tools | yes, zonestatd.c | Took gate's new copyright line | Yes: copyright resolver |
| da512a7e2e6 | brand-ops | yes, corenote.c and .msg | Oxide copyright 2024 to 2026 | Yes: copyright resolver |
| da512a7e2e6 | rtld-sgs | yes, same files | Same copyright change (replicated hunk) | Yes: copyright resolver |
| da512a7e2e6 | integration-manifest | no | Added `close_range.2` | Yes: manifest sync |

Seven of the eight are mechanical. The four rebase conflicts were all
in copyright lines or a Makefile list. The three manifest updates
raised no conflict at all; without a resolver they would surface only
when a build's manifest check fails. The one real judgment call,
smartos-test, raised no conflict either.

Nothing was held back from integration, no commit became empty, and no
change was left unrouted.

## Caveats

- Master's merges stood in for the person. A resolver that chose
  differently, even correctly, would show as a mismatch.
- The window has no upstream landing, so upstream detection is untested.
- No builds were run; each step equals a master commit that was built.
