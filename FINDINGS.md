# Findings

What restructuring illumos-joyent `master` has turned up: bugs,
deliberate divergences from illumos-gate, cleanup candidates, what was
reviewed, and the decisions behind the restructured branch.

Nothing here has been fixed.  The restructured branch is byte-identical
to `master` by design, so it carries every bug listed below.

## Status

- Branch `joyent-restructure` (in the illumos clone): 82 commits on
  479a4a914dc, the illumos-gate commit merged into `master`
  da512a7e2e6.  Its tree is identical to `master`'s.
- Delta: 1,778 paths (852 added, 915 modified, 11 deleted, counting a
  rename as a delete plus an add), from 4,041 non-merge joyent commits.
- Line numbers below are as of da512a7e2e6.

## Independent feature branches

`features.py` builds 80 `features/*` branches, each based directly on
illumos-gate and holding only that feature's hunks (shared files carry
just their share, plus copies of the file's copyright hunks), and
`features-merged`, an octopus merge of all 80.  The branches merge with
no conflicts, and the merged tree equals `master`.

Each hunk goes to the feature that wrote most of its lines, then
`hunks.py` moves hunks for compilability:

- **Function coherence.**  Hunks in the same C function body, or within
  3 lines of each other outside functions, go together.  Splitting
  interleaved hunks across features left uncompilable files (poll.c,
  timer.c).  This moved 158 hunks.
- **Includes.**  A hunk that only adds or removes `#include` lines goes
  to the feature owning most of the file's other changes.  For example,
  `#include <sys/brand.h>` in signalfd.c was written by an lx ticket
  but is needed by brand-events.
- **Makefile lists.**  Hunks of bare list entries (SUBDIRS, CHKHDRS)
  are split into one line per entry.  Each entry goes to the feature
  owning that subdirectory or file, e.g. `libresolv2_joy` to resolver,
  `zfscache` to zfs-zone-io.  An entry with no owner keeps the vote of
  the hunk it came from.
- **Hand overrides** (`HUNK_OVERRIDES` in `overrides.py`).

After these passes, about 0.6% of changed lines sit in a hunk owned by
another feature.  This undercounts, because the passes do not keep the
attribution of the hunks they move.

`deps.py` (static, identifiers only) reports that 49 branches depend on
no other feature.  The rest form one 14-feature cycle (brand-* hooks,
lx, zone-kernel, zones-admin, zones-tools, inotify, ptools, zfd,
zfs-zvol), three cyclic pairs (datalink/vnd, boot/dboot,
zfs-zio/zfs-zone-io), and features that depend on those.  Many edges
come from foundational definitions sitting in whichever feature's
ticket wrote them (e.g. `zone_did`, `zone_get_nroot`, the zone VFS
kstats).  Re-homing those should break much of the cycle.

## Compile checks

Run on the build host by `buildcheck.sh` in a private ZFS dataset, with
its own `ROOT`, so smartos-live's shared proto, which already holds
illumos-joyent's headers, cannot hide a missing dependency.

- **Plain illumos-gate needs 17 entries of build plumbing to build in a
  smartos-live environment** (`baseline.txt`, each with its reason):
  - OpenSSL linkage: the five `sunw_` renames (proto.strap has no
    generic libcrypto.so).
  - Native-tool include and library paths: smatch, ctf/dwarf, mandoc,
    vtfontcvt.
  - Other environment glue: `-lnetsnmphelpers`, PERL_VERSION 5.12,
    mkdemo run via `$(PERL)`, and javac `-Xlint:-path`.
  - Components SmartOS does not build: hal, latencytop, the python
    modules, and IPS licensing (`stage-licenses` needs pkgfmt).
  With those, a clean non-DEBUG nightly is clean (no errors, no
  warnings) in about 10.8 minutes; a no-op incremental takes 3.3.
- **A 34-job nightly needs more than 2,000 LWPs.**  The zone's
  sdc:max_lwps=2000 made builds fail intermittently with
  `fork failed: Resource temporarily unavailable` (peak measured: 1,938
  LWPs and 1,649 processes).  Nahum raised it to 20000 on 2026-10-15;
  a build then peaked at 1,831 LWPs and 1,718 processes.
