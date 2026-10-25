"""Tests that the flodym designer manifest in `pyproject.toml` lists the files the models read."""

import fnmatch
import importlib
import os
import sys
import tomllib
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

import pytest

from remind_mfa.common.helpers import ModelNames
from remind_mfa.designer import REPO_ROOT, load

with (REPO_ROOT / "pyproject.toml").open("rb") as pyproject_file:
    MANIFEST = tomllib.load(pyproject_file)["tool"]["flodym-designer"]
ENTRIES = MANIFEST["entries"]
HAS_INPUT_DATA = (REPO_ROOT / "data_in" / "parameters" / "rev.txt").exists()


def matches_glob(path: str, pattern: str) -> bool:
    """Check whether a relative POSIX path matches a glob, where `**` matches any number of
    path segments and other wildcards stay within a segment."""
    return _matches_segments(path.split("/"), pattern.split("/"))


def _matches_segments(path_segments: list[str], pattern_segments: list[str]) -> bool:
    if not pattern_segments:
        return not path_segments
    pattern_head, *pattern_rest = pattern_segments
    if pattern_head == "**":
        return any(
            _matches_segments(path_segments[start:], pattern_rest)
            for start in range(len(path_segments) + 1)
        )
    return (
        bool(path_segments)
        and fnmatch.fnmatchcase(path_segments[0], pattern_head)
        and _matches_segments(path_segments[1:], pattern_rest)
    )


def is_in_manifest(path: str, entry_name: str) -> bool:
    """Check whether the manifest makes a file available to the given entry."""
    patterns = [*MANIFEST["files"], *ENTRIES[entry_name]["files"]]
    is_included = any(matches_glob(path, pattern) for pattern in patterns)
    is_excluded = any(matches_glob(path, pattern) for pattern in MANIFEST["exclude"])
    return is_included and not is_excluded


class OpenedFilesRecorder:
    """Records the paths of the files opened while recording, using an audit hook.

    Audit hooks cannot be removed, so create a single recorder and reuse it.
    """

    def __init__(self):
        self._paths: list[str] | None = None
        sys.addaudithook(self._audit_hook)

    def _audit_hook(self, event: str, args: tuple) -> None:
        if event == "open" and self._paths is not None and not isinstance(args[0], int):
            self._paths.append(os.path.abspath(os.fsdecode(args[0])))

    @contextmanager
    def record(self) -> Generator[list[str]]:
        self._paths = []
        try:
            yield self._paths
        finally:
            self._paths = None


@pytest.fixture(scope="module")
def opened_files_recorder() -> OpenedFilesRecorder:
    return OpenedFilesRecorder()


def to_manifest_path(path: str, aliases: dict[Path, PurePosixPath]) -> str | None:
    """Express an absolute path relative to `pyproject.toml`, or return None if it is outside
    the repository or belongs to the Python environment."""
    absolute_path = Path(path)
    environment_paths = {Path(sys.prefix), Path(sys.base_prefix)}
    if any(absolute_path.is_relative_to(prefix) for prefix in environment_paths):
        return None
    if "__pycache__" in absolute_path.parts:
        return None
    for target, alias in aliases.items():
        if absolute_path.is_relative_to(target):
            return (alias / absolute_path.relative_to(target).as_posix()).as_posix()
    return None


def test_every_model_has_an_entry_that_points_to_load():
    entry_models = {entry["args"]["model"] for entry in ENTRIES.values()}
    assert entry_models == {model.value for model in ModelNames}
    for entry in ENTRIES.values():
        module_name, function_name = entry["call"].split(":")
        assert getattr(importlib.import_module(module_name), function_name) is load
        assert entry["title"]


@pytest.mark.parametrize("entry_name", list(ENTRIES))
def test_tracked_inputs_are_in_manifest(entry_name: str):
    sources = [path.relative_to(REPO_ROOT) for path in (REPO_ROOT / "remind_mfa").rglob("*.py")]
    scenarios = [
        path.relative_to(REPO_ROOT) for path in (REPO_ROOT / "config" / "scenarios").glob("*.csv")
    ]
    tracked_inputs = [*sources, *scenarios, Path("config") / "default.toml"]

    missing = [path for path in tracked_inputs if not is_in_manifest(path.as_posix(), entry_name)]

    assert not missing


@pytest.mark.skipif(not HAS_INPUT_DATA, reason="Input data is not available.")
@pytest.mark.parametrize("entry_name", list(ENTRIES))
def test_files_read_by_entry_are_in_manifest(
    entry_name: str, opened_files_recorder: OpenedFilesRecorder
):
    with opened_files_recorder.record() as opened_paths:
        designer_model = load(**ENTRIES[entry_name]["args"], configs=["default"], root=REPO_ROOT)
        assert designer_model.systems
        designer_model.run()

    # map the resolved data paths back to the configured relative ones, in case they are symlinks
    with (REPO_ROOT / "config" / "default.toml").open("rb") as config_file:
        configured_input_cfg = tomllib.load(config_file)["base"]["input"]
    resolved_input_cfg = designer_model.cfg["input"]
    aliases = {
        Path(resolved_input_cfg[key]): PurePosixPath(configured_input_cfg[key])
        for key in ("input_data_path", "scenarios_path")
    }
    aliases[REPO_ROOT] = PurePosixPath(".")
    read_files = {to_manifest_path(path, aliases) for path in opened_paths} - {None}

    assert {"config/default.toml", "data_in/parameters/rev.txt"} <= read_files
    missing = sorted(path for path in read_files if not is_in_manifest(path, entry_name))
    assert not missing


def test_manifest_excludes_outputs_and_environment():
    entry_patterns = [pattern for entry in ENTRIES.values() for pattern in entry["files"]]
    patterns = [*MANIFEST["files"], *entry_patterns]
    excluded_folders = ("madrat_output", "data", "data_out", ".venv")

    assert not [pattern for pattern in patterns if pattern.split("/")[0] in excluded_folders]
