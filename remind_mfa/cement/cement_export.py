from remind_mfa.common.common_export import CommonDataExporter, IamcVariable


class CementDataExporter(CommonDataExporter):

    def iamc_variables(self) -> list[IamcVariable]:
        return [
            IamcVariable(
                variable_name="Production|Non-Metallic Minerals|Cement",  # PRISMA nomenclature
                calculation_function=lambda mfa: (
                    mfa.flows["prod_cement => market_cement"]
                ).sum_to(("t", "r")),
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