- Upstream inconsistency: `bldenv` does not accept `-L`, although its
  comment says its getopts must match nightly's; smartos-live passes
  `-L`, so every build prints `-L: unknown option` (harmless).
- With postfix disabled, nightly's `-m` leaves a hung sendmail/postdrop
  pair per build; the experiment builds drop `-m`.
- **Each feature alone on the gate baseline:** 37 of 80 branches build
  cleanly (`buildcheck-results.txt`).  `buildfail.py` names the feature
  defining what each failure was missing.
  - The first sweep passed 35.  Fixing misplaced hunks (include lines,
    Makefile list entries, corenote.msg's brand names, tmpfs's own
    changes sitting in hyprlofs, tools/man) changed 31 branches.
    hyprlofs and resolver now pass.  Several others now get further
    and reach real dependencies (brand-exec, vnd, zfs-arc, tmpfs), so
    their error counts rose.
  - Most remaining failures are the dependency cycle above.
  - Known cross-feature references:
    - bunyan and vnd include `lib/Makefile.usdt`, which sits in
      integration.
    - vnd's ipf hooks use `hook4_vnd_*` declarations that were grouped
      into ipf-cfw's hunk of ip_fil_solaris.c.
    - overlay-svp's mdb `refhash.c` is not in the genunix module's
      file list on that branch.
    - The smartos-test and zfs-tests runfiles list other features'
      tests.

## Bugs

Every entry was confirmed by reading the code on `master`.  "Origin" is
the commit that introduced it.  None of these exist upstream.

Severity: HIGH = data corruption, a security boundary, or unprivileged
resource exhaustion; MED = wrong results or a failed operation; LOW =
edge case or cosmetic behavior.  `?` = the code is wrong but impact has
not been demonstrated.

| ID | Sev | Where | Origin | Summary |
|----|-----|-------|--------|---------|
| B1 | HIGH | uts/common/fs/tmpfs/tmp_vnops.c:924-925 | 08280dbb7d3 OS-5539 (2016) | xattr-dir error path cleans up the parent node |
| B11 | HIGH | uts/common/os/timer.c:622-627 | merge da28b8a59d9 (12789) | timer_setup() leaks an itimer_t per call at timer_max |
| B2 | MED? | uts/common/vm/vm_usage.c:1948-1950, 2057-2059, 2072-2083 | 2f904f0710c OS-750 (2012) | uninitialized req_zone_id; plausible cross-zone disclosure |
| B12 | MED? | uts/common/os/pid.c:571-582 | fac1ecb479c vs upstream 17458 | sprunprlock() lacks 17458's SIGKILL handling |
| B3 | MED | lib/fm/topo/modules/common/ipmi/ipmi_enum.c:837-838 | 4a99ae16188 OS-6527 (2017) | inet_ntop given sizeof (char *) |
| B4 | MED | uts/common/fs/zfs/zfs_ioctl.c:2221-2223, 2433-2435 | e4c080eef3a OS-1048 (2012) | `(error = get_nvlist(...) != 0)` precedence |
| B5 | LOW | uts/common/brand/lx/syscall/lx_fcntl.c:302 | merge 28a6b3a036f (2024) | Linux F_SETFD can set FD_CLOFORK |
| B6 | LOW | uts/common/exec/elf/elf.c:2129 | 685e6567cd5 (2021) | core-file .debug_* output loop off by one |
| B7 | LOW | lib/libproc/common/Psymtab.c:801 | 092a4fbb8cf OS-4573 (2015) | Pconvert_file_ctf() always returns NULL |
| B8 | LOW | cmd/zfs/zfs_main.c:1285-1336 | 954e970e290 OS-604 | `zfs destroy` prints errors twice without -F |
| B9 | LOW | cmd/cron/crontab.c:77-78, 189; man1/crontab.1:67, 77, 92 | merge 82a64156a05 | usage and man page advertise `-g` alone; code requires `-l` |
| B10 | LOW | uts/common/fs/zfs/zfs_zone.c:1181-1184 | 4851e24d85b OS-6540 (2018) | no txg delay for a zone being torn down |
| B13 | LOW | cmd/mdb/common/modules/mdb_ks/mdb_ks.c:1900-1968 | 1cc6f4c0fcc OS-7979 | `::status -v` prints no build version on non-SmartOS builds |
| B14 | LOW | cmd/nsadmin/Makefile:66, 93, 96 | d0ca2b08e18 OS-7685; 1cc6f4c0fcc | undefined variables make two install rules dead |
| B15 | LOW | uts/intel/os/driver_aliases | various | aliases drifted from upstream (iwn confirmed) |
| B16 | LOW | manifest | long-standing | svc-smbd not shipped, but shipped server.xml uses it |
| W1 | — | cmd/svc/milestone/net-early-admin:53-56 | merge 4822583a749 | live `XXX Until OS-8367` workaround |

