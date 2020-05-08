/*
 * SPDX-License-Identifier: GPL-2.0-only
 * Copyright (c) 2020 Max Rees
 * See LICENSE for more information.
 *
 * Based on abuild-rmtemp from abuild:
 * Copyright (c) 2017 Kaarle Ritvanen
 * Copyright (c) 2017 A. Wilcox
 * Copyright (c) 2018 Sören Tempel
 * Distributed under GPL-2
 */
#define PROG "af-rm-container"
#define USAGE PROG " [-n] [-v]"

#define _XOPEN_SOURCE 700
#include <err.h>       /* err, errx                            */
#include <errno.h>     /* errno                                */
#include <ftw.h>
#include <stdio.h>     /* puts, remove                         */
#include <string.h>    /* strcmp, strncmp                      */
#include <unistd.h>    /* F_OK, access, getopt, getuid, optind */

#ifdef __GNUC__
#	define UNUSED __attribute__((unused))
#else
#	define UNUSED
#endif

int verbose = 0;
int dry = 0;
const char *last_fpath = 0;

struct mount {
	size_t len;        /* strlen(dpath) + NUL OR strlen(cpath) */
	const char *dpath; /* keep dir?                            */
	const char *cpath; /* keep contents?                       */
};
#define M0 {0, 0, 0}
/* M(<directory without terminating />, <keep dir?>, <keep contents?>) */
#define M(p, d, c) {sizeof(p), d ? p : 0, c ? p "/" : 0}
/* Paths to exclude from deletion.
 * Note that things like /dev and /proc should already be protected
 * since nftw is called with FTW_MOUNT
 */
const struct mount mounts[] = {
	/* Ancestors of the mounts below */
	M("/af", 1, 0),

	/* System mounts */
	/* These are always mounted, so don't try to remove them. Don't try
	 * to remove the contents of /af/libexec either, it's mounted RO and
	 * its contents are precious anyway.
	 */
	M("/", 1, 0),
	M("/af/libexec", 1, 1),

	/* User-defined mounts */
	/* These should be unmounted - but just in case they aren't, don't
	 * delete their contents. Their contents are precious if they're
	 * mounted from a path outside the container.
	 *
	 * FIXME: /etc/apk/cache should symlink to a directory here instead
	 * of mounting directly to /etc/apk/cache, otherwise its contents
	 * will be deleted if it's not unmounted (which it should be...).
	 */
	M("/af/aports", 0, 1),
	M("/af/build", 0, 1),
	M("/af/repos", 0, 1),
	M("/af/distfiles", 0, 1),

	M0,
};
#undef M
#undef M0

static void usage(void) {
	errx(1, "usage: %s", USAGE);
}

static void fail(const char *msg) {
	err(1, "%s", msg);
}

static int handler(
		const char *fpath,
		UNUSED const struct stat *sb,
		int typeflag,
		UNUSED struct FTW *ftwbuf
	) {
	size_t i;
	last_fpath = fpath;

	for (i = 0; i < sizeof(mounts) && mounts[i].len; i++) {
		if (mounts[i].dpath && typeflag == FTW_DP)
			if (strcmp(fpath, mounts[i].dpath) == 0) {
				if (verbose)
					printf("keep dir: %s\n", fpath);
				return 0;
			}

		if (mounts[i].cpath)
			if (strncmp(fpath, mounts[i].cpath, mounts[i].len) == 0) {
				if (verbose)
					printf("keep contents: %s\n", fpath);
				return 0;
			}
	}

	if (verbose)
		puts(fpath);
	if (!dry)
		return remove(fpath);

	return 0;
}

int main(int argc, char *argv[]) {
	int opt;

	while ((opt = getopt(argc, argv, "nv")) != -1) {
		switch (opt) {
		case 'n':
			dry = 1;
			break;
		case 'v':
			verbose = 1;
			break;
		default:
			usage();
			break;
		}
	}

	if (optind < argc)
		usage();

	if (getuid())
		errx(1, "must be run as root");

	if (access("/af", F_OK))
		errx(1, "not an apkfoundry container");

	if (nftw("/", handler, 512, FTW_DEPTH|FTW_MOUNT|FTW_PHYS))
		fail(last_fpath ? last_fpath : "nftw /");

	return 0;
}
