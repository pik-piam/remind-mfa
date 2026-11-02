import numpy as np
from pydantic import PrivateAttr
import flodym as fd
from typing import TYPE_CHECKING, Optional

from remind_mfa.common.common_visualization import CommonVisualizer, SANKEY_COLORS
from remind_mfa.steel.steel_config import SteelVisualizationCfg

if TYPE_CHECKING:
    from remind_mfa.steel.steel_model import SteelModel


class SteelVisualizer(CommonVisualizer):

    cfg: SteelVisualizationCfg

    _model: Optional["SteelModel"] = PrivateAttr(default=None)

    def visualize_custom(self):
        if self.cfg.production.do_visualize:
            self.visualize_production(mfa=self._model.future_mfa, regional=True)
            self.visualize_production(mfa=self._model.future_mfa, regional=False)
        if self.cfg.scrap_demand_supply.do_visualize:
            self.visualize_scrap_demand_supply(self._model.future_mfa, regional=True)
            self.visualize_scrap_demand_supply(self._model.future_mfa, regional=False)
        self.stop_and_show()

    def visualize_consumption(self, mfa: fd.MFASystem):
        self.visualize_fdarr_stacked(
            mfa=mfa,
            flow=mfa.stocks["use"].inflow,
            name="Consumption",
            linecolor_dim="End Use",
            regional=True,
        )

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
                fn: SANKEY_COLORS["recycling"]
                for fn, f in mfa.flows.items()
                if f.from_process.name in ("scrap_market", "scrap_pool")
                or f.to_process.name in ("scrap_market", "scrap_pool")
            }
        )
        flow_color_dict.update(
            {
                fn: SANKEY_COLORS["losses"]
                for fn, f in mfa.flows.items()
                if f.to_process.name in ("losses", "excess_scrap", "hibernating", "eol_waste")
            }
        )
        flow_color_dict.update(
            {
                fn: SANKEY_COLORS["trade"]
                for fn, f in mfa.flows.items()
                if f.from_process.name == "imports" or f.to_process.name == "exports"
            }
        )

        legend_categories = ["production", "recycling", "losses"]
        self._plot_styled_sankey(mfa, flow_color_dict, legend_categories)

    def visualize_production_consumption(self, mfa: fd.MFASystem, regional=True):
        flw = mfa.flows
        production = (
            flw["steel_production_ore_based => forming"]
            + flw["steel_production_scrap_based => forming"]
        )
        manufacturing = flw["steel_market => manufacturing"]
        consumption = mfa.stocks["use"].inflow.sum_over("u")
        array_dict = {
            "Production": production,
            "Manufacturing": manufacturing,
            "Consumption": consumption,
        }

        subplot_dim, summing_func, name_str = self._get_regional_vs_global_params(regional)

        # visualize regional production
        fig = None
        for label, array in array_dict.items():
            plotter = self.plotter_class(
                array=summing_func(array),
                intra_line_dim="Time",
                **subplot_dim,
                line_label=label,
                display_names=self.display_names.dct,
                xlabel="Year",
                ylabel="Steel Flows [t]",
                fig=fig,
                # title=f"Steel Production {name_str}",
            )
            fig = plotter.plot()

        self.plot_and_save_figure(plotter, f"production_{name_str}", do_plot=False)

    def visualize_production(self, mfa: fd.MFASystem, regional=True):
        production = (
            mfa.flows["steel_production_ore_based => forming"]
            + mfa.flows["steel_production_scrap_based => forming"]
        )
        self.visualize_fdarr(mfa=mfa, flow=production, name="Steel production", regional=regional)

    def visualize_use_stock(self, mfa: fd.MFASystem, subplots_by_end_use=False):
        subplot_dim = "End Use" if subplots_by_end_use else None
        super().visualize_use_stock(mfa, stock=mfa.stocks["use"].stock, subplot_dim=subplot_dim)

    def visualize_trade(self, mfa: fd.MFASystem, linecolor_dims=False):
        if linecolor_dims is True:
            linecolor_dims = {
                "steel": None,
                "manufactured_products": "End Use",
                "scrap": None,
            }
        else:
            linecolor_dims = {
                "steel": None,
                "manufactured_products": None,
                "scrap": None,
            }
        super().visualize_trade(mfa, linecolor_dims=linecolor_dims)

    def visualize_scrap_demand_supply(self, mfa: fd.MFASystem, regional=True):

        subplot_dim, summing_func, name_str = self._get_regional_vs_global_params(regional)

        flw = mfa.flows
        prm = mfa.parameters

        total_production = (
            flw["forming => steel_market"]
            / (prm["forming_yield"] * (1 - prm["steel_production_loss_rate"]))
        )[{"t": mfa.dims["h"]}]
        scrap_supply = (
            flw["scrap_market => scrap_pool"]
            + flw["forming => scrap_pool"]
            + flw["manufacturing => scrap_pool"]
        )
        scrap_supply = scrap_supply[{"t": mfa.dims["h"]}]

        ap = self.plotter_class(
            array=summing_func(scrap_supply),
            intra_line_dim="Historical Time",
            **subplot_dim,
            line_label="Model",
            # fig=fig,
            display_names=self.display_names.dct,
        )
        fig = ap.plot()

        ap = self.plotter_class(
            array=summing_func(mfa.parameters["scrap_consumption"]),
            intra_line_dim="Historical Time",
            **subplot_dim,
            line_label="Real World" + (" - Reconstructed" if regional else ""),
            fig=fig,
            xlabel="Year",
            ylabel="Scrap [t]",
            line_type="dot" if regional else "solid",
            display_names=self.display_names.dct,
            title="Scrap Demand and Supply",
        )
        fig = ap.plot()

        if regional:
            v = mfa.parameters["scrap_consumption_no_assumptions"].values
            v[v == 0] = np.nan
            ap = self.plotter_class(
                array=summing_func(mfa.parameters["scrap_consumption_no_assumptions"]),
                intra_line_dim="Historical Time",
                **subplot_dim,
                line_label="Real World",
                fig=fig,
                xlabel="Year",
                ylabel="Scrap [t]",
                display_names=self.display_names.dct,
                title="Scrap Demand and Supply",
            )
            fig = ap.plot()

        ap = self.plotter_class(
            array=summing_func(total_production.sum_to(("h", "r"))),
            intra_line_dim="Historical Time",
            **subplot_dim,
            line_label="Total Production",
            line_type="dash",
            fig=fig,
        )

        # for trade_name, trade in mfa.trade_set.markets.items():
        #     fig = ap.plot()

        #     ap = self.plotter_class(
        #         array=summing_func(trade.net_imports[{"t": mfa.dims["h"]}].sum_to(("h", "r"))),
        #         intra_line_dim="Historical Time",
        #         **subplot_dim,
        #         line_label=f"Net imports ({trade_name})",
        #         line_type="dot",
        #         fig=fig,
        #     )

        self.plot_and_save_figure(ap, f"scrap_demand_supply_{name_str}")
