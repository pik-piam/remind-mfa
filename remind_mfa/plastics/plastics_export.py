import flodym as fd
import numpy as np

from plotly import colors as plc
from plotly.subplots import make_subplots
import plotly.graph_objects as go
from typing import TYPE_CHECKING
import flodym.export as fde
from typing import Any, List, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.colors as pc


from remind_mfa.common.common_export import CommonDataExporter

if TYPE_CHECKING:
    from remind_mfa.plastics.plastics_model import PlasticsModel


class PlasticsDataExporter(CommonDataExporter):

    # Dictionary of variable names vs names displayed in figures. Used by visualization routines.
    _display_names: dict = {
        "sysenv": "System environment",
        "virginfoss": "Prim(fossil)",
        "virginbio": "Prim(biomass)",
        "virgindaccu": "Prim(daccu)",
        "virginccu": "Prim(ccu)",
        "virgin": "Prim(total)",
        "polymerization": "Poly",
        "processing": "Proc",
        "fabrication": "Fabri",
        "recl": "Recycling(total)",
        "reclmech": "Mech recycling",
        "reclchem": "Chem recycling",
        "use": "Use Phase",
        "eol": "EoL",
        "collected": "Collect",
        "mismanaged": "Uncollected",
        "incineration": "Incineration",
        "landfill": "Landfill",
        "uncontrolled": "Uncontrolled",
        "emission": "Emissions",
        "captured": "Captured",
        "atmosphere": "Atmosphere",
        "waste_imports": "Wastes Imports",
        "waste_exports": "Wastes Exports",
        "waste_market": "Waste Market",
        "primary_imports": "Prim Imports",
        "primary_exports": "Prim Exports",
        "primary_market": "Prim Market",
        "intermediate_imports": "Inter Imports",
        "intermediate_exports": "Inter Exports",
        "intermediate_market": "Inter Market",
        "manufactured_imports": "Manu Imports",
        "manufactured_exports": "Manu Exports",
        "manufactured_market": "Manu Market",
        "final_imports": "Final Imports",
        "final_exports": "Final Exports",
        "good_market": "Good Market",
    }

    def visualize_results(self, model: "PlasticsModel"):
        self.export_eol_data_by_region_and_year(mfa=model.mfa_future)
        self.export_use_data_by_region_and_year(mfa=model.mfa_future)
        self.export_recycling_data_by_region_and_year(mfa=model.mfa_future)

        if self.cfg.production["do_visualize"]:
            self.visualize_production(mfa=model.mfa_future)

            # 绘制annual production堆积面积图
            fig_production = self.plot_annual_production_stacked_area(
                mfa=model.mfa_future,
                per_capita=False,
                by_region=False,
                save_path="annual_production_by_good_type.png" if self.cfg.do_save_figs else None
            )

        if self.cfg.use_stock["do_visualize"]:
            self.visualize_stock(mfa=model.mfa_future, subplots_by_good=False)
            # 绘制按Good type分类的stock堆积面积图
            fig = self.plot_stocks_by_good_type_stacked_area(
                mfa=model.mfa_future,
                stock_name="in_use",  # 使用有Good维度的stock
                per_capita=False,
                by_region=False,
                save_path="stocks_by_good_type.png" if self.cfg.do_save_figs else None
            )

            # 绘制annual waste generation堆积面积图
            fig_waste = self.plot_annual_waste_generation_stacked_area(
                mfa=model.mfa_future,
                per_capita=False,
                by_region=False,
                save_path="annual_waste_generation_by_good_type.png" if self.cfg.do_save_figs else None
            )

        if self.cfg.sankey["do_visualize"]:
            self.visualize_sankey(mfa=model.mfa_future)
        self.stop_and_show()

    def visualize_production(self, mfa: fd.MFASystem):
        ap_modeled = self.plotter_class(
            array=mfa.stocks["in_use"].inflow.sum_over(("r", "m", "e")),
            intra_line_dim="Time",
            subplot_dim="Good",
            line_label="Modeled",
            display_names=self._display_names,
        )
        fig = ap_modeled.plot()
        ap_historic = self.plotter_class(
            array=mfa.parameters["production"].sum_over("r"),
            intra_line_dim="Historic Time",
            subplot_dim="Good",
            line_label="Historic Production",
            fig=fig,
            xlabel="Year",
            ylabel="Production [Mt]",
            display_names=self._display_names,
        )
        self.plot_and_save_figure(ap_historic, "production.png")

    def visualize_stock(self, mfa: fd.MFASystem, subplots_by_good=False):
        per_capita = self.cfg.use_stock["per_capita"]

        stock = mfa.stocks["in_use"].stock * 1000 * 1000
        population = mfa.parameters["population"]
        x_array = None

        pc_str = " pC" if per_capita else ""
        x_label = "Year"
        y_label = f"Plastic Stock{pc_str} [t]"
        title = f"Plastic Stocks{pc_str}"
        if self.cfg.use_stock.get("over_gdp", False):
            title = title + f" over GDP{pc_str}"
            x_label = f"GDP/PPP{pc_str} [2005 USD]"
            x_array = mfa.parameters["gdppc"]
            if not per_capita:
                x_array = x_array * population

        if subplots_by_good:
            subplot_dim = {"subplot_dim": "Good"}
        else:
            subplot_dim = {}
            stock = stock.sum_over("g")
            stock = stock.sum_over(["e", "m"])

        if per_capita:
            stock = stock / population

        colors = plc.qualitative.Dark24
        colors = (
            colors[: stock.dims["r"].len]
            + colors[: stock.dims["r"].len]
            + ["black" for _ in range(stock.dims["r"].len)]
        )

        ap_stock = self.plotter_class(
            array=stock,
            intra_line_dim="Time",
            linecolor_dim="Region",
            **subplot_dim,
            display_names=self._display_names,
            x_array=x_array,
            xlabel=x_label,
            ylabel=y_label,
            title=title,
            color_map=colors,
            line_type="dot",
            suppress_legend=True,
        )
        fig = ap_stock.plot()

        hist_stock = stock[{"t": mfa.dims["h"]}]
        hist_x_array = x_array[{"t": mfa.dims["h"]}] if x_array is not None else None
        ap_hist_stock = self.plotter_class(
            array=hist_stock,
            intra_line_dim="Historic Time",
            linecolor_dim="Region",
            **subplot_dim,
            display_names=self._display_names,
            x_array=hist_x_array,
            fig=fig,
            color_map=colors,
        )
        fig = ap_hist_stock.plot()

        last_year_dim = fd.Dimension(
            name="Last Historic Year", letter="l", items=[mfa.dims["h"].items[-1]]
        )
        scatter_stock = hist_stock[{"h": last_year_dim}]
        scatter_x_array = hist_x_array[{"h": last_year_dim}] if hist_x_array is not None else None
        ap_scatter_stock = self.plotter_class(
            array=scatter_stock,
            intra_line_dim="Last Historic Year",
            linecolor_dim="Region",
            **subplot_dim,
            display_names=self._display_names,
            x_array=scatter_x_array,
            fig=fig,
            chart_type="scatter",
            color_map=colors,
            suppress_legend=True,
        )
        fig = ap_scatter_stock.plot()

        if self.cfg.plotting_engine == "plotly":
            fig.update_xaxes(type="log", range=[3, 5])
        elif self.cfg.plotting_engine == "pyplot":
            for ax in fig.get_axes():
                ax.set_xscale("log")
                ax.set_xlim(1e3, 1e5)

        self.plot_and_save_figure(
            ap_scatter_stock,
            f"plastic_stocks_global_by_region{'_per_capita' if per_capita else ''}.png",
            do_plot=False,
        )

    def visualize_sankey(self, mfa: fd.MFASystem):
        # Define colors for each stage
        production_color = "#EDC948"
        use_color = "#9EC3D5"
        eol_color = "#499894"
        recycle_color = "#86BCB6"
        emission_color = "#E15759"
        trade_color = "#D37295"

        # Initialize default flow color mapping
        flow_color_dict = {"default": production_color}

        # Assign colors to 'use' flows
        flow_color_dict.update(
            {
                fn: use_color
                for fn, f in mfa.flows.items()
                if f.from_process.name == "use" or f.to_process.name == "use"
            }
        )

        # Assign colors to end-of-life flows
        flow_color_dict.update(
            {
                fn: eol_color
                for fn, f in mfa.flows.items()
                if f.from_process.name in ("eol", "collected")
            }
        )

        # Assign colors to emission flows
        flow_color_dict.update(
            {
                fn: emission_color
                for fn, f in mfa.flows.items()
                if f.to_process.name
                in ("atmosphere", "mismanaged", "incineration", "uncontrolled", "emission")
            }
        )

        # Assign colors to recycling flows
        flow_color_dict.update(
            {
                fn: recycle_color
                for fn, f in mfa.flows.items()
                if f.from_process.name in ("reclmech", "reclchem", "recl")
                or f.to_process.name in ("reclmech", "reclchem", "recl")
            }
        )

        # Update Sankey layout configuration
        self.cfg.sankey.update(
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
        display_names_fmt = {k: f"<b>{v}</b>" for k, v in self._display_names.items()}
        plotter = fde.PlotlySankeyPlotter(
            mfa=mfa, display_names=display_names_fmt, **self.cfg.sankey
        )
        fig = plotter.plot()

        # Add legend entries
        legend_entries = [
            (production_color, "Production"),
            (eol_color, "End-of-Life"),
            (recycle_color, "Use"),
            (emission_color, "Losses"),
            (trade_color, "Trade"),
        ]
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

    def export_eol_data_by_region_and_year(
        self, mfa: fd.MFASystem, output_path: str = "eol_by_region_year.csv"
    ):
        if "use => eol" not in mfa.flows:
            raise KeyError("The MFA system does not contain 'eol' in flows.")
        eol_data = (
            mfa.flows["eol => collected"]
            + mfa.flows["waste_imports => collected"]
            - mfa.flows["collected => waste_exports"]
        )
        df = eol_data.to_df(index=True)
        df_grouped = df.groupby(["Time", "Region", "Material"], as_index=True)["value"].sum()

        df_grouped.to_csv(output_path, index=True)

    def export_use_data_by_region_and_year(
        self, mfa: fd.MFASystem, output_path: str = "use_by_region_year.csv"
    ):
        if "fabrication => use" not in mfa.flows:
            raise KeyError(f"The MFA system does not contain 'use' in flows.")

        df = mfa.flows["fabrication => use"].to_df(index=True)
        df_grouped = df.groupby(["Time", "Region"], as_index=True)["value"].sum()

        df_grouped.to_csv(output_path, index=True)

    def export_recycling_data_by_region_and_year(
        self, mfa: fd.MFASystem, output_path: str = "recycling_by_region_year.csv"
    ):

        if "collected => reclmech" not in mfa.flows:
            raise KeyError(f"The MFA system does not contain 'reclmech' in flows.")
        recl_data = mfa.flows["collected => reclmech"] + mfa.flows["collected => reclchem"]
        df = recl_data.to_df(index=True)

        df_grouped = df.groupby(["Time", "Region", "Material"], as_index=True)["value"].sum()

        df_grouped.to_csv(output_path, index=True)

    def plot_stocks_by_good_type_stacked_area(
        self,
        mfa: Any,                      # fd.MFASystem
        stock_name: str = "in_use_dsm",
        per_capita: bool = False,
        by_region: bool = True,
        title: Optional[str] = None,
        y_label: Optional[str] = None,
        colors: Optional[List[str]] = None,
        save_path: Optional[str] = None
    ):
        """
        Plot stacked-area charts of a single STOCK by 'Good' type (units: Mt),
        and overlay a line showing total PRODUCTION (units: Mt/yr).
        """
        # ---------- Basic checks ----------
        if stock_name not in mfa.stocks:
            print(f"Error: Stock '{stock_name}' not found in MFA system")
            print(f"Available stocks: {list(mfa.stocks.keys())}")
            return None

        stock = mfa.stocks[stock_name].stock
        print(f"Processing stock '{stock_name}': dims={stock.dims.letters}, shape={stock.shape}")
        if "g" not in stock.dims.letters:
            print(f"Error: Stock '{stock_name}' does not have 'g' (Good) dimension")
            return None

        # Production series for overlay (prefer in_use.inflow if available)
        prod = None
        if "in_use" in mfa.stocks and hasattr(mfa.stocks["in_use"], "inflow"):
            prod = mfa.stocks["in_use"].inflow

        # ---------- Units and per-capita handling ----------
        # Keep stock in Mt; if per-capita, divide both stock and production by population.
        stock_data = stock
        if per_capita and "population" in mfa.parameters:
            stock_data = stock_data / mfa.parameters["population"]
            if prod is not None:
                prod = prod / mfa.parameters["population"]

        # ---------- Reduce other dimensions ----------
        keep_dims = {"t", "r", "g"}
        sum_dims_s = [d for d in stock_data.dims.letters if d not in keep_dims]
        if sum_dims_s:
            stock_data = stock_data.sum_over(sum_dims_s)
            print(f"Summed stock over dims: {sum_dims_s} -> new shape: {stock_data.shape}")

        if prod is not None:
            # Production overlay needs totals over 'g' (and others except t,r)
            sum_dims_p = [d for d in prod.dims.letters if d not in {"t", "r"}]
            if sum_dims_p:
                prod = prod.sum_over(sum_dims_p)
                print(f"Summed production over dims: {sum_dims_p} -> new shape: {prod.shape}")

        # ---------- Labels and colors ----------
        display_names = getattr(self, "_display_names", {})
        goods = list(stock_data.dims["g"].items)
        good_labels = [display_names.get(g, g) for g in goods]

        pc_str = " per Capita" if per_capita else ""
        if title is None:
            title = f"{display_names.get(stock_name, stock_name)} by Good Type{pc_str}"
        if y_label is None:
            y_label = f"Stock{pc_str} [Mt]"

        if colors is None:
            colors = (
                pc.qualitative.Set3
                + pc.qualitative.Pastel
                + pc.qualitative.Dark24
                + pc.qualitative.Alphabet
            )

        has_r = "r" in stock_data.dims.letters
        times = list(stock_data.dims["t"].items)
        production_line_color = "#111111"

        # Helper: add opaque stacked-area traces for one panel
        def _add_stacked_traces(fig, series_by_good, row=None, col=None, show_legend=False, stack_id="stack"):
            for j, (label, yvals) in enumerate(zip(good_labels, series_by_good)):
                color = colors[j % len(colors)]
                fig.add_trace(
                    go.Scatter(
                        x=times,
                        y=yvals,
                        mode="lines",
                        stackgroup=stack_id,
                        line=dict(width=0.8, color=color),
                        fillcolor=color,
                        opacity=1.0,
                        name=label,
                        legendgroup=label,
                        showlegend=show_legend,
                        hovertemplate=(
                            f"<b>{label}</b><br>"
                            "Year: %{x}<br>"
                            "Stock: %{y:.2f} Mt<extra></extra>"
                        ),
                    ),
                    row=row, col=col
                )

        # Helper: add production total line for one panel
        def _add_production_line(fig, prod_series, row=None, col=None, show_legend=False):
            if prod_series is None:
                return
            fig.add_trace(
                go.Scatter(
                    x=times,
                    y=prod_series,
                    mode="lines",
                    line=dict(width=2.0, color=production_line_color),
                    name="Production (total, Mt/yr)",
                    legendgroup="__production__",
                    showlegend=show_legend,
                    hovertemplate="Year: %{x}<br>Production: %{y:.2f} Mt/yr<extra></extra>",
                ),
                row=row, col=col
            )

        # ---------- Build figure ----------
        if by_region and has_r:
            regions = list(stock_data.dims["r"].items)
            n_regions = len(regions)
            n_cols = min(3, n_regions)
            n_rows = (n_regions + n_cols - 1) // n_cols

            subplot_titles = [display_names.get(r, r) for r in regions]
            fig = make_subplots(
                rows=n_rows,
                cols=n_cols,
                subplot_titles=subplot_titles,
                vertical_spacing=0.10,
                horizontal_spacing=0.06
            )

            for i, region in enumerate(regions):
                r_idx = i // n_cols + 1
                c_idx = i % n_cols + 1

                # area series per Good for this region
                panel_series = [stock_data[{"r": region, "g": g}].values for g in goods]
                _add_stacked_traces(
                    fig, panel_series, row=r_idx, col=c_idx,
                    show_legend=(i == 0), stack_id=f"stack_{i}"
                )

                # production total for this region (sum over Good already)
                prod_series = None
                if prod is not None and "r" in prod.dims.letters:
                    prod_series = prod[{"r": region}].values
                elif prod is not None:
                    prod_series = prod.values

                _add_production_line(fig, prod_series, row=r_idx, col=c_idx, show_legend=(i == 0))

                fig.update_xaxes(title_text="Year", row=r_idx, col=c_idx)
                fig.update_yaxes(title_text=y_label, row=r_idx, col=c_idx)

        else:
            fig = go.Figure()
            data_1panel = stock_data.sum_over("r") if has_r else stock_data
            panel_series = [data_1panel[{"g": g}].values for g in goods]
            _add_stacked_traces(fig, panel_series, show_legend=True, stack_id="stack_all")

            # production total (sum over regions if present)
            prod_series = None
            if prod is not None:
                if "r" in getattr(prod, "dims", {}).letters:
                    prod_series = prod.sum_over("r").values
                else:
                    prod_series = prod.values
            _add_production_line(fig, prod_series, show_legend=True)

            fig.update_xaxes(title_text="Year")
            fig.update_yaxes(title_text=y_label)

        # ---------- Layout & output ----------
        fig.update_layout(
            title=title,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0)
        )

        if save_path:
            fig.write_image(save_path)
            print(f"Figure saved to: {save_path}")

        if getattr(getattr(self, "cfg", object()), "do_show_figs", False):
            if getattr(getattr(self, "cfg", object()), "plotting_engine", "plotly") == "plotly":
                if hasattr(self, "_show_and_save_plotly"):
                    self._show_and_save_plotly(fig, name=f"stocks_by_good_type_{stock_name}")
                else:
                    fig.show()
            else:
                fig.show()
        else:
            print("Figure created but not displayed (do_show_figs=False)")

        return fig


    def plot_annual_production_stacked_area(
        self,
        mfa: Any,                      # fd.MFASystem
        per_capita: bool = False,
        by_region: bool = True,
        title: Optional[str] = None,
        y_label: Optional[str] = None,
        colors: Optional[List[str]] = None,
        save_path: Optional[str] = None
    ):
        """
        Plot stacked-area charts of annual plastic PRODUCTION by 'Good' type (units: Mt).

        Parameters
        ----------
        mfa : fd.MFASystem
            MFA system object. Must contain stocks['in_use'].inflow with dims including 't' and 'g'.
        per_capita : bool, default False
            If True, divide production by population (when available).
        by_region : bool, default True
            If True and 'r' dimension exists, draw small multiples by region; otherwise sum regions.
        title : str, optional
            Figure title.
        y_label : str, optional
            Y-axis label (defaults to Mt/year).
        colors : list[str], optional
            Color list for Good types. Falls back to Plotly qualitative palettes if None.
        save_path : str, optional
            If provided, save static image via `fig.write_image(save_path)`.

        Returns
        -------
        go.Figure
            The Plotly figure object.
        """
        # ---------- Basic checks ----------
        if "in_use" not in mfa.stocks:
            print("Error: 'in_use' stock not found in MFA system")
            print(f"Available stocks: {list(mfa.stocks.keys())}")
            return None

        prod = mfa.stocks["in_use"].inflow
        print(f"Processing production data: dims={prod.dims.letters}, shape={prod.shape}")

        if "g" not in prod.dims.letters:
            print("Error: Production data does not have 'g' (Good) dimension")
            return None

        # ---------- Units and per-capita handling ----------
        # Keep units in Mt (do NOT convert to t). If per-capita, divide by population.
        if per_capita and "population" in mfa.parameters:
            prod = prod / mfa.parameters["population"]

        # ---------- Reduce other dimensions ----------
        # Keep only time (t), region (r, if exists), and Good (g). Sum over anything else.
        keep_dims = {"t", "r", "g"}
        sum_dims = [d for d in prod.dims.letters if d not in keep_dims]
        if sum_dims:
            prod = prod.sum_over(sum_dims)
            print(f"Summed over dimensions: {sum_dims} -> new shape: {prod.shape}")

        # ---------- Labels and colors ----------
        display_names = getattr(self, "_display_names", {})

        goods = list(prod.dims["g"].items)
        good_labels = [display_names.get(g, g) for g in goods]

        pc_str = " per Capita" if per_capita else ""
        if title is None:
            title = f"Annual Plastic Production by Good Type{pc_str}"
        if y_label is None:
            y_label = f"Production{pc_str} [Mt/year]"

        if colors is None:
            # Long palette to cover many Good types
            colors = (
                pc.qualitative.Set3
                + pc.qualitative.Pastel
                + pc.qualitative.Dark24
                + pc.qualitative.Alphabet
            )

        has_r = "r" in prod.dims.letters
        times = list(prod.dims["t"].items)

        # Helper: add opaque stacked-area traces for one panel
        def _add_stacked_traces(fig, series_by_good, row=None, col=None, show_legend=False, stack_id="stack"):
            """
            series_by_good: list of 1D arrays (len = len(times)) ordered as `goods`.
            """
            for j, (label, yvals) in enumerate(zip(good_labels, series_by_good)):
                color = colors[j % len(colors)]
                fig.add_trace(
                    go.Scatter(
                        x=times,
                        y=yvals,
                        mode="lines",
                        stackgroup=stack_id,   # stacking is handled automatically
                        line=dict(width=0.8, color=color),
                        fillcolor=color,       # opaque fill (no transparency)
                        opacity=1.0,
                        name=label,
                        legendgroup=label,     # toggle same Good across panels
                        showlegend=show_legend,
                        hovertemplate=(
                            f"<b>{label}</b><br>"
                            "Year: %{x}<br>"
                            "Production: %{y:.2f} Mt/yr<extra></extra>"
                        ),
                    ),
                    row=row, col=col
                )

        # ---------- Build figure ----------
        if by_region and has_r:
            regions = list(prod.dims["r"].items)
            n_regions = len(regions)
            n_cols = min(3, n_regions)
            n_rows = (n_regions + n_cols - 1) // n_cols

            subplot_titles = [display_names.get(r, r) for r in regions]
            fig = make_subplots(
                rows=n_rows,
                cols=n_cols,
                subplot_titles=subplot_titles,
                vertical_spacing=0.10,
                horizontal_spacing=0.06
            )

            for i, region in enumerate(regions):
                r_idx = i // n_cols + 1
                c_idx = i % n_cols + 1

                # Collect per-Good series for this region
                panel_series = [prod[{"r": region, "g": g}].values for g in goods]

                # Only first panel shows legend; stackgroup must be unique per panel
                _add_stacked_traces(
                    fig,
                    panel_series,
                    row=r_idx,
                    col=c_idx,
                    show_legend=(i == 0),
                    stack_id=f"stack_{i}"
                )

                fig.update_xaxes(title_text="Year", row=r_idx, col=c_idx)
                fig.update_yaxes(title_text=y_label, row=r_idx, col=c_idx)

        else:
            # Sum over regions if present; single chart
            fig = go.Figure()
            data_1panel = prod.sum_over("r") if has_r else prod

            panel_series = [data_1panel[{"g": g}].values for g in goods]
            _add_stacked_traces(fig, panel_series, show_legend=True, stack_id="stack_all")

            fig.update_xaxes(title_text="Year")
            fig.update_yaxes(title_text=y_label)

        # ---------- Layout & output ----------
        fig.update_layout(
            title=title,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0)
        )

        if save_path:
            fig.write_image(save_path)
            print(f"Figure saved to: {save_path}")

        if getattr(getattr(self, "cfg", object()), "do_show_figs", False):
            if getattr(getattr(self, "cfg", object()), "plotting_engine", "plotly") == "plotly":
                if hasattr(self, "_show_and_save_plotly"):
                    self._show_and_save_plotly(fig, name="annual_production_by_good_type")
                else:
                    fig.show()
            else:
                fig.show()
        else:
            print("Figure created but not displayed (do_show_figs=False)")

        return fig

    def plot_annual_waste_generation_stacked_area(
        self,
        mfa: Any,                      # fd.MFASystem
        per_capita: bool = False,
        by_region: bool = True,
        title: Optional[str] = None,
        y_label: Optional[str] = None,
        colors: Optional[List[str]] = None,
        save_path: Optional[str] = None
    ):
        """
        Plot stacked-area charts of annual plastic WASTE by 'Good' type (units: Mt/yr),
        and overlay a line showing total PRODUCTION (units: Mt/yr).
        """
        # ---------- Basic checks ----------
        if "in_use" not in mfa.stocks:
            print("Error: 'in_use' stock not found in MFA system")
            print(f"Available stocks: {list(mfa.stocks.keys())}")
            return None

        waste = mfa.stocks["in_use"].outflow
        print(f"Processing waste generation data: dims={waste.dims.letters}, shape={waste.shape}")
        if "g" not in waste.dims.letters:
            print("Error: Waste generation data does not have 'g' (Good) dimension")
            return None

        # Production series for overlay (optional if available)
        prod = getattr(mfa.stocks["in_use"], "inflow", None)

        # ---------- Units and per-capita handling ----------
        # Keep units in Mt. If per-capita, divide by population (broadcast handled by MFA).
        if per_capita and "population" in mfa.parameters:
            waste = waste / mfa.parameters["population"]
            if prod is not None:
                prod = prod / mfa.parameters["population"]

        # ---------- Reduce other dimensions ----------
        keep_dims = {"t", "r", "g"}
        sum_dims_w = [d for d in waste.dims.letters if d not in keep_dims]
        if sum_dims_w:
            waste = waste.sum_over(sum_dims_w)
            print(f"Summed waste over dims: {sum_dims_w} -> new shape: {waste.shape}")

        if prod is not None:
            # For production overlay we only need totals over 'g' (and other dims except t,r)
            sum_dims_p = [d for d in prod.dims.letters if d not in {"t", "r"}]
            if sum_dims_p:
                prod = prod.sum_over(sum_dims_p)
                print(f"Summed production over dims: {sum_dims_p} -> new shape: {prod.shape}")

        # ---------- Labels and colors ----------
        display_names = getattr(self, "_display_names", {})
        goods = list(waste.dims["g"].items)
        good_labels = [display_names.get(g, g) for g in goods]

        pc_str = " per Capita" if per_capita else ""
        if title is None:
            title = f"Annual Plastic Waste Generation by Good Type{pc_str}"
        if y_label is None:
            y_label = f"Waste Generation{pc_str} [Mt/yr]"

        if colors is None:
            colors = (
                pc.qualitative.Set3
                + pc.qualitative.Pastel
                + pc.qualitative.Dark24
                + pc.qualitative.Alphabet
            )

        has_r = "r" in waste.dims.letters
        times = list(waste.dims["t"].items)
        production_line_color = "#111111"

        # Helper: add opaque stacked-area traces for one panel
        def _add_stacked_traces(fig, series_by_good, row=None, col=None, show_legend=False, stack_id="stack"):
            for j, (label, yvals) in enumerate(zip(good_labels, series_by_good)):
                color = colors[j % len(colors)]
                fig.add_trace(
                    go.Scatter(
                        x=times,
                        y=yvals,
                        mode="lines",
                        stackgroup=stack_id,
                        line=dict(width=0.8, color=color),
                        fillcolor=color,
                        opacity=1.0,
                        name=label,
                        legendgroup=label,
                        showlegend=show_legend,
                        hovertemplate=(
                            f"<b>{label}</b><br>"
                            "Year: %{x}<br>"
                            "Waste: %{y:.2f} Mt/yr<extra></extra>"
                        ),
                    ),
                    row=row, col=col
                )

        # Helper: add production total line for one panel
        def _add_production_line(fig, prod_series, row=None, col=None, show_legend=False):
            if prod_series is None:
                return
            fig.add_trace(
                go.Scatter(
                    x=times,
                    y=prod_series,
                    mode="lines",
                    line=dict(width=2.0, color=production_line_color),
                    name="Production (total)",
                    legendgroup="__production__",
                    showlegend=show_legend,
                    hovertemplate="Year: %{x}<br>Production: %{y:.2f} Mt/yr<extra></extra>",
                ),
                row=row, col=col
            )

        # ---------- Build figure ----------
        if by_region and has_r:
            regions = list(waste.dims["r"].items)
            n_regions = len(regions)
            n_cols = min(3, n_regions)
            n_rows = (n_regions + n_cols - 1) // n_cols

            subplot_titles = [display_names.get(r, r) for r in regions]
            fig = make_subplots(
                rows=n_rows,
                cols=n_cols,
                subplot_titles=subplot_titles,
                vertical_spacing=0.10,
                horizontal_spacing=0.06
            )

            for i, region in enumerate(regions):
                r_idx = i // n_cols + 1
                c_idx = i % n_cols + 1

                # area series per Good for this region
                panel_series = [waste[{"r": region, "g": g}].values for g in goods]
                _add_stacked_traces(
                    fig, panel_series, row=r_idx, col=c_idx,
                    show_legend=(i == 0), stack_id=f"stack_{i}"
                )

                # production total for this region (sum over Good already)
                prod_series = None
                if prod is not None and "r" in prod.dims.letters:
                    prod_series = prod[{"r": region}].values
                elif prod is not None:
                    prod_series = prod.values  # no region dimension present

                _add_production_line(fig, prod_series, row=r_idx, col=c_idx, show_legend=(i == 0))

                fig.update_xaxes(title_text="Year", row=r_idx, col=c_idx)
                fig.update_yaxes(title_text=y_label, row=r_idx, col=c_idx)

        else:
            fig = go.Figure()
            data_1panel = waste.sum_over("r") if has_r else waste
            panel_series = [data_1panel[{"g": g}].values for g in goods]
            _add_stacked_traces(fig, panel_series, show_legend=True, stack_id="stack_all")

            # production total (sum over regions if present)
            prod_series = None
            if prod is not None:
                if "r" in getattr(prod, "dims", {}).letters:
                    prod_series = prod.sum_over("r").values
                else:
                    prod_series = prod.values
            _add_production_line(fig, prod_series, show_legend=True)

            fig.update_xaxes(title_text="Year")
            fig.update_yaxes(title_text=y_label)

        # ---------- Layout & output ----------
        fig.update_layout(
            title=title,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0)
        )

        if save_path:
            fig.write_image(save_path)
            print(f"Figure saved to: {save_path}")

        if getattr(getattr(self, "cfg", object()), "do_show_figs", False):
            if getattr(getattr(self, "cfg", object()), "plotting_engine", "plotly") == "plotly":
                if hasattr(self, "_show_and_save_plotly"):
                    self._show_and_save_plotly(fig, name="annual_waste_generation_by_good_type")
                else:
                    fig.show()
            else:
                fig.show()
        else:
            print("Figure created but not displayed (do_show_figs=False)")

        return fig
