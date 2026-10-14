# Findings

Running log of suspected bugs, mismerges, dead code, and decisions.
Nothing here has been fixed; these are leads for review.

## Decisions

- Base is the upstream parent of the newest `[illumos-gate merge]`
  (479a4a914dc at the start), not the latest `illumos/master`.
- Whole files per commit for the first pass.  `integration` goes last.
- Feature tickets are listed in commit messages; bug-fix tickets are
  summarized collectively.
- Intermediate commits are not expected to build.
- First pass is byte-identical to master, bugs and all: that proves the
  restructuring broke nothing.  Fixes come later as follow-up commits,
  possibly folded in afterwards.  (Nahum, 2026-10-14)
- Deliberate divergences with no ticket are documented via FILE_NOTES
  in buckets.py, which prints them in the carrying commit's message.
- Commits are authored by Claude <noreply@anthropic.com>, committed by
  whoever runs the build; bot identities (BOTS in build.py) are not
  credited.  (Nahum, 2026-10-14)
- Co-authors are credited under their newest name/email only.
  (Nahum confirmed for Brianna Bennett.)

## Context

- Dan's map of differences is `README-SmartOS.md` in
  TritonDataCenter/illumos-joyent PR #547 (unmerged).  Bucket names
  follow its sections where possible.
- Clustering files by shared tickets is useless: sweep tickets (OS-8361
  man renumbering, OS-7685 overlay merge, OS-2800 Bardiche, OS-7960,
  OS-7768 smatch) join ~1,300 of the ~1,800 files into one component.

## Leads

1. **qede binary blobs exist only in joyent.**
   `usr/src/uts/common/io/qede/579xx/drivers/ecore/{ecore_init_values.bin,
   ecore_init_values_zipped.bin,documentation/pictures/*}` were added by
   OS-5969 and upstream never shipped them.  Likely dead weight.
   `qede_list.h` / `qede_version.h` differ only by trailing whitespace.
2. **bpf_filter.c location.** Joyent has it in `uts/common/inet/`
   (OS-5549 moved it into ip for SO_ATTACH_FILTER on ICMP) and deletes
   upstream's `uts/common/io/bpf/bpf_filter.c`.  Deliberate, but a
   standing divergence to keep in mind when upstream touches bpf.
3. **Merge-resolution lines**: after diff restriction, ~5.1k surviving
   lines were written in merge commits; ~4.8k of those are `manifest`
   and driver tables (expected).  The ~70 code files are under review
   (results below).  To list: `./report.py merge-lines`; to inspect one:
   `./merge_lines.py <path>`.
4. **BOUNDARY lines**: ~800 `+` lines blame to upstream commits at or
   before BASE.  Nearly all are upstream content joyent moved or copied
   (bpf_filter.c 551, brand XMLs copied from ipkg).  The useful signal
   is a file whose joyent diff has *no* joyent commit behind it, which
   is how the sed revert (lead 6) was found.  `./report.py boundary`.
5. Several joyent commits are labelled "fix mismerge" of upstream
   tickets and still own lines that differ from upstream (13925 elf.c,
   12349 syscall_asm_amd64.S, 13097 vm_pageout.c, 11909 pid.c, 12789
   timer.c, 17297 libproc).  These may be legitimate lx adaptations or
   leftovers; each needs a look.
6. **sed: upstream 586 is still reverted (CONFIRMED divergence).**
   58474c20a52 (John Sonnenschein, 2011-11-24) reverted illumos 586
   "sed -i should take an optional argument" with no stated reason, and
   it was never reinstated.  Joyent sed lacks `--in-place` and the
   optional `-i`/`-I` argument; sed.1 documents the old behavior too.
   Hypothesis (unverified): kept so BSD-style `sed -i ''`/`sed -i .bak`
   in SmartOS scripts keeps working.  DECIDED: keep, documented in the
   carrying commit via FILE_NOTES.
