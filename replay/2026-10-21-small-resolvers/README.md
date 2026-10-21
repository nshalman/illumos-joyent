# Replay with resolvers: release-20260903 to da512a7e2e6

Run 2026-10-21, on the same window and bootstrap as
`../2026-10-21-small`, with features/tooling 1ad185d0f20: the conflict
resolvers (`resolve.py`) and the manifest sync (`manifest.py`) on.

All 15 master commits were reproduced tree for tree, and the replayed
features at da512a7e2e6 again have the same trees as phase 1's split,
for all 78.

## Against the first run

| Master merge | First run: person needed | With resolvers |
| --- | --- | --- |
| eab31c4851f | smartos-test (header tests) | Same: still a person |
| a2098682c51 | integration Makefile conflict | makefile-list resolver |
| a2098682c51 | integration-manifest zoneinfo | Manifest sync, but see below |
| 0c4fef4daef | integration-manifest `userattr.1` | Manifest sync |
| 3d97d1d7245 | zones-tools copyright | copyright resolver |
| da512a7e2e6 | brand-ops copyright | copyright resolver |
| da512a7e2e6 | rtld-sgs copyright | copyright resolver |
| da512a7e2e6 | integration-manifest `close_range.2` | Manifest sync, leaving out the os-tests files as master did |

Seven of the eight now need no person. The one left is smartos-test,
which no mechanical rule could have known.

## The zoneinfo lines: the tool right, master wrong

At a2098682c51 gate turned four zoneinfo hard links (CST6CDT, EST5EDT,
MST7MDT, PST8PDT) into files. The manifest sync wrote them as
`f usr/share/lib/zoneinfo/CST6CDT 0644 root bin`. Master's merge wrote
`f usr/share/lib/zoneinfo/CST6CDT`, with no mode, owner or group, and
four commits later eb7e560a400 ("manifest: add zoneinfo permissions")
fixed them to `0644 root bin`.

Replay has to match master at every step, so it routed master's bare
lines back into integration-manifest at a2098682c51
("Resolve as master did in a2098682c51"), and eb7e560a400 then routed
as an ordinary joyent commit. Had the tool been running, that bug and
its fix would not have happened.

## Caveats

- Master's merges still stand in for the person, here only for
  smartos-test.
- The window has no upstream landing; upstream detection is untested.
- No builds were run.
