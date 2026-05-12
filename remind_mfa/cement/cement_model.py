from copy import deepcopy
import flodym as fd
import numpy as np

from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.cement.cement_definition import get_cement_definition
from remind_mfa.cement.cement_mfa_system_historic import InflowDrivenHistoricCementMFASystem
from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.cement.cement_mappings import CementDimensionFiles, CementDisplayNames
from remind_mfa.cement.cement_export import CementDataExporter
from remind_mfa.cement.cement_visualization import CementVisualizer
from remind_mfa.common.common_model import CommonModel
from remind_mfa.cement.cement_definition import scenario_parameters as cement_scn_prm_def
from remind_mfa.cement.cement_parameter_reconciliation import CementParameterReconciliation
from remind_mfa.common.data_blending import CriticallyDampedBlender
from remind_mfa.common.parameter_extrapolation import ParameterExtrapolationManager


class CementModel(CommonModel):

    ConfigCls = CementCfg
    DimensionFilesCls = CementDimensionFiles
    DataExporterCls = CementDataExporter
    VisualizerCls = CementVisualizer
    DisplayNamesCls = CementDisplayNames
    HistoricMFASystemCls = InflowDrivenHistoricCementMFASystem
    FutureMFASystemCls = StockDrivenCementMFASystem
    ParameterReconciliationCls = CementParameterReconciliation
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

        # TODO add cement ratio as parameter here, or rather in mrmfa?

    def run(self):
        self.original_parameters_hist = self.parameters.copy()
        super().run()

        if not self.cfg.model_switches.parameter_reconciliation.do_reconcile:
            return
        
        # collect non-reconciled mfas
        self.td_hist_mfa = self.historic_mfa
        self.td_mfa = self.future_mfa

        # assume trade as zero for BU MFA's, so those are only representative for demands
        zero_trade = self._create_zero_trade(self.td_hist_mfa.trade_set)

        # compute non-reconiled bottom-up mfa
        self.bu_stock = self.get_bottom_up_stock(stock_ref=self.td_mfa.stocks["in_use"].stock) # concrete stock
        self.bu_mfa = self.make_mfa(historic=False)
        self.bu_mfa.compute(self.bu_stock, zero_trade, stock_is_cement=False)

        # reconcile parameters
        self.parameters = self.original_parameters_hist
        self.reconcile_parameters()

        # compute reconciled historic mfa
        self.td_hist_mfa_reconciled = self.make_mfa(historic=True)
        self.td_hist_mfa_reconciled.compute()

        # save reconciled historic mfa for reconciled stock extrapolation
        self.historic_mfa = self.td_hist_mfa_reconciled

        # apply scenarios to parameters for future mfa (as in common model)
        # 1. extend historic parameters into future
        self.parameters = ParameterExtrapolationManager(
            self.cfg, self.dims["h"], self.dims["t"]
        ).apply_prm_extrapolation(self.parameters, self.scenario_parameters)
        # 2. adjust future parameters based on scenario
        self.apply_scenario_adjustments_to_parameters()

        # compute reconciled future top-down mfa
        self.td_stock_reconciled = self.get_long_term_stock() # cement stock        
        self.td_mfa_reconciled = self.make_mfa(historic=False)
        self.td_mfa_reconciled.compute(self.td_stock_reconciled, self.td_hist_mfa_reconciled.trade_set)

        # compute reconciled future bottom-up mfa
        self.bu_stock_reconciled = self.get_bottom_up_stock(stock_ref=self.td_mfa_reconciled.stocks["in_use"].stock) # concrete stock
        self.bu_mfa_reconciled = self.make_mfa(historic=False)
        self.bu_mfa_reconciled.compute(self.bu_stock_reconciled, zero_trade, stock_is_cement=False)

        # compute combined mfa, using bu where possible and td as fallback
        self.combined_mfa = self.compute_combined_mfa(
            td_stock=self.td_mfa_reconciled.stocks["in_use"].stock,
            bu_stock=self.bu_mfa_reconciled.stocks["in_use"].stock,
        )
        if self.cfg.model_switches.parameter_reconciliation.do_combine_mfas:
            self.future_mfa = self.combined_mfa

    def _create_zero_trade(self, trade_ref):
        zero_trade = deepcopy(trade_ref)
        for market in trade_ref.markets.keys():
            zero_trade[market].imports = fd.FlodymArray.full_like(trade_ref[market].imports, fill_value=0)
            zero_trade[market].exports = fd.FlodymArray.full_like(trade_ref[market].exports, fill_value=0)
        return zero_trade

    def get_bottom_up_stock(self, stock_ref: fd.FlodymArray):
        """Calculate bottom-up product stock (product mass, no k constituent dimension).
        Unavailible stock dimensions, e.g. mortar or civ/ind are filled with zeros.
        Data available until 1990. To fill pre-1990 data,
        the stock is backcasted by using growth rate of top-down stock."""
        stock_ref = stock_ref.sum_over("k")  # work at product-mass level
        stock = fd.FlodymArray.full_like(stock_ref, fill_value=0)

        bu_concrete_stock = self.ParameterReconciliationCls.calc_bottom_up_stock(
            self.parameters, stock_type_letter=self.end_use_good_letter
        )
        stock[self.concrete_mask] = bu_concrete_stock
        stock = backcast_by_reference(stock, stock_ref, anchor_year=1990)
        return stock
    
    @property
    def concrete_mask(self):
        return {"m": "concrete"}

    @property
    def bottom_up_mask(self):
        reduced_dim_mask = {
            **self.concrete_mask,
            "s": self.parameter_reconciliation._reduced_stock_type,
        }
        return reduced_dim_mask

    def compute_combined_mfa(self, td_stock, bu_stock):
        # blend at product-mass level (k is a derived quantity, not an independent trajectory)
        td_stock = td_stock.sum_over("k")
        bu_stock = bu_stock.sum_over("k")

        reduced_bu_stock = bu_stock[self.bottom_up_mask]
        reduced_td_stock = td_stock[self.bottom_up_mask][{"t": self.dims["h"]}]

        # blend smoothly between historic td and future bu
        blender = CriticallyDampedBlender(
            time=self.dims["t"].items,
            historical=reduced_td_stock.values,
            prediction=reduced_bu_stock.values,
            # TODO set lifetime here,
        )
        blended_stock = fd.FlodymArray.full_like(
            other=reduced_bu_stock,
            fill_value=blender.blend(),
        )

        # prepare combined stock
        combined_stock = td_stock.copy()
        combined_stock[self.bottom_up_mask] = blended_stock

        # compute combined mfa

        self.combined_mfa = self.make_mfa(historic=False)
        self.combined_mfa.compute(combined_stock, self.historic_trade, stock_is_cement=False)

        return self.combined_mfa

