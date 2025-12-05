import flodym as fd
import pandas as pd
import pyam
from typing import TYPE_CHECKING

from remind_mfa.common.common_export import CommonDataExporter
if TYPE_CHECKING:
    from remind_mfa.plastics.plastics_model import PlasticsModel


class PlasticsDataExporter(CommonDataExporter):

    def export_custom(self, model: "PlasticsModel"):
        if self.cfg.csv.do_export:
            self.export_eol_data_by_region_and_year(mfa=model.future_mfa)
            self.export_use_data_by_region_and_year(mfa=model.future_mfa)
            self.export_recycling_data_by_region_and_year(mfa=model.future_mfa)
            self.export_stock_extrapolation(model=model)
            self.export_stock(mfa=model.mfa_historic)

    def export_stock_extrapolation(self, model: "PlasticsModel"):
        model.future_mfa.stock_handler.pure_parameters.to_df().to_csv(
            self.export_path("stock_extrapolation_parameters.csv")
        )
        model.future_mfa.stock_handler.bound_list.bound_list[0].upper_bound.to_df().to_csv(
            self.export_path("stock_extrapolation_saturationLevel.csv")
        )

    def export_stock(self, mfa: fd.MFASystem):
        inflow = mfa.stocks["in_use_historic"].inflow.sum_to(("g", "h")).to_df()
        inflow["variable"] = "inflow"
        outflow = mfa.stocks["in_use_historic"].outflow.sum_to(("g", "h")).to_df()
        outflow["variable"] = "outflow"
        stock = mfa.stocks["in_use_historic"].stock.sum_to(("g", "h")).to_df()
        stock["variable"] = "stock"
        pd.concat([inflow, outflow, stock]).to_csv(self.export_path("stock.csv"))

    def export_eol_data_by_region_and_year(
        self, mfa: fd.MFASystem, output_path: str = "eol_by_region_year.csv"
    ):
        eol_data = (
            mfa.flows["eol => collected"]
            + mfa.flows["waste_market => collected"]
            - mfa.flows["collected => waste_market"]
        )
        df = eol_data.sum_to(("t", "r", "m")).to_df(index=True)
        df.to_csv(self.export_path(output_path), index=True)

    def export_use_data_by_region_and_year(
        self, mfa: fd.MFASystem, output_path: str = "use_by_region_year.csv"
    ):
        df = mfa.flows["fabrication => use"].sum_to(("t", "r")).to_df(index=True)
        df.to_csv(self.export_path(output_path), index=True)

    def export_recycling_data_by_region_and_year(
        self, mfa: fd.MFASystem, output_path: str = "recycling_by_region_year.csv"
    ):
        recl_data = mfa.flows["collected => reclmech"] + mfa.flows["collected => reclchem"]
        df = recl_data.sum_to(("t", "r", "m")).to_df(index=True)
        df.to_csv(self.export_path(output_path), index=True)

    def write_iamc(self, mfa: fd.MFASystem):

        model = "REMIND 3.0"
        scenario = "SSP2_NPi"
        constants = {"model": model, "scenario": scenario}

        # production
        ## primary production
        prod_virgin = (
            mfa.flows["virginfoss => virgin"]
            + mfa.flows["virginbio => virgin"]
            + mfa.flows["virgindaccu => virgin"]
            + mfa.flows["virginccu => virgin"]
        )
        prod_virgin_df = self.to_iamc_df(prod_virgin.sum_to(("t", "r")))
        prod_virgin_idf = pyam.IamDataFrame(
            prod_virgin_df,
            variable="Production|Chemicals|Plastics|Primary",
            unit="Mt/yr",
            **constants,
        )
        ## secondary production
        prod_recl = mfa.flows["reclmech => processing"] + mfa.flows["reclchem => virgin"]
        prod_recl_df = self.to_iamc_df(prod_recl.sum_to(("t", "r")))
        prod_recl_idf = pyam.IamDataFrame(
            prod_recl_df,
            variable="Production|Chemicals|Plastics|Secondary",
            unit="Mt/yr",
            **constants,
        )
        ## total production
        prod_idf = pyam.concat(
            [
                prod_virgin_idf,
                prod_recl_idf,
            ]
        )
        prod_idf.aggregate(
            variable="Production|Chemicals|Plastics",
            append=True,
        )

        # demand
        ## demand by good
        plastic_demand_by_good = mfa.stocks["in_use"].inflow.sum_to(("t", "r", "g"))
        demand_df = self.to_iamc_df(plastic_demand_by_good)
        demand_df["variable"] = "Material Demand|Chemicals|Plastics|" + demand_df["Good"]
        demand_df = demand_df.drop(columns=["Good"])
        demand_idf = pyam.IamDataFrame(
            demand_df,
            unit="Mt/yr",
            **constants,
        )
        demand_idf.aggregate(
            variable="Material Demand|Chemicals|Plastics",
            append=True,
        )
        ## demand by origin (primary/secondary) and good
        recycled = prod_recl / (prod_virgin + prod_recl)
        ### primary
        plastic_demand_virgin = mfa.stocks["in_use"].inflow * (1 - recycled)
        demand_virgin_df = self.to_iamc_df(plastic_demand_virgin.sum_to(("t", "r", "g")))
        demand_virgin_df["variable"] = (
            "Material Demand|Chemicals|Plastics|Primary|" + demand_virgin_df["Good"]
        )
        demand_virgin_df = demand_virgin_df.drop(columns=["Good"])
        demand_virgin_idf = pyam.IamDataFrame(
            demand_virgin_df,
            unit="Mt/yr",
            **constants,
        )
        demand_virgin_idf.aggregate(
            variable="Material Demand|Chemicals|Plastics|Primary",
            append=True,
        )
        ### secondary
        plastic_demand_recl = mfa.stocks["in_use"].inflow * recycled
        demand_recl_df = self.to_iamc_df(plastic_demand_recl.sum_to(("t", "r", "g")))
        demand_recl_df["variable"] = (
            "Material Demand|Chemicals|Plastics|Secondary|" + demand_recl_df["Good"]
        )
        demand_recl_df = demand_recl_df.drop(columns=["Good"])
        demand_recl_idf = pyam.IamDataFrame(
            demand_recl_df,
            unit="Mt/yr",
            **constants,
        )
        demand_recl_idf.aggregate(
            variable="Material Demand|Chemicals|Plastics|Secondary",
            append=True,
        )
        demand_origin_idf = pyam.concat(
            [
                demand_virgin_idf,
                demand_recl_idf,
            ]
        )
        # demand_origin_idf.aggregate(
        #     variable="Material Demand|Chemicals|Plastics",
        #     append=True,
        # )

        idf = pyam.concat(
            [
                prod_idf,
                demand_idf,
                demand_origin_idf,
            ]
        )
        idf.aggregate_region(
            variable=idf.variable,
            region="World",
            append=True,
        )

        idf.to_excel(self.export_path(f"output_iamc.xlsx"))

    @staticmethod
    def to_iamc_df(array: fd.FlodymArray):
        time_items = list(range(2025, 2101))  # TODO: more flexible
        time_out = fd.Dimension(name="Time Out", letter="O", items=time_items)
        df = array[{"t": time_out}].to_df(dim_to_columns="Time Out", index=False)
        df = df.rename(columns={"Region": "region"})
        return df
