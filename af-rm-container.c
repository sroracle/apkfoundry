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
#include <err.h>       /* err, errx              */
#include <errno.h>     /* errno                  */
#include <ftw.h>
#include <grp.h>       /* getgrnam               */
#include <stdio.h>     /* puts, remove           */
#include <string.h>    /* strcmp, strncmp        */
#include <sys/stat.h>  /* stat                   */
#include <unistd.h>    /* getopt, getuid, optind */

int verbose = 0;
int dry = 0;
const char *last_fpath = 0;

/* Don't try to remove these directories */
const char *m_dirs[] = {
	/* Ancestors of the mounts below */
	"/af",
	"/var",

	/* System mounts */
	"/",
	"/af/libexec",
	"/tmp",
	"/var/tmp",

	/* User-defined mounts */
	"/af/aports",
	"/af/build",
	"/af/repos",
	"/af/distfiles",
	0,
};

/* Don't delete anything under these paths. Note that things like /dev
 * and /proc should already be protected since nftw is called with
 * FTW_MOUNT
 */
const char *m_contents[] = {
	/* Intentionally exclude this since we DO want to delete its
	 * contents, unless otherwise already excluded
	 *
	 * "/",
	 */
	"/af/libexec/",
	/* Ditto
	 *
	 * "/tmp/",
	 * "/var/tmp/",
	 */

	"/af/aports/",
	"/af/build/",
	"/af/repos/",
	"/af/distfiles/",
	0,
};

static void usage(void) {
	errx(1, "usage: %s", USAGE);
}

static void fail(const char *msg) {
	err(1, "%s", msg);
}

static int handler(const char *fpath, const struct stat *sb, int typeflag, struct FTW *ftwbuf) {
	int i;

	for (i = 0; i < sizeof(m_contents) && m_contents[i]; i++)
		if (strncmp(fpath, m_contents[i], sizeof(m_contents[i])) == 0)
			return 0;

	if (typeflag == FTW_D || typeflag == FTW_DP)
		for (i = 0; i < sizeof(m_dirs) && m_dirs[i]; i++)
			if (strcmp(fpath, m_dirs[i]) == 0)
				return 0;

	last_fpath = fpath;
	if (verbose)
		puts(fpath);
	if (!dry)
		return remove(fpath);

	return 0;
}

int main(int argc, char *argv[]) {
	int opt;
	struct stat s;
	struct group *g;

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

	if (getuid())
		errx(1, "must be run as root");

	if (optind < argc)
		usage();

	if (stat("/", &s))
		fail("stat /");

	errno = 0;
	g = getgrnam("apkfoundry");
	if (!g) {
		if (errno)
			fail("getgrnam apkfoundry");
		else
			errx(1, "apkfoundry group not found");
	}

	if (s.st_gid != g->gr_gid)
		errx(1, "not an apkfoundry container");

	if (nftw("/", handler, 512, FTW_DEPTH|FTW_MOUNT|FTW_PHYS))
		fail(last_fpath ? last_fpath : "nftw /");

	return 0;
}
