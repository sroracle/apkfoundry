import asyncio
import json         # JSONDecodeError
import contextlib
import os
import logging


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@contextlib.contextmanager
def chdir_context(new_path):
    curdir = os.getcwd()
    try:
        os.chdir(new_path)
        yield
    finally:
        os.chdir(curdir)

def assert_exists(level, path, asserttype=None):
    # TODO: maybe check length as well?

    level_name = "(root)"
    arg = None

    for arg in path.split("/"):
        if arg not in level:
            raise json.JSONDecodeError(
                f"Missing {arg} in {level_name}", "unused", 0)

        level = level[arg]
        level_name = arg

    if asserttype:
        if not isinstance(level, asserttype):
            raise json.JSONDecodeError(
                f"{arg} was {type(level)} instead of {asserttype}",
                "unused", 0)

    return level

async def run_blocking_command(arglist, env=None, log=None):
    if not log:
        log = asyncio.subprocess.PIPE

    proc = await asyncio.create_subprocess_exec(*arglist, env=env, stdout=log, stderr=log)
    return await proc.wait()

async def get_command_output(args, shell=False, env=None, retcodes=None, stderr=None):
    if stderr:
        stderr = asyncio.subprocess.PIPE
    if not retcodes:
        retcodes = [0]

    if shell:
        proc = await asyncio.create_subprocess_shell(
            *args, env=env, stdout=asyncio.subprocess.PIPE, stderr=stderr)
    else:
        proc = await asyncio.create_subprocess_exec(
            *args, env=env, stdout=asyncio.subprocess.PIPE, stderr=stderr)
    result = await proc.communicate()

    if proc.returncode not in retcodes:
        raise RuntimeError(f"Child exited with status {proc.returncode}")

    if stderr:
        return (proc.returncode, *result)
    else:
        return result[0].decode("utf-8").strip("\n")
