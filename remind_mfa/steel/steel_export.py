import pyam
import flodym as fd

from remind_mfa.common.common_export import CommonDataExporter


class SteelDataExporter(CommonDataExporter):

    def write_iamc(self, mfa: fd.MFASystem):

        model = "REMIND 3.0"
        scenario = "SSP2_NPi"
        constants = {"model": model, "scenario": scenario}

        # production
        prod_df = self.to_iamc_df(mfa.flows["forming => ip_market"])
        prod_idf = pyam.IamDataFrame(
            prod_df,
            variable="Production|Iron and Steel|Steel",
            unit="t/yr",
            **constants,
        )

        # demand
        steel_demand_by_good = (
            mfa.flows["fabrication => good_market"] / mfa.parameters["fabrication_yield"]
        )
        demand_df = self.to_iamc_df(steel_demand_by_good)
        demand_df["variable"] = "Material Demand|Iron and Steel|Steel|" + demand_df["Good"]
        demand_df = demand_df.drop(columns=["Good"])
        demand_idf = pyam.IamDataFrame(
            demand_df,
            unit="t/yr",
            **constants,
        )
        demand_idf.aggregate(
            variable="Material Demand|Iron and Steel|Steel",
            append=True,
        )

        # stocks
        stock_df = self.to_iamc_df(mfa.stocks["in_use"].stock)
        stock_df["variable"] = "Material Stock|Iron and Steel|Steel|" + stock_df["Good"]
        stock_df = stock_df.drop(columns=["Good"])
        stock_idf = pyam.IamDataFrame(
            stock_df,
            unit="t",
            **constants,
        )
        stock_idf.aggregate(
            variable="Material Stock|Iron and Steel|Steel",
            append=True,
        )

        # scrap
        scrap_df = self.to_iamc_df(mfa.stocks["in_use"].outflow)
        scrap_df["variable"] = "Scrap|Iron and Steel|Steel|" + scrap_df["Good"]
        scrap_df = scrap_df.drop(columns=["Good"])
        scrap_idf = pyam.IamDataFrame(
            scrap_df,
            unit="t/yr",
            **constants,
        )
        scrap_idf.aggregate(
            variable="Scrap|Iron and Steel|Steel",
            append=True,
        )

        idf = pyam.concat(
            [
                prod_idf,
                demand_idf,
                stock_idf,
                scrap_idf,
            ]
        )
        idf.aggregate_region(
            variable=idf.variable,
            region="World",
            append=True,
        )
        idf.convert_unit(current="t/yr", to="Mt/yr", inplace=True)
        idf.convert_unit(current="t", to="Mt", inplace=True)

        idf.to_excel(self.export_path("iamc", f"output_iamc.xlsx"))
