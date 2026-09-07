"""Shared helpers for coupling REMIND-MFA with the ATLAS steel trade model."""

import math
import os
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from remind_mfa.common.config_loader import load_config
from remind_mfa.common.helpers import ModelNames

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ATLAS_DATA_PIPELINE_ROOT = PROJECT_ROOT / "ATLAS_Trade_data_pipeline"
ATLAS_TRADE_ROOT = PROJECT_ROOT / "ATLAS_Trade"
ATLAS_CACHE_EXPORTER = PROJECT_ROOT / "remind_mfa" / "export_atlas_cache.py"
ANNUAL_FUTURE_YEARS = tuple(range(2025, 2051))
H12_REGION_SET = "REMIND"

from enum import Enum


class AtlasVariant(Enum):
    SINGLE_RES = "single-res"
    GREEN_GREY = "green-grey"


class AtlasCo2Price(Enum):
    ALL = "all"
    CBAM = "cbam"
    DOMESTIC = "domestic"
    NONE = "none"


class AtlasScenarioPkBudg(Enum):
    BUDG_650 = "650"
    BUDG_1000 = "1000"
    BOTH = "both"


class AtlasCouplingError(ValueError):
    """Raised when data does not satisfy the ATLAS coupling contract."""


@dataclass(frozen=True)
class ModelSpec:
    """The external interface of one REMIND-MFA model."""

    name: str
    model: ModelNames
    supported: bool
    demand_variable: str | None
    demand_filename: str | None
    pipeline_demand_filename: str | None
    trade_market: str | None
    parameter_prefix: str | None


MATERIAL_SPECS = {
    "steel": ModelSpec(
        name="steel",
        model=ModelNames.STEEL,
        supported=True,
        demand_variable="steel_demand",
        demand_filename="steel_demand.csv",
        pipeline_demand_filename="ip_market__fabrication.csv",
        trade_market="steel",
        parameter_prefix="st",
    ),
    "plastics": ModelSpec(
        name="plastics",
        model=ModelNames.PLASTICS,
        supported=False,
        demand_variable="plastics_demand",
        demand_filename="plastics_demand.csv",
        pipeline_demand_filename=None,
        trade_market="primary",
        parameter_prefix="pl",
    ),
}


@dataclass(frozen=True)
class CouplingPaths:
    """Filesystem locations relevant to ATLAS coupling for one REMIND-MFA model."""

    exported_demand_path: Path
    atlas_demand_path: Path
    input_data_path: Path
    region_dimension_path: Path
    time_dimension_path: Path


def get_model_spec(model: ModelNames) -> ModelSpec:
    """Resolve a supported model name and explain planned capabilities clearly."""
    normalized = model.strip().lower()
    if normalized == "cement":
        raise AtlasCouplingError("ATLAS coupling does not support model 'cement'.")
    spec = MATERIAL_SPECS.get(normalized)
    if spec is None:
        choices = ", ".join([*MATERIAL_SPECS, "cement"])
        raise AtlasCouplingError(f"Unknown model {model!r}. Choose one of: {choices}.")
    if not spec.supported:
        raise AtlasCouplingError(
            f"ATLAS coupling for model '{spec.name}' is planned but not implemented yet."
        )
    return spec


