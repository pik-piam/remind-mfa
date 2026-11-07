"""Validation: the IAMC variables of the models against the validation data, and the REMIND
inputs the models produce against the ones REMIND currently uses."""

import functools
import io
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

import blicket as bk
from blicks._helpers import REGION, REGION_SPLIT, TIME, VALUE, by_model, frame, model_of

if TYPE_CHECKING:  # annotations only, so blicket list does not import remind-mfa
    from blicketconf import Run
    from remind_mfa.common.common_model import CommonModel

bk.group("validation", title="Validation against external data")

SOURCE = "Source"
SCENARIO = "Scenario"
SERIES = "Series"
VARIABLE = "Variable"
VALIDATION_FILE = Path("validation") / "validation.mif"
IAMC_ID_COLUMNS = ["model", "scenario", "region", "variable", "unit"]
GIGATONNES = 1e-9


@bk.blick(
    title="IAMC variables against validation data",
    plot=bk.plots.line(x=TIME, y=VALUE, color=SOURCE, linetype=SCENARIO),
    controls=REGION_SPLIT,
    independent_y=True,
)
def iamc_against_validation(run: "Run") -> pd.DataFrame:
    """Every IAMC variable of the models that the validation data also reports, per region and
    year, one model and variable at a time: the model as one source, each model of the validation
    data as another, in the units of the IAMC export, which the variable names carry.

    The validation data is data_in/validation/validation.mif; the Blick is skipped when the
    input data folder lacks it.
    """
    path = Path(next(iter(run)).cfg.input.input_data_path) / VALIDATION_FILE
    if not path.is_file():
        raise bk.Skip(f"no validation data at {path}")
    validation = _iamc_long(_read_mif(path))
    return by_model(run, functools.partial(_against_validation, validation=validation))


def _against_validation(model: "CommonModel", validation: pd.DataFrame) -> pd.DataFrame:
    """The model's IAMC variables that ``validation`` also reports, as one table of sources."""
    iamc = model.data_writer.iamc_dataframe(model)
    if iamc is None:
        raise bk.Skip(f"the {model.name} model reports no IAMC variables")
    modelled = _iamc_long(iamc.data)
    first = modelled.drop_duplicates("key").set_index("key")
    units, names = first["unit"], first["variable"]
    validation = validation[validation["key"].isin(units.index)]
    table = pd.concat([modelled, validation], ignore_index=True)
    table[VARIABLE] = table["key"].map(names) + " [" + table["key"].map(units) + "]"
    table = table.rename(columns={"model": SOURCE, "scenario": SCENARIO, "region": REGION})
    return table[[VARIABLE, SOURCE, SCENARIO, REGION, TIME, VALUE]].sort_values(
        [VARIABLE, SOURCE, SCENARIO, REGION, TIME], ignore_index=True
    )


def _iamc_long(data: pd.DataFrame) -> pd.DataFrame:
    """IAMC data, wide or long, as a long table with ``key``, the variable in lowercase."""
    data = data.rename(columns={column: str(column).lower() for column in data.columns})
    if "year" not in data.columns:
        years = [column for column in data.columns if column not in IAMC_ID_COLUMNS]
        data = data.melt(id_vars=IAMC_ID_COLUMNS, value_vars=years, var_name="year")
    data = data.dropna(subset=["value"])
    return pd.DataFrame(
        {
            "model": data["model"].astype(str),
            "scenario": data["scenario"].astype(str),
            "region": data["region"].astype(str),
            "variable": data["variable"].astype(str),
            "key": data["variable"].astype(str).str.lower(),
            "unit": data["unit"].astype(str),
            TIME: pd.to_numeric(data["year"]).astype(int),
            VALUE: pd.to_numeric(data["value"]),
        }
    )


