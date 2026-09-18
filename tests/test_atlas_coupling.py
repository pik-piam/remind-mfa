from pathlib import Path

import pandas as pd
import pytest

from remind_mfa.atlas_coupling import (
    AtlasCouplingError,
    AtlasScenarioPkBudg,
    aggregate_bilateral_trade,
    copy_demand_to_atlas,
    copy_trade_to_mfa,
    get_model_spec,
)
from remind_mfa.common.helpers import ModelNames


def test_copy_steel_demand_converts_schema(tmp_path):
    source = tmp_path / "steel_demand.csv"
    target = tmp_path / "REMIND_MFA" / "ip_market__fabrication.csv"
    pd.DataFrame(
        {
            "Time": [2026, 2025],
            "Region": ["B", "A"],
            "steel_demand": [2.5, 1.0],
        }
    ).to_csv(source, index=False)

    result = copy_demand_to_atlas(ModelNames.STEEL, source, target)

    expected = pd.DataFrame({"Time": [2026, 2025], "Region": ["B", "A"], "value": [2.5, 1.0]})
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(pd.read_csv(target), expected)


def test_aggregate_bilateral_trade_excludes_domestic_flows():
    bilateral = pd.DataFrame(
        {
            "i": ["A", "B", "A"],
            "j": ["B", "A", "A"],
            "year": [2025, 2025, 2025],
            "quantity": [2.0, 3.0, 99.0],
        }
    )

    imports, exports = aggregate_bilateral_trade(bilateral)

    assert imports.to_dict("records") == [
        {"year": 2025, "region": "A", "quantity": 3.0},
        {"year": 2025, "region": "B", "quantity": 2.0},
    ]
    assert exports.to_dict("records") == [
        {"year": 2025, "region": "A", "quantity": 2.0},
        {"year": 2025, "region": "B", "quantity": 3.0},
    ]


def test_aggregate_bilateral_trade_sums_flows():
    bilateral = pd.DataFrame(
        {
            "i": ["A", "A", "A"],
            "j": ["B", "B", "A"],
            "year": [2025, 2025, 2025],
            "quantity": [2.0, 3.0, 99.0],
        }
    )

    imports, exports = aggregate_bilateral_trade(bilateral)

    assert imports.to_dict("records") == [{"year": 2025, "region": "B", "quantity": 5.0}]
    assert exports.to_dict("records") == [{"year": 2025, "region": "A", "quantity": 5.0}]


def _write_dimensions(tmp_path: Path) -> tuple[Path, Path]:
    regions = tmp_path / "regions.csv"
    times = tmp_path / "time_in_years.csv"
    regions.write_text("A\nB\n", encoding="utf-8")
    times.write_text("2025\n2026\n", encoding="utf-8")
    return regions, times


def _write_projection(path: Path, rows: list[dict]) -> None:
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="PkBudg1000_q_ij", index=False)


def test_copy_trade_writes_cs4r_files(tmp_path):
    regions, _ = _write_dimensions(tmp_path)
    projection = tmp_path / "future.xlsx"
    _write_projection(
        projection,
        [{"i": "A", "j": "B", "year": year, "quantity": 2.0} for year in (2025, 2026)]
        + [{"i": "B", "j": "A", "year": year, "quantity": 3.0} for year in (2025, 2026)],
    )

    imports_path, exports_path = copy_trade_to_mfa(
        model=ModelNames.STEEL,
        source=projection,
        scenario_pkbudg=AtlasScenarioPkBudg.BUDG_1000,
        input_data_path=tmp_path / "mfa",
        region_dimension_path=regions,
    )

    assert imports_path.read_text(encoding="utf-8") == (
        "* note: dimensions: (Time,Region,value)\n2025,A,3\n2025,B,2\n2026,A,3\n2026,B,2\n"
    )
    assert exports_path.read_text(encoding="utf-8") == (
        "* note: dimensions: (Time,Region,value)\n2025,A,2\n2025,B,3\n2026,A,2\n2026,B,3\n"
    )


def test_copy_trade_rejects_domestic_flows(tmp_path):
    regions, _ = _write_dimensions(tmp_path)
    projection = tmp_path / "future.xlsx"
    _write_projection(
        projection,
        [
            {"i": "A", "j": "B", "year": 2025, "quantity": 2.0},
            {"i": "A", "j": "A", "year": 2025, "quantity": 2.0},
        ],
    )

    with pytest.raises(AtlasCouplingError, match="domestic"):
        copy_trade_to_mfa(
            model=ModelNames.STEEL,
            source=projection,
            scenario_pkbudg=AtlasScenarioPkBudg.BUDG_1000,
            input_data_path=tmp_path / "mfa",
            region_dimension_path=regions,
        )


def test_cement_is_an_unsupported_model():
    with pytest.raises(AtlasCouplingError, match="does not support"):
        get_model_spec("cement")
