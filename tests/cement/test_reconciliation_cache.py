from types import SimpleNamespace

import flodym as fd
import numpy as np

from remind_mfa.cement.reconciliation_cache import (
    compute_cache_key,
    get_cache_path,
    load_cache,
    save_cache,
)
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


def test_save_and_load_cache(tmp_path):
    cache_path = get_cache_path(tmp_path / "cache", region_mapping="h12")
    parameters = make_ref_mfa().parameters

    assert load_cache(cache_path, key="abc") is None  # no file yet

    save_cache(cache_path, {"key": "abc", "parameters": parameters, "mismatch": 0.01})
    entry = load_cache(cache_path, key="abc")
    assert entry is not None
    assert entry["mismatch"] == 0.01
    np.testing.assert_array_equal(
        entry["parameters"]["floorspace"].values, parameters["floorspace"].values
    )

    assert load_cache(cache_path, key="other") is None  # outdated key

    # saving again overwrites the single file of this region mapping
    save_cache(cache_path, {"key": "other", "parameters": parameters, "mismatch": 0.02})
    assert load_cache(cache_path, key="abc") is None
    assert list(cache_path.parent.iterdir()) == [cache_path]
