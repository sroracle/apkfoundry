#!/bin/sh -e
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2020 Max Rees
# See LICENSE for more information.
export PATH="$PWD/bin:$PATH"
export PYTHONPATH="$PWD:$PYTHONPATH"
export AF_TESTDIR="tests/tmp"

rm -rf "$AF_TESTDIR"
mkdir -p "$AF_TESTDIR"

if [ "$1" = "-q" ]; then
	quiet=1
	exec 3>"$AF_TESTDIR/log" 4>&3
	shift
else
	exec 3>&1 4>&2
fi

log() {
	printf "$@" >&2
	[ -z "$quiet" ] || printf "$@" >&4
}

failures=0
for test; do
	if ! [ -x "$test" ]; then
		log 'XXXX %s: no such test\n' "${test##*/}"
		failures=$((failures + 1))
		continue
	fi
	log 'TEST %s\n' "${test##*/}"
	if ! "$test" >&3 2>&4; then
		log 'FAIL %s\n' "${test##*/}"
		failures=$((failures + 1))
	else
		log 'PASS %s\n' "${test##*/}"
	fi
done

if [ "$failures" -ne 0 ]; then
	cat >&2 <<-EOF

	Re-run failed tests:
	tests/run-tests.sh [-q] tests/TEST1 [tests/TEST2 ...]

	Output is in tests/tmp/log
EOF
fi

exit "$failures"