**B1. tmpfs: xattr directory error path cleans up the parent.**  In
tmp_lookup(), when `tdirinit(tp, xdp)` fails (ENOSPC on a size-limited
tmpfs), the code does `xdp->tn_vnode->v_flag &= V_XATTRDIR;` (meant
`&= ~V_XATTRDIR`) and then `tmpnode_cleanup(tp);`, where `tp` is the
*parent* file or directory, not the new `xdp`.  That zeroes the parent's
link count, truncates it if it is a directory, releases a hold its
caller still owns, and leaks xdp.  Trigger: open an xattr directory
(runat, openat O_XATTR) on a file in a full size-limited tmpfs.
tmp_dir.c:1160-1161 does the equivalent cleanup correctly on the new
node.  Likely fix: `&= ~V_XATTRDIR; tmpnode_cleanup(xdp);` (the hold and
lock state of xdp at that point still needs checking).

**B11. timer_setup() leaks an itimer_t.**  When timer_get_id() fails
(the process already has timer_max timers, default MAX(4 * NCPU, 32)),
the path frees `sigq` but not `it`, which came from
kmem_cache_alloc(clock_timer_cache) at line 618.  Upstream frees both
(BASE timer.c:679).  Joyent's code before the merge used timer_alloc(),
which freed it internally; merge da28b8a59d9 (12789) adopted upstream's
allocation without the free, and the later "fix mismerge" 3d070613ff2
only renamed a variable.  The other two error paths (682, 694) are
correct.  Any unprivileged process can create timer_max timers and then
loop on timer_create() (native or lx) to leak kernel memory without
bound.  Fix: `kmem_cache_free(clock_timer_cache, it);` after mutex_exit,
and `return (EAGAIN)` (callers set errno themselves).

**B2. vm_getusage() with VMUSAGE_A_ZONE from a non-global zone.**  For
a non-global caller, `flags` has VMUSAGE_A_ZONE replaced by
VMUSAGE_ZONE, but `flags_orig`, which is passed to
vmu_copyout_results(), keeps it, while `req_zone_id` is only assigned
when `flags` has A_ZONE, so it is used uninitialized.
vmu_copyout_results() then filters VMUSAGE_ZONE results only by
`vmu_zoneid != req_zone_id`, with no check against the caller's zone.
The result cache is shared: if a global-zone caller recently computed
ALL_ZONES, a non-global request is served from that cache, so whether
the caller sees nothing, its own zone, or *another zone's* memory usage
depends on stack contents.  Plausible from the code; not demonstrated.
Fix: strip A_ZONE from flags_orig too, or initialize req_zone_id to the
caller's zone.

**B12. sprunprlock() lacks upstream 17458's SIGKILL handling.**  The
joyent-only sprunprlock() (used by lx_pid.c:380, lx_ptrace.c:1273,
lx_prsubr.c:275) releases P_PR_LOCK like sprunlock(), but without the
`SKILLED && p_tlist` → runlwps(TS_XSTART | TS_PSTART) block that
upstream 17458 (82b7b979be1, 2025) added to sprunlock().  A SIGKILL
posted while lx holds P_PR_LOCK on a fully stopped process may then
never be acted on, leaving the process stuck.  The code difference is
confirmed; reachability through the lx paths is not.  Fix: share the
SKILLED block between both functions.

**B3. FMA ipmi IPv6 routes.**  `inet_ntop(AF_INET6, ...,
ipv6_routes[i], sizeof (ipv6_routes[i]))` passes 8 (a `char *`) for an
INET6_ADDRSTRLEN buffer, so any route longer than 7 characters fails
with ENOSPC and the whole service-processor node enumeration aborts.
Fix: `INET6_ADDRSTRLEN`.

