from remind_mfa.common.common_export import CommonDataExporter, IamcVariable


class CementDataExporter(CommonDataExporter):

    def iamc_variables(self) -> list[IamcVariable]:
        return [
            IamcVariable(
                variable="Production|Non-Metallic Minerals|Cement",
                getter=lambda mfa: (
                    mfa.flows["prod_cement => market_cement"] + mfa.flows["prod_cement => sysenv"]
                ).sum_to(("t", "r")),
                unit="t/yr",
            ),
            IamcVariable(
                variable="Production|Non-Metallic Minerals|Cement Clinker",
                getter=lambda mfa: (
                    mfa.flows["prod_clinker => market_clinker"]
                    + mfa.flows["prod_clinker => sysenv"]
                ).sum_to(("t", "r")),
                unit="t/yr",
            ),
            IamcVariable(
                variable="Material Demand|Non-Metallic Minerals|Cement",
                getter=lambda mfa: mfa.flows["market_cement => prod_product"].sum_to(
                    ("t", "r", "s")
                ),
                unit="t/yr",
                per="Stock Type",
            ),
            IamcVariable(
                variable="Material Stock|Non-Metallic Minerals|Cement",
                getter=lambda mfa: mfa.stocks["in_use"]
                .stock[{"k": "cement"}]
                .sum_to(("t", "r", "s")),
                unit="t",
                per="Stock Type",
            ),
            IamcVariable(
                variable="Scrap|Non-Metallic Minerals|Cement",
                getter=lambda mfa: (
                    mfa.stocks["in_use"].outflow[{"k": "cement"}].sum_to(("t", "r", "s"))
                ),
                unit="t/yr",
                per="Stock Type",
            ),
        ]