def _resolve_path(value: str, root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def get_coupling_paths(
    model: ModelNames,
    config_names: Sequence[str],
    config_dir: Path = PROJECT_ROOT / "config",
    root: Path = PROJECT_ROOT,
) -> CouplingPaths:
    """Resolve export, input, and dimensions paths from layered MFA configuration."""
    spec = get_model_spec(model)
    config = load_config(list(config_names), spec.model, config_dir=config_dir)
    export_cfg = config["export"]
    atlas_cfg = export_cfg.get("atlas", {})
    export_path = _resolve_path(export_cfg["path"], root)
    atlas_export_path = (
        _resolve_path(atlas_cfg["path"], root) if atlas_cfg.get("path") else export_path / "atlas"
    )
    input_data_path = _resolve_path(config["input"]["input_data_path"], root)
    dimensions_path = input_data_path / "dimensions" / spec.name

    if spec.demand_filename is None:
        raise AtlasCouplingError(f"Model '{spec.name}' has no ATLAS demand export configured.")

    if spec.pipeline_demand_filename is None:
        raise AtlasCouplingError(
            f"No ATLAS data-pipeline demand location is configured for model '{spec.name}'."
        )

    if os.environ.get("ATLAS_MFA_INPUT_DIRECTORY"):
        atlas_demand_path = (
            Path(os.environ["ATLAS_MFA_INPUT_DIRECTORY"]) / spec.pipeline_demand_filename
        )
    else:
        from ATLAS_Trade_data_pipeline.config.paths import RAW_DATA as ATLAS_RAW_DATA

        atlas_demand_path = ATLAS_RAW_DATA / "REMIND_MFA" / spec.pipeline_demand_filename
    return CouplingPaths(
        exported_demand_path=atlas_export_path / spec.demand_filename,
        atlas_demand_path=atlas_demand_path,
        input_data_path=input_data_path,
        region_dimension_path=dimensions_path / "regions.csv",
        time_dimension_path=dimensions_path / "time_in_years.csv",
    )


def _validate_nonnegative_frame(frame: pd.DataFrame, value_column: str, context: str) -> None:
    values = pd.to_numeric(frame[value_column], errors="coerce")
    if values.isna().any() or not values.map(math.isfinite).all():
        raise AtlasCouplingError(
            f"{context} contains missing or non-finite values in '{value_column}'."
        )
    if (values < 0).any():
        raise AtlasCouplingError(f"{context} contains negative values in '{value_column}'.")
    frame[value_column] = values


def _validate_coordinates(frame: pd.DataFrame, columns: Sequence[str], context: str) -> None:
    if frame[list(columns)].isna().any().any():
        raise AtlasCouplingError(f"{context} contains missing coordinates.")
    for column in columns:
        if frame[column].astype(str).str.strip().eq("").any():
            raise AtlasCouplingError(f"{context} contains blank '{column}' coordinates.")
    if frame.duplicated(list(columns)).any():
        raise AtlasCouplingError(f"{context} contains duplicate {tuple(columns)} coordinates.")


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def copy_steel_demand_to_atlas(source: Path, target: Path) -> pd.DataFrame:
    """Convert a steel demand export into the A_6 fabrication input CSV."""
    frame = pd.read_csv(source)
    required_columns = {"Time", "Region", "steel_demand"}
    missing_columns = sorted(required_columns - set(frame.columns))
    if missing_columns:
        raise AtlasCouplingError(
            f"MFA steel demand export {source} is missing columns: {', '.join(missing_columns)}."
        )

    result = frame.loc[:, ["Time", "Region", "steel_demand"]].rename(
        columns={"steel_demand": "value"}
    )
    result["Time"] = pd.to_numeric(result["Time"], errors="coerce")
    if result["Time"].isna().any() or (result["Time"] % 1 != 0).any():
        raise AtlasCouplingError("MFA steel demand export contains invalid Time values.")
    result["Time"] = result["Time"].astype(int)
    result["Region"] = result["Region"].astype(str).str.strip()
    _validate_coordinates(result, ("Time", "Region"), "MFA steel demand export")
    _validate_nonnegative_frame(result, "value", "MFA steel demand export")
    result = result.sort_values(["Time", "Region"], ignore_index=True)
    _atomic_write_text(target, result.to_csv(index=False, lineterminator="\n"))
    return result


def copy_demand_to_atlas(
    model: ModelNames, source: Path, target: Path, force: bool = False
) -> pd.DataFrame:
    """Convert a model demand export for ATLAS preprocessing."""
    if not source.is_file():
        raise AtlasCouplingError(f"MFA demand export was not found: {source}")

    if target.exists() and not force:
        raise AtlasCouplingError(
            f"ATLAS demand target already exists: {target}, use '--force' to overwrite."
        )

    if model == ModelNames.STEEL:
        return copy_steel_demand_to_atlas(source, target)
    raise AtlasCouplingError(f"No demand converter is implemented for model '{model}'.")


def _load_dimension_items(path: Path, dimension_name: str) -> list[str]:
    if not path.is_file():
        raise AtlasCouplingError(f"MFA {dimension_name} dimension file was not found: {path}")
    values = [
        line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not values:
        raise AtlasCouplingError(f"MFA {dimension_name} dimension file is empty: {path}")
    return values


def load_atlas_trade_projection(
    source: Path, scenario_pkbudg: AtlasScenarioPkBudg, region_dimension_path: Path
) -> pd.DataFrame:
    """Load one ATLAS scenario through the ATLAS Pixi environment."""

    if not source.is_file():
        raise AtlasCouplingError(f"ATLAS result file was not found: {source}")

    data = pd.read_excel(source, sheet_name=f"PkBudg{scenario_pkbudg.value}_q_ij")

    required_columns = {"i", "j", "year", "quantity"}
    missing_columns = sorted(required_columns - set(data.columns))
    if missing_columns:
        raise AtlasCouplingError(
            f"ATLAS bilateral trade is missing columns: {', '.join(missing_columns)}."
        )

    if data["year"].isna().any() or (data["year"] % 1 != 0).any():
        raise AtlasCouplingError("ATLAS bilateral trade contains invalid year values.")

    if data["quantity"].isna().any() or not data["quantity"].map(math.isfinite).all():
        raise AtlasCouplingError(
            "ATLAS bilateral trade contains missing or non-finite values in 'quantity'."
        )
    if (data["quantity"] < 0).any():
        raise AtlasCouplingError("ATLAS bilateral trade contains negative values in 'quantity'.")

    expected_regions = _load_dimension_items(region_dimension_path, "Region")
    invalid_regions = sorted(set(data["i"]) - set(expected_regions))
    if invalid_regions:
        raise AtlasCouplingError(
            f"ATLAS bilateral trade contains regions outside the MFA H12 dimension: {invalid_regions}."
        )

    domestic = data.loc[(data["i"] == data["j"]) & (data["quantity"] > 0)]
    if not domestic.empty:
        raise AtlasCouplingError(
            f"ATLAS bilateral trade contains {len(domestic)} domestic flows (i=j)."
        )

    return data


def aggregate_bilateral_trade(bilateral: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate ATLAS bilateral flows into one import and export value per region/year."""
    cross_border = bilateral.loc[bilateral["i"] != bilateral["j"]]
    if cross_border.empty:
        raise AtlasCouplingError("ATLAS bilateral trade has no cross-border flows.")

    imports = (
        cross_border.groupby(["year", "j"], as_index=False)["quantity"]
        .sum()
        .rename(columns={"j": "region"})
    )
    exports = (
        cross_border.groupby(["year", "i"], as_index=False)["quantity"]
        .sum()
        .rename(columns={"i": "region"})
    )
    return imports, exports


def _validate_global_balance(imports: pd.DataFrame, exports: pd.DataFrame) -> None:
    import_totals = imports.groupby("year")["quantity"].sum()
    export_totals = exports.groupby("year")["quantity"].sum()
    for year in sorted(set(import_totals.index) | set(export_totals.index)):
        imported = float(import_totals.get(year, 0.0))
        exported = float(export_totals.get(year, 0.0))
        if not math.isclose(imported, exported, rel_tol=1e-9, abs_tol=1e-6):
            raise AtlasCouplingError(
                f"ATLAS trade is not globally balanced in {year}: imports={imported}, exports={exported}."
            )


def _write_cs4r(path: Path, data: pd.DataFrame) -> None:
    result = data.rename(columns={"year": "Time", "region": "Region", "quantity": "value"}).loc[
        :, ["Time", "Region", "value"]
    ]
    _atomic_write_text(
        path,
        "* note: dimensions: (Time,Region,value)\n"
        + result.to_csv(index=False, header=False, lineterminator="\n"),
    )


def copy_trade_to_mfa(
    model: ModelNames,
    source: Path,
    scenario_pkbudg: AtlasScenarioPkBudg,
    input_data_path: Path,
    region_dimension_path: Path,
) -> tuple[Path, Path]:
    """Convert one exact ATLAS result scenario into native MFA trade parameters."""
    spec = get_model_spec(model)
    if spec.parameter_prefix is None or spec.trade_market is None:
        raise AtlasCouplingError(f"Model '{spec.name}' has no MFA trade parameter mapping.")
    data = load_atlas_trade_projection(source, scenario_pkbudg, region_dimension_path)
    imports, exports = aggregate_bilateral_trade(data)

    _validate_global_balance(imports, exports)

    parameter_dir = Path(input_data_path) / "input_data"
    imports_path = parameter_dir / f"{spec.parameter_prefix}_trade_{spec.trade_market}_imports.cs4r"
    exports_path = parameter_dir / f"{spec.parameter_prefix}_trade_{spec.trade_market}_exports.cs4r"
    _write_cs4r(imports_path, imports)
    _write_cs4r(exports_path, exports)
    return imports_path, exports_path


def execute_command(command: Sequence[str], cwd: Path) -> None:
    """Run one external command."""
    rendered = " ".join(command)
    print(f"cwd={Path(cwd)} command={rendered}")
    subprocess.run(list(command), cwd=cwd, check=True)
