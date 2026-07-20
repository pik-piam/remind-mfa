from remind_mfa.common.common_export import CommonDataExporter, IamcVariable


class SteelDataExporter(CommonDataExporter):

    def iamc_variables(self) -> list[IamcVariable]:
        return [
            IamcVariable(
                variable_name="Production|Iron and Steel|Steel",
                calculation_function=lambda mfa: mfa.flows["forming => ip_market"].sum_to(("t", "r")),
                unit="t/yr",
            ),
            IamcVariable(
                variable_name="Material Demand|Iron and Steel|Steel",
                calculation_function=lambda mfa: (
                    mfa.flows["fabrication => good_market"] / mfa.parameters["fabrication_yield"]
                ).sum_to(("t", "r", "g")),
                unit="t/yr",
                split_name="Good",
            ),
            IamcVariable(
                variable_name="Material Stock|Iron and Steel|Steel",
                calculation_function=lambda mfa: mfa.stocks["in_use"].stock.sum_to(("t", "r", "g")),
                unit="t",
                split_name="Good",
            ),
            IamcVariable(
                variable_name="Scrap|Iron and Steel|Steel",
                calculation_function=lambda mfa: mfa.stocks["in_use"].outflow.sum_to(("t", "r", "g")),
                unit="t/yr",
                split_name="Good",
            ),
        ]
