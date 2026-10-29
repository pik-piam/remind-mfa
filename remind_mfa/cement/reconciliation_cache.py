"""File cache for the results of the cement parameter reconciliation.

One cache file is kept per region mapping. It stores the reconciled parameters together with
a hash ("cache key") of everything the result depends on. A cached result is only used if the
stored key equals the key of the current run; otherwise the reconciliation is recomputed and
the file is overwritten.
"""

import hashlib
import logging
import os
import pickle
from pathlib import Path
from typing import TypedDict

import flodym as fd
import numpy as np

import remind_mfa
from remind_mfa.common.common_mfa_system import CommonMFASystem


class ReconciliationCacheEntry(TypedDict):
    """Content of a reconciliation cache file."""

    key: str
    """Hash of all inputs, settings and source code the result depends on."""
    parameters: dict[str, fd.Parameter]
    """Reconciled parameters, as returned by `CementParameterReconciliation.correct_parameters`."""
    mismatch: float
    """Final max |log(td/bu)| reached by the reconciled parameters."""


def get_cache_path(cache_dir: str | Path, region_mapping: str) -> Path:
    """Path of the cache file for one region mapping."""
    return Path(cache_dir) / f"cement_reconciliation_{region_mapping}.pickle"


def compute_cache_key(ref_mfa: CommonMFASystem, settings: dict[str, object]) -> str:
    """Hash everything the reconciliation result depends on.

    The key changes if any of the following changes:
        - the values and dimensions of the input parameters and the trade of `ref_mfa`
          (the flows and stocks of `ref_mfa` are still empty at this point, so they are skipped)
        - the reconciliation settings (e.g. `max_iter`, `tol`)
        - any source file of `remind_mfa` or `flodym`

    Hashing the whole source code is deliberately conservative: also unrelated code changes
    trigger a recompute, but no relevant change can be missed.

    Args:
        ref_mfa: Reference MFA system that is passed to the reconciliation.
        settings: Further arguments that influence the result.

    Returns:
        Hexadecimal SHA-256 hash.
    """
    hasher = hashlib.sha256()

    for name in sorted(ref_mfa.parameters):
        _hash_flodym_array(hasher, f"parameter {name}", ref_mfa.parameters[name])

    for market_name in sorted(ref_mfa.trade_set.markets):
        market = ref_mfa.trade_set.markets[market_name]
        _hash_flodym_array(hasher, f"trade {market_name} imports", market.imports)
        _hash_flodym_array(hasher, f"trade {market_name} exports", market.exports)

    for setting_name in sorted(settings):
        hasher.update(f"setting {setting_name}={settings[setting_name]!r}".encode())

    for package in (remind_mfa, fd):
        _hash_package_source(hasher, package_dir=Path(package.__file__).parent)

    return hasher.hexdigest()


def _hash_flodym_array(hasher: "hashlib._Hash", label: str, array: fd.FlodymArray):
    """Add the dimensions and values of a flodym array to the hash."""
    hasher.update(label.encode())
    for dim in array.dims:
        hasher.update(f"{dim.letter}:{dim.items!r}".encode())
    values = np.ascontiguousarray(array.values)
    hasher.update(f"{values.dtype}{values.shape}".encode())
    hasher.update(values.tobytes())


def _hash_package_source(hasher: "hashlib._Hash", package_dir: Path):
    """Add the content of all python files of a package to the hash.

    Files are hashed by content (not modification time), so checking out the same code
    again yields the same key.
    """
    for source_file in sorted(package_dir.rglob("*.py")):
        relative_path = source_file.relative_to(package_dir).as_posix()
        hasher.update(f"{package_dir.name}/{relative_path}".encode())
        hasher.update(source_file.read_bytes())


def load_cache(cache_path: Path, key: str) -> ReconciliationCacheEntry | None:
    """Load a cache entry if the file exists and was created with the same key.

    Returns:
        The cache entry, or None if there is no usable cache.
    """
    if not cache_path.exists():
        logging.info(f"No reconciliation cache found at {cache_path}.")
        return None

    try:
        with open(cache_path, "rb") as file:
            entry: ReconciliationCacheEntry = pickle.load(file)
    except Exception as error:
        # e.g. a file written with an incompatible version of a class
        logging.warning(f"Could not read reconciliation cache {cache_path} ({error}).")
        return None

    if entry["key"] != key:
        logging.info(
            f"Reconciliation cache at {cache_path} is outdated "
            "(inputs, settings or code changed)."
        )
        return None

    return entry


def save_cache(cache_path: Path, entry: ReconciliationCacheEntry):
    """Write a cache entry, replacing an existing file.

    The entry is first written to a temporary file which then replaces the cache file in one
    step. This way, runs started in parallel never read a half-written file.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = cache_path.with_name(f"{cache_path.name}.{os.getpid()}.tmp")
    with open(temporary_path, "wb") as file:
        pickle.dump(entry, file)
    os.replace(temporary_path, cache_path)
    logging.info(f"Saved reconciliation result to cache {cache_path}.")
