#!/bin/sh -e
# vi:noet
. "$AF_LIBEXEC/af-functions"

"${0%/*}/refresh"

# If the hosts(5) and/or resolv.conf(5) are unmodified, apk will try to
# overwrite them even though they are read-only. So we work around it
# using symlinks.
rm -f /etc/hosts /etc/resolv.conf
ln -sr /af/hosts /etc/hosts
ln -sr /af/resolv.conf /etc/resolv.conf

apk upgrade -Ual
ln -sr /usr/share/zoneinfo/UTC /etc/localtime

af_mkuser
af_userconf

# Copy temporary public key to uploads directory
(
	. "$ABUILD_USERCONF"
	cp "$PACKAGER_PRIVKEY.pub" "$REPODEST"
)
