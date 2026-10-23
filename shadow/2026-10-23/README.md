# Shadow run: da512a7e2e6 to 37d708fdd3c (2026-10-23)

The first shadow-mode run: `replay.py` (features/tooling 28661567948) over
master's 8 new first-parent commits since da512a7e2e6, starting from the 78
phase 1 features on the fork (`features/*`, without `features/tooling`). All 8
were reproduced tree for tree. The updated features are on the build host
under `refs/shadow/` and have not been pushed.

| Master commit | Kind | Result |
| --- | --- | --- |
| 1b35490ea37 OS-8771 | joyent | routed to lx |
| ccbc1e1e426 | gate merge | no person needed |
| 7daf51d797c | gate merge | manifest sync added 7 paths; master also shipped gate's new efi driver package (3 lines), a person's choice the sync rightly leaves alone (`divergence/`) |
| eca1910b093 | gate merge | no person needed |
| 4896e3cfc6b 8391 | joyent | a fix carried ahead of gate; new feature upstream-8391, by decision |
| 516afaab248 OS-8770 | joyent | an lx fix adding a flag to generic sockfs code; to lx by a commit-scoped decision, with the part next to datafilt's lines routed to datafilt |
| badf02468d2 OS-8773 | joyent | routed to lx |
| 37d708fdd3c | gate merge | no person needed |

Two decisions were added to `../../decisions` (the decisions file, now kept
at the top of this branch): `upstream-8391` for the mr_sas fix, and
`commit:516afaab248 lx`.

The new commands were also run on real data against a simulated master on
the build host: `dispatch.py dry-run` and `land --write` for OS-8771 (9 s);
`intake.py --write` to gate 3581f14f537 (35.6 s), whose merge has exactly the
tree of master's real merge ccbc1e1e426; `release.py cut`; and
`release.py check` of release-20261023 against master: ok.
