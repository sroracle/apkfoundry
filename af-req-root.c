/*
 * SPDX-License-Identifier: GPL-2.0-only
 * Copyright (c) 2019-2020 Max Rees
 * See LICENSE for more information.
 */
#define PROG "af-req-root"
#define USAGE PROG " COMMAND [ARGS ...]"
#define BUF_SIZE 4096
#define NUM_FDS 3

#define _XOPEN_SOURCE 700
#include <err.h>        /* err, errx      */
#include <errno.h>      /* errno          */
#include <libgen.h>     /* basename       */
#include <stdlib.h>     /* getenv, strtol */
#include <stdio.h>      /* snprintf       */
#include <string.h>     /* memcpy, strcmp */
#include <sys/socket.h>
#include <unistd.h>     /* *_FILENO       */

#define FATAL_IF(what, why) \
	errno = 0; \
	if (what) \
	err(3, "%s", why);

static void usage(void) {
	errx(1, "usage: %s", USAGE);
}

static int fd_from_env(char *name) {
	int fd;
	char *value;

	value = getenv(name);
	if (value == 0)
		errx(1, "%s is not set", name);

	errno = 0;
	fd = (int) strtol(value, 0, 10);
	if (errno != 0)
		errx(1, "%s=%s is not a valid FD", name, value);

	return fd;
}

static void send_cmd(int sock_fd, int my_fds[NUM_FDS], int argc, int start, char *argv[]) {
	char buf[BUF_SIZE];
	int i, written, remaining, added;
	struct iovec iov;
	struct msghdr msg;
	struct cmsghdr *cmsg;
	unsigned char cbuf[CMSG_SPACE(NUM_FDS * sizeof(int))];

	written = 0;
	for (i = start; i < argc; i++) {
		remaining = BUF_SIZE - written;
		added = snprintf(buf + written, remaining, "%s", argv[i]) + 1;
		if (added >= remaining)
			errx(2, "argv length exceeds maximum size of %d", BUF_SIZE);
		else if (added < 0)
			err(3, "send_cmd snprintf");

		written += added;
	}
	written -= 1;

	iov.iov_base = buf;
	iov.iov_len = written;

	msg.msg_namelen = 0;
	msg.msg_iov = &iov;
	msg.msg_iovlen = 1;
	msg.msg_control = cbuf;
	msg.msg_controllen = sizeof(cbuf);
	msg.msg_flags = 0;

	cmsg = CMSG_FIRSTHDR(&msg);
	cmsg->cmsg_len = CMSG_LEN(NUM_FDS * sizeof(int));
	cmsg->cmsg_level = SOL_SOCKET;
	cmsg->cmsg_type = SCM_RIGHTS;
	memcpy(CMSG_DATA(cmsg), my_fds, NUM_FDS * sizeof(int));

	FATAL_IF(sendmsg(sock_fd, &msg, 0) == -1, "send_cmd sendmsg");
}

static int recv_retcode(int sock_fd) {
	char buf[BUF_SIZE];
	int *rc;

	FATAL_IF(recv(sock_fd, buf, BUF_SIZE, 0) == -1, "recv_retcode recv");
	rc = (int *) buf;
	return *rc;
}

int main(int argc, char *argv[]) {
	int start, sock_fd;
	char *cmd;
	int my_fds[NUM_FDS] = {STDIN_FILENO, STDOUT_FILENO, STDERR_FILENO};

	if (argc == 0)
		usage();

	cmd = basename(argv[0]);
	if (strcmp(cmd, PROG) == 0)
		start = 1;
	else
		start = 0;

	if (argc - start == 0)
		usage();

	sock_fd = fd_from_env("AF_ROOT_FD");

	send_cmd(sock_fd, my_fds, argc, start, argv);
	return recv_retcode(sock_fd);
}
