from remind_mfa.common.common_export import CommonDataExporter, IamcVariable


class SteelDataExporter(CommonDataExporter):

    def iamc_variables(self) -> list[IamcVariable]:
        return [
            IamcVariable(
                variable="Production|Iron and Steel|Steel",
                getter=lambda mfa: mfa.flows["forming => ip_market"].sum_to(("t", "r")),
                unit="t/yr",
            ),
            IamcVariable(
                variable="Material Demand|Iron and Steel|Steel",
                getter=lambda mfa: (
                    mfa.flows["fabrication => good_market"] / mfa.parameters["fabrication_yield"]
                ).sum_to(("t", "r", "g")),
                unit="t/yr",
                per="Good",
            ),
            IamcVariable(
                variable="Material Stock|Iron and Steel|Steel",
                getter=lambda mfa: mfa.stocks["in_use"].stock.sum_to(("t", "r", "g")),
                unit="t",
                per="Good",
            ),
            IamcVariable(
                variable="Scrap|Iron and Steel|Steel",
                getter=lambda mfa: mfa.stocks["in_use"].outflow.sum_to(("t", "r", "g")),
                unit="t/yr",
                per="Good",
            ),
        ]
