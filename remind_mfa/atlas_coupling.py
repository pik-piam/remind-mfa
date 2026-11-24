"""Shared helpers for coupling REMIND-MFA with the ATLAS steel trade model."""

import math
import os
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from remind_mfa.common.config_loader import load_config
from remind_mfa.common.helpers import ModelNames

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ATLAS_DATA_PIPELINE_ROOT = PROJECT_ROOT / "ATLAS_Trade_data_pipeline"
ATLAS_TRADE_ROOT = PROJECT_ROOT / "ATLAS-Trade"
ATLAS_CACHE_EXPORTER = PROJECT_ROOT / "remind_mfa" / "export_atlas_cache.py"
# ATLAS projects in 5-year steps, later we interpolate the years in between
ATLAS_PROJECTION_YEARS = tuple(range(2025, 2051, 5))
H12_REGION_SET = "REMIND"

from enum import Enum


class AtlasShareMode(Enum):
    SINGLE_FOSSIL = "single-fossil"
    EQUAL = "equal"
    SHARES = "shares"
    SINGLE_RES = "single-res"
    SINGLE_SCRAP = "single-scrap"


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


class AtlasGreySupplySource(Enum):
    """Source of grey-supply curves for ATLAS-Trade."""

    ATLAS_DEFAULT = "steel_iq"
    MIC3_BASELINE = "steel_iq-mic3_baseline"
    MIC3_POLICY = "steel_iq-mic3_policy"


@dataclass(frozen=True)
class ModelSpec:
    """The external interface of one REMIND-MFA model."""

    name: str
    model: ModelNames
    mfa_pipeline_mapping: dict[str, str]
    trade_market: str | None
    parameter_prefix: str | None
    atlas_scenario_tag: str | None = None


MATERIAL_SPECS = {
    "steel": ModelSpec(
        name="steel",
        model=ModelNames.STEEL,
        mfa_pipeline_mapping={
            "steel_demand.csv": "steel/steel_market__manufacturing.csv",
            "steel_scrap_production.csv": "steel/scrap_pool__steel_production_scrap_based.csv",
            "steel_scrap_excess.csv": "steel/scrap_pool__excess_scrap.csv",
            "steel_scrap_eol_pre_trade.csv": "steel/eol_management__scrap_market.csv",
            "steel_scrap_eol_post_trade.csv": "steel/scrap_market__scrap_pool.csv",
        },
        trade_market="steel",
        parameter_prefix="st",
    ),
    "plastics": ModelSpec(
        name="plastics",
        model=ModelNames.PLASTICS,
        mfa_pipeline_mapping={
            "plastics_demand.csv": "plastics/primary_market__fabrication.csv",
            "plastics_production.csv": "plastics/production_by_region_year.csv",
        },
        trade_market="primary",
        parameter_prefix="pl",
        # ATLAS-Trade has no REMIND carbon-budget scenarios for plastics (only steel's
        # technology split depends on them), so it always runs a single "Baseline" future
        # scenario and writes the trade projection under a "Baseline_q_ij" sheet regardless
        # of --scenario-pkbudg (see ATLAS-Trade/config/model_settings.py GOOD_SETTINGS).
        atlas_scenario_tag="Baseline",
    ),
}

# The default target of the ATLAS data pipeline builds the input tables of all goods at once, so it
# reads the MFA exports of every model with a pipeline mapping, whichever model is coupled.
PIPELINE_INPUT_MODELS: tuple[ModelNames, ...] = tuple(
    spec.model for spec in MATERIAL_SPECS.values()
)


@dataclass(frozen=True)
class CouplingPaths:
    """Filesystem locations relevant to ATLAS coupling for one REMIND-MFA model."""

    mfa_pipeline_mapping: dict[Path, Path]
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
    return spec


def scenario_pkbudg_is_effective(model: ModelNames) -> bool:
    """True if `scenario_pkbudg` selects the ATLAS future scenario for `model`."""
    return get_model_spec(model).atlas_scenario_tag is None


