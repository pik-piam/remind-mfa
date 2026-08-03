import flodym as fd

from remind_mfa.common.common_export import (
    CommonDataExporter,
    IamcVariable,
    RemindInputVariable,
)


class CementDataExporter(CommonDataExporter):
    @staticmethod
    def _cement_production(mfa: fd.MFASystem) -> fd.FlodymArray:
        """Cement output before trade and construction losses"""  
        return mfa.flows["prod_cement => market_cement"].sum_to(("t", "r"))

    def get_mrindustry_variables(self) -> list[RemindInputVariable]:
        return [
            RemindInputVariable(
                name="cement_production",
                calculation_function=CementDataExporter._cement_production,
                unit="t/yr",
            ),
            RemindInputVariable(
                name="cement_clinker_ratio",
                calculation_function=lambda mfa: (mfa.parameters["clinker_ratio"]),
            ),
        ]

    def iamc_variables(self) -> list[IamcVariable]:
        return [
            IamcVariable(
                variable_name="Production|Non-Metallic Minerals|Cement",  # PRISMA nomenclature
                calculation_function=lambda mfa: (mfa.flows["prod_cement => market_cement"]).sum_to(
                    ("t", "r")
                ),
                unit="t/yr",
            ),
            IamcVariable(
                variable_name="Production|Non-Metallic Minerals|Cement Clinker",  # PRISMA nomenclature
                calculation_function=lambda mfa: (
                    mfa.flows["prod_clinker => market_clinker"]
                    + mfa.flows["prod_clinker => sysenv"]
                ).sum_to(("t", "r")),
                unit="t/yr",
            ),
            IamcVariable(
                variable_name="Material Demand|Non-Metallic Minerals|Cement",  # PRISMA nomenclature
                calculation_function=lambda mfa: mfa.flows["market_cement => prod_product"].sum_to(
                    ("t", "r", "s")
                ),
                unit="t/yr",
                split_name="Stock Type",
            ),
            IamcVariable(
                variable_name="Material Stock|Non-Metallic Minerals|Cement",  # PRISMA nomenclature
                calculation_function=lambda mfa: mfa.stocks["in_use"]
                .stock[{"k": "cement"}]
                .sum_to(("t", "r", "s")),
                unit="t",
                split_name="Stock Type",
            ),
            IamcVariable(
                variable_name="Scrap|Non-Metallic Minerals|Cement",  # PRISMA nomenclature
                calculation_function=lambda mfa: (
                    mfa.stocks["in_use"].outflow[{"k": "cement"}].sum_to(("t", "r", "s"))
                ),
                unit="t/yr",
                split_name="Stock Type",
            ),
        ]
