import logging
from typing import Optional
from copy import deepcopy
import flodym as fd

from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.cement.cement_definition import get_cement_definition
from remind_mfa.cement.cement_mfa_system_bottom_up import StockDrivenBottomUpCementMFASystem
from remind_mfa.cement.cement_mfa_system_historic import InflowDrivenHistoricCementMFASystem
from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.cement.cement_mappings import CementDimensionFiles, CementDisplayNames
from remind_mfa.cement.cement_export import CementDataExporter
from remind_mfa.cement.cement_visualization import CementVisualizer
from remind_mfa.common.common_model import CommonModel
from remind_mfa.cement.cement_definition import scenario_parameters as cement_scn_prm_def
from remind_mfa.cement.cement_parameter_reconciliation import CementParameterReconciliation


class CementModel(CommonModel):

    ConfigCls = CementCfg
    DimensionFilesCls = CementDimensionFiles
    DataExporterCls = CementDataExporter
    VisualizerCls = CementVisualizer
    DisplayNamesCls = CementDisplayNames
    HistoricMFASystemCls = InflowDrivenHistoricCementMFASystem
    FutureMFASystemCls = StockDrivenCementMFASystem
    BottomUpMFASystemCls = StockDrivenBottomUpCementMFASystem
    custom_scn_prm_def = cement_scn_prm_def
    get_definition = staticmethod(get_cement_definition)

    # TODO: unify, then delete
    end_use_good_letter: str = "s"
    historic_stock_name: str = "in_use"

    def modify_parameters(self):
        # copy/rename for use in common model
        self.parameters["sector_split_limit"] = self.parameters["stock_type_split"]

        # construct lifetime std from mean and relative std
        lifetime_std = fd.Parameter(dims=self.parameters["lifetime_mean"].dims)
        lifetime_std[...] = self.parameters["lifetime_mean"] * self.parameters["lifetime_rel_std"]
        self.parameters["lifetime_std"] = lifetime_std

    def run(self):
        super().run()

        if self.cfg.model_switches.parameter_reconciliation.do_reconcile:
            return self.run_with_reconciliation()

    def make_bottom_up_mfa(self) -> StockDrivenBottomUpCementMFASystem:
        """Construct the future bottom-up MFA."""
        return self.make_mfa(
            definition=self.get_definition(self.cfg, historic=False, bottom_up=True),
            mfasystem_class=self.BottomUpMFASystemCls,
        )

    def run_with_reconciliation(self):
        """Run the full reconciled model pipeline, producing both top-down and bottom-up MFAs.

        Called by `run()` when `do_reconcile` is enabled. Extends the base model run with a
        parameter reconciliation loop that aligns historic top-down and bottom-up stocks, then
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
        self.td_hist_mfa = self.historic_mfa
        self.td_mfa = self.future_mfa

        # TODO zero trade was a cheat to use top-down mfa system for bottom-up - not done currently
        # zero_trade = self._create_zero_trade(self.td_hist_mfa.trade_set)

        # TODO: once we can initialize stock vintage in flodym, we can provide them to bu stock.
        # Then, we can set up a whole the bottom-up MFA system - and compare bu vs td demands.
        # For now, we simply compute non-reconiled bottom-up stock for analysis.
        bu_mfa = self.make_bottom_up_mfa()
        bu_mfa.compute_floorspace_stock()
        bu_mfa.compute_bottom_up_stock()
        self.bu_stock = bu_mfa.stocks["bu_in_use"].stock

        # reconcile parameters
        self.parameters = self.historic_parameters
        self.reconcile_parameters()

        # compute reconciled historic top-down mfa
        self.td_hist_mfa_reconciled = self.make_mfa(historic=True)
        self.td_hist_mfa_reconciled.compute()

        # save reconciled top-down historic mfa for reconciled stock extrapolation
        self.historic_mfa = self.td_hist_mfa_reconciled

        # apply scenarios to parameters for future mfa (as in common model)
        self.extrapolate_parameters()

        # compute reconciled future top-down mfa
        self.td_stock_reconciled = self.get_long_term_stock()  # cement stock
        self.td_mfa_reconciled = self.make_mfa(historic=False)
        self.td_mfa_reconciled.compute(
            self.td_stock_reconciled, self.td_hist_mfa_reconciled.trade_set
        )

        # compute reconciled future bottom-up mfa
        self.bu_mfa_reconciled = self.make_bottom_up_mfa()
        self.bu_mfa_reconciled.compute(
            self.td_mfa_reconciled.stocks["in_use"], self.td_hist_mfa_reconciled.trade_set
        )

        # overwrite future_mfa with update
        self.future_mfa = self.bu_mfa_reconciled

    def reconcile_parameters(
        self,
        max_iter: int = 10,
        tol: Optional[float] = 1e-3,
    ):
        """Reconcile parameters between top-down and bottom-up stocks.

        Args:
            max_iter: Maximum number of correction iterations.
            tol: Convergence tolerance; stop early when max |log(td/bu)| < tol.
                 If None, always run max_iter iterations.
        """
        logging.info(f"Starting parameter reconciliation (max_iter={max_iter}, tol={tol})...")

        ref_mfa = self.make_mfa(historic=True)
        ref_mfa.trade_set = (
            self.historic_mfa.trade_set
        )  # trade is not altered during reconciliation, so we can just take it from the already computed historic MFA

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
