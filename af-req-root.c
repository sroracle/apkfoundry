char const *PROG = "af-req-root";
char const *USAGE = "af-req-root COMMAND [ARGS ...]";
#define BUF_SIZE 4096
#define NUM_FDS 3

#include <errno.h>                /* errno                   */
#include <libgen.h>               /* basename                */
#include <stdlib.h>               /* getenv, strtol          */
#include <stdio.h>                /* snprintf                */
#include <string.h>               /* memcpy                  */
#include <sys/socket.h>           /* sendmsg                 */
#include <unistd.h>               /* *_FILENO                */

#include <skalibs/bytestr.h>      /* str_equal               */
#include <skalibs/strerr2.h>      /* strerr_*                */
#include <skalibs/webipc.h>       /* ipc_connect             */

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

void send_cmd(int sock_fd, int my_fds[NUM_FDS], int argc, int start, char *argv[]) {
	char buf[BUF_SIZE];
	int i, written, remaining, added;
	struct iovec iov;
	struct msghdr msg;
	struct cmsghdr *cmsg;
	unsigned char cbuf[CMSG_SPACE(NUM_FDS * sizeof(int))];

	written = 0;
	for (i = start; i < argc; i++) {
		remaining = BUF_SIZE - written;
		added = snprintf(buf + written, remaining, "%s ", argv[i]);
		if (added >= remaining)
			strerr_dief1x(2, "argv too long");
		else if (added < 0)
			strerr_diefu1x(3, "snprintf argv");

		written += added;
	}

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

	FATAL_IF(sendmsg(sock_fd, &msg, 0) == -1, "send cmd");
}

int recv_retcode(int sock_fd) {
	char buf[BUF_SIZE];
	int *rc;

	FATAL_IF(recv(sock_fd, buf, BUF_SIZE, 0) == -1, "receive retcode");
	rc = (int *) buf;
	return *rc;
}

int main(int argc, char *argv[]) {
	int start, sock_fd;
	char *cmd;
	int my_fds[NUM_FDS] = {STDIN_FILENO, STDOUT_FILENO, STDERR_FILENO};

	if (argc == 0)
		strerr_dieusage(1, USAGE);

	cmd = basename(argv[0]);
	if (str_equal(cmd, PROG))
		start = 1;
	else
		start = 0;

	if (argc - start == 0)
		strerr_dieusage(1, USAGE);

	sock_fd = fd_from_env("AF_ROOT_FD");

	send_cmd(sock_fd, my_fds, argc, start, argv);
	return recv_retcode(sock_fd);
}
