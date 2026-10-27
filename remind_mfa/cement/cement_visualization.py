from pydantic import PrivateAttr
import flodym as fd
from typing import TYPE_CHECKING, Optional
import logging

from remind_mfa.common.common_visualization import CommonVisualizer, SANKEY_COLORS
from remind_mfa.cement.cement_config import CementVisualizationCfg
from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem

if TYPE_CHECKING:
    from remind_mfa.cement.cement_model import CementModel


class CementVisualizer(CommonVisualizer):
    cfg: CementVisualizationCfg

    _model: Optional["CementModel"] = PrivateAttr(default=None)

    def _end_use_letter(self, mfa: fd.MFASystem) -> str:
        """The end-use-like letter the MFA's flows carry: u in top-down runs,
        e in combined/reconciled runs."""
        return "e" if "e" in mfa.flows["construction => use"].dims.letters else "u"

    def _end_use_dim_name(self, mfa: fd.MFASystem) -> str:
        return mfa.dims[self._end_use_letter(mfa)].name

    def visualize_custom(self):
        mfa: StockDrivenCementMFASystem = self._model.future_mfa
        if self.cfg.clinker_production.do_visualize:
            self.visualize_clinker_production(mfa=mfa)
        if self.cfg.cement_production.do_visualize:
            self.visualize_cement_production(mfa=mfa, regional=False)
            self.visualize_cement_production(mfa=mfa, regional=True)
        if self.cfg.construction.do_visualize:
            self.visualize_construction(mfa=mfa)
        if self.cfg.eol_stock.do_visualize:
            self.visualize_eol_stock(mfa=mfa)
        if self.cfg.carbonation.do_visualize:
            if not self._model.cfg.model_switches.carbonation:
                logging.warning(
                    "Carbonation visualization requested, but carbonation module not activated."
                )
            else:
                self.visualize_carbonation(mfa=mfa)

    def visualize_sankey(self, mfa: fd.MFASystem):
        flow_color_dict = {"default": SANKEY_COLORS["production"]}
        flow_color_dict.update(
            {
                fn: SANKEY_COLORS["eol"]
                for fn, f in mfa.flows.items()
                if f.from_process.name == "eol_management"
            }
        )
        flow_color_dict.update(
            {
                fn: SANKEY_COLORS["losses"]
                for fn, f in mfa.flows.items()
                if f.to_process.name in ("hibernating", "eol_waste")
            }
        )
        flow_color_dict.update(
            {
                fn: SANKEY_COLORS["trade"]
                for fn, f in mfa.flows.items()
                if f.from_process.name == "imports" or f.to_process.name == "exports"
            }
        )

        # only the cement share of concrete and other construction materials
        self.cfg.sankey.plotter_args.setdefault("slice_dict", {}).setdefault("k", "Cement")

        legend_categories = ["production", "losses"]
        self._plot_styled_sankey(
            mfa, flow_color_dict, legend_categories, end_use_dim=self._end_use_dim_name(mfa)
        )

    def visualize_clinker_production(self, mfa: fd.MFASystem, regional: bool = False):
        production = (
            mfa.flows["clinker_production => clinker_market"]
            + mfa.flows["clinker_production => sysenv"]
        )
        self.visualize_fdarr(mfa=mfa, flow=production, name="Clinker production", regional=regional)

    def visualize_cement_production(self, mfa: fd.MFASystem, regional: bool = False):
        production = mfa.flows["cement_production => cement_market"]
        self.visualize_fdarr(mfa=mfa, flow=production, name="Cement production", regional=regional)

    def visualize_construction(self, mfa: fd.MFASystem, regional: bool = False):
        production = mfa.flows["construction => use"].sum_over(self._end_use_letter(mfa))
        self.visualize_fdarr(
            mfa=mfa, flow=production, name="Construction material production", regional=regional
        )

    def visualize_consumption(self, mfa: fd.MFASystem):
        consumption = mfa.stocks["use"].inflow[{"k": "Cement"}]
        self.visualize_fdarr_stacked(
            mfa=mfa,
            flow=consumption,
            name="Cement consumption",
            linecolor_dim=self._end_use_dim_name(mfa),
            regional=True,
        )

    def visualize_eol_stock(self, mfa: fd.MFASystem):
        pass

    def visualize_use_stock(self, mfa: fd.MFASystem, subplots_by_end_use=False):
        subplot_dim = self._end_use_dim_name(mfa) if subplots_by_end_use else None
        stock = mfa.stocks["use"].stock[{"k": "Cement"}]
        super().visualize_use_stock(mfa, stock=stock, subplot_dim=subplot_dim)

    def visualize_carbonation(self, mfa: fd.MFASystem):
        annual_uptake = mfa.stocks["carbonated_co2"].inflow
        cumulative_uptake = mfa.stocks["carbonated_co2"].stock
        linecolor_dim = "Carbonation Location"
        self.visualize_fdarr_stacked(
            mfa=mfa,
            flow=annual_uptake,
            name="Annual CO2 uptake from carbonation",
            linecolor_dim=linecolor_dim,
            regional=False,
        )
