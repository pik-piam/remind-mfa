import logging

import flodym as fd
import numpy as np

from .plastics_mfa_system_future import PlasticsMFASystemFuture
from .plastics_mfa_system_historical import PlasticsMFASystemHistorical
from .plastics_export import PlasticsDataExporter
from .plastics_visualization import PlasticsVisualizer
from .plastics_definition import get_plastics_definition
from .plastics_mappings import PlasticsDisplayNames
from remind_mfa.plastics.plastics_definition import scenario_parameters as plastics_scn_prm_def
from remind_mfa.plastics.plastics_config import PlasticsCfg
from remind_mfa.common.common_definition import EU_MFA_REGION
from remind_mfa.common.common_model import CommonModel


class PlasticsModel(CommonModel[PlasticsCfg]):

    ConfigCls = PlasticsCfg
    DataExporterCls = PlasticsDataExporter
    VisualizerCls = PlasticsVisualizer
    DisplayNamesCls = PlasticsDisplayNames
    HistoricalMFASystemCls = PlasticsMFASystemHistorical
    FutureMFASystemCls = PlasticsMFASystemFuture
    get_definition = staticmethod(get_plastics_definition)
    custom_scn_prm_def = plastics_scn_prm_def

    do_stock_extrapolation_with_time_factor: bool = True
    time_factor_prms = {"horizontal_shift_base": 1970, "growth_rate": 0.02}
    # penetration of plastics at constant income (stock extrapolation function, shifted by the end-use
    # lifetime): 50% in 1970 and ~95% in 2005, when per-capita demand in mature economies plateaued
    # while GDP kept growing.

    def modify_parameters(self):
        # cast lifetime mean to correct dimensions for use in common model
        self.parameters["lifetime_mean"] = fd.Parameter(
            dims=self.dims["t", "r", "u"],
            values=self.parameters["lifetime_mean"].cast_to(self.dims["t", "r", "u"]).values,
        )
        self.parameters["lifetime_std"] = fd.Parameter(
            dims=self.dims["t", "r", "u"],
            values=self.parameters["lifetime_std"].cast_to(self.dims["t", "r", "u"]).values,
        )
        # cast rates that are globally historically zero to the region dimension to allow for future extrapolation
        # differentiated by region
        self.parameters["chemical_recycling_rate"] = fd.Parameter(
            dims=self.dims["r",],
            values=self.parameters["chemical_recycling_rate"].cast_to(self.dims["r",]).values,
        )
        self.parameters["bio_production_rate"] = fd.Parameter(
            dims=self.dims["r",],
            values=self.parameters["bio_production_rate"].cast_to(self.dims["r",]).values,
        )
        self.parameters["daccu_production_rate"] = fd.Parameter(
            dims=self.dims["r",],
            values=self.parameters["daccu_production_rate"].cast_to(self.dims["r",]).values,
        )
        self.parameters["emission_capture_rate"] = fd.Parameter(
            dims=self.dims["r",],
            values=self.parameters["emission_capture_rate"].cast_to(self.dims["r",]).values,
        )

        # the future MFA does not carry the polymer type dimension 'P' (it is redundant with the
        # polymer dimension 'p'), and the waste trade is only used there, so collapse 'P' away
        for name in ("waste_imports", "waste_exports"):
            self.parameters[name] = fd.Parameter(
                name=name,
                dims=self.dims["h", "r", "p"],
                values=self.parameters[name].sum_values_over("P"),
            )

        # calculate landfill rate from historical eol rates (1 - sum of other eol rates)
        self.parameters["landfill_rate"] = fd.Parameter(
            name="landfill_rate",
            dims=self.dims["h", "r"],
            values=(
                1
                - self.parameters["incineration_rate"]
                - self.parameters["mechanical_recycling_rate"]
                - self.parameters["chemical_recycling_rate"].cast_to(self.dims["h", "r"])
            ).values,
        )

        # 0/1 membership of each polymer in its polymer type, derived from the (P, p) sparsity of
        # the end-use split. The future MFA drops the polymer type dimension 'P', since each polymer
        # belongs to exactly one polymer type; multiply a p-resolved array by this mapping to
        # re-expand it to 'P' where the polymer type resolution is needed (e.g. the IAMC export by
        # polymer type).
        membership = self.parameters["end_use_polymer_split"].sum_over(("h", "r", "u"))  # (P, p)
        mapping = fd.Parameter(
            name="polymer_type_mapping",
            dims=self.dims["P", "p"],
            values=(membership.values > 0).astype(float),
        )
        unmapped = mapping.sum_over("P").items_where(lambda x: x != 1)
        if unmapped.size:
            raise ValueError(
                "Each polymer must belong to exactly one polymer type in 'end_use_polymer_split', but "
                f"{[row[0] for row in unmapped]} do(es) not. Check the polymer type/polymer "
                "combinations in the input data and the plastics polymer type and polymer dimension files."
            )
        self.parameters["polymer_type_mapping"] = mapping

    def transfer_historical_parameters(self):
        # get polymer split of stock inflow from historical MFA to be extrapolated by ParameterExtrapolation for use in future MFA
        self.parameters["polymer_shares_use_inflow"] = self.historical_mfa.parameters[
            "polymer_shares_use_inflow"
        ]
        # get global end use split of stock inflow from historical MFA to be used as end-use split limit in the stock extrapolation
        self.parameters["end_use_split_limit"] = fd.Parameter(
            dims=self.dims["u",],
            values=self.historical_mfa.parameters["global_end_use_shares_use_inflow"][
                self.dims["h"].items[-1]
            ].values,
        )

    def compute_transience_parameters(self):
        logging.warning(
            f"TRANSIENCE mode is on. Collection rate, mechanical recycling rate and mechanical recycling yield for {EU_MFA_REGION} region are computed from EU-MFA. "
        )
        v_items, n_items, f_items = (
            self.dims["v"].items,
            self.dims["n"].items,
            self.dims["f"].items,
        )
        # zero denominators (no EU-MFA flows) give NaN/Inf, which are replaced by REMIND-MFA values below
        with np.errstate(divide="ignore", invalid="ignore"):
            self.parameters["collection_rate_EU-MFA"] = fd.Parameter(
                dims=self.dims["v", "n", "f"],
                values=(
                    self.parameters["collected_eol_EU-MFA"]
                    / self.parameters["stock_outflow_EU-MFA"]
                )[{"r": EU_MFA_REGION}].values,
            )
            self.parameters["mechanical_recycling_rate_EU-MFA"] = fd.Parameter(
                dims=self.dims["v", "n"],
                values=(
                    self.parameters["sorted_eol_EU-MFA"].sum_to(("v", "r", "n"))
                    / self.parameters["collected_eol_EU-MFA"].sum_to(("v", "r", "n"))
                )[{"r": EU_MFA_REGION}].values,
            )
            self.parameters["mechanical_recycling_yield_EU-MFA"] = fd.Parameter(
                dims=self.dims["v", "n"],
                values=(
                    self.parameters["recycled_eol_EU-MFA"].sum_to(("v", "r", "n"))
                    / self.parameters["sorted_eol_EU-MFA"].sum_to(("v", "r", "n"))
                )[{"r": EU_MFA_REGION}].values,
            )
        # adjust dimensions of REMIND-MFA rates and replace EU region with EU-MFA rates
        self.parameters["collection_rate"] = fd.Parameter(
            name="collection_rate",
            dims=self.dims["t", "r", "p", "u"],
            values=self.parameters["collection_rate"].cast_to(self.dims["t", "r", "p", "u"]).values,
        )
        eu_mfa_collection_rate = _fill_non_finite(
            "collection_rate_EU-MFA",
            self.parameters["collection_rate_EU-MFA"].values,
            self.parameters["collection_rate"][
                {"r": EU_MFA_REGION, "p": self.dims["n"], "u": self.dims["f"], "t": self.dims["v"]}
            ].values,
            [v_items, n_items, f_items],
        )
        self.parameters["collection_rate"][
            {"r": EU_MFA_REGION, "p": self.dims["n"], "u": self.dims["f"], "t": self.dims["v"]}
        ] = fd.Parameter(dims=self.dims["v", "n", "f"], values=eu_mfa_collection_rate)
        self.parameters["mechanical_recycling_rate"] = fd.Parameter(
            name="mechanical_recycling_rate",
            dims=self.dims["t", "r", "p"],
            values=self.parameters["mechanical_recycling_rate"]
            .cast_to(self.dims["t", "r", "p"])
            .values,
        )
        eu_mfa_mech_rate = _fill_non_finite(
            "mechanical_recycling_rate_EU-MFA",
            self.parameters["mechanical_recycling_rate_EU-MFA"].values,
            self.parameters["mechanical_recycling_rate"][
                {"r": EU_MFA_REGION, "p": self.dims["n"], "t": self.dims["v"]}
            ].values,
            [v_items, n_items],
        )
        self.parameters["mechanical_recycling_rate"][
            {"r": EU_MFA_REGION, "p": self.dims["n"], "t": self.dims["v"]}
        ] = fd.Parameter(dims=self.dims["v", "n"], values=eu_mfa_mech_rate)
        self.parameters["mechanical_recycling_yield"] = fd.Parameter(
            name="mechanical_recycling_yield",
            dims=self.dims["t", "r", "p"],
            values=self.parameters["mechanical_recycling_yield"]
            .cast_to(self.dims["t", "r", "p"])
            .values,
        )
        eu_mfa_mech_yield = _fill_non_finite(
            "mechanical_recycling_yield_EU-MFA",
            self.parameters["mechanical_recycling_yield_EU-MFA"].values,
            self.parameters["mechanical_recycling_yield"][
                {"r": EU_MFA_REGION, "p": self.dims["n"], "t": self.dims["v"]}
            ].values,
            [v_items, n_items],
        )
        self.parameters["mechanical_recycling_yield"][
            {"r": EU_MFA_REGION, "p": self.dims["n"], "t": self.dims["v"]}
        ] = fd.Parameter(dims=self.dims["v", "n"], values=eu_mfa_mech_yield)


