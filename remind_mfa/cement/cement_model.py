import logging
from typing import Optional
from copy import deepcopy
import numpy as np
import flodym as fd

from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.cement.cement_bottom_up_definition import bottom_up_scenario_parameters
from remind_mfa.cement.cement_definition import get_cement_definition
from remind_mfa.cement.cement_mfa_system_bottom_up import (
    StockDrivenBottomUpCementMFASystem,
    expand_common_to_bu,
    extend_end_use_intensive,
)
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.data_blending import blend, blend_regional_with_global_mean
from remind_mfa.cement.cement_mfa_system_historical import InflowDrivenHistoricalCementMFASystem
from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.cement.cement_mappings import CementDisplayNames
from remind_mfa.cement.cement_export import CementDataExporter
from remind_mfa.cement.cement_visualization import CementVisualizer
from remind_mfa.common.common_model import CommonModel
from remind_mfa.cement.cement_definition import scenario_parameters as cement_scn_prm_def
from remind_mfa.cement.cement_parameter_reconciliation import CementParameterReconciliation


def converge_lifetime_factor(
    lifetime_current: fd.Parameter,
    lifetime_ref: fd.FlodymArray,
    factor: fd.FlodymArray,
    exponent: float,
) -> fd.FlodymArray:
    """Lifetime extension factor that lets lifetimes converge towards a reference lifetime.

    The new lifetime is max(lifetime_current, factor * lifetime_ref - gap / factor ** exponent),
    with gap = lifetime_ref - lifetime_current. A lifetime equal to the reference is extended by
    `factor`, and the absolute gap of all other lifetimes to it shrinks by 1 / factor ** exponent.
    For factor >= 1, the new lifetime increases monotonically with the current lifetime and is
    never below it. A factor of 1 leaves lifetimes unchanged.
    Plain english: lifetimes below reference receive a larger multiplier than factor,
    lifetimes above reference a smaller one until they just remain at their value.

    Args:
        lifetime_current (fd.Parameter): Current lifetime.
        lifetime_ref (fd.FlodymArray): Reference lifetime to converge towards.
        factor (fd.FlodymArray): Lifetime extension factor at the reference lifetime. Its
            dimensions must contain those of `lifetime_current` and `lifetime_ref`.
        exponent (float): Exponent n of the gap shrinkage 1 / factor ** n.

    Returns:
        fd.Parameter: Ratio of the new to the current lifetime, with the dimensions of `factor`.
    """
    lifetime_current = lifetime_current.cast_to(factor.dims)
    lifetime_ref = lifetime_ref.cast_to(factor.dims)
    lifetime_new = factor * lifetime_ref - (lifetime_ref - lifetime_current) / factor**exponent
    lifetime_factor = lifetime_new.maximum(lifetime_current) / lifetime_current
    return lifetime_factor.to_class(fd.Parameter)