@functools.cache
def _read_mif(path: Path) -> pd.DataFrame:
    """A ``.mif`` file: semicolon-separated with a trailing semicolon, ``N/A`` for missing."""
    data = pd.read_csv(path, sep=";", na_values=["N/A"])
    return data.loc[:, [column for column in data.columns if not str(column).startswith("Unnamed")]]


# --- the REMIND inputs --------------------------------------------------------------------------


@bk.blick(
    title="Steel production against the REMIND inputs",
    unit="Gt per year",
    plot=bk.plots.line(x=TIME, y=VALUE, color=SOURCE, linetype=SERIES),
    controls=REGION_SPLIT,
    independent_y=True,
)
def remind_steel_production(run: "Run") -> pd.DataFrame:
    """Total and secondary steel production of the steel model against the steel demand
    REMIND's input data holds per scenario (f_fedemandInd.cs4r), per region and year.

    The REMIND inputs are read from the newest *_remind.tgz archive in the madrat output
    folder; the Blick is skipped without one. Only the regions both resolve are shown: run the
    model with the mrindustry configuration layer for REMIND's region mapping.
    """
    steel = model_of(run, "steel")
    archive = _remind_archive(steel)
    demand = _remind_demand(archive)
    remind = pd.concat(
        {
            "Total": demand["ue_steel_primary"] + demand["ue_steel_secondary"],
            "Secondary": demand["ue_steel_secondary"],
        },
        names=[SERIES],
    ).reset_index()
    modelled = _mrindustry(
        steel, {"steel_production_total": "Total", "steel_production_secondary": "Secondary"}
    )
    return _against_remind(modelled, remind)


@bk.blick(
    title="Secondary steel share against the REMIND inputs",
    unit="fraction",
    plot=bk.plots.line(x=TIME, y=VALUE, color=SOURCE, linetype=SERIES),
    controls=REGION_SPLIT,
)
def remind_secondary_steel_share(run: "Run") -> pd.DataFrame:
    """The secondary share of the steel model's production against REMIND's maximum secondary share
    (p37_steel_secondary_max_share.cs4r) and the share in REMIND's steel demand, per region
    and year."""
    steel = model_of(run, "steel")
    archive = _remind_archive(steel)
    demand = _remind_demand(archive)
    total = demand["ue_steel_primary"] + demand["ue_steel_secondary"]
    maximum = _read_cs4r(
        archive, "p37_steel_secondary_max_share.cs4r", [TIME, REGION, SCENARIO, VALUE]
    )
    remind = pd.concat(
        {
            "Share in demand": (demand["ue_steel_secondary"] / total.where(total != 0)),
            "Maximum share": maximum.set_index([TIME, REGION, SCENARIO])[VALUE],
        },
        names=[SERIES],
    ).reset_index()
    production = _mrindustry(
        steel, {"steel_production_total": "total", "steel_production_secondary": "secondary"}
    ).pivot(index=[TIME, REGION], columns=SERIES, values=VALUE)
    modelled = (
        (production["secondary"] / production["total"].where(production["total"] != 0))
        .rename(VALUE)
        .reset_index()
        .assign(**{SERIES: "Share in production"})
    )
    return _against_remind(modelled, remind, scale=1.0)


@bk.blick(
    title="Cement production against the REMIND inputs",
    unit="Gt per year",
    plot=bk.plots.line(x=TIME, y=VALUE, color=SOURCE),
    controls=REGION_SPLIT,
    independent_y=True,
)
def remind_cement_production(run: "Run") -> pd.DataFrame:
    """Cement production of the cement model against the cement demand REMIND's input data holds per
    scenario, per region and year."""
    cement = model_of(run, "cement")
    demand = _remind_demand(_remind_archive(cement))
    remind = demand["ue_cement"].rename(VALUE).reset_index().assign(**{SERIES: "Cement"})
    modelled = _mrindustry(cement, {"cement_production": "Cement"})
    return _against_remind(modelled, remind).drop(columns=SERIES)


