"""Tests of the historical scrap share and the check that the future steel system reproduces it."""

import flodym as fd
import numpy as np
import pytest

from remind_mfa.steel.steel_mfa_system_future import SteelMFASystem
from remind_mfa.steel.steel_mfa_system_historical import SteelMFASystemHistorical

H = fd.Dimension(name="Historical Time", letter="h", items=[2021, 2022])
T = fd.Dimension(name="Time", letter="t", items=[2021, 2022, 2023])
R = fd.Dimension(name="Region", letter="r", items=["A", "B", "C"])
DIMS = fd.DimensionSet(dim_list=[H, T, R])

LOSS_RATE = 0.2
# Regions A and B produce steel, region C does not.
STEEL_PRODUCTION = [80.0, 80.0, 0.0]
METALLIC_INPUT = np.array(STEEL_PRODUCTION) / (1 - LOSS_RATE)


def make_flows(
    flow_values: dict[tuple[str, str], list[float] | np.ndarray], time_letter: str
) -> tuple[dict[str, fd.Process], dict[str, fd.Flow]]:
    """Processes and flows over time and region with the given values in all years."""
    names = sorted({process for pair in flow_values for process in pair} - {"sysenv"})
    processes = fd.make_processes(["sysenv", *names])
    flows = {}
    for (source, target), values in flow_values.items():
        name = f"{source} => {target}"
        flows[name] = fd.Flow(
            from_process=processes[source],
            to_process=processes[target],
            dims=DIMS[time_letter, "r"],
            name=name,
        )
        flows[name].values[...] = values
    return processes, flows


def make_historical_system(
    scrap_from_market: list[float], new_scrap: list[float]
) -> SteelMFASystemHistorical:
    """Historical steel system with the given scrap inflows to the scrap pool and empty
    production flows."""
    production_flows = [
        ("scrap_pool", "steel_production_scrap_based"),
        ("scrap_pool", "sysenv"),
        ("sysenv", "steel_production_ore_based"),
        ("steel_production_scrap_based", "forming"),
        ("steel_production_scrap_based", "sysenv"),
        ("steel_production_ore_based", "forming"),
        ("steel_production_ore_based", "sysenv"),
    ]
    processes, flows = make_flows(
        {
            ("scrap_market", "scrap_pool"): scrap_from_market,
            ("forming", "scrap_pool"): new_scrap,
            ("manufacturing", "scrap_pool"): [0.0, 0.0, 0.0],
            **{pair: [0.0, 0.0, 0.0] for pair in production_flows},
        },
        time_letter="h",
    )
    steel_production = fd.Parameter(dims=DIMS["h", "r"], name="steel_production")
    steel_production.values[...] = STEEL_PRODUCTION
    loss_rate = fd.Parameter(dims=fd.DimensionSet(dim_list=[]), name="steel_production_loss_rate")
    loss_rate.values[...] = LOSS_RATE
    return SteelMFASystemHistorical.model_construct(
        dims=DIMS,
        parameters={"steel_production": steel_production, "steel_production_loss_rate": loss_rate},
        processes=processes,
        flows=flows,
        stocks={},
    )


def test_historical_scrap_input_is_the_available_scrap_up_to_the_maximum_scrap_share():
    # A: available scrap below the maximum, B: above it, C: no steel production
    system = make_historical_system(scrap_from_market=[20, 60, 5], new_scrap=[10, 30, 0])
    system.compute_steel_production()

    flw = system.flows
    np.testing.assert_allclose(flw["scrap_pool => steel_production_scrap_based"].values, [[30, 70, 0]] * 2)
    np.testing.assert_allclose(flw["scrap_pool => sysenv"].values, [[0, 20, 5]] * 2)
    np.testing.assert_allclose(flw["sysenv => steel_production_ore_based"].values, [[70, 30, 0]] * 2)
    forming_input = (
        flw["steel_production_scrap_based => forming"] + flw["steel_production_ore_based => forming"]
    )
    np.testing.assert_allclose(forming_input.values, [STEEL_PRODUCTION] * 2)
    # the share falls back to the maximum where a region has no steel production
    np.testing.assert_allclose(system.scrap_share().values, [[0.3, 0.7, 0.7]] * 2)


def make_future_system(available_scrap: list[float], max_scrap_share: list[float]) -> SteelMFASystem:
    """Future steel system with the production flows of the given available scrap and maximum
    scrap share per region, the same in all years."""
    available = np.array(available_scrap)
    scrap_input = np.minimum(available, np.array(max_scrap_share) * METALLIC_INPUT)
    processes, flows = make_flows(
        {
            ("scrap_pool", "steel_production_scrap_based"): scrap_input,
            ("scrap_pool", "excess_scrap"): available - scrap_input,
            ("extraction", "steel_production_ore_based"): METALLIC_INPUT - scrap_input,
        },
        time_letter="t",
    )
    return SteelMFASystem.model_construct(
        dims=DIMS, parameters={}, processes=processes, flows=flows, stocks={}
    )


@pytest.fixture
def historical_system() -> SteelMFASystemHistorical:
    """Computed historical system. A: scrap share below the maximum, B: capped at it,
    C: no steel production."""
    system = make_historical_system(scrap_from_market=[30, 90, 0], new_scrap=[0, 0, 0])
    system.compute_steel_production()
    return system


def test_check_passes_where_the_future_system_has_the_historical_scrap_flows(
    historical_system: SteelMFASystemHistorical,
):
    system = make_future_system(available_scrap=[30, 90, 0], max_scrap_share=[0.3, 0.7, 0.7])
    system.check_historical_scrap_flows(historical_system)


@pytest.mark.parametrize(
    "available_scrap, max_scrap_share, differing",
    [
        pytest.param([35, 90, 0], [0.3, 0.7, 0.7], "available scrap", id="more scrap"),
        pytest.param([30, 90, 0], [0.25, 0.7, 0.7], "scrap input", id="lower maximum"),
        pytest.param([30, 80, 0], [0.3, 0.7, 0.7], "available scrap", id="less excess scrap"),
    ],
)
def test_check_fails_where_the_systems_compute_the_scrap_differently(
    historical_system: SteelMFASystemHistorical,
    available_scrap: list[float],
    max_scrap_share: list[float],
    differing: str,
):
    system = make_future_system(available_scrap, max_scrap_share)
    with pytest.raises(ValueError, match=f"the .*{differing}.* of the future steel system"):
        system.check_historical_scrap_flows(historical_system)
