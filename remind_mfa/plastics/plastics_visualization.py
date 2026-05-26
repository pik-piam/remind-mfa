import flodym as fd
import numpy as np
import pandas as pd

import plotly.graph_objects as go
from typing import TYPE_CHECKING
import flodym.export as fde
import plotly.express as px

from remind_mfa.common.common_visualization import CommonVisualizer

if TYPE_CHECKING:
    from remind_mfa.plastics.plastics_model import PlasticsModel


class PlasticsVisualizer(CommonVisualizer):

    def visualize_custom(self, model: "PlasticsModel"):
        if self.cfg.use_stock.do_visualize:
            self.visualize_stock(mfa=model.future_mfa)

        if self.cfg.consumption.do_visualize:
            self.compare_demand(mfa=model.future_mfa)
            self.visualize_material_splits(mfa=model.future_mfa)

        if self.cfg.extrapolation.do_visualize:
            self.visualize_extrapolation(model=model, subplot_dim="Good", linecolor_dim="Region")
            self.visualize_extrapolation(model=model, subplot_dim="Region", linecolor_dim="Good")
            self.visualize_extrapolation_functions(model=model, stock_handler=model.stock_handler)

        if self.cfg.flows.do_visualize:
            self.visualize_flow(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["polymerization => primary_market"],
                name="Primary production",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.future_mfa,
                flow=(
                    model.future_mfa.flows["polymerization => primary_market"]
                    - model.future_mfa.flows["primary_market => exports"]
                ),
                name="Primary production for domestic market",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["primary_market => fabrication"],
                name="Primary plastics demand",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["fabrication => good_market"],
                name="Fabrication",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.future_mfa,
                flow=(
                    model.future_mfa.flows["fabrication => good_market"]
                    - model.future_mfa.flows["good_market => exports"]
                ),
                name="Fabrication for domestic market",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.future_mfa,
                flow=model.future_mfa.stocks["in_use"].inflow,
                name="Demand",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["reclmech => fabrication"],
                name="Mechanically recycled",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["reclchem => HVC_input"],
                name="Chemically recycled",
            )
            self.visualize_flow(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["eol => collected"],
                name="Collected",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["collected => reclmech"],
                name="Sorted to mechanical recycling",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["collected => landfill"],
                name="Landfilled",
                linecolor_dim="Material",
            )
            self.visualize_flow(
                mfa=model.future_mfa,
                flow=model.future_mfa.flows["collected => incineration"],
                name="Incinerated",
                linecolor_dim="Material",
            )

        if model.cfg.transience.transience_run:
            self.visualize_transience_eol_parameters(
                model, 
                parameter_REMIND_MFA=model.parameters["collection_rate"][{"r": "EU27+3", "m": model.dims["n"], "g": model.dims["f"], "t": model.dims["u"]}],
                parameter_EU_MFA=model.parameters["collection_rate_EU-MFA"],
                subplot_dim="EU-MFA_Good",
                linecolor_dim="EU-MFA_Material",)
            self.visualize_transience_eol_parameters(
                model, 
                parameter_REMIND_MFA=model.parameters["mechanical_recycling_rate"][{"r": "EU27+3", "m": model.dims["n"], "t": model.dims["u"]}],
                parameter_EU_MFA=model.parameters["mechanical_recycling_rate_EU-MFA"],
                linecolor_dim="EU-MFA_Material",)
            self.visualize_transience_eol_parameters(
                model, 
                parameter_REMIND_MFA=model.parameters["mechanical_recycling_yield"][{"r": "EU27+3", "m": model.dims["n"], "t": model.dims["u"]}],
                parameter_EU_MFA=model.parameters["mechanical_recycling_yield_EU-MFA"],
                linecolor_dim="EU-MFA_Material",)
            self.visualize_transience_eol_parameters(
                model, 
                parameter_REMIND_MFA=model.future_mfa.flows["reclmech => fabrication"].sum_to(("t", "r", "m"))[{"r": "EU27+3", "m": model.dims["n"], "t": model.dims["u"]}],
                parameter_EU_MFA=model.parameters["recycled_eol_EU-MFA"].sum_to(("u", "r", "n"))[{"r": "EU27+3"}],
                linecolor_dim="EU-MFA_Material",)
            # these flows are not totally equal because REMIND-MFA includes trade while for EU-MFA recycling rate we currently assume that no waste is traded (TODO get sorted_waste_market__recycling flow to be sure that this is correct)

        self.stop_and_show()

    def visualize_consumption(self, mfa: fd.MFASystem):
        per_capita = self.cfg.consumption.per_capita
        demand = mfa.stocks["in_use"].inflow.sum_over(("m", "e"))
        self.visualize_flow_stacked(
            mfa=mfa,
            flow=demand,
            name="Plastic consumption",
            linecolor_dim="Good",
            per_capita=per_capita,
            regional=True,
        )

    def compare_demand(self, mfa: fd.MFASystem):
        df = pd.read_csv("data/plastics/input/validation.csv", sep=";")

        # Convert year to numeric
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        # Convert Mt to t
        df["value"] = df["value"] * 1000 * 1000

        # Plotly line plot
        fig = px.line(df, x="year", y="value", color="source", markers=True)

        ap = self.plotter_class(
            array=mfa.stocks["in_use"].inflow.sum_over(("r", "m", "e", "g")),
            intra_line_dim="Time",
            title="Demand [t]",
            line_label="REMIND-MFA",
            fig=fig,
        )
        ap.plot()
        self.plot_and_save_figure(ap, "demand_validation.png", do_plot=False)

    def visualize_use_stock(self, mfa: fd.MFASystem, subplots_by_good=False):
        subplot_dim = "Good" if subplots_by_good else None
        super().visualize_use_stock(mfa, stock=mfa.stocks["in_use"].stock, subplot_dim=subplot_dim)

    def visualize_trade(self, mfa: fd.MFASystem, linecolor_dims=True):
        if linecolor_dims is True:
            linecolor_dims = {
                "primary": "Material",
                "final": "Material",
                "waste": "Material",
            }
        else:
            linecolor_dims = {
                "primary": None,
                "final": None,
                "waste": None,
            }
        super().visualize_trade(mfa, linecolor_dims=linecolor_dims)

    def visualize_stock(self, mfa: fd.MFASystem):
        stock = mfa.stocks["in_use"].stock.sum_over(("r", "m", "e"))
        good_dim = stock.dims.index("g")
        stock = stock.apply(np.cumsum, kwargs={"axis": good_dim})
        ap = self.plotter_class(
            array=stock,
            intra_line_dim="Time",
            linecolor_dim="Good",
            chart_type="area",
            display_names=self.display_names.dct,
            title="Stock [t]",
        )
        fig = ap.plot()
        self.plot_and_save_figure(ap, "stock_stacked.png", do_plot=False)

    def visualize_sankey(self, mfa: fd.MFASystem):
        # Define colors for each stage
        production_color = "#EDC948"
        use_color = "#9EC3D5"
        eol_color = "#499894"
        recycle_color = "#86BCB6"
        emission_color = "#E15759"
        trade_color = "#D37295"
        # differentiate materials with a color gradient
        material_colors = [f"hsl({190 + 10 *i},40,{77-5*i})" for i in range(len(mfa.dims["Material"].items))]

        # Initialize default flow color mapping
        flow_color_dict = {"default": use_color}
        flow_color_dict.update(
            {fn: ("Material", material_colors) for fn, f in mfa.flows.items() if "Material" in f.dims}
        )

        # # Assign colors to 'use' flows
        # flow_color_dict.update(
        #     {
        #         fn: use_color
        #         for fn, f in mfa.flows.items()
        #         if f.from_process.name == "use" or f.to_process.name == "use"
        #     }
        # )

        # # Assign colors to end-of-life flows
        # flow_color_dict.update(
        #     {
        #         fn: eol_color
        #         for fn, f in mfa.flows.items()
        #         if f.from_process.name in ("eol", "collected")
        #     }
        # )

        # # Assign colors to emission flows
        # flow_color_dict.update(
        #     {
        #         fn: emission_color
        #         for fn, f in mfa.flows.items()
        #         if f.to_process.name in ("atmosphere", "mismanaged", "uncontrolled", "emission", "losses")
        #     }
        # )

        # # Assign colors to recycling flows
        # flow_color_dict.update(
        #     {
        #         fn: recycle_color
        #         for fn, f in mfa.flows.items()
        #         if f.from_process.name in ("reclmech", "reclchem")
        #         or f.to_process.name in ("reclmech", "reclchem")
        #     }
        # )

        # # Assign colors to trade flows
        # flow_color_dict.update(
        #     {
        #         fn: trade_color
        #         for fn, f in mfa.flows.items()
        #         if f.from_process.name in ("imports", "exports")
        #         or f.to_process.name in ("imports", "exports")
        #     }
        # )

        # Update Sankey layout configuration
        self.cfg.sankey.plotter_args.update(
            {
                "valueformat": ".2s",  # scientific notation, two significant digits
                "node_pad": 15,  # padding between nodes
                "node_thickness": 20,  # node thickness
                "arrangement": "snap",  # reduce crossings by snapping nodes
                "flow_color_dict": flow_color_dict,
                "node_color_dict": {"default": "gray", "use": "black"},
            }
        )

        # Prepare display names and generate the Sankey diagram
        display_names_fmt = {k: f"<b>{v}</b>" for k, v in self.display_names.dct.items()}
        plotter = fde.PlotlySankeyPlotter(
            mfa=mfa, display_names=display_names_fmt, **self.cfg.sankey.plotter_args
        )
        fig = plotter.plot()

        # Add legend entries
        legend_entries = [
            # (production_color, "Production"),
            (use_color, "Total"),
            # (eol_color, "End-of-Life"),
            # (recycle_color, "Recycling"),
            # (emission_color, "Losses"),
            # (trade_color, "Trade"),
        ]
        for material, color in zip(mfa.dims["Material"].items, material_colors):
            legend_entries.append([color, material])
        for color, label in legend_entries:
            fig.add_trace(
                go.Scatter(
                    mode="markers",
                    x=[None],
                    y=[None],
                    marker=dict(size=10, color=color, symbol="square"),
                    name=label,
                )
            )

        # Final layout adjustments and display
        fig.update_layout(
            font_size=18, showlegend=True, plot_bgcolor="rgba(0,0,0,0)", font_color="black"
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)

        self._show_and_save_plotly(fig, name="sankey")

    def visualize_material_splits(self, mfa: fd.MFASystem):

        material_shares = mfa.parameters["material_shares_use_inflow"][
            {"t": 2019}
        ]  # material shares are kept constant over time, so we can just take the value for one year
        material_shares = material_shares.cumsum(dim_letter="m")

        ap_sector_splits = self.plotter_class(
            array=material_shares,
            intra_line_dim="Region",
            subplot_dim="Good",
            linecolor_dim="Material",
            xlabel="Year",
            ylabel="Material Splits [%]",
            display_names=self.display_names.dct,
            title=f"Product demand material splits",
            chart_type="area",
        )

        self.plot_and_save_figure(ap_sector_splits, f"material_splits.png")

    def visualize_extrapolation(self, model: "PlasticsModel", subplot_dim: str = "Region", linecolor_dim: str = None, show_extrapolation: bool = True, show_future: bool = True):
        super().visualize_extrapolation(model=model, subplot_dim=subplot_dim, linecolor_dim=linecolor_dim, show_extrapolation=show_extrapolation, show_future=show_future)
    
    def visualize_transience_inflow(self, model: "PlasticsModel", subplot_dim: str = None):
        EU_region = "EU27+3"
        inflow = model.future_mfa.stocks["in_use"].inflow[{"r": "EU27+3", "m": model.dims["n"], "g": model.dims["f"], "t": model.dims["u"]}]
        super().visualize_transience_inflow(model, EU_region = EU_region, subplot_dim=subplot_dim, inflow=inflow)

    def visualize_transience_outflow(self, model: "PlasticsModel", subplot_dim: str = None):
        EU_region = "EU27+3"
        inflow = model.future_mfa.stocks["in_use"].inflow[{"r": "EU27+3", "m": model.dims["n"], "g": model.dims["f"], "t": model.dims["u"]}]
        super().visualize_transience_outflow(model, EU_region = EU_region, subplot_dim=subplot_dim, inflow=inflow)
    