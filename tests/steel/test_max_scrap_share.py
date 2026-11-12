"""Tests of the check that the steel maximum scrap share is the scrap share in historical years."""

import flodym as fd
import numpy as np
import pytest

from remind_mfa.steel.steel_mfa_system_future import SteelMFASystem

H = fd.Dimension(name="Historical Time", letter="h", items=[2021, 2022])
T = fd.Dimension(name="Time", letter="t", items=[2021, 2022, 2023])
R = fd.Dimension(name="Region", letter="r", items=["A", "B", "C"])
DIMS = fd.DimensionSet(dim_list=[H, T, R])

HISTORICAL_MAX_SCRAP_SHARE = 0.7
# Regions A and B produce steel, region C does not.
METALLIC_INPUT = np.array([100.0, 100.0, 0.0])


def make_system(available_scrap: list[float], max_scrap_share: list[float]) -> SteelMFASystem:
    """Future steel system with the production flows of the given scrap and maximum scrap share
    per region, the same in all years."""
    available = np.array(available_scrap)
    scrap_input = np.minimum(available, np.array(max_scrap_share) * METALLIC_INPUT)
    flow_values = {
        ("scrap_pool", "steel_production_scrap_based"): scrap_input,
        ("scrap_pool", "excess_scrap"): available - scrap_input,
        ("extraction", "steel_production_ore_based"): METALLIC_INPUT - scrap_input,
    }
    processes = fd.make_processes(
        ["sysenv", "scrap_pool", "steel_production_scrap_based", "excess_scrap", "extraction"]
        + ["steel_production_ore_based"]
    )
    flows = {}
    for (source, target), values in flow_values.items():
        name = f"{source} => {target}"
        flows[name] = fd.Flow(
            from_process=processes[source],
            to_process=processes[target],
            dims=DIMS["t", "r"],
            name=name,
        )
        flows[name].values[...] = values
    parameter = fd.Parameter(dims=DIMS["t", "r"], name="max_scrap_share")
    parameter.values[...] = max_scrap_share
    return SteelMFASystem.model_construct(
        dims=DIMS,
        parameters={"max_scrap_share": parameter},
        processes=processes,
        flows=flows,
        stocks={},
    )


def test_check_passes_where_the_maximum_scrap_share_is_the_scrap_share():
    # A: scrap share below the historical maximum, B: capped at it, C: no steel production
    system = make_system(available_scrap=[30, 90, 0], max_scrap_share=[0.3, 0.7, 0.7])
    system.check_historical_scrap_input(HISTORICAL_MAX_SCRAP_SHARE)


@pytest.mark.parametrize(
    "available_scrap, max_scrap_share",
    [
        pytest.param([35, 90, 0], [0.3, 0.7, 0.7], id="more scrap than the historical system"),
        pytest.param([30, 90, 0], [0.35, 0.7, 0.7], id="less scrap than the historical system"),
    ],
)
def test_check_fails_where_the_systems_compute_the_scrap_differently(
    available_scrap: list[float], max_scrap_share: list[float]
):
    system = make_system(available_scrap, max_scrap_share)
    with pytest.raises(ValueError, match="compute the scrap differently"):
        system.check_historical_scrap_input(HISTORICAL_MAX_SCRAP_SHARE)
