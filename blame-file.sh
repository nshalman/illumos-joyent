#!/bin/sh
#
# blame-file.sh <path>: helper for collect.sh and omnios.py (expects
# ILLUMOS, JOYENT, BASE, DATA in the environment, and cwd inside $ILLUMOS).
#
# Writes <OUT>/<path with / as %> with lines "<count> <commit>", where
# <commit> is a full sha or BOUNDARY, counting only the lines of REV's
# version that are '+' relative to FROM's version.  Blame covers
# BASE..REV.  Defaults: FROM=$BASE, REV=$JOYENT, OUT=$DATA/blame.
#
f="$1"
FROM=${FROM:-$BASE}
REV=${REV:-$JOYENT}
OUT=${OUT:-$DATA/blame}
out="$OUT/$(echo "$f" | tr / %)"

git diff --no-ext-diff --no-renames -U0 "$FROM" "$REV" -- "$f" |
    LC_ALL=C awk '/^@@/ {
	split($3, a, ","); s = substr(a[1], 2); n = (a[2] == "") ? 1 : a[2]
	for (i = 0; i < n; i++) print s + i
    }' > "$out.lines"

if [ -s "$out.lines" ]; then
	git blame --line-porcelain "$BASE..$REV" -- "$f" 2>/dev/null |
	    LC_ALL=C awk -v L="$out.lines" '
		BEGIN { while ((getline x < L) > 0) want[x] = 1 }
		/^[0-9a-f]{40} / { c = $1; ln = $3 }
		/^boundary/ { c = "BOUNDARY" }
		/^\t/ { if (ln in want) n[c]++ }
		END { for (k in n) print n[k], k }' > "$out"
else
	: > "$out"
fi
rm -f "$out.lines"