**B4. zfs_ioctl get_nvlist() precedence.**  `(error = get_nvlist(...) !=
0)` assigns the comparison, so callers get 1 (EPERM) instead of the real
error.  Two sites, both from the cached-properties work.

**B5. lx F_SETFD.**  `fcntl(fd, F_SETFD, arg, 0)` passes the Linux
argument unmasked.  Since upstream 16624, f_setfd_int() (os/fio.c:1591)
honors `FD_CLOEXEC | FD_CLOFORK` (FD_CLOFORK is 2), so a Linux program
setting bit 0x2 gets close-on-fork, which Linux would ignore.  Fix:
`arg & FD_CLOEXEC`.  Related but harmless on its own: lx_ioctl.c:1838
FIOCLEX/FIONCLEX assign rather than OR, which would clear an FD_CLOFORK
set this way.

**B6. Core-file .debug_* output off by one.**  Joyent's 685e6567cd5
reworked upstream 13925's single-loop debug-section handling into
separate count and output loops.  The count loop starts at
`off = ehdr.e_shentsize` (line 1963); the output loop sets `off = 0`
with `i = 1`, so it reads header i-1 and never the last header.  A
.debug_* section in the last slot is counted but not written.  Fix:
`off = ehdr.e_shentsize;`, or take upstream's function (see Cleanup).

**B7. libproc on-the-fly CTF.**  Pconvert_file_ctf() sets
`fptr->file_ctfp` and then returns NULL, so the first Pbuild_file_ctf()
call reports no CTF; later calls work.  Fix: `return (fp);`.  Also, if
ctf_convert_init() fails, file_cvt is never set and conversion is
retried on every call.

**B8. zfs destroy prints errors twice.**  libzfs print_on_error stays on
without -F, and destroy_callback() also prints
libzfs_error_action/description.

**B9. crontab -g usage.**  The merge with upstream 13066 (crontab -u)
renders joyent's `-g` as `{ -e | -g | -l | -r }` in the usage string and
crontab.1, but line 189 rejects `-g` without `-l`.  Before the merge the
usage read `crontab -l [-g] [username]`.

**B10. zfs_zone_txg_delay().**  Returns 0 (no delay) when the zone's
zpers_zfsp is NULL, where code before OS-6540 returned 10ms.
zpers_zfsp is NULL only after zone_shutdown() frees it, so this affects
only writes from a dying zone.  Probably harmless.

**B13. mdb build version.**  Joyent replaced upstream 11626's
`build version: %s` print with a parser for smartos-live's
build_etcrelease JSON, which prints git branch and revision only for a
`"repo": "illumos-joyent"` entry.  A plain nightly using the in-tree
default (`BUILDVERSION_EXEC="git describe ..."` in tools/env/illumos.sh)
gets nothing from `::status -v` or kmdb.  Fix: fall back to the raw
print (copy the string before strtok).

**B14. nsadmin Makefile.**  The rules `$(ROOTETCBASHDIR)/%: %` (line 93)
and `$(ROOTETCBASHCOMPLETIONDDIR)/%: %` (line 96) and the directory
target at line 66 use variables that are never defined; the Makefile
defines ETCBASHDIR and ETCBASHCOMPLETIONDDIR.  The rules collapse to
`/%: %`, and installation works only because Makefile.cmd's generic
`$(ROOTETC)/%: %` matches.  Fix: use the defined names.

**B15. driver_aliases drift.**  Joyent keeps its own 2,117-line table;
upstream generates aliases from the package manifests.  Confirmed: iwn
has 30 `pci8086,*` aliases where upstream's driver-network-iwn.p5m has
31 `pciex8086,*`; PCIe devices bind by pciex names, so iwn likely never
attaches on SmartOS.  Reported by a review agent, not individually
checked: amr uses old subsystem-ID forms; joyent lacks upstream's qlc
pci1077,2322, si3124 pci1095,3531, yge pciex1148,9e00 and two usbftdi
aliases; bge has 11 joyent-only aliases and the cpqary3 IDs go to smrt
(both likely deliberate).  Overall, 228 aliases are joyent-only and 221
are upstream-only; worth a systematic reconciliation.