def _resolve_path(value: str, root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def get_coupling_paths(
    model: ModelNames,
    config_names: Sequence[str],
    config_dir: Path = PROJECT_ROOT / "config",
    root: Path = PROJECT_ROOT,
    run_label: str | None = None,
) -> CouplingPaths:
    """Resolve export, input, and dimensions paths from layered MFA configuration.

    Args:
        model: MFA model.
        config_names: Configuration layers of the MFA run.
        config_dir: Directory of the configuration files.
        root: Root against which relative paths are resolved.
        run_label: Suffix of the run folder name that the MFA run exported into, if any.

    Returns:
        The resolved coupling paths.
    """
    spec = get_model_spec(model)
    config = load_config(list(config_names), spec.model, config_dir=config_dir)
    export_cfg = config["export"]
    scenario = config["model_switches"].get("scenario")
    region_mapping = config["input"].get("region_mapping")
    transience_scenario = config["transience"].get("transience_scenario")
    trade_scenario = config["transience"].get("trade_scenario")
    open_gem_alignment = config["transience"].get("open_gem_alignment", False)
    run_name = f"{export_cfg['prefix']}_{model.value}_{scenario}_{region_mapping}_{transience_scenario}_{trade_scenario}"
    if open_gem_alignment:
        # same suffix as CommonDataExporter.run_path
        run_name += "_OPEN-GEM"
    if run_label:
        # same suffix as CommonDataExporter.run_path with export.run_suffix
        run_name += f"_{run_label}"
    export_path = _resolve_path(export_cfg["path"], root)
    atlas_export_path = export_path / f"{export_cfg['prefix']}_series" / run_name / "atlas"
    input_data_path = _resolve_path(config["input"]["input_data_path"], root)
    dimensions_path = input_data_path / "dimensions" / spec.name

    if not spec.mfa_pipeline_mapping:
        raise AtlasCouplingError(
            f"No ATLAS output-pipeline mapping is configured for model '{spec.name}'."
        )

    if os.environ.get("ATLAS_MFA_INPUT_DIRECTORY"):
        target_dir = Path(os.environ["ATLAS_MFA_INPUT_DIRECTORY"])
    else:
        from ATLAS_Trade_data_pipeline.config.paths import RAW_DATA as ATLAS_RAW_DATA

        target_dir = ATLAS_RAW_DATA / "REMIND_MFA"

    mfa_pipeline_mapping = {
        atlas_export_path / key: target_dir / value
        for key, value in spec.mfa_pipeline_mapping.items()
    }

    return CouplingPaths(
        mfa_pipeline_mapping=mfa_pipeline_mapping,
        input_data_path=input_data_path,
        region_dimension_path=input_data_path / "parameters" / "regionmapping.csv",
        time_dimension_path=dimensions_path / "time.csv",
    )


def find_missing_pipeline_inputs(config_names: Sequence[str]) -> dict[ModelNames, list[Path]]:
    """Find the MFA exports that the ATLAS data pipeline reads but that have not been copied yet.

    Args:
        config_names: Configuration layers of the first MFA run, used to resolve the paths.

    Returns:
        The missing pipeline input files per model. Models with all files present are left out.
    """
    missing_inputs: dict[ModelNames, list[Path]] = {}
    for model in PIPELINE_INPUT_MODELS:
        targets = get_coupling_paths(model, config_names).mfa_pipeline_mapping.values()
        missing_targets = [target for target in targets if not target.is_file()]
        if missing_targets:
            missing_inputs[model] = missing_targets
    return missing_inputs


def default_atlas_trade_source(model: ModelNames, variant: AtlasVariant) -> Path:
    """Trade projection written by the ATLAS future model for the given model and variant."""
    variant_value = variant.value.replace("-", "_")
    model_folder = "future" if model == ModelNames.STEEL else "future_plastics"
    return (
        ATLAS_TRADE_ROOT
        / "outputs"
        / "output_no_cet"
        / model_folder
        / variant_value
        / "cache"
        / f"future_projections_summary_{variant_value}.xlsx"
    )


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


def copy_mfa_output_to_atlas(
    source: Path, target: Path, column_map: dict[str, str]
) -> pd.DataFrame:
    """Convert a MFA export into the input CSV for ATLAS."""
    frame = pd.read_csv(source)
    result = frame.rename(columns=column_map)
    _atomic_write_text(target, result.to_csv(index=False, lineterminator="\n"))
    return result


def copy_demand_to_atlas(
    model: ModelNames, source: Path, target: Path, force: bool = False
) -> pd.DataFrame:
    """Convert a model demand (or, for steel, scrap) export for ATLAS preprocessing."""
    if not source.is_file():
        raise AtlasCouplingError(f"MFA demand export was not found: {source}")

    if target.exists() and not force:
        raise AtlasCouplingError(
            f"ATLAS demand target already exists: {target}, use '--force' to overwrite."
        )

    if model == ModelNames.STEEL:
        return copy_mfa_output_to_atlas(
            source,
            target,
            column_map={
                "steel_demand": "value",
                "steel_scrap_production": "value",
                "steel_scrap_excess": "value",
                "steel_scrap_eol_pre_trade": "value",
                "steel_scrap_eol_post_trade": "value",
            },
        )
    if model == ModelNames.PLASTICS:
        return copy_mfa_output_to_atlas(
            source,
            target,
            column_map={
                "plastics_demand": "value",
                "plastics_production": "value",
                # the ATLAS data pipeline still expects the polymer column under its old name "Material"
                "Polymer": "Material",
            },
        )
    raise AtlasCouplingError(f"No demand converter is implemented for model '{model}'.")


def _load_region_items(path: Path) -> list[str]:
    """Region codes of the MFA Region dimension, read from the region mapping in the same way as
    `CommonDimensionReader`."""
    if not path.is_file():
        raise AtlasCouplingError(f"MFA region mapping file was not found: {path}")
    regions = pd.read_csv(path, delimiter=";")["RegionCode"].unique().tolist()
    if not regions:
        raise AtlasCouplingError(f"MFA region mapping file is empty: {path}")
    return regions


def _atlas_scenario_sheet_name(spec: ModelSpec, scenario_pkbudg: AtlasScenarioPkBudg) -> str:
    tag = spec.atlas_scenario_tag or f"PkBudg{scenario_pkbudg.value}"
    return f"{tag}_q_ij"


def load_atlas_trade_projection(
    model: ModelNames,
    source: Path,
    scenario_pkbudg: AtlasScenarioPkBudg,
    region_dimension_path: Path,
) -> pd.DataFrame:
    """Load one ATLAS scenario through the ATLAS Pixi environment."""

    if not source.is_file():
        raise AtlasCouplingError(f"ATLAS result file was not found: {source}")

    spec = get_model_spec(model)
    data = pd.read_excel(source, sheet_name=_atlas_scenario_sheet_name(spec, scenario_pkbudg))

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

    expected_regions = _load_region_items(region_dimension_path)
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
    result = data.rename(
        columns={
            "year": "Time",
            "region": "Region",
            "quantity": "value",
            "type": "Polymer Type",
            "material": "Polymer",
        }
    )
    dimensions = ",".join(result.columns)
    _atomic_write_text(
        path,
        f"* note: dimensions: ({dimensions})\n"
        + result.to_csv(index=False, header=False, lineterminator="\n"),
    )


def _load_historic_plastics_trade(flow: str) -> pd.DataFrame:
    """Historic plastics trade per region and polymer in the latest historic year."""
    historic_path = PROJECT_ROOT / "data_in" / "parameters" / f"pl_primary_{flow}.cs4r"
    if not historic_path.is_file():
        raise AtlasCouplingError(
            f"Historic plastics {flow} trade parameter was not found: {historic_path}"
        )

    historic_trade = pd.read_csv(
        historic_path,
        comment="*",
        header=None,
        names=["historic_year", "region", "type", "material", "quantity"],
    )
    if historic_trade.empty:
        raise AtlasCouplingError(f"Historic plastics {flow} trade parameter is empty.")

    historic_trade["historic_year"] = pd.to_numeric(
        historic_trade["historic_year"], errors="coerce"
    )
    historic_trade["quantity"] = pd.to_numeric(historic_trade["quantity"], errors="coerce")
    if historic_trade[["historic_year", "quantity"]].isna().any().any():
        raise AtlasCouplingError(
            f"Historic plastics {flow} trade parameter contains invalid values."
        )
    if (historic_trade["quantity"] < 0).any():
        raise AtlasCouplingError(
            f"Historic plastics {flow} trade parameter contains negative values."
        )

    latest_year = historic_trade["historic_year"].max()
    latest_trade = historic_trade.loc[historic_trade["historic_year"] == latest_year]
    return latest_trade.groupby(["region", "material"], as_index=False)["quantity"].sum()


def _ras_balance(
    imports: np.ndarray,
    exports: np.ndarray,
    tolerance: float = 1e-8,
    max_iterations: int = 1000,
) -> tuple[np.ndarray, np.ndarray]:
    """Balance trade of several goods by a RAS (iterative proportional fitting).

    Imports and exports are arrays with dimensions (year, region, good). They are rescaled such that
    the region totals (summed over goods) are kept, and that global imports equal global exports for
    each year and good. Each iteration sets the global imports and exports of each good to their
    geometric mean and then restores the region totals. This converges to the solution closest to
    the given arrays (in the sense of the Kullback-Leibler divergence), so it keeps the given shares
    of the goods as far as possible. Zeros remain zero.
    """
    region_imports = imports.sum(axis=2, keepdims=True)
    region_exports = exports.sum(axis=2, keepdims=True)
    imports = imports.astype(float)
    exports = exports.astype(float)
    for _ in range(max_iterations):
        global_imports = imports.sum(axis=1, keepdims=True)
        global_exports = exports.sum(axis=1, keepdims=True)
        global_target = np.sqrt(global_imports * global_exports)
        imports *= _divide_or_zero(global_target, global_imports)
        exports *= _divide_or_zero(global_target, global_exports)
        imports *= _divide_or_zero(region_imports, imports.sum(axis=2, keepdims=True))
        exports *= _divide_or_zero(region_exports, exports.sum(axis=2, keepdims=True))

        if (
            np.allclose(imports.sum(axis=1), exports.sum(axis=1), rtol=tolerance, atol=0.0)
            and np.allclose(
                imports.sum(axis=2, keepdims=True), region_imports, rtol=tolerance, atol=0.0
            )
            and np.allclose(
                exports.sum(axis=2, keepdims=True), region_exports, rtol=tolerance, atol=0.0
            )
        ):
            return imports, exports

    raise AtlasCouplingError(
        f"RAS did not converge within {max_iterations} iterations. The region totals can probably "
        "not be met, given which goods each region trades and the global trade balance."
    )


def _divide_or_zero(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    return np.divide(
        numerator,
        denominator,
        out=np.zeros(np.broadcast_shapes(numerator.shape, denominator.shape)),
        where=denominator > 0,
    )


POLYMER_TRADE_INDEX = ["year", "region", "material"]


def _polymer_trade_index(
    years: list[int], regions: list[str], polymers: list[str]
) -> pd.MultiIndex:
    return pd.MultiIndex.from_product([years, regions, polymers], names=POLYMER_TRADE_INDEX)


def _polymer_trade_frame(values: np.ndarray, index: pd.MultiIndex) -> pd.DataFrame:
    return pd.DataFrame({"quantity": values.ravel()}, index=index).reset_index()


def split_plastics_trade(
    imports: pd.DataFrame, exports: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split future plastics trade into polymers with the latest historic polymer shares.

    ATLAS trades plastics as a single good, so it only gives the total imports and exports of each
    region. These are split with the polymer shares of the same region in the latest historic year.
    The global imports and exports of a polymer then generally differ, see
    :func:`balance_polymer_trade`.
    """
    future_trade = {"imports": imports, "exports": exports}
    historic_trade = {flow: _load_historic_plastics_trade(flow) for flow in future_trade}

    years = sorted(set(imports["year"]) | set(exports["year"]))
    regions = sorted(set(imports["region"]) | set(exports["region"]))
    polymers = sorted(set().union(*(trade["material"] for trade in historic_trade.values())))

    seeds = []
    for flow, trade in future_trade.items():
        region_totals = trade.pivot_table(
            index="year", columns="region", values="quantity", aggfunc="sum", fill_value=0.0
        ).reindex(index=years, columns=regions, fill_value=0.0)
        historic = historic_trade[flow].pivot_table(
            index="region", columns="material", values="quantity", aggfunc="sum"
        )
        historic = historic.reindex(index=regions, columns=polymers).fillna(0.0)
        historic_totals = historic.sum(axis=1)

        missing = [
            region
            for region in regions
            if historic_totals[region] == 0 and (region_totals[region] > 0).any()
        ]
        if missing:
            raise AtlasCouplingError(
                f"Historic plastics {flow} trade has no polymer shares for regions with future "
                f"{flow}: {missing}."
            )

        shares = historic.div(historic_totals.where(historic_totals > 0, 1.0), axis=0)
        seeds.append(region_totals.to_numpy()[:, :, None] * shares.to_numpy()[None, :, :])

    index = _polymer_trade_index(years, regions, polymers)
    return tuple(_polymer_trade_frame(seed, index) for seed in seeds)


def balance_polymer_trade(
    imports: pd.DataFrame, exports: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Balance polymer trade with a RAS (see :func:`_ras_balance`).

    The region totals (summed over polymers) are kept, and the trade of each polymer clears
    globally. Both frames have the columns year, region, material and quantity.
    """
    trade = pd.concat([imports, exports])
    years = sorted(set(trade["year"]))
    regions = sorted(set(trade["region"]))
    polymers = sorted(set(trade["material"]))
    index = _polymer_trade_index(years, regions, polymers)

    arrays = [
        flow.groupby(POLYMER_TRADE_INDEX)["quantity"]
        .sum()
        .reindex(index, fill_value=0.0)
        .to_numpy()
        .reshape(len(years), len(regions), len(polymers))
        for flow in (imports, exports)
    ]
    return tuple(_polymer_trade_frame(balanced, index) for balanced in _ras_balance(*arrays))


def _adjust_plastics_trade(
    imports: pd.DataFrame, exports: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split future plastics trade into polymers, keeping the regional ATLAS totals and clearing
    the trade of each polymer globally."""
    return balance_polymer_trade(*split_plastics_trade(imports, exports))


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
    data = load_atlas_trade_projection(model, source, scenario_pkbudg, region_dimension_path)
    imports, exports = aggregate_bilateral_trade(data)

    _validate_global_balance(imports, exports)

    if model == ModelNames.PLASTICS:
        imports, exports = _adjust_plastics_trade(imports, exports)

    parameter_dir = Path(input_data_path) / "parameters"
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
