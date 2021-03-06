#!/bin/sh -e
# vi:noet
# Disable colors if logging to a separate file (see below)
#export USE_COLORS=

. /usr/share/abuild/functions.sh
. "$AF_LIBEXEC/af-functions"

# Logging each build to a separate file: (make sure to update
# .gitlab-ci.yml to save artifacts if necessary):
#
#af_loginit -at

printf "${STRONG}>>> Upgrading container${NORMAL}\n" >&2
$SUDO_APK upgrade --available --latest

printf "${STRONG}>>> Adding extra dependencies${NORMAL}\n" >&2
case "$1" in
# configure: error: GNAT is required to build ada
system/gcc) $SUDO_APK add -t .makedepends-gcc-self gcc-gnat;;
esac

printf "${STRONG}>>> abuild -r${NORMAL}\n" >&2
af_abuild

printf "${STRONG}>>> checkapk${NORMAL}\n" >&2
"$AF_LIBEXEC/checkapk"
