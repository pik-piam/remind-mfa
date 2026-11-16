"""File cache for the results of the cement parameter reconciliation.

One cache file is kept per region mapping. It stores the log-corrections δ of the reconciled
parameters together with a hash ("cache key") of everything the result depends on (see
`ReconciliationCache`).
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
from remind_mfa.cement.cement_parameter_reconciliation import CementParameterReconciliation
from remind_mfa.common.common_mfa_system import CommonMFASystem


class ReconciliationCacheContent(TypedDict):
    """Content of a reconciliation cache file."""

    key: str
    """Hash of all inputs, settings and source code the result depends on."""
    delta: dict[str, fd.FlodymArray]
    """Log-corrections δ of the reconciled parameters, as stored in
    `CementParameterReconciliation.delta`. The parameters are rebuilt from them with
    `CementParameterReconciliation.calc_corrected_parameters`."""
    mismatch: float
    """Final max |log(td/bu)| reached by the reconciled parameters."""


def compute_cache_key(ref_mfa: CommonMFASystem, settings: dict[str, object]) -> str:
    """Hash everything the reconciliation result depends on.

    The key changes if any of the following changes:
        - the values and dimensions of the input parameters and the trade of `ref_mfa`
          (the flows and stocks of `ref_mfa` are still empty at this point, so they are skipped)
        - the reconciliation settings (e.g. `max_iter`, `tol_r`, `tol_step`)
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


class ReconciliationCache:
    """Cache file of the parameter reconciliation of one region mapping.

    A cached result is used if it was created from the same inputs, settings and code (`key`),
    and if the parameters corrected by its δ still reconcile the stocks. Otherwise, the
    reconciliation has to be recomputed and the file is overwritten. With `force_use`, the δ of
    an existing file is applied to the current input parameters without these checks (e.g. to
    apply the reconciliation of one scenario to all scenarios); the reached mismatch is only
    logged.

    Args:
        cache_dir: Folder of the cache files, which holds one file per region mapping.
        region_mapping: Region mapping of the current run.
        ref_mfa: Reference MFA system that is passed to the reconciliation.
        settings: Further arguments that influence the result (see `compute_cache_key`).
    """

    def __init__(
        self,
        cache_dir: str | Path,
        region_mapping: str,
        ref_mfa: CommonMFASystem,
        settings: dict[str, object],
    ):
        self.path = Path(cache_dir) / f"cement_reconciliation_{region_mapping}.pickle"
        """Path of the cache file."""
        self.key = compute_cache_key(ref_mfa, settings)
        """Hash of the inputs, settings and code of the current run."""

    def load(self, reconciliation: CementParameterReconciliation, force_use: bool) -> bool:
        """Set the cached log-corrections δ as the result of the reconciliation (`delta`,
        `output_prms`, `final_mismatch`), as after
        `CementParameterReconciliation.correct_parameters`.

        Args:
            reconciliation: Reconciliation set up with the input parameters of the current run.
            force_use: Whether to use an existing file without checking key and mismatch.

        Returns:
            Whether the cached result is used. If not, the reconciliation has to be computed.
        """
        cached = self._read(check_key=not force_use)
        if cached is None:
            return False

        reconciliation.delta = cached["delta"]
        reconciliation.output_prms = reconciliation.calc_corrected_parameters(cached["delta"])
        mismatch = reconciliation.calc_mismatch(
            reconciliation.output_prms,
            label="force-used cached result" if force_use else "cached result",
        )
        reconciliation.final_mismatch = mismatch

        if force_use:
            logging.warning(
                f"Reusing reconciliation cache {self.path} without checking that it was created "
                f"from the current inputs. Its corrections reach a mismatch of {mismatch:.4f} "
                f"for the current stocks (stored: {cached['mismatch']:.4f})."
            )
            return True

        # The mismatch is recomputed from scratch, so it must equal the stored one (up to
        # rounding).
        if mismatch <= cached["mismatch"] + 1e-9:
            logging.info(f"Using cached reconciliation result from {self.path}.")
            return True
        logging.warning(
            f"Cached reconciliation result from {self.path} does not reconcile the stocks "
            f"(mismatch {mismatch:.4f}, expected {cached['mismatch']:.4f}). "
            "Recomputing and overwriting the cache."
        )
        return False

    def save(self, reconciliation: CementParameterReconciliation):
        """Save the log-corrections δ and the mismatch of a computed reconciliation."""
        self._write(
            {
                "key": self.key,
                "delta": reconciliation.delta,
                "mismatch": reconciliation.final_mismatch,
            }
        )

    def _read(self, check_key: bool = True) -> ReconciliationCacheContent | None:
        """Read the cache entry if the file exists and was created with the same key.

        Args:
            check_key: Whether to check the key. If False, any existing file is read, as long
                as it stores log-corrections (files of older versions stored the corrected
                parameters).

        Returns:
            The cache entry, or None if there is no usable cache.
        """
        if not self.path.exists():
            logging.info(f"No reconciliation cache found at {self.path}.")
            return None

        try:
            with open(self.path, "rb") as file:
                entry: ReconciliationCacheContent = pickle.load(file)
        except Exception as error:
            # e.g. a file written with an incompatible version of a class
            logging.warning(f"Could not read reconciliation cache {self.path} ({error}).")
            return None

        if check_key and entry["key"] != self.key:
            logging.info(
                f"Reconciliation cache at {self.path} is outdated "
                "(inputs, settings or code changed)."
            )
            return None

        if "delta" not in entry:
            logging.info(f"Reconciliation cache at {self.path} has an outdated format.")
            return None

        return entry

    def _write(self, entry: ReconciliationCacheContent):
        """Write a cache entry, replacing an existing file.

        The entry is first written to a temporary file which then replaces the cache file in
        one step. This way, runs started in parallel never read a half-written file.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        with open(temporary_path, "wb") as file:
            pickle.dump(entry, file)
        os.replace(temporary_path, self.path)
        logging.info(f"Saved reconciliation result to cache {self.path}.")
