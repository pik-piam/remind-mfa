import pickle
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

import atlas
from remind_mfa.atlas_coupling import (
    AtlasCouplingError,
    CouplingPaths,
    aggregate_bilateral_trade,
    copy_steel_demand_to_atlas,
    copy_trade_to_mfa,
    get_material_spec,
)


def test_copy_steel_demand_converts_schema_and_drops_export_index(tmp_path):
    source = tmp_path / "steel_demand.csv"
    target = tmp_path / "REMIND_MFA" / "ip_market__fabrication.csv"
    pd.DataFrame(
        {
            "Unnamed: 0": [0, 1],
            "Time": [2026, 2025],
            "Region": ["B", "A"],
            "steel_demand": [2.5, 1.0],
        }
    ).to_csv(source, index=False)

    result = copy_steel_demand_to_atlas(source, target)

    expected = pd.DataFrame({"Time": [2025, 2026], "Region": ["A", "B"], "value": [1.0, 2.5]})
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(pd.read_csv(target), expected)


def test_copy_steel_demand_rejects_duplicate_coordinates(tmp_path):
    source = tmp_path / "steel_demand.csv"
    pd.DataFrame({"Time": [2025, 2025], "Region": ["A", "A"], "steel_demand": [1.0, 2.0]}).to_csv(
        source, index=False
    )

    with pytest.raises(AtlasCouplingError, match="duplicate"):
        copy_steel_demand_to_atlas(source, tmp_path / "target.csv")


def test_aggregate_bilateral_trade_excludes_domestic_flows():
    scenario = {
        "q_ij": pd.DataFrame(
            {
                "i": ["A", "B", "A"],
                "j": ["B", "A", "A"],
                "year": [2025, 2025, 2025],
                "quantity": [2.0, 3.0, 99.0],
            }
        )
    }

    imports, exports = aggregate_bilateral_trade(scenario)

    assert imports.to_dict("records") == [
        {"Time": 2025, "Region": "A", "value": 3.0},
        {"Time": 2025, "Region": "B", "value": 2.0},
    ]
    assert exports.to_dict("records") == [
        {"Time": 2025, "Region": "A", "value": 2.0},
        {"Time": 2025, "Region": "B", "value": 3.0},
    ]


def test_aggregate_bilateral_trade_sums_technology_fallback():
    scenario = {
        "q_ij_e": pd.DataFrame(
            {
                "i": ["A", "A", "A"],
                "j": ["B", "B", "A"],
                "e": ["RES", "fossil", "RES"],
                "year": [2025, 2025, 2025],
                "quantity_e": [2.0, 3.0, 99.0],
            }
        )
    }

    imports, exports = aggregate_bilateral_trade(scenario)

    assert imports.to_dict("records") == [{"Time": 2025, "Region": "B", "value": 5.0}]
    assert exports.to_dict("records") == [{"Time": 2025, "Region": "A", "value": 5.0}]


def _write_dimensions(tmp_path: Path) -> tuple[Path, Path]:
    regions = tmp_path / "regions.csv"
    times = tmp_path / "time_in_years.csv"
    regions.write_text("A\nB\n", encoding="utf-8")
    times.write_text("2025\n2026\n", encoding="utf-8")
    return regions, times


def _write_cache(path: Path, rows: list[dict]) -> None:
    with path.open("wb") as stream:
        pickle.dump(
            {
                "meta": {"region_set": "REMIND"},
                "scenarios_dfs": {"selected": {"q_ij": pd.DataFrame(rows)}},
            },
            stream,
        )


def test_copy_trade_writes_complete_annual_cs4r_files(tmp_path):
    regions, times = _write_dimensions(tmp_path)
    cache = tmp_path / "future.pkl"
    _write_cache(
        cache,
        [{"i": "A", "j": "B", "year": year, "quantity": 2.0} for year in (2025, 2026)]
        + [{"i": "B", "j": "A", "year": year, "quantity": 3.0} for year in (2025, 2026)],
    )

    imports_path, exports_path = copy_trade_to_mfa(
        material="steel",
        cache_path=cache,
        scenario_key="selected",
        input_data_path=tmp_path / "mfa",
        region_dimension_path=regions,
        time_dimension_path=times,
        years=(2025, 2026),
    )

    assert imports_path.read_text(encoding="utf-8") == (
        "* note: dimensions: (Time,Region,value)\n2025,A,3.0\n2025,B,2.0\n2026,A,3.0\n2026,B,2.0\n"
    )
    assert exports_path.read_text(encoding="utf-8") == (
        "* note: dimensions: (Time,Region,value)\n2025,A,2.0\n2025,B,3.0\n2026,A,2.0\n2026,B,3.0\n"
    )


def test_copy_trade_rejects_missing_annual_coordinates(tmp_path):
    regions, times = _write_dimensions(tmp_path)
    cache = tmp_path / "future.pkl"
    _write_cache(
        cache,
        [
            {"i": "A", "j": "B", "year": 2025, "quantity": 2.0},
            {"i": "B", "j": "A", "year": 2025, "quantity": 2.0},
        ],
    )

    with pytest.raises(AtlasCouplingError, match="missing"):
        copy_trade_to_mfa(
            material="steel",
            cache_path=cache,
            scenario_key="selected",
            input_data_path=tmp_path / "mfa",
            region_dimension_path=regions,
            time_dimension_path=times,
            years=(2025, 2026),
        )


def test_plastics_is_a_planned_but_unsupported_material():
    with pytest.raises(AtlasCouplingError, match="planned"):
        get_material_spec("plastics")


def test_couple_dry_run_emits_ordered_stages(monkeypatch, tmp_path):
    paths = CouplingPaths(
        exported_demand_path=tmp_path / "demand.csv",
        input_data_path=tmp_path / "input",
        region_dimension_path=tmp_path / "regions.csv",
        time_dimension_path=tmp_path / "times.csv",
    )
    monkeypatch.setattr(atlas, "load_mfa_paths", lambda *_: paths)
    monkeypatch.setattr(atlas, "default_pipeline_demand_path", lambda *_: tmp_path / "pipeline.csv")

    result = CliRunner().invoke(
        atlas.app,
        [
            "couple",
            "--material",
            "steel",
            "--cache-path",
            str(tmp_path / "future.pkl"),
            "--scenario-key",
            "selected",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (
        result.output.index("MFA material=steel config=default,atlas_run1")
        < result.output.index("copy-demand")
        < result.output.index("command=snakemake")
        < result.output.index("run/run_history_calibration.py")
        < result.output.index("run/run_history_validation.py")
        < result.output.index("run/run_future_scenarios.py")
        < result.output.index("copy-trade")
        < result.output.rindex("MFA material=steel config=default,atlas_run2")
    )