def backcast_by_reference(
    x: fd.FlodymArray,
    ref: fd.FlodymArray,
    anchor_year,
    time_letter: str = "t",
) -> fd.FlodymArray:
    """Fill years before ``anchor_year`` in ``x`` with ``ref`` rescaled to match at the anchor.
    Inspired but simplified from backcast_by_reference in mrmfa: https://github.com/pik-piam/mrmfa.
 
    For each non-time cell the scaling factor is ``x[anchor] / ref[anchor]``.
    That factor is applied to ``ref`` for every year strictly before the anchor,
    so filled values match ``x``'s level at the anchor year and inherit
    ``ref``'s growth in the backcast period. Years at or after the anchor are
    kept as-is from ``x``. Cells where ``ref`` is zero at the anchor (so the
    ratio is undefined) are filled with zero in the backcast period.
 
    Parameters
    ----------
    x
        Array with leading zeros (or any values to be overwritten) before the
        anchor year.
    ref
        Reference array with full coverage and the same dimensions as ``x``.
    anchor_year
        Item from the time dimension where ``x`` is known.
    time_letter
        Letter of the time dimension (default ``"t"``).
    """
    if x.dims.letters != ref.dims.letters:
        raise ValueError(
            f"x and ref must share dimensions; got {x.dims.letters} vs {ref.dims.letters}"
        )
 
    # Per-cell scaling factor at the anchor year. Slicing on a single item
    # drops the time dimension, so the ratio broadcasts over time below.
    # Where ref[anchor] == 0 the ratio is undefined; set it to 0 so the
    # backcast period is filled with zeros for those cells.
    x_anchor = x[{time_letter: anchor_year}]
    ref_anchor = ref[{time_letter: anchor_year}]
    ratio = fd.FlodymArray(dims=x_anchor.dims)
    np.divide(
        x_anchor.values, ref_anchor.values,
        out=ratio.values, where=ref_anchor.values != 0,
    )
 
    # Mask of years strictly before the anchor, shaped to broadcast over the
    # time axis only.
    time_dim = x.dims[time_letter]
    t_axis = x.dims.letters.index(time_letter)
    before = np.array(time_dim.items) < anchor_year
    before = before.reshape([-1 if i == t_axis else 1 for i in range(x.values.ndim)])
 
    # Build the filled array: ref * ratio before the anchor, x from the anchor on.
    scaled = ref * ratio
    out = fd.FlodymArray(dims=x.dims, name=getattr(x, "name", None))
    out.values[...] = np.where(before, scaled.values, x.values)
    return out