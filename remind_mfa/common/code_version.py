"""Version of the running remind-mfa code: package version and git commit."""

import os
import subprocess
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Self

PROJECT_ROOT = Path(__file__).parents[2]
"""Root of the remind-mfa checkout, if the code runs from one."""

SHORT_SHA_LENGTH = 8
"""Number of hex digits of the short commit."""

UNKNOWN = "unknown"
"""Stands for a package version or commit that cannot be determined."""


class GitCheckout:
    """Git checkout rooted at a given folder."""

    def __init__(self, root: Path):
        self.root = root

    def _git(self, *args: str) -> str | None:
        """Run a git command in the checkout.

        Args:
            *args: Arguments of the git command.

        Returns:
            Output of the command, None if git is not installed or the command fails.
        """
        command = ["git", "-C", str(self.root), *args]
        try:
            result = subprocess.run(command, capture_output=True, check=True)
        except OSError, subprocess.CalledProcessError:
            return None
        return result.stdout.decode("utf-8", errors="surrogateescape")

    def head_sha(self) -> str | None:
        """Commit that is checked out.

        Returns:
            Full sha of the commit, None if `root` is not the root of a git checkout. A folder
            inside another repository, such as an installed package in the virtual environment of
            another project, does not count: that commit would not describe the code.
        """
        output = self._git("rev-parse", "--show-toplevel", "HEAD")
        if output is None:
            return None
        lines = output.splitlines()
        if len(lines) != 2 or not os.path.samefile(lines[0], self.root):
            return None
        return lines[1]


@dataclass(frozen=True)
class CodeVersion:
    """Version of the remind-mfa code: the package version and the commit."""

    remind_mfa_version: str
    """Version of the remind-mfa package."""
    git_sha: str | None = None
    """Commit that is checked out, None if the code does not run from a git checkout."""

    @property
    def short_sha(self) -> str:
        """Abbreviated commit, `unknown` if the code does not run from a git checkout."""
        return self.git_sha[:SHORT_SHA_LENGTH] if self.git_sha else UNKNOWN

    @classmethod
    def detect(cls, root: Path = PROJECT_ROOT) -> Self:
        """Determine the version of the code in a folder.

        Args:
            root: Root of the remind-mfa checkout.
        """
        try:
            remind_mfa_version = version("remind-mfa")
        except PackageNotFoundError:
            remind_mfa_version = UNKNOWN
        return cls(remind_mfa_version, GitCheckout(root).head_sha())
