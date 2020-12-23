#!/bin/sh -e
# vi:noet
. /usr/share/abuild/functions.sh
. "$AF_LIBEXEC/af-functions"

if [ -d "$AF_AFTERDIR" ]; then
	export PACKAGER_PRIVKEY="$AF_AFTERDIR/test@example.org.rsa"
	RSYNC_KEY="$AF_AFTERDIR/rsync.key"
	RSYNC_DEST=x.zv.io:rsync-test
	export RSYNC_RSH="
		ssh
		-l sroracle
		-p 6422
		-i '$RSYNC_KEY'
		-o 'IdentitiesOnly yes'
	"

	cd "$REPODEST"

	if [ -e "$PACKAGER_PRIVKEY" ]; then
		af_resign_files
	else
		warning "Could not find '$PACKAGER_PRIVKEY'"
	fi

	if [ -e "$RSYNC_KEY" ]; then
		$SUDO_APK add openssh-client rsync
		af_sync_files "$RSYNC_DEST"
	else
		warning "Could not find '$RSYNC_KEY'"
	fi
fi