**B16. svc-smbd not shipped.**  usr/src/cmd/smbsrv/smbd/server.xml:127,
which ships, uses `/lib/svc/method/svc-smbd ipfilter` as its firewall
method, but svc-smbd has never been in `manifest`.  Matters only for
the SMB server with ipfilter.  (libzfsbootenv has never shipped either.)

**W1. varpd workaround.**  net-early-admin unconditionally runs
`svcadm enable varpd` "XXX Until OS-8367 is sorted out".  No commit on
`master` references OS-8367, so the workaround is live.

## Deliberate divergences

These differ from upstream on purpose and stay as they are.

- **sed lacks illumos 586** (`sed -i` with an optional argument,
  `--in-place`).  58474c20a52 (John Sonnenschein, 2011) reverted it with
  no stated reason and it was never reinstated; sed(1) documents the
  older behavior.  Probably kept so BSD-style `sed -i ''` and
  `sed -i .bak` in SmartOS scripts keep working (unverified).  Kept,
  and noted in the `sed` commit message (FILE_NOTES in buckets.py).
  This is the only upstream revert still in effect: of the seven
  upstream changes joyent ever reverted, 17136, 13761, 8021, 8007, 7571
  and 1948 are all fully present again.
- **bpf_filter.c lives in uts/common/inet/**, not upstream's
  uts/common/io/bpf/: OS-5549 moved it into ip for SO_ATTACH_FILTER on
  ICMP sockets.  Worth remembering whenever upstream touches bpf.
- **DLPI/DLS/MAC promiscuous FIXUPS flags were renumbered**
  (DL_PROMISC_FIXUPS 0x05 to 0x07, and the DLS and MAC equivalents) to
  avoid new upstream values.  Consistent in-tree; an ABI change only for
  out-of-tree DLPI consumers.

## illumos-joyent's lx compared with OmniOS's

Compared against OmniOS master 88c163d5a22, which has merged
illumos-gate up to 6a2df4aa538, 5 commits behind our base.

- Every lx file OmniOS carries is also in joyent: 217 shared, 175 of them
  byte-identical, 42 different by +882/-1050 lines (joyent relative to
  OmniOS).  The largest differences are in the lx cgroup file system,
  lx_init (lxinit.c), lx procfs (lx_prvnops.c) and the zone boot
  scripts.
- 19 lx files are joyent-only: the lx zone brand scripts and XML
  (lib/brand/lx/zone/), the legacy lxproc file system, and the lx(7)
  and lxproc(4FS) manual pages.
- Of the 138 generic kernel/libc files in the brand-* commits, 102 are
  byte-identical to OmniOS's; in 35 OmniOS differs from both joyent and
  upstream (presumably OmniOS's own changes; not examined); 1 matches
  upstream in OmniOS.
- The branch shows this directly: the `lx-omnios` commit is OmniOS's lx,
  and the `lx` commit after it is exactly joyent's difference.

## Cleanup candidates

None of these change behavior; all would shrink the delta or remove dead
code.

- **60 copyright/whitespace-only files.**  They differ from upstream
  only in copyright lines, blank comment lines or whitespace: residue of
  changes that were reverted or upstreamed.  They have their own commit
  (`copyright-residue`).  List: `data/copyright_only.txt`.
- **elf_process_obj_scns()** (elf.c) is an older joyent-only two-loop
  variant of what upstream now has (14236, 15583).  Apart from B6 it is
  equivalent: debug sections are written after CTF/symtab rather than
  before, and the `count > remain` code around lines 2030-2033 is dead.
  Taking upstream's function and call site removes B6 too.
- **zil.c (b573326a8ab, OS-6277 restoring OS-2313)** is redundant: upstream
  8585's zl_dirty_max_txg already makes zil_close() wait for the dirty
  txg.  Joyent's extra `txg_wait_synced(dp, 0)` is stricter, costing up
  to about two extra txg syncs when closing a dirty log.
- **qede blobs** (`.../qede/579xx/drivers/ecore/ecore_init_values*.bin`
  and `documentation/pictures/*`) were added by OS-5969 and never
  shipped upstream.  `qede_list.h` and `qede_version.h` differ only by
  whitespace.
- **Lint leftovers** (LINTLIB, llib-l* files, lint targets) in libzdoor,
  libbunyan, libresolv2_joy, libsmartsshd, libvnd and lx_vdso.
- **ptools:** ptree and pwdx link an unused ptools_common object.
- **lx_vdso** passes its mapfile to the linker twice (MAPOPTS and
  DYNFLAGS).
- **cron** renames upstream's POBJS to OBJS for CTF; `CTF_MODE = link`
  might avoid that (untested).
- **nsadmin:** bash_completion.d/machines and vms are in the tree but
  neither installed nor shipped.
- **linkprop.c** differs from upstream only by line wrapping in one
  declaration list.
- **Cosmetic:** vm_pageout.c:1364 comment lost its first line ("If
  scanning because the system is low on memory,") in e995d04dc2a;
  vm_pageout.c:274-276 indented 6 spaces instead of 5; libzfs_iter.c
  dropped braces (129-131) and double blank lines (156-158);
  zpool_main.c:2836 space indentation; eventfd.c:239 stale
  `/*ARGSUSED*/` and :272 `__unused` on used arguments; exit.c four
  comments with tabs for double spaces (a13af751641); zcons.c:62
  "Zcons driver" capitalized in merge f3389cfd79d; cron.h:79 stale
  "anything below here can be changed" comment that upstream 3206
  removed; lx_socket.c:1215-1216 redundantly ORs `f_getfd()` into
  f_setfd_or().

## What was reviewed

- **Merge-conflict resolutions.**  About 5.1k delta lines were written
  in merge commits; about 4.8k of those are `manifest` and driver tables.
  The ~70 code files were reviewed: every resolution is a correct
  adaptation to an upstream change (FD_CLOFORK and the 4-argument
  fcntl, 17689 posix_spawn in fork.c, zfs mount/share and snapshot
  batching, txg_delay in ns, vdev_queue AVL trees, 13097 pageout, 14890
  dboot EFI memory map, 15583 core-file sizing, ucontext uc_filler
  alias, 16700 eventfd wakeups, handle-based ctf_convert, zonecfg token
  renumbering checked index for index).  dboot_add_memlist() dropping
  upstream's `size != 0 && type == t` guard is harmless, because joyent
  selects the list by type first.
- **"Fix mismerge" commits.**  77 joyent commits are labelled as
  mismerge fixes; the 24 that still own lines in the delta were
  reviewed.  Most are correct, still-needed adaptations: f559d4b8282
  restores the lx int80 entry points that 12349 dropped; 9408eb512c8
  sizes the branded auxv exactly (exec fails otherwise); OS-8389's
  procfs PR_ARGV/PR_CMDLINE numbering is consistent across all four
  prvnops tables; the vm_pageout.c zone-cap scanning is a consistent
  port onto 13097.  B6, B11 and B12 sit next to these commits;
  elf_process_obj_scns() and zil.c are cleanup candidates.
- **Upstream reverts.**  All seven reverts of upstream changes in
  joyent history were checked; only sed (586) is still in effect.
- **Microcode packaging.**  The 535 `platform/i86pc/ucode` entries in
  `manifest` match upstream's system-microcode-{intel,amd}.p5m exactly
  (paths, hardlink targets, modes).
- **Manifest against package manifests.**  The SmartOS builder fails on
  a missing `f` entry, so stale file entries cannot hide in a passing
  build; the silent failure is the reverse (built but not listed, so
  not shipped), which is how B16 was found.

## Not yet reviewed

- posix_spawn (17689) for branded processes: fork.c calls b_forklwp for
  the spawn LWP, but whether lx needs more was not examined.
- Upstream 18213 (rpc/xdr.h no longer includes stdio.h) may affect lx
  userland files beyond the two already fixed; only a build will tell.
- Deliberate divergence in large diffs (libzonecfg.c, ip_fil_solaris.c,
  net-physical) was reviewed only next to merge-written lines.
- dladm(8) and flowadm(8): most of joyent's lines (116 and 32) were
  written in merge commits, probably joyent's additions re-applied when
  upstream converted the pages; not verified.
- The 35 brand-* files where OmniOS differs from both joyent and
  upstream.
- Possible *upstream* bug, unverified: upstream timer_lwpexit() and
  timer_lwpbind() cache `p->p_itimer` across a p_lock drop while
  timer_get_id() may resize and free it.  Joyent re-reads the array on
  each iteration and avoids it.

## Open questions

- Is OS-8367 resolved, so W1's workaround can go?
- Ulyssa Mello's credit uses cody.mello@joyent.com, the only address in
  either history.  Current preferred address?
- Brianna Bennett's history also contains "Brie Bennett"; Brianna is
  what is credited now.  Confirm with Dan, along with any other name
  changes the automatic merging cannot catch.

## Decisions

- Base is the upstream parent of the newest `[illumos-gate merge]`, not
  the latest `illumos/master`.
- The first pass is byte-identical to `master`, bugs and all, which
  proves the restructuring broke nothing.  Fixes come later as
  follow-up commits, possibly folded in afterwards.
- Whole files per commit; `integration` (shared hub files) goes last.
- Commit messages list feature tickets; fix tickets are listed by ID.
- Intermediate commits are not expected to build.
- Deliberate divergences with no ticket are explained via FILE_NOTES in
  buckets.py, in the message of the commit that carries the file.
- Commits are authored by Claude <noreply@anthropic.com> and committed
  by whoever runs the build.  Everyone whose surviving or removed lines
  are in a commit is credited with Co-authored-by, under their newest
  name and email.  Bot identities (BOTS in build.py) are not credited.

## Identity mappings

From `mailmap` (explicit) and automatic merging of identities that share
a name or email (credited under the newest).

- Name updates: Ulyssa Mello (was Cody Peter Mello); Lexi Wilson
  <lexi@cooperi.net> (was Alex Wilson, both addresses; her current
  address is from her own 2026-07-09 illumos-gate commit).
- Placeholder identities: `jerry@opensolaris.(none)` and
  `jerry@bh1-build.(none)` are Jerry Jelinek; `bmc@bh1-build.(none)` is
  Bryan Cantrill.
- Carlos Neira replaces "Neirac" (their commits say "Carlos Neira
  (Neirac)").
- Automatic: Brianna Bennett (also Brian Bennett, Brie Bennett), Keith M
  Wesolowski (also Keith Wesolowski), Michael Zeller (also Mike
  Zeller), Jorge Schrauwen (also sjorge).
- Dropped: Joyent Automation <releng@joyent.com> (bot).

## Known limitations

- Commit messages list every ticket with at least one surviving line in
  the commit's files, so large commits list 100-800 tickets and some
  look misplaced (whole-file rule).  Thinning them, e.g. with a
  line-share threshold, is deferred.
- The feature/fix split of tickets is a subject-line heuristic.
- Credit for removed lines (deletions.py) is a text match and
  over-counts repeated removals (9,340 credited vs 8,192 removed).  It
  affects only the order of Co-authored-by trailers; tickets are
  attributed from surviving lines only.
- Commit descriptions in buckets.py are summaries written from ticket
  subjects and code reading; no subsystem owner has reviewed them.
- `misc` holds 14 genuine singletons.

## Method notes

- Attribution counts only lines that differ from BASE.  Plain blame
  over-credits joyent, because on merges it tries the joyent parent
  first.
- `./report.py merge-lines` and `./merge_lines.py <path>` show lines
  written during merge resolution; `merge_lines.py --commit <sha>` shows
  one commit's surviving lines.
- `./report.py boundary` lists `+` lines that blame to upstream commits.
  Most are upstream content joyent moved or copied (bpf_filter.c, brand
  XMLs); a file whose diff has no joyent commit behind it is how the sed
  revert was found.
- Path-limited `git log` simplifies history and can drop joyent commits
  on merged side branches; deletions.py uses `--full-history`.
- Clustering files by shared tickets does not work: sweep tickets
  (OS-8361, OS-7685, OS-2800, OS-7960, OS-7768) join most of the delta
  into one component.
- Dan's map of the differences is README-SmartOS.md in
  TritonDataCenter/illumos-joyent PR #547 (unmerged); commit names
  follow its sections where possible.
