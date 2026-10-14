#!/bin/sh
#
# Gather the raw data the classifier works from.  Everything lands in
# data/, which is regenerable and not committed.
#
#   ILLUMOS   path to the illumos-joyent clone (default ~/Workspace/illumos)
#   JOYENT    the joyent ref to analyze (default master)
#   BASE      upstream illumos-gate commit (default: upstream parent of the
#             most recent "[illumos-gate merge]" on $JOYENT)
#
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
ILLUMOS=${ILLUMOS:-$HOME/Workspace/illumos}
JOYENT=${JOYENT:-master}
DATA=$HERE/data
export ILLUMOS JOYENT DATA

cd "$ILLUMOS"
if [ -z "$BASE" ]; then
	merge=$(git log -1 --merges --grep='illumos-gate merge' --format=%H "$JOYENT")
	BASE=$(git rev-parse "$merge^2")
fi
BASE=$(git rev-parse "$BASE")
JOYENT_SHA=$(git rev-parse "$JOYENT")
export BASE

rm -rf "$DATA"
mkdir -p "$DATA/blame"
printf 'BASE=%s\nJOYENT=%s\n' "$BASE" "$JOYENT_SHA" > "$DATA/refs"

# Every path that differs, without rename pairing (a rename is a delete
# plus an add, and each side gets its own bucket).
git diff --no-ext-diff --no-renames --name-status "$BASE" "$JOYENT" \
    > "$DATA/delta.txt"

# All joyent-side commits, including merges.
git log --format='%H%x09%P%x09%ad%x09%an <%ae>%x09%s' --date=short "$BASE..$JOYENT" \
    > "$DATA/commits.tsv"

# For each surviving file, credit every line that is '+' relative to BASE
# to the commit blame names.  Restricting to '+' lines matters: on merges
# blame prefers the first (joyent) parent, so lines identical to upstream
# would otherwise be credited to joyent commits.  Lines blamed to BASE or
# earlier come out as BOUNDARY: joyent carries an older upstream line.
awk -F'\t' '$1 != "D" { print $2 }' "$DATA/delta.txt" |
    xargs -P 10 -I{} "$HERE/blame-file.sh" {}

# "Portions contributed by:" credits from commit messages (sometimes the
# whole message is on the subject line, so match anywhere).
git log --format='@@%H%n%B' "$BASE..$JOYENT" | python3 -c '
import re, sys
h = None
for l in sys.stdin:
    if l.startswith("@@"):
        h = l[2:].strip()
        continue
    for who in re.findall(r"[Pp]ortions [Cc]ontributed [Bb]y:\s*([^<>]+<[^<>]+>)", l):
        print(h + "\t" + who.strip())
' > "$DATA/contrib.tsv"

"$HERE/copyright_only.py" > "$DATA/copyright_only.txt"

echo "base $BASE, $(wc -l < "$DATA/delta.txt") paths," \
    "$(wc -l < "$DATA/commits.tsv") commits"
