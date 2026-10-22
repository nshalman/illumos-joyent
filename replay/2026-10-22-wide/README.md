# Replay: release-20260416 to da512a7e2e6

Run 2026-10-22 on nshalman-builds, with features/tooling 2cd003134cc,
in a single pass. All 73 master commits (60 gate merges, 13 joyent
commits) were reproduced tree for tree. Every release forked in the
window can be rebuilt from gate, gate backports and the features:
release-20260430 and release-20260514 by `release.py`, the other nine
because each equals a master commit the replay reproduced.

## Setup

- Bootstrap: the phase 1 pipeline (meta/restructure 7ced730) rerun with
  JOYENT=06ea1eb6c40 (release-20260416's branch point), gate base
  ec14ab0836c, and OMNIOS=95fc2f0bab5, the last commit on omniosce/master's
  first-parent line before that date. It gave the same 78 feature names
  with no override changes, and their merge equals 06ea1eb6c40.
- `decide`: the placement decisions a person made where the rules could
  not, each with its reason.
- `steps.txt`, `steps.jsonl`: the tool's output, one record per step.
  `summary.txt`: the tallies below.

## Results

| | Count |
| --- | --- |
| Gate merges needing no person | 47 of 60 |
| Conflict regions resolved by the copyright resolver | 46 |
| Resolved by the Makefile list resolver | 1 |
| Gate merges where the manifest sync changed the manifest | 16 |
| Joyent commits routed with no help | 10 of 13 |
| Joyent commits needing a recorded decision | 3 (18158, OS-8746, OS-8756) |

The 13 gate merges that needed a person:

| Master merge | Feature(s) | What it was |
| --- | --- | --- |
| ea4f3c70350 | fm-topo, lx | 17974 (64-bit fmtopo) restructured the ipmi Makefile and Targetdirs |
| a3358a59295, a2414f708f5 | ptools | ps.1 converted to mdoc; joyent's copyright line reworded |
| 9418decce6f | integration, smartos-test | dladm tests moved into dladm/; PROG list and runfile paths |
| 57dd2952050 | lx and others | 17689 (posix_spawn) in fork.c and exec.c, including removing an unused variable |
| f84c70cade9 | integration-checks | a conflict, not analysed further |
| 0821a720ccf | dtrace, integration-pkg, zone-kernel, zone-memory | master's return to gate's os-tests runfile, plus conflicts in sysconfig.c and vm_usage.c |
| feb8a55d8d3 | brand-net, tcp-connstat | a conflict, not analysed further |
| eab31c4851f | smartos-test | 18295: header tests run differently; no conflict, semantic |
| a2098682c51 | integration-manifest | master's own mistake (zoneinfo lines without attributes, fixed in eb7e560a400); the sync was right |
| 87e8f1919ac | dtrace, upstream-os-8746 | master's own mistake: kept a stale os-tests runfile, fixed six weeks later in 0821a720ccf |
| bd38a94beda | integration-manifest | the sync added opt/libc-tests/tests/posix_spawn, which master does not list (gap below) |
| fe81ae281e2 | integration-manifest | master corrected cxgbe firmware modes from 0666 to 0644 |

## Upstream landings

- 18158 (bhyve PQOS): committed on master (2b2a7a8e922) before gate landed
  the same patch (59853c12bd). Placed by decision in a new feature
  upstream-18158, which retired at 3ec3681e34d when gate had all of it.
- OS-8746's fixes to gate's test runfiles: upstreamed as 18163.
  upstream-os-8746 retired at 87e8f1919ac. Master's stale runfile brought
  it back for six weeks; it retired again at dd34022052d. One OS-8746
  commit routed into zfs-tests emptied the same way.

## Against phase 1

72 of the 78 replayed features at da512a7e2e6 have the same trees as
phase 1's split made there directly. The six that differ hold the same
lines in different places:

- `zhyve.c` (294 lines) and a Makefile line: OS-8737 changed a file that
  zone-brands owned at the start point, so replay kept it there; phase 1,
  voting by ticket at the end point, gives it to bhyve.
- An OmniOS copyright line OS-8748 added in exec.c and exit.c: phase 1
  copies it into every feature touching the file (brand-process, lx,
  ptools, zone-kernel); replay gives an ownerless copyright line only to
  the features whose file changed.

## Known gaps

- The manifest sync treats a package as shipped when any of its files or
  links is listed. libc-tests delivers a few test locale files that
  SmartOS ships, so its /opt/libc-tests directories looked shipped too
  (bd38a94beda). Narrowing the rule to the package's files under the
  same top directory would fix it; not done yet.
- Lines git can merge only together, such as both sides of a deleted gate
  line, end up in each of the features involved until a person
  reassigns them.
- Master's merges stand in for the person; no builds were run, since
  every step equals a master commit that was built.
