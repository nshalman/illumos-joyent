#!/usr/bin/env python3
"""Tests for manifest.py, which keeps the top-level manifest in step
with gate's package manifests.

The cases mirror updates master made by hand in 2026: see
replay/2026-10-21-small on the meta/state branch.

  python3 test_manifest.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manifest  # noqa: E402
from test_ft import FtTest, lines  # noqa: E402

PKG = 'usr/src/pkg/manifests/'
Z = 'usr/share/lib/zoneinfo'

OLD_GATE = {
    PKG + 'system-data-zoneinfo.p5m': lines(
        '# zoneinfo',
        '<transform file -> default mode 0644>',
        'set name=pkg.fmri value=pkg:/system/data/zoneinfo',
        'dir  path=%s' % Z,
        'file path=%s/America/Chicago' % Z,
        'file path=%s/Brazil/West' % Z,
        'hardlink path=%s/CST6CDT target=America/Chicago' % Z,
        'file path=%s/Old' % Z),
    PKG + 'SUNWcs.man1.inc': lines(
        'file path=usr/share/man/man1/pack.1',
        'link path=usr/share/man/man1/unpack.1 target=pack.1'),
    PKG + 'system-test-ostest.p5m': lines(
        'file path=opt/os-tests/tests/a mode=0555'),
}

NEW_GATE = {
    PKG + 'system-data-zoneinfo.p5m': lines(
        '# zoneinfo',
        '<transform file -> default mode 0644>',
        'set name=pkg.fmri value=pkg:/system/data/zoneinfo',
        'dir  path=%s' % Z,
        'file path=%s/America/Chicago' % Z,
        'file path=%s/Brazil/West' % Z,
        'file path=%s/CST6CDT' % Z,
        'file path=%s/tool \\' % Z,
        '    mode=0555'),
    PKG + 'SUNWcs.man1.inc': lines(
        'file path=usr/share/man/man1/pack.1',
        'link path=usr/share/man/man1/unpack.1 target=pack.1',
        'file path=usr/share/man/man1/userattr.1',
        'link path=usr/share/man/man1/zz.1 target=pack.1'),
    PKG + 'system-test-ostest.p5m': lines(
        'file path=opt/os-tests/tests/a mode=0555',
        'file path=opt/os-tests/tests/close_range.32 mode=0555'),
}

MANIFEST = lines(
    '#',
    '# The platform image manifest',
    '#',
    'd %s 0755 root bin' % Z,
    'f %s/America/Chicago 0644 root bin' % Z,
    'f %s/Brazil/West 0644 root bin' % Z,
    'h %s/CST6CDT=%s/America/Chicago' % (Z, Z),
    'f %s/Old 0644 root bin' % Z,
    'f usr/share/man/man1/pack.1 0444 root bin',
    's usr/share/man/man1/unpack.1=pack.1')

SYNCED = lines(
    '#',
    '# The platform image manifest',
    '#',
    'd %s 0755 root bin' % Z,
    'f %s/America/Chicago 0644 root bin' % Z,
    'f %s/Brazil/West 0644 root bin' % Z,
    'f %s/CST6CDT 0644 root bin' % Z,
    'f %s/tool 0555 root bin' % Z,
    'f usr/share/man/man1/pack.1 0444 root bin',
    's usr/share/man/man1/unpack.1=pack.1',
    'f usr/share/man/man1/userattr.1 0444 root bin',
    's usr/share/man/man1/zz.1=pack.1')


class ParseTest(unittest.TestCase):

    def test_actions_join_continuations_and_skip_the_rest(self):
        acts = manifest.parse_p5m(NEW_GATE[PKG + 'system-data-zoneinfo.p5m'])
        self.assertEqual([(k, a['path']) for k, a in acts][-1],
                         ('file', Z + '/tool'))
        self.assertEqual(acts[-1][1]['mode'], '0555')
        self.assertNotIn('set', [k for k, _ in acts])

    def test_macros(self):
        acts = manifest.parse_p5m(lines(
            'file path=usr/lib/$(ARCH64)/libx.so.1',
            '$(i386_ONLY)file path=kernel/drv/$(ARCH64)/x',
            '$(sparc_ONLY)file path=kernel/drv/sparcv9/x',
            'file path=usr/lib/python$(PYVER)/x.py',
            'file path="usr/share/a b"'))
        self.assertEqual([a['path'] for _, a in acts],
                         ['usr/lib/amd64/libx.so.1', 'kernel/drv/amd64/x',
                          'usr/share/a b'])


class SyncTest(FtTest):

    def setUp(self):
        super().setUp()
        self.old = self.r.commit(OLD_GATE, msg='old gate')
        self.new = self.r.commit(NEW_GATE, parent=self.old, msg='new gate')

    def test_sync_follows_gate(self):
        text, report = manifest.sync(self.g, self.old, self.new,
                                     MANIFEST.encode())
        self.assertEqual(text.decode(), SYNCED)
        self.assertEqual(sorted(report['added']),
                         [Z + '/tool', 'usr/share/man/man1/userattr.1',
                          'usr/share/man/man1/zz.1'])
        self.assertEqual(report['changed'], [Z + '/CST6CDT'])
        self.assertEqual(report['removed'], [Z + '/Old'])
        self.assertEqual(report['not shipped'],
                         ['opt/os-tests/tests/close_range.32'])

    def test_no_gate_change_no_manifest_change(self):
        text, report = manifest.sync(self.g, self.old, self.old,
                                     MANIFEST.encode())
        self.assertEqual(text.decode(), MANIFEST)
        self.assertEqual(report['added'], [])

    def test_path_declared_by_several_packages(self):
        # Directories are often declared by many packages, with and
        # without attributes.
        dirs = {PKG + 'one.p5m': 'dir path=usr/share/x mode=0755\n',
                PKG + 'two.p5m': 'dir path=usr/share/x\n'}
        old = self.r.commit(dict(OLD_GATE, **dirs), msg='old')
        new = self.r.commit(dict(NEW_GATE, **dirs), parent=old, msg='new')
        text, report = manifest.sync(self.g, old, new, MANIFEST.encode())
        self.assertEqual(text.decode(), SYNCED)

    def test_new_directory_takes_attributes_from_above(self):
        # 17974 added usr/lib/fm/topo/plugins/$(ARCH64)/: nothing is
        # listed there yet, so owner and group come from the parent.
        fm = PKG + 'service-fault-management.p5m'
        old_pkg = lines('dir path=usr/lib/fm/topo/plugins',
                        'file path=usr/lib/fm/topo/plugins/dimm.so mode=0555')
        new_pkg = old_pkg + lines(
            'dir path=usr/lib/fm/topo/plugins/$(ARCH64)',
            'file path=usr/lib/fm/topo/plugins/$(ARCH64)/dimm.so mode=0555')
        old = self.r.commit({fm: old_pkg}, msg='old')
        new = self.r.commit({fm: new_pkg}, parent=old, msg='new')
        listed = lines('d usr/lib/fm/topo/plugins 0755 root bin',
                       'f usr/lib/fm/topo/plugins/dimm.so 0555 root bin')
        text, report = manifest.sync(self.g, old, new, listed.encode())
        self.assertEqual(text.decode(), lines(
            'd usr/lib/fm/topo/plugins 0755 root bin',
            'd usr/lib/fm/topo/plugins/amd64 0755 root bin',
            'f usr/lib/fm/topo/plugins/amd64/dimm.so 0555 root bin',
            'f usr/lib/fm/topo/plugins/dimm.so 0555 root bin'))
        self.assertEqual(report['no attributes'], [])

    def test_sync_feature_commits_on_the_owner(self):
        rebased = self.r.commit(dict(NEW_GATE, manifest=MANIFEST),
                                parent=self.new, msg='manifest feature')
        commit, report = manifest.sync_feature(self.g, self.old, self.new,
                                               rebased)
        self.assertEqual(self.r.files(commit)['manifest'], SYNCED)
        self.assertEqual(self.r.git('rev-parse', commit + '^'), rebased)
        self.assertIsNone(manifest.sync_feature(self.g, self.old, self.new,
                                                self.new)[0])


if __name__ == '__main__':
    unittest.main()
