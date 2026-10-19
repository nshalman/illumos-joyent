# Commit order and descriptions for the restructured branch.
# Every bucket classify.py can emit must appear here exactly once.
#
# (bucket, subject, body)
BUCKETS = [
    ('brand-ops', 'brand framework: brand operations, exec hooks and x86 entry',
     'The brand operations vector and its plumbing as extended for lx '
     '(sys/brand.h, os/brand.c, machbrand.h, brandsys), with the sn1 and '
     'solaris10 brands updated to fill in the new operations.  Exec and '
     'ELF loading for branded binaries: interpreter (.interp) handling and '
     'native-root lookup, auxv additions (AT_RANDOM, AT_SECURE, brand aux '
     'entries), PT_GNU_STACK, prelinked binaries, shebang and nested '
     'interpreter behavior, and core-file changes.  x86 entry for lx: '
     'system call entry points (int80 and fast paths), signal frames on '
     'an alternate stack, ucontext brand data, comm page/vdso support, '
     'CPUID limits for glibc, and descriptor table entries.  These are one '
     'change to the brand interface: every new or changed operation has '
     'to land together with all of its callers and implementations.'),
    ('brand-process', 'process, LWP and signal hooks for branded processes',
     'Brand hooks in fork, exit, lwp creation and signal delivery; more '
     'real-time signals; ptrace support (OS-3820); Linux accounting; '
     'per-process RLIMIT_MEMLOCK; MAP_32BIT; contract and init handling.'),
    ('brand-events', 'poll, epoll, eventfd, signalfd, timers and pipes',
     'Kernel support for Linux-flavored event semantics: nested epoll, '
     'eventfd overflow, SIGEV_THREAD_ID timers, larger pipe buffers and '
     'splice support, ppoll overflow fixes.'),
    ('brand-net', 'socket and UDP/IP behavior for lx',
     'SO_REUSEPORT, recvmsg MSG_PEEK|MSG_TRUNC, async socket errors, '
     'rtnetlink socket registration, UDP changes for Linux NFS, and DHCP '
     'client options for lx zones.'),
    ('brand-fs', 'file and terminal syscalls for lx',
     'open/close/fcntl moved into the kernel for lx, O_PATH emulation, '
     'chdir with CLONE_FS, umount and uadmin locking fixes, pty changes.'),
    ('brand-nfs', 'NFS locking and mounting for lx zones',
     'lockd/statd interaction with Linux clients, NFS mount without a '
     'native nfssec.conf, netconfig lookup in the native root.'),
    ('brand-native', 'native userland inside branded zones',
     'Native-root aware libc, libcurses and system(3C); truss decoding of '
     'lx-related calls; prstat changes.'),
    ('zone-kernel', 'zones: kernel zone core',
     'zone.c/zone.h extensions: persistent zone IDs, init exit status and '
     'restart control, zone datalink restrictions, VFS and ZFS I/O kstats, '
     'sysevents, contract handling, zone_did for DTrace, and the resource '
     'control documentation.'),
    ('zone-memory', 'zones: memory caps, RSS tracking and page invalidation',
     'Physical memory caps as an rctl with kstats, accurate in-kernel zone '
     'RSS, in-kernel page invalidation for capped zones, vm_getusage '
     'performance, per-process segment limits, and rcapd/rcapstat.'),
    ('zone-cpu', 'zones: CPU caps with bursting and high-priority zones',
     'CPU caps that allow bursting, with kstats to track it, and FX/RT '
     'high-priority zone configuration.'),
    ('zone-security', 'zones: privileges and kernel memory access',
     'New privileges (hyprlofs, zfs receive), kmem/physmem/ksyms access '
     'disabled from non-global zones, and a hardened random pool for '
     'zones.'),
    ('zones-admin', 'zones: zoneadmd and zlogin',
     'zoneadmd logging (generic zfd logging, JSON log output), console '
     'handling, platform setup (vplat) and state-transition changes, and '
     'zlogin options for zfd-backed zones.'),
    ('zones-tools', 'zones: zonecfg, libzonecfg and zoneadm extensions',
     'Additional zonecfg resources and properties (net, device, and more), '
     'native-root awareness in libzonecfg, zoneadm changes, and the zones '
     'SMF services.'),
    ('zone-brands', 'zones: joyent, joyent-minimal, builder, bhyve and kvm brands',
     'The SmartOS native and HVM zone brands.  See joyent(7).'),
    ('zfd', 'zfd(4D) zone file descriptor devices',
     'Zone fd devices used to connect zone stdio (e.g. docker-style '
     'containers) to zoneadmd.'),
    ('datalink', 'per-zone datalinks',
     'Per-zone datalink names (every zone has its own net0) through '
     'dlmgmtd, libdladm, dls and dld; link kstats by zone; ipmgmtd and '
     'libipadm in branded zones; flowadm, flowstat and dlstat zone '
     'support.'),
    ('link-protection', 'VNIC link protection',
     'Link protection properties allowed-ips (with dynamic methods) and '
     'allowed-dhcp-cids, enforced in mac_protect and ip, with tests.'),
    ('vnd', 'vnd: Project Bardiche (vnd, frameio, gsqueue, sdev plugins)',
     'The vnd(4D) virtual network device, libvnd, vndadm/vndstat, generalized '
     'squeues, and the libdlpi/snoop support for them.'),
    ('overlay-svp', 'overlay: SVP varpd plugin and supporting pieces',
     'Triton fabric networking: the SVP varpd plugin, refhash, snoop SVP '
     'decoding, and overlay changes not yet upstream.'),
    ('ipf-cfw', 'ipfilter: Cloud Firewall logging',
     'Hooks in ipfilter for Triton Cloud Firewall (cfw) logging.'),
    ('icmp-bpf', 'SO_ATTACH_FILTER for ICMP sockets',
     'Move the BPF filter functions into ip and allow attaching BPF '
     'filters to ICMP sockets.'),
    ('datafilt', 'datafilt socket filter',
     'Server-side TCP accept filter (illumos#1403), from OmniOS.'),
    ('tcp-connstat', 'TCP: connstat, pluggable congestion control, RTT tracking',
     'connstat(8) and the TCP statistics it needs, pluggable congestion '
     'control, nanosecond RTT tracking, SO_REUSEPORT.'),
    ('net-misc', 'networking tool additions',
     'ndp(8), route -z, arp/ndp native-root handling, DHCP fixes, ipd.'),
    ('inotify', 'inotify(7) and file event monitoring',
     'inotify, the fem changes it depends on, and vnode event emission '
     'across filesystems.'),
    ('hyprlofs', 'hyprlofs file system', 'Fast namespace virtual file system.'),
    ('tmpfs', 'tmpfs sizing and accounting', 'tmpfs size and accounting improvements.'),
    ('sdev', 'sdev: zvol and network device handling', '/dev plugin fixes.'),
    ('zfs-arc', 'ZFS: zfs_arc_max tunable',
     'Allow the ARC maximum to be specified (OS-8638).'),
    ('zfs-props', 'ZFS: cached-only property listing and pool history',
     '`zfs list/get -c` returning only cached properties (OS-1048, '
     'OS-1104) through libzfs and zfs_ioctl, plus logging zpool modify '
     'ioctls to the pool history (OS-7443).'),
    ('zfs-cli', 'ZFS: zfs and zpool command changes',
     '`zfs destroy -F` and clone creation retry on EBUSY (OS-604, OS-993), '
     'and `zpool import -m` printing the last txg time (OS-6417).'),
    ('zfs-zvol', 'ZFS: zvol kstats and probes',
     'Per-zvol kstats and SDT probes for zvol_read/zvol_write (OS-525, '
     'OS-530).'),
    ('zfs-metaslab', 'ZFS: metaslab counters and condensing control',
     'Metaslab load/unload counter kstats and a way to avoid condensing '
     'metaslabs (OS-7646, OS-2711).'),
    ('zfs-zio', 'ZFS: ZIO, ZIL and vdev_disk changes',
     'Better handling of a dying SLOG (OS-5872), zil_commit latency '
     '(OS-7917), the OS-2313 zil_close race fix (OS-6277), and vdev_disk '
     'changes for pulled disks and ziostat (OS-1987, OS-393).'),
    ('zfs', 'ZFS: other fixes',
     'dbuf read behavior (OS-1792), abd chunk size guidance (OS-6387), a '
     'zone reference leak on forced unmount (OS-1439), and a '
     'zfs_write/zfs_putpage deadlock (OS-1811).'),
    ('zfs-tests', 'ZFS test suite adjustments for SmartOS',
     'zfstest scaffolding and test changes for running on SmartOS.'),
    ('zfs-zone-io', 'ZFS: zone I/O throttling and observability',
     'Per-zone ZFS I/O throttling and prioritization (zfs_zone.c and its '
     'hooks in dmu_tx, dsl_dir, dsl_pool, txg and vdev_queue), plus '
     'vfsstat, ziostat, arcstat and zfscache.'),
    ('dump-encryption', 'encrypted kernel crash dumps and arc4random',
     'Kernel crash dump encryption (OS-7828) and the chacha changes it uses.'),
    ('storage-drivers', 'drivers and storage support', 'Hardware driver changes.'),
    ('nfp', 'nfp(4D) driver', 'nCipher HSM support.'),
    ('vmxnet', 'vmxnet(4D) driver', 'VMware guest network driver.'),
    ('dboot', 'dboot memory mapping changes', 'Early boot changes for difficult hardware and iPXE.'),
    ('boot', 'loader and boot branding', 'SmartOS/Triton loader menus, branding, and boot fixes.'),
    ('bhyve', 'bhyve changes for bhyve-branded zones',
     'Delayed privilege drop for zone provisioning, uart rate limiting, '
     'zhyve.'),
    ('dtrace', 'DTrace enhancements', 'DTrace changes not upstream.'),
    ('mdb', 'mdb enhancements', 'mdb changes not upstream.'),
    ('rtld-sgs', 'rtld and sgs changes', 'Toxic libraries, PAX headers, branded symbol lookup.'),
    ('ctf', 'CTF tooling differences',
     'ctf conversion uses the native root; libproc can convert CTF on the '
     'fly (OS-4573).'),
    ('fm-topo', 'FMA topology additions', 'Topology maps and modules for supported hardware.'),
    ('ptools', 'ptools and procfs enhancements',
     'Service FMRIs, process arguments via procfs, ps/pgrep/ptools additions.'),
    ('resolver', 'libresolv2_joy and nsswitch dns', 'See OS-2115.'),
    ('smartlogin', 'libzdoor and libsmartsshd', 'Support for Triton smartlogin.'),
    ('bunyan', 'libbunyan', 'Bunyan-format JSON logging.'),
    ('nvpair-json', 'nvlist JSON output', 'nvlist_dump_json() and friends.'),
    ('openssl-sunw', 'link platform OpenSSL consumers with sunw_ libraries',
     'The platform OpenSSL is delivered with sunw_ prefixed names.'),
    ('smf', 'SMF changes', 'svc.startd, svc.configd and svcs changes.'),
    ('platform-config', 'platform image configuration',
     'Milestone services, default /etc contents, shell profiles, cron, '
     'logadm and syslog configuration for the SmartOS ramdisk root.'),
    ('altexec', 'altexec(8)', 'Wrappers for tools delivered from pkgsrc.'),
    ('column', 'column(1)', 'From BSD.'),
    ('machid', 'machid(1)', ''),
    ('nicstat', 'nicstat', ''),
    ('ssh-removal', 'remove SunSSH', 'SSH is delivered from illumos-extra.'),
    ('onbld-tools', 'build tool changes', 'onbld checks, webrev, build environment.'),
    ('smartos-test', 'smartos-test and test suite adjustments',
     'The smartos-test runner and SmartOS-specific test changes.'),
    ('lx-omnios', 'lx brand as delivered by OmniOS',
     'The Linux-emulating lx brand files exactly as OmniOS has them: '
     'kernel brand module, user-level emulation library, lx procfs, sysfs, '
     'cgroupfs and devfs, lxautofs, lx_netlink and tests.  The next commit '
     'layers the illumos-joyent differences on top.'),
    ('lx', 'lx brand: illumos-joyent changes on top of OmniOS',
     'Brings the lx files from OmniOS\'s versions to illumos-joyent\'s, '
     'and adds what OmniOS does not carry: the lx zone brand scripts and '
     'configuration, the legacy lxproc file system, and the lx(7) and '
     'lxproc(4FS) manual pages.'),
    ('sed', 'sed: keep -i/-I with a required argument',
     'Joyent reverted illumos 586 (sed -i optional argument, --in-place) '
     'in 2011 and has kept the older behavior.'),
    ('sysv-ipc', 'System V IPC: deferred shared memory removal',
     'SHM_RMID marks a shared memory segment for removal at its last '
     'detach instead of removing it immediately (OS-5223).'),
    ('kernel-platform', 'kernel tunables and x86 platform tweaks',
     'Larger default and maximum pid, CPR disabled for GCC builds, quieter '
     'iBFT and lgroup boot messages, PCBE modules under the platform '
     'directory.'),
    ('sched', 'dispatcher: fewer thread migrations',
     'Reduce thread migrations caused by pg_cmt_can_migrate() and by '
     'high-priority threads (OS-2250, OS-2251).'),
    ('compiler-fixes', 'compiler warning fixes in joyent-touched code',
     'Small fixes for newer GCC and smatch.'),
    ('nfs', 'NFS client, server and sharing tweaks',
     'NFS mount transport selection (OS-2679), nfs-server service '
     'ordering (STOR-55), and NFS sharing from delegated datasets in '
     'non-global zones (STOR-54).'),
    ('man-fixes', 'manual page fixes and additions',
     'Manual page corrections and additions not tied to a larger feature, '
     'including swap(4).'),
    ('misc', 'miscellaneous fixes and enhancements',
     'Small changes that do not belong to a larger feature.'),
    ('copyright-residue', 'copyright and whitespace residue',
     'Files whose only differences from illumos-gate are copyright lines, '
     'blank comment lines or whitespace: leftovers of changes that were '
     'reverted or upstreamed.  Candidates for restoring to upstream.'),
    ('integration', 'integration: build system Makefiles and mapfiles',
     'Makefile and mapfile changes shared between the features above: '
     'top-level, cmd, lib, man, test and kernel Makefiles (Makefile.files, '
     'Makefile.intel, Makefile.rules) and library mapfiles.'),
    ('integration-pkg', 'integration: package manifests and man page links',
     'Changes to upstream IPS package manifests, Manlink files and '
     'Targetdirs needed by the features above.'),
    ('integration-drivers', 'integration: driver tables',
     'SmartOS keeps driver_aliases, driver_classes, minor_perm, '
     'name_to_major, path_to_inst and device_policy in the source tree, '
     'where upstream generates them from package manifests.'),
    ('integration-checks', 'integration: checker and repository configuration',
     'Exception lists for the build checks, mancheck.conf, .gitignore '
     'files and the Jenkinsfile.'),
    ('integration-manifest', 'integration: platform image manifests',
     'The SmartOS platform image `manifest` and boot image `boot.manifest`: '
     'every file, directory and link delivered into the ramdisk root.'),
]

# Notes about individual files, printed in the message of whichever
# commit carries the file.  For deliberate divergences from upstream
# that no ticket explains.
FILE_NOTES = {
    'usr/src/cmd/sed/main.c':
        'cmd/sed and sed(1) deliberately lack illumos 586 ("sed -i should '
        'take an optional argument"): joyent reverted it in 58474c20a52 '
        '(2011) and has kept the older behavior, where -i and -I require '
        'an argument and there is no --in-place.',
}
