#!/usr/bin/env python3
"""Escalation: hand what the tools cannot do to a person.

An escalation is an issue: written as a Markdown file, title first, so
it can be read or reviewed before anything is published, and opened on
GitHub with `gh issue create` only when a repository is named.
"""
import os
import subprocess


def write_issue(directory, name, title, body):
    """Write DIRECTORY/NAME.md; return its path."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name + '.md')
    with open(path, 'w') as f:
        f.write('# %s\n\n%s' % (title, body))
    return path


def open_issue(repo, title, body, run=subprocess.run):
    """Open an issue on REPO (OWNER/NAME) with gh; return its URL."""
    r = run(['gh', 'issue', 'create', '--repo', repo, '--title', title,
             '--body-file', '-'], input=body, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError('gh issue create failed: %s' % r.stderr)
    return r.stdout.strip()


def escalate(directory, name, title, body, repo=None, run=subprocess.run):
    """Write the issue, and open it on REPO if one is named."""
    write_issue(directory, name, title, body)
    if repo:
        return open_issue(repo, title, body, run)
    return None