class CementModel(CommonModel[CementCfg]):

    ConfigCls = CementCfg
    DataExporterCls = CementDataExporter
    VisualizerCls = CementVisualizer
    DisplayNamesCls = CementDisplayNames
    HistoricalMFASystemCls = InflowDrivenHistoricalCementMFASystem
    FutureMFASystemCls = StockDrivenCementMFASystem
    BottomUpMFASystemCls = StockDrivenBottomUpCementMFASystem
    custom_scn_prm_def = cement_scn_prm_def
    get_definition = staticmethod(get_cement_definition)

    @property
    def bottom_up_active(self) -> bool:
        """Whether the bottom-up module is active, which is only used for parameter reconciliation."""
        return self.cfg.model_switches.parameter_reconciliation

    def get_scenario_parameter_definitions(self) -> list:
        definitions = super().get_scenario_parameter_definitions()
        if self.bottom_up_active:
            definitions = definitions + bottom_up_scenario_parameters
        return definitions

    def get_inactive_scenario_parameter_names(self) -> set[str]:
        if self.bottom_up_active:
            return set()
        return {definition.name for definition in bottom_up_scenario_parameters}

    def modify_parameters(self):
        # construct lifetime std from mean and relative std
        lifetime_std = fd.Parameter(dims=self.parameters["lifetime_mean"].dims)
        lifetime_std[...] = self.parameters["lifetime_mean"] * self.parameters["lifetime_rel_std"]
        self.parameters["lifetime_std"] = lifetime_std

        self.set_hibernation_share(0.3)

        # development weight for gdp-dependent parameters/scenarios
        self.parameters["development_weight"] = self.calc_development_weight()

    def calc_development_weight(self) -> fd.Parameter:
        """Development weight per region from GDP per capita at the last historical year:
        Blends log(GDP per capita) from 1 at low GDP to 0 at high GDP, with the transition range
        defined by the scenario parameters `development_gdppc_low` and `development_gdppc_high`."""
        gdppc = self.parameters["gdppc"][{"t": self.dims["h"].items[-1]}]
        weight = fd.Parameter(dims=gdppc.dims, name="development_weight")
        weight[...] = blend(
            target_dims=gdppc.dims,
            y_lower=1.0,
            y_upper=0.0,
            x=gdppc.apply(np.log),
            x_lower=np.log(self.scenario_parameters["development_gdppc_low"]),
            x_upper=np.log(self.scenario_parameters["development_gdppc_high"]),
            type="poly_mix",
        )
        return weight

    def set_structure_share(
        self,
        structure_split: fd.Parameter,
        structure: str,
        new_share: fd.FlodymArray | float,
    ) -> fd.Parameter:
        """Set the share of one structure type and rescale the others proportionally.

        Args:
            structure_split: Split over the structure dimension, summing to one.
            structure: Item of the structure dimension whose share is set.
            new_share: New share of `structure`.

        Returns:
            Structure split with the new share, still summing to one.
        """
        old_share = structure_split[{"s": structure}]
        # scaling of the other shares, which absorb the change of the set share
        others_scaling = (1.0 - new_share) / (1.0 - old_share).maximum(1e-9)

        adjusted_split = fd.Parameter(dims=structure_split.dims, name=structure_split.name)
        adjusted_split[...] = structure_split * others_scaling
        adjusted_split[{"s": structure}] = new_share
        return adjusted_split

    def calculate_derived_parameters(self):

        # copy/rename for use in common model
        self.parameters["end_use_split_limit"] = self.parameters["end_use_split"]

        if self.bottom_up_active:
            self.calculate_bottom_up_scenario_parameters()

    def calculate_bottom_up_scenario_parameters(self):

        # derive mean residential type and structure splits from global weighted average
        prm = self.parameters
        floorspace = prm["floorspace"][{"t": self.dims["h"].items[-1]}]

        # residential type split target
        res_floorspace = floorspace[{"c": "Residential"}]
        prm["residential_type_split_mean"] = blend_regional_with_global_mean(
            regional_values=prm["residential_type_split"],
            mean_weights=res_floorspace,
            global_share=prm["development_weight"],
            name="residential_type_split_mean",
        )

        # structure split target: global weighted mean without unknown structures,
        # with a floor on the timber share
        bu_floorspace = expand_common_to_bu(floorspace, prm)
        structure_split_mean = blend_regional_with_global_mean(
            regional_values=prm["structure_split"],
            mean_weights=bu_floorspace,
            global_share=prm["development_weight"],
            name="structure_split_mean",
        )
        # where no structure type is known, the regional split carries no information:
        # fall back to the global mean
        global_structure_split_mean = (prm["structure_split"] * bu_floorspace).sum_over(
            "r"
        ) / bu_floorspace.sum_over("r")
        only_unspecified = structure_split_mean[{"s": "Unspecified Structure"}].apply(
            lambda x: (x > 1.0 - 1e-9).astype(float)
        )
        structure_split_mean[...] = (
            structure_split_mean * (1.0 - only_unspecified)
            + global_structure_split_mean * only_unspecified
        )
        add_assumption_doc(
            type="model switch",
            name="Global mean structure split for unknown structures",
            description=(
                "Where the historical structure split contains only the unknown structure type, "
                "the structure split converges to the global weighted mean."
            ),
        )
        prm["structure_split_mean"] = self.set_structure_share(
            structure_split_mean, "Unspecified Structure", 0.0
        )
        add_assumption_doc(
            type="model switch",
            name="No unknown structure type in target",
            value="0",
            description=(
                "The structure split converges to a target without the unknown structure type. "
                "Its share is redistributed to the other structure types proportionally."
            ),
        )

        timber = prm["structure_split_mean"][{"s": "Timber Structure"}]
        floor = self.scenario_parameters["min_timber_share"].cast_to(timber.dims)
        prm["structure_split_target"] = self.set_structure_share(
            prm["structure_split_mean"], "Timber Structure", timber.maximum(floor)
        )
        add_assumption_doc(
            type="model switch",
            name="Minimum timber share of buildings",
            value=str(np.unique(floor.values)),
            description=(
                "The structure split converges to a target in which the timber share is at "
                "least the scenario value given here. Regions above it keep their share. The "
                "added timber share is taken from the other structure types proportionally."
            ),
        )

    def get_lifetime_factor_cohort(self) -> fd.Parameter:
        """Lifetime extension factor by age-cohort (nature), derived from the scenario parameter
        `lifetime_factor_nature`.

        Lifetimes of new age-cohorts converge to the GDP-weighted regional mean lifetime of the
        last historical year (see `converge_lifetime_factor`).
        """
        lifetime_convergence_exponent = 3
        factor = self.parameters["lifetime_factor_nature"]
        last_historical = {"t": self.dims["h"].items[-1]}

        # calculate gdp-weighted global lifetime average
        lifetime_current = self.parameters["lifetime_mean"][last_historical]
        gdp = (
            self.parameters["gdppc"][last_historical]
            * self.parameters["population"][last_historical]
        )
        lifetime_ref = (lifetime_current * gdp).sum_over("r") / gdp.sum_over("r")

        add_assumption_doc(
            type="model switch",
            name="Lifetime convergence of new age-cohorts",
            value=lifetime_convergence_exponent,
            description=(
                "New age-cohorts (nature) of a region at the GDP-weighted regional mean lifetime "
                "of the last historical year are extended by 'lifetime_factor_nature'. The gap of "
                "other regions to this reference lifetime shrinks by the factor "
                "1 / lifetime_factor_nature ** n, with n = 3. Lifetimes are never reduced."
            ),
        )
        return converge_lifetime_factor(
            lifetime_current, lifetime_ref, factor, lifetime_convergence_exponent
        )

    def run(self):
        super().run()

        if self.cfg.model_switches.parameter_reconciliation:
            return self.run_with_reconciliation()

    def make_bottom_up_mfa(self) -> StockDrivenBottomUpCementMFASystem:
        """Construct the future bottom-up MFA.

        Intensive end-use-resolved parameters (`intensive_end_use_prms`) are broadcasted to the
        extended-end-use dimension for the bottom-up MFA.
        """
        intensive_end_use_prms = (
            "lifetime_mean",
            "lifetime_std",
            "lifetime_factor_nurture",
            "lifetime_factor_cohort",
        )
        bu_mfa = self.make_mfa(
            definition=self.get_definition(self.cfg, historical=False, bottom_up=True),
            mfasystem_class=self.BottomUpMFASystemCls,
        )
        bu_mfa.parameters = {
            **bu_mfa.parameters,
            **{
                name: extend_end_use_intensive(self.parameters[name], self.dims["e"])
                for name in intensive_end_use_prms
            },
        }
        return bu_mfa

    def run_with_reconciliation(self):
        """Run the full reconciled model pipeline, producing both top-down and bottom-up MFAs.

        Called by `run()` when `parameter_reconciliation` is enabled. Extends the base model run with a
        parameter reconciliation loop that aligns historical top-down and bottom-up stocks, then
        propagates reconciled parameters into the future projection.

        Saves the full set of MFAs as attributes:
        - `td_hist_mfa`: Original historical top-down MFA (pre-reconciliation) as calculated in super.run().
        - `td_mfa`: Original future top-down MFA (pre-reconciliation) as calculated in super.run().
        - `bu_mfa`: Future bottom-up MFA calculated from original parameters and zero trade (pre-reconciliation).
        - `td_hist_mfa_reconciled`: Reconciled historical top-down MFA.
        - `td_mfa_reconciled`: Reconciled future top-down MFA.
        - `bu_mfa_reconciled`: Reconciled future bottom-up MFA.
        - `combined_mfa`: Future MFA combining reconciled bottom-up where available and top-down as fallback (if enabled in config).

        """

        # collect non-reconciled mfas
        self.td_hist_mfa = self.historical_mfa
        self.td_mfa = self.future_mfa

        # TODO zero trade was a cheat to use top-down mfa system for bottom-up - not done currently
        # zero_trade = self._create_zero_trade(self.td_hist_mfa.trade_set)

        # TODO: once we can initialize stock vintage in flodym, we can provide them to bu stock.
        # Then, we can set up a whole the bottom-up MFA system - and compare bu vs td demands.
        # For now, we simply compute non-reconiled bottom-up stock for analysis.
        bu_mfa = self.make_bottom_up_mfa()
        bu_mfa.compute_floorspace_stock()
        self.bu_stock = bu_mfa.compute_bottom_up_stock()

        # reconcile parameters, then re-derive dependent parameters from the result
        self.parameters = self.historical_parameters
        self.reconcile_parameters()
        self.calculate_derived_parameters()

        # compute reconciled historical top-down mfa
        self.td_hist_mfa_reconciled = self.make_mfa(historical=True)
        self.td_hist_mfa_reconciled.compute()

        # save reconciled top-down historical mfa for reconciled stock extrapolation
        self.historical_mfa = self.td_hist_mfa_reconciled

        # apply scenarios to parameters for future mfa (as in common model)
        self.extrapolate_parameters()

        # compute reconciled future top-down mfa
        self.td_stock_reconciled = self.get_long_term_stock()
        self.td_mfa_reconciled = self.make_mfa(historical=False)
        self.td_mfa_reconciled.compute(
            self.td_stock_reconciled, self.td_hist_mfa_reconciled.trade_set
        )

        # compute reconciled future bottom-up mfa
        self.bu_mfa_reconciled = self.make_bottom_up_mfa()
        self.bu_mfa_reconciled.compute(
            self.td_mfa_reconciled.stocks["use"], self.td_hist_mfa_reconciled.trade_set
        )

        # overwrite future_mfa with update
        self.future_mfa = self.bu_mfa_reconciled

    def reconcile_parameters(
        self,
        max_iter: int = 5,
        tol: Optional[float] = 1e-3,
    ):
        """Reconcile parameters between top-down and bottom-up stocks.

        Args:
            max_iter: Maximum number of correction iterations.
            tol: Convergence tolerance; stop early when max |log(td/bu)| < tol.
                 If None, always run max_iter iterations.
        """
        logging.info(f"Starting parameter reconciliation (max_iter={max_iter}, tol={tol})...")

        ref_mfa = self.make_mfa(historical=True)
        ref_mfa.trade_set = (
            self.historical_mfa.trade_set
        )  # trade is not altered during reconciliation, so we can just take it from the already computed historical MFA

        self.parameter_reconciliation = CementParameterReconciliation(
            ref_mfa=ref_mfa,
            output_dims_are_independent=True,
        )
        self.parameters = self.parameter_reconciliation.correct_parameters(
            max_iter=max_iter,
            tol=tol,
        )

    def _create_zero_trade(self, trade_ref):
        zero_trade = deepcopy(trade_ref)
        for market in trade_ref.markets.keys():
            zero_trade[market].imports = fd.FlodymArray.full_like(
                trade_ref[market].imports, fill_value=0
            )
            zero_trade[market].exports = fd.FlodymArray.full_like(
                trade_ref[market].exports, fill_value=0
            )
        return zero_trade
