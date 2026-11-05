from pathlib import Path
from types import SimpleNamespace

import flodym as fd
import numpy as np

from remind_mfa.cement.cement_parameter_reconciliation import CementParameterReconciliation
from remind_mfa.cement.reconciliation_cache import ReconciliationCache, compute_cache_key
from remind_mfa.common.trade import Trade, TradeSet


def make_ref_mfa(floorspace_value: float = 1.0) -> SimpleNamespace:
    """Minimal stand-in for the reference MFA: only parameters and trade are hashed."""
    regions = fd.Dimension(name="Region", letter="r", items=["EUR", "USA"])
    dims = fd.DimensionSet(dim_list=[regions])
    floorspace = fd.Parameter(dims=dims, name="floorspace", values=np.full(2, floorspace_value))
    trade = Trade(
        imports=fd.FlodymArray(dims=dims, values=np.array([1.0, 2.0])),
        exports=fd.FlodymArray(dims=dims, values=np.array([2.0, 1.0])),
    )
    return SimpleNamespace(
        parameters={"floorspace": floorspace},
        trade_set=TradeSet(markets={"cement": trade}),
    )


def make_delta() -> dict[str, fd.FlodymArray]:
    return {"floorspace": make_ref_mfa().parameters["floorspace"].apply(np.log)}


class FakeReconciliation(CementParameterReconciliation):
    """Reconciliation stand-in whose corrected parameters reach a given mismatch."""

    def __init__(self, mismatch: float):
        self.mismatch = mismatch

    def calc_corrected_parameters(
        self, delta: dict[str, fd.FlodymArray]
    ) -> dict[str, fd.Parameter]:
        return {
            name: delta_p.apply(np.exp).to_class(fd.Parameter) for name, delta_p in delta.items()
        }

    def calc_mismatch(self, source_prms: dict[str, fd.Parameter], label: str) -> float:
        return self.mismatch


def make_cache(cache_dir: Path, setting: int = 1) -> ReconciliationCache:
    """Cache whose key depends on `setting`."""
    return ReconciliationCache(cache_dir, "h12", make_ref_mfa(), settings={"setting": setting})


def save_entry(cache: ReconciliationCache, mismatch: float):
    reconciliation = FakeReconciliation(mismatch)
    reconciliation.delta = make_delta()
    reconciliation.final_mismatch = mismatch
    cache.save(reconciliation)


def test_cache_key_is_deterministic():
    settings = {"max_iter": 5, "tol": 1e-3}
    assert compute_cache_key(make_ref_mfa(), settings) == compute_cache_key(
        make_ref_mfa(), settings
    )


def test_cache_key_changes_with_inputs_and_settings():
    settings = {"max_iter": 5, "tol": 1e-3}
    key = compute_cache_key(make_ref_mfa(), settings)
    assert compute_cache_key(make_ref_mfa(floorspace_value=1.1), settings) != key
    assert compute_cache_key(make_ref_mfa(), {"max_iter": 6, "tol": 1e-3}) != key


def test_cache_path_per_region_mapping(tmp_path):
    cache = make_cache(tmp_path)
    assert cache.path == tmp_path / "cement_reconciliation_h12.pickle"


def test_save_and_load_cache(tmp_path):
    """A saved result is loaded with the same key; saving with another key overwrites it."""
    cache = make_cache(tmp_path / "cache")
    save_entry(cache, mismatch=0.01)
    reconciliation = FakeReconciliation(mismatch=0.01)
    assert cache.load(reconciliation, force_use=False)
    np.testing.assert_array_equal(
        reconciliation.delta["floorspace"].values, make_delta()["floorspace"].values
    )

    other_cache = make_cache(tmp_path / "cache", setting=2)
    assert not other_cache.load(FakeReconciliation(mismatch=0.01), force_use=False)
    save_entry(other_cache, mismatch=0.01)
    assert not cache.load(FakeReconciliation(mismatch=0.01), force_use=False)
    assert list(cache.path.parent.iterdir()) == [cache.path]


def test_old_cache_format_is_ignored(tmp_path):
    """Files of older versions, which stored the corrected parameters, are never used."""
    cache = make_cache(tmp_path)
    old_entry = {"key": cache.key, "parameters": make_ref_mfa().parameters, "mismatch": 0.01}
    cache._write(old_entry)
    assert not cache.load(FakeReconciliation(mismatch=0.01), force_use=False)
    assert not cache.load(FakeReconciliation(mismatch=0.01), force_use=True)


def test_load_checks_mismatch(tmp_path):
    """A cached result is used if it reaches the stored mismatch, and sets the result of the
    reconciliation."""
    cache = make_cache(tmp_path)
    assert not cache.load(FakeReconciliation(mismatch=0.01), force_use=False)  # no file

    save_entry(cache, mismatch=0.01)
    reconciliation = FakeReconciliation(mismatch=0.01)
    assert cache.load(reconciliation, force_use=False)
    np.testing.assert_allclose(reconciliation.output_prms["floorspace"].values, 1.0)
    assert reconciliation.final_mismatch == 0.01
    assert list(reconciliation.delta) == ["floorspace"]

    assert not cache.load(FakeReconciliation(mismatch=0.5), force_use=False)


def test_load_force_use(tmp_path):
    """With `force_use`, a file with another key and a larger mismatch is used anyway."""
    save_entry(make_cache(tmp_path), mismatch=0.01)
    cache = make_cache(tmp_path, setting=2)

    assert not cache.load(FakeReconciliation(mismatch=0.5), force_use=False)
    reconciliation = FakeReconciliation(mismatch=0.5)
    assert cache.load(reconciliation, force_use=True)
    assert reconciliation.final_mismatch == 0.5