7. **Audit of joyent reverts of upstream changes.**  Seven upstream
   commits were reverted in joyent history.  Checking whether the
   upstream lines still present in BASE are missing from master: only
   586 (sed) is still in effect.  17136, 13761, 8021, 8007, 7571 and
   1948 are fully present again (8021 differs by one comment block in
   abd.c, from OS-6387).
8. **Copyright/whitespace residue: 60 files** differ from upstream only
   in copyright lines, blank comment lines or whitespace (some show the
   same copyright line on both sides).  These are what is left of
   changes that were reverted or upstreamed.  They have their own
   commit (`copyright-residue`); restoring them to upstream would
   shrink the delta by 60 files with no functional change.  List:
   `data/copyright_only.txt`.

## Bugs

Every entry was checked by reading the code on master (da512a7e2e6);
"origin" is the commit that introduced it (found with git log/blame).
None exist upstream unless stated.  Nothing has been fixed: the branch is
byte-identical to master by design.  Line numbers are as of master.

Severity: HIGH = data corruption or a security boundary; MED = wrong
results or a failed operation; LOW = edge case or cosmetic behavior.

| ID | Sev | Where | Origin | Summary |
|----|-----|-------|--------|---------|
| B1 | HIGH | uts/common/fs/tmpfs/tmp_vnops.c:924-925 | 08280dbb7d3 OS-5539 (2016) | xattr-dir error path cleans up the parent node |
| B2 | MED? | uts/common/vm/vm_usage.c:2057-2059,2072-2083,1948-1950 | 2f904f0710c OS-750 (2012) | uninitialized req_zone_id; plausible cross-zone disclosure |
| B3 | MED | lib/fm/topo/modules/common/ipmi/ipmi_enum.c:837-838 | 4a99ae16188 OS-6527 (2017) | inet_ntop given sizeof(char *) |
| B4 | MED | uts/common/fs/zfs/zfs_ioctl.c:2221-2223, 2433-2435 | e4c080eef3a OS-1048 (2012) | `(error = get_nvlist(...) != 0)` precedence |
| B5 | LOW | uts/common/brand/lx/syscall/lx_fcntl.c:302 | merge 28a6b3a036f (2024) | Linux F_SETFD can set FD_CLOFORK |
| B6 | LOW | uts/common/exec/elf/elf.c:2129 | 685e6567cd5 13925 fix-mismerge (2021) | .debug_* output loop off by one |
| B7 | LOW | lib/libproc/common/Psymtab.c:801 | 092a4fbb8cf OS-4573 (2015) | Pconvert_file_ctf always returns NULL |
| B8 | LOW | cmd/zfs/zfs_main.c:1285-1336 | OS-604 (954e970e290) | zfs destroy prints errors twice without -F |
| B9 | LOW | cmd/cron/crontab.c:77-78,189; man1/crontab.1:67,77,92 | merge 82a64156a05 | usage/man advertise `-g` alone; code needs `-l` |
| B10 | LOW | uts/common/fs/zfs/zfs_zone.c:1181-1184 | 4851e24d85b OS-6540 (2018) | no txg delay for a zone being torn down |
| B11 | HIGH | uts/common/os/timer.c:622-627 | merge da28b8a59d9 (12789) | timer_setup leaks an itimer_t per call at timer_max (unprivileged) |
| B12 | MED? | uts/common/os/pid.c:571-582 | fac1ecb479c vs upstream 17458 | sprunprlock() lacks 17458's SIGKILL runlwps() |
| B13 | LOW | cmd/mdb/common/modules/mdb_ks/mdb_ks.c:1900-1968 | OS-7201/OS-7979 (1cc6f4c0fcc) | ::status -v prints no build version for non-SmartOS buildversion |
| W1 | — | cmd/svc/milestone/net-early-admin:53-56 | merge 4822583a749 | live `XXX Until OS-8367` workaround |

