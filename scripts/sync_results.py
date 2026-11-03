#!/usr/bin/env python3
"""Pull a selected experiment-results directory from thor2 with rsync.

The default is a dry run.  This utility is intentionally one-way: it never
deletes destination files and never pushes files to the remote host.

The ``--mkpath`` option requires local rsync 3.2.3 or newer. It lets a dry run
target a destination whose parents do not yet exist.
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path, PurePosixPath


DEFAULT_REMOTE = "thor2:JTPC"
DEFAULT_DESTINATION = Path(__file__).resolve().parents[2] / "JTPC-results" / "thor2"
_HOST_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_ROOT_RE = re.compile(r"^[A-Za-z0-9_./-]+$")
_RELATIVE_RE = re.compile(r"^[A-Za-z0-9_./-]+$")


def _relative_results(value: str) -> str:
    if not value or value.startswith("-") or not _RELATIVE_RE.fullmatch(value):
        raise ValueError("results directory must be a nonempty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError("results directory must be relative and must not contain '..'")
    if not path.parts or path.parts[0] == ".git":
        raise ValueError("results directory must name a directory")
    return "/".join(path.parts)


def _remote(value: str) -> tuple[str, str]:
    host, separator, root = value.partition(":")
    if not separator or host.startswith("-") or not _HOST_RE.fullmatch(host) or not root or not _ROOT_RE.fullmatch(root):
        raise ValueError("remote must have the form HOST:POSIX_ROOT (for example thor2:JTPC)")
    root_path = PurePosixPath(root)
    if any(part == ".." for part in root_path.parts):
        raise ValueError("remote root must not contain '..'")
    return host, root


def build_command(results: str, remote: str, destination: Path, apply: bool) -> list[str]:
    relative = _relative_results(results)
    host, root = _remote(remote)
    source = f"{host}:{root.rstrip('/')}/{relative}/"
    target = destination / Path(*PurePosixPath(relative).parts)
    flags = "-avh" if apply else "-avhn"
    return ["rsync", flags, "--mkpath", "--itemize-changes", "--exclude=.git/", "--", source, f"{target}/"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pull one selected experiment-results directory from thor2; default is a dry run."
    )
    parser.add_argument("results_dir", help="relative directory below the remote JTPC project")
    parser.add_argument("--apply", action="store_true", help="perform the copy (default: rsync dry run)")
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--remote", default=DEFAULT_REMOTE, help="remote project as HOST:POSIX_ROOT")
    args = parser.parse_args(argv)
    try:
        command = build_command(args.results_dir, args.remote, args.destination.expanduser(), args.apply)
    except ValueError as exc:
        parser.error(str(exc))
    target = Path(command[-1][:-1])
    if args.apply:
        target.mkdir(parents=True, exist_ok=True)
    print(shlex.join(command), flush=True)
    try:
        completed = subprocess.run(command, check=False)
    except FileNotFoundError:
        print("error: rsync was not found on PATH", file=sys.stderr)
        return 127
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