@bk.blick(
    title="Clinker ratio against the REMIND inputs",
    unit="fraction",
    plot=bk.plots.line(x=TIME, y=VALUE, color=SOURCE),
    controls=REGION_SPLIT,
)
def remind_clinker_ratio(run: "Run") -> pd.DataFrame:
    """The clinker-to-cement ratio of the cement model against the one REMIND's input data holds
    (p37_clinker-to-cement-ratio.cs4r), per region and year."""
    cement = model_of(run, "cement")
    archive = _remind_archive(cement)
    ratio = _read_cs4r(archive, "p37_clinker-to-cement-ratio.cs4r", [TIME, REGION, VALUE])
    remind = ratio.assign(**{SCENARIO: "all", SERIES: "Clinker ratio"})
    modelled = _mrindustry(cement, {"cement_clinker_ratio": "Clinker ratio"})
    return _against_remind(modelled, remind, scale=1.0).drop(columns=SERIES)


def _remind_archive(model: "CommonModel") -> Path:
    """The newest REMIND input data archive in the madrat output folder of the model's config."""
    try:
        folder = Path(model.cfg.input.resolved_madrat_output_path)
    except ValueError as error:
        raise bk.Skip(str(error)) from error
    archives = sorted(folder.glob("*_remind.tgz"))
    if not archives:
        raise bk.Skip(f"no *_remind.tgz archive in {folder}")
    return archives[-1]


def _read_cs4r(archive: Path, name: str, columns: list[str]) -> pd.DataFrame:
    """A ``.cs4r`` file of a madrat archive as a table with ``columns``."""
    with tarfile.open(archive, "r:gz") as tar:
        try:
            stream = tar.extractfile(f"./{name}")
        except KeyError:
            raise bk.Skip(f"{name} is not in {archive.name}") from None
        if stream is None:
            raise bk.Skip(f"{name} cannot be read from {archive.name}")
        text = io.TextIOWrapper(stream, encoding="utf-8")
        return pd.read_csv(text, comment="*", header=None, names=columns)


def _remind_demand(archive: Path) -> pd.DataFrame:
    """REMIND's industry demand per year, region and scenario, one column per variable, in Gt."""
    demand = _read_cs4r(archive, "f_fedemandInd.cs4r", [TIME, REGION, SCENARIO, VARIABLE, VALUE])
    return demand.pivot_table(index=[TIME, REGION, SCENARIO], columns=VARIABLE, values=VALUE)


def _mrindustry(model: "CommonModel", series: dict[str, str]) -> pd.DataFrame:
    """The model's REMIND input variables named in ``series`` (variable name to series label),
    per year and region, from the definitions of the model's exporter."""
    variables = {v.name: v for v in model.data_writer.get_mrindustry_variables()}
    parts = {}
    for name, label in series.items():
        array = variables[name].calculation_function(model.future_mfa)
        parts[label] = frame(array.sum_to(("t", "r")))
    return pd.concat(parts, names=[SERIES]).reset_index(level=SERIES).reset_index(drop=True)


def _against_remind(
    modelled: pd.DataFrame, remind: pd.DataFrame, scale: float = GIGATONNES
) -> pd.DataFrame:
    """The model (its values times ``scale``, t to Gt by default) and REMIND's scenarios as
    sources of one table, over the regions both have and the years of the model."""
    modelled = modelled.assign(**{VALUE: modelled[VALUE] * scale, SOURCE: "REMIND-MFA"})
    remind = remind.assign(**{SOURCE: "REMIND " + remind[SCENARIO].astype(str)})
    regions = set(modelled[REGION]) & set(remind[REGION])
    remind = remind[remind[TIME].between(modelled[TIME].min(), modelled[TIME].max())]
    table = pd.concat([modelled, remind], ignore_index=True)
    table = table[table[REGION].isin(regions)]
    table[TIME] = table[TIME].astype(int)
    return table[[SOURCE, SERIES, TIME, REGION, VALUE]].reset_index(drop=True)
