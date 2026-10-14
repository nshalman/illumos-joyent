# Commit order and descriptions for the restructured branch.
# Every bucket classify.py can emit must appear here exactly once.
#
# (bucket, subject, body)
BUCKETS = [
    ('brand-kernel', 'kernel and libc hooks for branded zones (lx)',
     'Generic kernel and libc changes driven mostly by the lx brand: brand '
     'operations and their callers in exec, fork, exit, lwp and signal '
     'delivery; native-root handling; Linux-flavored semantics in poll/'
     'epoll, eventfd, signalfd, timers, fifos, sockets and rctls; truss '
     'and libproc support.  Also the sn1/s10 brand updates for the new '
     'brand ops.'),
    ('zone-kernel', 'zones: kernel zone extensions and resource management',
     'zone.c/zone.h extensions and per-zone resource management: physical '
     'memory caps and accurate RSS tracking, in-kernel page invalidation, '
     'vm_getusage improvements, CPU caps with bursting, FX/RT high-priority '
     'zones, zone-aware privileges, restricting kmem/physmem access from '
     'zones, and rcapd/rcapstat.'),
    ('zones-tools', 'zones: zoneadm, zoneadmd, zonecfg and libzonecfg extensions',
     'Userland zone management changes for SmartOS: additional zonecfg '
     'properties, zoneadmd logging and console handling, persistent zone '
     'IDs, native-root awareness.'),
    ('zone-brands', 'zones: joyent, joyent-minimal, builder, bhyve and kvm brands',
     'The SmartOS native and HVM zone brands.  See joyent(7).'),
    ('zfd', 'zfd(4D) zone file descriptor devices',
     'Zone fd devices used to connect zone stdio (e.g. docker-style '
     'containers) to zoneadmd.'),
    ('datalink', 'per-zone datalinks and link protection',
     'Per-zone datalink names (every zone has its own net0), dlmgmtd/'
     'libdladm/dls/dld support, ipmgmtd/ipadm counterparts, and VNIC '
     'protection: allowed-ips, allowed-dhcp-cids, dynamic methods.'),
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
    ('zfs', 'ZFS changes', 'SmartOS ZFS changes not upstream, and test adjustments.'),
    ('zfs-zone-io', 'ZFS zone I/O throttling and observability',
     'Per-zone ZFS I/O throttling, plus vfsstat/ziostat/arcstat/zfscache.'),
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
    ('ctf', 'CTF tooling differences', 'ctf conversion uses the native root.'),
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
    ('lx', 'lx brand', 'The Linux-emulating lx brand: kernel, user-level '
     'emulation library, lx procfs/sysfs/cgroupfs/devfs, lxautofs, '
     'lx_netlink, and the lx test skip lists.'),
    ('misc', 'miscellaneous fixes and enhancements',
     'Small changes that do not belong to a larger feature.'),
    ('copyright-residue', 'copyright and whitespace residue',
     'Files whose only differences from illumos-gate are copyright lines, '
     'blank comment lines or whitespace: leftovers of changes that were '
     'reverted or upstreamed.  Candidates for restoring to upstream.'),
    ('integration', 'integration: build system, packaging and platform manifests',
     'Files shared between the features above: top-level and kernel '
     'Makefiles, Makefile.files, driver tables, package manifests, '
     'exception lists, the platform `manifest`.'),
]
