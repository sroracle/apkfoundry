#!/bin/sh -e
# vi:noet
. "$AF_LIBEXEC/af-functions"

"${0%/*}/refresh"

apk upgrade -Ual
ln -sr /usr/share/zoneinfo/UTC /etc/localtime

af_mkuser
af_userconf

# Copy temporary public key to uploads directory
(
	. "$ABUILD_USERCONF"
	cp "$PACKAGER_PRIVKEY.pub" "$REPODEST"
)
