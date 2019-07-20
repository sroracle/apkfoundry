char const *PROG = "af-req-root";
char const *USAGE = "af-req-root COMMAND [ARGS ...]";
#define BUF_SIZE 4096
#include <errno.h>                // errno
#include <fcntl.h>                // fcntl, F_GETFL, F_SETFL, O_NONBLOCK
#include <libgen.h>               // basename
#include <stdlib.h>               // getenv, strtol

#include <skalibs/bytestr.h>      // str_equal, str_len
#include <skalibs/iopause.h>      // iopause, iopause_fd
#include <skalibs/strerr2.h>      // strerr_*
#include <skalibs/allreadwrite.h> // allread, allwrite, fd_read, fd_write

#define FATAL_IF(what, why) \
	errno = 0; \
	if (what) \
	strerr_diefu1x(errno, why);

int fd_from_env(char *name) {
	int fd;
	char *value;

	value = getenv(name);
	if (value == 0)
		strerr_dienotset(1, name);

	errno = 0;
	fd = (int) strtol(value, 0, 10);
	if (errno != 0)
		strerr_dieinvalid(1, name);

	return fd;
}

void write_user_w(int user_w, int argc, char *argv[], int start) {
	size_t len;

	for (int i = start; i < argc; i++) {
		len = str_len(argv[i]);
		FATAL_IF(
			allwrite(user_w, argv[i], len) == -1,
			"write to AF_USER_W"
		);
		FATAL_IF(allwrite(user_w, " ", 1) == -1, "write to AF_USER_W");
	}
	FATAL_IF(allwrite(user_w, "\n", 1) == -1, "write to AF_USER_W");
}

void empty_ret_r(int ret_r) {
	int old_flags;
	char rc[3];

	FATAL_IF(
		(old_flags = fcntl(ret_r, F_GETFL)) < 0,
		"get AF_RET_R flags"
	);
	FATAL_IF(
		fcntl(ret_r, F_SETFL, old_flags | O_NONBLOCK) == -1,
		"set AF_RET_R as nonblocking"
	);

	for (;;) {
		errno = 0;
		if (fd_read(ret_r, rc, sizeof(rc)) == -1) {
			if (errno == EAGAIN)
				break;
			else
				strerr_diefu1sys(errno, "read from AF_RET_R");
		}
	}

	FATAL_IF(
		fcntl(ret_r, F_SETFL, old_flags) == -1,
		"set AF_RET_R as blocking"
	);
}

void read_root_r(int fd_out, int root_r) {
	char buf[BUF_SIZE];
	ssize_t len = 0;

	errno = 0;
	switch ((len = fd_read(root_r, buf, BUF_SIZE))) {
		case -1:
			if (fd_out == 1)
				strerr_diefu1x(errno, "read from AF_STDOUT_R");
			else
				strerr_diefu1x(errno, "read from AF_STDERR_R");
			break;
		case 0:
			strerr_dief1x(2, "lost connection with server");
			break;
	}

	fd_write(fd_out, buf, len);
}

int read_ret_r(int ret_r) {
	int rc_i;
	char rc_s[5];
	rc_s[4] = 0;

	errno = 0;
	switch (allread(ret_r, rc_s, sizeof(rc_s) - 1)) {
		case -1:
			strerr_diefu1x(errno, "read from AF_RET_R");
			break;
		case 0:
			strerr_dief1x(2, "lost connection with server");
			break;
		case sizeof(rc_s) - 1:
			break;
		default:
			strerr_dief1x(2, "partial read from AF_RET_R");
			break;
	}

	errno = 0;
	rc_i = (int) strtol(rc_s, 0, 10);
	if (errno != 0)
		strerr_dieinvalid(2, "retcode from AF_RET_R");

	return rc_i;
}

int main(int argc, char *argv[]) {
	char *cmd;
	int start;
	int user_w;
	iopause_fd sel_fds[2];
	iopause_fd *sel_stdout = &sel_fds[0];
	iopause_fd *sel_stderr = &sel_fds[1];
	iopause_fd *sel_ret = &sel_fds[2];

	if (argc == 0)
		strerr_dieusage(1, USAGE);

	cmd = basename(argv[0]);
	if (str_equal(cmd, PROG))
		start = 1;
	else
		start = 0;

	if (argc - start == 0)
		strerr_dieusage(1, USAGE);

	user_w = fd_from_env("AF_USER_W");
	sel_stdout->fd = fd_from_env("AF_STDOUT_R");
	sel_stdout->events = IOPAUSE_READ;
	sel_stderr->fd = fd_from_env("AF_STDERR_R");
	sel_stderr->events = IOPAUSE_READ;
	sel_ret->fd = fd_from_env("AF_RET_R");
	sel_ret->events = IOPAUSE_READ;

	empty_ret_r(sel_ret->fd);
	write_user_w(user_w, argc, argv, start);

	for (;;) {
		FATAL_IF(
			iopause(sel_fds, sizeof(sel_fds), 0, 0) == -1,
			"poll"
		);

		if (sel_stdout->revents & IOPAUSE_EXCEPT)
			strerr_diefu1x(2, "read AF_STDOUT_R");
		if (sel_stdout->revents & IOPAUSE_EXCEPT)
			strerr_diefu1x(2, "read AF_STDERR_R");
		if (sel_ret->revents & IOPAUSE_EXCEPT)
			strerr_diefu1x(2, "read AF_RET_R");

		if (sel_stdout->revents & IOPAUSE_READ)
			read_root_r(1, sel_stdout->fd);

		if (sel_stderr->revents & IOPAUSE_READ)
			read_root_r(2, sel_stderr->fd);

		if (sel_ret->revents & IOPAUSE_READ)
			exit(read_ret_r(sel_ret->fd));
	}
}
