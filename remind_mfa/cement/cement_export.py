import pyam
import flodym as fd

from remind_mfa.common.common_export import CommonDataExporter


class CementDataExporter(CommonDataExporter):
    def write_iamc(self, mfa: fd.MFASystem):

        model = "REMIND 3.0"
        scenario = "SSP2_NPi"
        constants = {"model": model, "scenario": scenario}

        cement_ratio = mfa.parameters["product_cement_content"] / mfa.parameters["product_density"]
        reported_dims = ("t", "r", "s")

        # production (same as demand + losses as no trade is considered yet)
        # cement
        cement_prod_by_stock_type = mfa.flows["prod_cement => prod_product"] + mfa.flows["prod_cement => sysenv"]
        other_dimletters = tuple(letter for letter in cement_prod_by_stock_type.dims.letters if letter not in reported_dims)
        cement_prod_by_stock_type = cement_prod_by_stock_type.sum_over(other_dimletters).sum_over("s")
        prod_df = self.to_iamc_df(cement_prod_by_stock_type)
        prod_df["variable"] = "Production|Non-Metallic Minerals|Cement"
        cement_prod_idf = pyam.IamDataFrame(
            prod_df,
            unit="t/yr",
            **constants,
        )
        cement_prod_idf.aggregate(
            variable="Production|Non-Metallic Minerals|Cement",
            append=True,
        )

        # clinker
        clinker_prod_by_stock_type = mfa.flows["prod_clinker => prod_cement"] + mfa.flows["prod_clinker => sysenv"]
        other_dimletters = tuple(letter for letter in clinker_prod_by_stock_type.dims.letters if letter not in reported_dims)
        clinker_prod_by_stock_type = clinker_prod_by_stock_type.sum_over(other_dimletters).sum_over("s")
        clinker_prod_df = self.to_iamc_df(clinker_prod_by_stock_type)
        clinker_prod_df["variable"] = "Production|Non-Metallic Minerals|Cement Clinker"
        clinker_prod_idf = pyam.IamDataFrame(
            clinker_prod_df,
            unit="t/yr",
            **constants,
        )
        clinker_prod_idf.aggregate(
            variable="Production|Non-Metallic Minerals|Cement Clinker",
            append=True,
        )
    
        # demand
        cement_demand_by_stock_type = mfa.flows["prod_cement => prod_product"]
        other_dimletters = tuple(letter for letter in cement_demand_by_stock_type.dims.letters if letter not in reported_dims)
        cement_demand_by_stock_type = cement_demand_by_stock_type.sum_over(other_dimletters)
        demand_df = self.to_iamc_df(cement_demand_by_stock_type)
        demand_df["variable"] = "Material Demand|Non-Metallic Minerals|Cement|" + demand_df["Stock Type"]
        demand_df = demand_df.drop(columns=["Stock Type"])
        demand_idf = pyam.IamDataFrame(
            demand_df,
            unit="t/yr",
            **constants,
        )
        demand_idf.aggregate(
            variable="Material Demand|Non-Metallic Minerals|Cement",
            append=True,
        )

        # stocks
        cement_stock_by_stock_type = mfa.stocks["in_use"].stock * cement_ratio
        other_dimletters = tuple(letter for letter in cement_stock_by_stock_type.dims.letters if letter not in reported_dims)
        cement_stock_by_stock_type = cement_stock_by_stock_type.sum_over(other_dimletters)
        stock_df = self.to_iamc_df(cement_stock_by_stock_type)
        stock_df["variable"] = "Material Stock|Non-Metallic Minerals|Cement|" + stock_df["Stock Type"]
        stock_df = stock_df.drop(columns=["Stock Type"])
        stock_idf = pyam.IamDataFrame(
            stock_df,
            unit="t",
            **constants,
        )
        stock_idf.aggregate(
            variable="Material Stock|Non-Metallic Minerals|Cement",
            append=True,
        )

        # scrap
        cement_scrap_by_stock_type = mfa.stocks["in_use"].outflow * cement_ratio
        other_dimletters = tuple(letter for letter in cement_scrap_by_stock_type.dims.letters if letter not in reported_dims)
        cement_scrap_by_stock_type = cement_scrap_by_stock_type.sum_over(other_dimletters)
        scrap_df = self.to_iamc_df(cement_scrap_by_stock_type)
        scrap_df["variable"] = "Scrap|Non-Metallic Minerals|Cement|" + scrap_df["Stock Type"]
        scrap_df = scrap_df.drop(columns=["Stock Type"])
        scrap_idf = pyam.IamDataFrame(
            scrap_df,
            unit="t/yr",
            **constants,
        )
        scrap_idf.aggregate(
            variable="Scrap|Non-Metallic Minerals|Cement",
            append=True,
        )

        idf = pyam.concat([
            cement_prod_idf,
            clinker_prod_idf,
            demand_idf,
            stock_idf,
            scrap_idf,
        ])
        idf.aggregate_region(
            variable=idf.variable,
            region="World",
            append=True,
        )
        idf.convert_unit(current="t/yr", to="Mt/yr", inplace=True)
        idf.convert_unit(current="t", to="Mt", inplace=True)

        idf.to_excel(self.export_path("iamc", f"output_iamc.xlsx"))