**B1. tmpfs xattr dir error path cleans up the parent.**  In
tmp_lookup(), when `tdirinit(tp, xdp)` fails (ENOSPC on a size-limited
tmpfs) the code does `xdp->tn_vnode->v_flag &= V_XATTRDIR;` (meant
`&= ~V_XATTRDIR`) and `tmpnode_cleanup(tp);` where `tp` is the *parent*
file/dir, not the new `xdp`.  That zeroes the parent's link count,
truncates it if it is a directory, releases a hold its caller still
owns, and leaks xdp.  Trigger: open an xattr directory (e.g. runat,
openat O_XATTR) on a file in a full tmpfs with a size limit.
tmp_dir.c:1160-1161 does the equivalent cleanup correctly on the new
node.  Likely fix: `&= ~V_XATTRDIR; tmpnode_cleanup(xdp);` (hold/lock
state of xdp at that point not yet checked).

**B2. vm_getusage VMUSAGE_A_ZONE from a non-global zone.**  For an NGZ
caller, `flags` has VMUSAGE_A_ZONE replaced by VMUSAGE_ZONE, but
`flags_orig` (passed to vmu_copyout_results) keeps it, while
`req_zone_id` is only assigned when `flags` has A_ZONE, so it is used
uninitialized.  In vmu_copyout_results, VMUSAGE_ZONE results are then
filtered only by `vmu_zoneid != req_zone_id`, with no check against the
caller's zone.  The result cache is shared: if a global-zone caller
recently computed ALL_ZONES, an NGZ request (flags=ZONE) is satisfied
from that cache, so whether the NGZ sees nothing, its own zone, or
*another zone's* memory usage depends on stack garbage.  The disclosure
is plausible from reading the code but NOT demonstrated; the review
agent thought there was no leak and missed the shared cache.  Fix:
strip A_ZONE from flags_orig too (or initialize req_zone_id to the
caller's zone).

**B3. fm ipmi IPv6 routes.**  `inet_ntop(AF_INET6, ...,
ipv6_routes[i], sizeof (ipv6_routes[i]))` passes 8 (a `char *`) for an
INET6_ADDRSTRLEN buffer, so any route longer than 7 characters fails
with ENOSPC and the whole service-processor node enumeration aborts.
Fix: `INET6_ADDRSTRLEN`.

**B4. zfs_ioctl get_nvlist precedence.**  `(error = get_nvlist(...) !=
0)` assigns the comparison, so callers get 1 (EPERM) instead of the real
error.  Two sites, both from the cached-props work.

**B5. lx F_SETFD.**  `fcntl(fd, F_SETFD, arg, 0)` passes the Linux
argument unmasked.  Since upstream 16624, f_setfd_int (os/fio.c:1591)
honors `FD_CLOEXEC | FD_CLOFORK` (FD_CLOFORK == 2), so a Linux program
setting bit 0x2 gets close-on-fork, which Linux would ignore.  Fix:
`arg & FD_CLOEXEC`.  Related, harmless on its own: lx_ioctl.c:1838
FIOCLEX/FIONCLEX use f_setfd_error (assign), which would clear a
FD_CLOFORK set via B5.  Cosmetic: lx_socket.c:1215-1216 ORs
`f_getfd()|FD_CLOEXEC` into f_setfd_or, redundant.

**B6. Core-file .debug_* output.**  Joyent restructured upstream 13925's
single-loop debug-section handling into separate count and output loops.
The count loop starts at `off = ehdr.e_shentsize` (line 1963); the
output loop sets `off = 0` with `i = 1`, so it reads header i-1 and
never the last header.  A .debug_* section in the last slot is counted
but not written.  Fix: `off = ehdr.e_shentsize;`.

**B7. libproc on-the-fly CTF.**  Pconvert_file_ctf sets
`fptr->file_ctfp` then `return (NULL)`, so the first Pbuild_file_ctf
call reports no CTF; later calls work.  Fix: `return (fp);`.  Also, if
ctf_convert_init fails, file_cvt is never set and conversion is retried
on every call.

**B8. zfs destroy double error.**  libzfs print_on_error is on unless
`-F`, and destroy_callback also prints libzfs_error_action/description,
so failures print twice.

**B9. crontab -g usage.**  The merge with upstream 13066 (crontab -u)
renders joyent's `-g` as `{ -e | -g | -l | -r }`, in the usage string
and crontab.1, but line 189 rejects `-g` without `-l`.  Pre-merge usage
was `crontab -l [-g] [username]`.

**B10. zfs_zone_txg_delay.**  Returns 0 (no delay) when the zone's
zpers_zfsp is NULL, where pre-OS-6540 code returned 10ms.  zpers_zfsp is
only NULL after zone_shutdown frees it, so this affects writes from a
dying zone only.  Probably harmless; listed for completeness.

**B11. timer_setup() leaks itimer_t.**  When timer_get_id() fails
(process already at timer_max, default MAX(4*NCPU, 32)), the path frees
`sigq` but not `it` from kmem_cache_alloc(clock_timer_cache) at line
618.  Upstream (BASE timer.c:679) frees both; joyent's pre-merge code
used timer_alloc(), which freed it internally; merge da28b8a59d9
(12789) took upstream's allocation without the free, and 3d070613ff2
"fix mismerge" only renamed i to tid.  The other two error paths (682,
694) are correct.  Any unprivileged process can create timer_max
timers and then loop on timer_create() (native or lx) to leak kernel
memory without bound.  Fix: add `kmem_cache_free(clock_timer_cache,
it);` after mutex_exit (and `return (EAGAIN)`: callers set errno
themselves).

**B12. sprunprlock() vs upstream 17458.**  Joyent-only sprunprlock()
(used by lx_pid.c:380, lx_ptrace.c:1273, lx_prsubr.c:275) releases
P_PR_LOCK like sprunlock() but without the `SKILLED && p_tlist` ->
runlwps(TS_XSTART|TS_PSTART) block upstream 17458 (82b7b979be1, 2025)
added to sprunlock().  A SIGKILL posted while lx held P_PR_LOCK on a
fully stopped process may then never be acted on (stuck process).
Code difference VERIFIED; reachability through the lx paths NOT shown.
Fix: share the SKILLED block via a helper used by both.

**B13. mdb build version.**  Joyent replaced upstream 11626's raw
`build version: %s` print with a parser for smartos-live's
build_etcrelease JSON, printing git branch/rev only for a
`"repo": "illumos-joyent"` entry.  A plain nightly using the in-tree
default (`BUILDVERSION_EXEC="git describe ..."`, tools/env/illumos.sh)
gets nothing from ::status -v / kmdb.  Fix: fall back to the raw print
(copy the string before strtok).

**W1. varpd workaround.**  net-early-admin unconditionally runs
`svcadm enable varpd` "XXX Until OS-8367 is sorted out".  No commit on
master references OS-8367, so the workaround is live.  Check the ticket.

### Reviewed and not bugs

- All ~70 files with merge-written lines (four review agents, see
  README for method): every merge resolution is a correct adaptation to
  an upstream API change.  Notables: FD_CLOFORK (4-arg fcntl,
  f_setfd_or), 17689 posix_spawn (fork.c took upstream's spawn path
  intact plus joyent's GETPROC_ZSCHED and lwp_ctmpl_clear arg), zfs
  mount_and_share / snapshot batching, txg_delay in ns, vdev_queue AVL,
  13097 pageout, dboot EFI memmap (14890), core-file sizing (15583),
  ucontext uc_filler alias, eventfd wakeups (16700), handle-based
  ctf_convert, zonecfg token renumbering (checked index-for-index).
- dboot_add_memlist drops upstream's `size != 0 && type == t` merge
  guard: joyent selects the list by type first, so only adjacent
  reserved ranges of different reserved types merge; harmless.
- DL_PROMISC_FIXUPS 0x05->0x07 (and DLS/MAC equivalents) renumbered to
  dodge new upstream values; consistent in-tree, an ABI change only for
  out-of-tree DLPI consumers.

### Fix-mismerge commits (lead 5)

77 joyent commits are labelled as mismerge fixes; 24 still own lines in
the delta.  Reviewed so far (kernel core): f559d4b8282 restores the lx
sys_int80/brand_sys_int80 entry points 12349 dropped (correct, needed);
9408eb512c8 sizes the branded auxv for joyent's AT_SUN_BRAND_AUX4
(correct, needed: exec fails if the count is off); 3d070613ff2 adapts
timer.c to joyent's timer_setup() refactor (correct; B11 sits next to
it).  685e6567cd5's elf_process_obj_scns() is a stale joyent-only
two-loop variant of what upstream now has (14236, 15583); apart from B6
it is equivalent (debug sections are written after, not before,
CTF/symtab; dead `count > remain` code ~2030-2033).  Recommendation for
the fix-up phase: take upstream's function and call site wholesale,
which also removes B6.  Filesystems/tools: no functional bugs.  b573326a8ab (zil.c, OS-6277
restoring OS-2313) is now redundant: upstream 8585's zl_dirty_max_txg
already makes zil_close wait for the dirty txg; joyent's extra
`txg_wait_synced(dp, 0)` is stricter (up to ~2 extra txg syncs on
closing a dirty zil) but harmless; cleanup candidate, revert to
upstream.  vm_pageout.c zone-cap scanning is a consistent port of
OS-6355/OS-6484 onto 13097.  OS-8389 procfs PR_ARGV/PR_CMDLINE
numbering checked end to end across all four prvnops tables (joyent-only
node types; nothing outside fs/proc depends on them).  17297, 6342,
8149, 12679/12693 and 14019 fixes are correct adaptations (linkprop.c
differs from upstream only by line wrapping).  Cosmetic: vm_pageout.c
274-276 indented 6 spaces instead of 5.
Possible *upstream* issue, NOT verified:
upstream timer_lwpexit/timer_lwpbind cache `p->p_itimer` across a
p_lock drop while timer_get_id() may free/resize it; joyent re-reads
the array each iteration and avoids it.

### Not reviewed

- posix_spawn (17689) for branded processes: fork.c calls
  b_forklwp for the spawn LWP, but whether lx needs more (e.g. its own
  spawn emulation) was not examined.
- The upstream 18213 stdio.h fallout may affect other lx userland files;
  only a build shows that.
- Deliberate divergence in large diffs (libzonecfg.c, ip_fil_solaris.c,
  net-physical) was only reviewed next to merge-written lines.

### Cosmetic leftovers (all confirmed)

vm_pageout.c:1364 comment lost its first line ("If scanning because the
system is low on memory,") in e995d04dc2a; libzfs_iter.c:129-131
dropped braces and :156-158 double blank lines; zpool_main.c:2836 space
indentation; eventfd.c:239 stale `/*ARGSUSED*/` and :272 `__unused` on
used args; exit.c four comments with tabs for double spaces
(a13af751641); zcons.c:62 "Zcons driver" capitalized in merge
f3389cfd79d; cron.h:79 stale "anything below here can be changed"
comment that upstream 3206 removed.

## Questions for Nahum

- (answered) Joyent Automation bot: dropped from co-authors.

Answered: jerry@opensolaris.(none) and jerry@bh1-build.(none) are Jerry
Jelinek (mailmap); newest-name crediting is correct; keep sed divergence.

## Known limitations of the current branch

- Ticket lists in commit messages include every ticket with at least
  one surviving line in the bucket's files, so a few look misplaced
  (e.g. OS-6547 KPTI shows in brand-kernel because desctbls.c has lx
  and KPTI lines interleaved).  That is accurate to the whole-file
  rule, not a classification error.
- The feature/fix split is a subject-line heuristic.
- `misc` (54 files) is a catch-all that deserves splitting.
