# common.py
# Copyright (c) 2018-2020 Pablo Acosta-Serafini
# See LICENSE for details
# pylint: disable=C0111,E1129,R0205,R0912,W0611,W1113

# Standard library imports
import collections
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import types

# PyPI imports
import decorator


###
# Functions
###
def _find_ref_fname(fname, ref_fname):
    """
    Find reference file.

    Start one directory above where current script is located
    """
    curr_dir = ""
    next_dir = os.path.dirname(os.path.abspath(fname))
    while next_dir != curr_dir:
        curr_dir = next_dir
        rcfile = os.path.join(curr_dir, ref_fname)
        if os.path.exists(rcfile):
            return rcfile
        next_dir = os.path.dirname(curr_dir)
    return ""


def _grep(fname, words):
    """Return line numbers in which words appear in a file."""
    # pylint: disable=W0631
    pat = "(.*[^a-zA-Z]|^){}([^a-zA-Z].*|$)"
    regexps = [(word, re.compile(pat.format(word))) for word in words]
    ldict = collections.defaultdict(list)
    for num, line in enumerate(_read_file(fname)):
        for word in [word for word, regexp in regexps if regexp.match(line)]:
            ldict[word].append(num + 1)
    return ldict


def _make_abspath(value):
    """Homogenize files to have absolute paths."""
    value = value.strip()
    if not os.path.isabs(value):
        value = os.path.abspath(os.path.join(os.getcwd(), value))
    return value


def _read_file(fname):
    """Return file lines as strings."""
    with open(fname) as fobj:
        for line in fobj:
            yield _tostr(line).strip()


def _shcmd(cmd, timeout=15):
    """Safely execute shell command."""
    delay = 1.0
    obj = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if sys.hexversion < 0x03000000:
        while (obj.poll() is None) and (timeout > 0):
            time.sleep(delay)
            timeout -= delay
        if not timeout:
            obj.kill()
        stdout, stderr = obj.communicate()
    else:
        try:
            stdout, stderr = obj.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            obj.kill()
            stdout, stderr = obj.communicate()
    if obj.returncode:
        print("COMMAND: " + (" ".join(cmd)))
        print("STDOUT:" + os.linesep + _tostr(stdout))
        print("STDERR:" + os.linesep + _tostr(stderr))
        raise RuntimeError("Shell command could not be executed successfully")
    stdout = _tostr(stdout).split(os.linesep)
    stderr = _tostr(stderr).split(os.linesep)
    return stdout, stderr


def _tostr(obj):  # pragma: no cover
    """Convert to string if necessary."""
    return obj if isinstance(obj, str) else obj.decode()


class StreamFile(object):
    # pylint: disable=R0903
    """Stream class."""

    def __init__(self, lint_file):  # noqa
        self.lint_file = lint_file

    def __enter__(self):  # noqa
        with open(self.lint_file, "r") as fobj:
            for line in fobj:
                yield line

    def __exit__(self, exc_type, exc_value, exc_tb):  # noqa
        return not exc_type is not None


@decorator.contextmanager
def ignored(*exceptions):
    try:
        yield
    except exceptions:
        pass


class TmpFile(object):
    """
    Use a temporary file within context.

    From pmisc package
    """

    def __init__(self, fpointer=None, *args, **kwargs):  # noqa
        if (
            fpointer
            and (not isinstance(fpointer, types.FunctionType))
            and (not isinstance(fpointer, types.LambdaType))
        ):
            raise RuntimeError("Argument `fpointer` is not valid")
        self._fname = None
        self._fpointer = fpointer
        self._args = args
        self._kwargs = kwargs

    def __enter__(self):  # noqa
        fdesc, fname = tempfile.mkstemp()
        # fdesc is an OS-level file descriptor, see problems if this
        # is not properly closed in this post:
        # https://www.logilab.org/blogentry/17873
        os.close(fdesc)
        if platform.system().lower() == "windows":  # pragma: no cover
            fname = fname.replace(os.sep, "/")
        self._fname = fname
        if self._fpointer:
            with open(self._fname, "w") as fobj:
                self._fpointer(fobj, *self._args, **self._kwargs)
        return self._fname

    def __exit__(self, exc_type, exc_value, exc_tb):  # noqa
        with ignored(OSError):
            os.remove(self._fname)
        return not exc_type is not None