def _year_ranges(years: list[int]) -> str:
    """Compress a sorted list of years into ranges, e.g. [1950, 1951, 1952, 1990] -> '1950-1952, 1990'."""
    if not years:
        return "none"
    ranges = []
    start = prev = years[0]
    for y in years[1:]:
        if y != prev + 1:
            ranges.append((start, prev))
            start = y
        prev = y
    ranges.append((start, prev))
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges)


def _fill_non_finite(
    name: str, new: np.ndarray, existing: np.ndarray, items: list[list]
) -> np.ndarray:
    """Replace non-finite entries of new by existing and log a summary: years in which all cells
    are non-finite, and, for the remaining years, each set of non-finite cells with its years.
    The first axis of new must be time; items holds the item lists of all axes."""
    mask = ~np.isfinite(new)
    if not mask.any():
        return new
    years = items[0]
    n_cells = mask[0].size
    full = []
    partial: dict[tuple, list[int]] = {}
    for i, y in enumerate(years):
        if mask[i].all():
            full.append(y)
        elif mask[i].any():
            cells = tuple(
                tuple(item_list[j] for item_list, j in zip(items[1:], idx))
                for idx in np.argwhere(mask[i])
            )
            partial.setdefault(cells, []).append(y)
    partial_str = "".join(
        f"\n  {len(cells)}/{n_cells} cells in {_year_ranges(ys)}: {list(cells)}"
        for cells, ys in partial.items()
    )
    logging.warning(
        f"{name}: {mask.sum()}/{mask.size} non-finite values replaced by REMIND-MFA values "
        f"(of which Inf (x/0): {np.isinf(new).sum()}). Fully missing years: {_year_ranges(full)}. "
        f"Partially missing:{partial_str or ' none'}"
    )
    return np.where(mask, existing, new)
