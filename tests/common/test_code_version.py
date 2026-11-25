"""Tests for the version of the code, which is read from the git checkout."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from remind_mfa.common.code_version import CodeVersion

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def git(repository: Path, *args: str) -> str:
    """Run a git command in a test repository and return its output."""
    command = ["git", "-C", str(repository), *args]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Committed checkout with a source file."""
    # Keep the user's git configuration and the repository of a calling git hook out of the tests
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)

    repository = tmp_path / "checkout"
    (repository / "remind_mfa").mkdir(parents=True)
    (repository / "remind_mfa" / "model.py").write_text("result = 1\n", encoding="utf-8")
    git(repository, "init", "--quiet")
    git(repository, "add", "--all")
    identity = ["-c", "user.name=Test", "-c", "user.email=test@example.org"]
    git(repository, *identity, "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "initial")
    return repository


def test_version_outside_of_a_checkout_has_no_commit(tmp_path: Path):
    version = CodeVersion.detect(tmp_path)

    assert version.remind_mfa_version
    assert version.git_sha is None


@requires_git
def test_checkout_has_its_commit(checkout: Path):
    version = CodeVersion.detect(checkout)

    sha = git(checkout, "rev-parse", "HEAD")
    assert version.git_sha == sha


@requires_git
def test_folder_inside_another_checkout_has_no_commit(checkout: Path):
    """The commit of an enclosing repository does not describe the code in a subfolder."""
    version = CodeVersion.detect(checkout / "remind_mfa")

    assert version.git_sha is None
