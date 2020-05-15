/*
 * SPDX-License-Identifier: GPL-2.0-only
 * Copyright (c) 2020 Max Rees
 * See LICENSE for more information.
 */
#define PROG "af-su"
#define USAGE PROG " COMMAND [ARGS ...]"

#include <err.h>        /* err, errx              */
#include <unistd.h>     /* execvp, setgid, setuid */

static void usage(void) {
	errx(1, "usage: %s", USAGE);
}

int main(int argc, char *argv[]) {
	if (argc < 2)
		usage();

	if (setuid(0))
		err(2, "setuid");
	if (setgid(0))
		err(2, "setgid");

	argv++;
	if (execvp(argv[0], argv))
		err(2, "execvp");
	return 1;
}
