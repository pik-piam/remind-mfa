import flodym as fd

from remind_mfa.common.common_export import (
    CommonDataExporter,
    IamcVariable,
    RemindInputVariable,
)


class SteelDataExporter(CommonDataExporter):
    @staticmethod
    def _steel_production(mfa: fd.MFASystem) -> fd.FlodymArray:
        """Raw steel output after production and forming losses, before trade."""
        return mfa.flows["forming => ip_market"].sum_to(("t", "r"))

    @staticmethod
    def _steel_scrap(mfa: fd.MFASystem) -> fd.FlodymArray:
        """Total scrap available after collection and before the model diverts any surplus to excess scrap."""
        return mfa.stocks["in_use"].outflow.sum_to(("t", "r", "g"))

    def get_remind_input_variables(self) -> list[RemindInputVariable]:

        return [
            RemindInputVariable(
                name="steel_production",
                calculation_function=SteelDataExporter._steel_production,
                unit="t/yr",
            ),
            RemindInputVariable(
                name="steel_scrap",
                calculation_function=SteelDataExporter._steel_scrap,
                unit="t/yr",
            ),
        ]

    def iamc_variables(self) -> list[IamcVariable]:
        return [
            IamcVariable(
                variable_name="Production|Iron and Steel|Steel",  # PRISMA nomenclature
                calculation_function=SteelDataExporter._steel_production,
                unit="t/yr",
            ),
            IamcVariable(
                variable_name="Material Demand|Iron and Steel|Steel",  # PRISMA nomenclature
                calculation_function=lambda mfa: (
                    mfa.flows["fabrication => good_market"] / mfa.parameters["fabrication_yield"]
                ).sum_to(("t", "r", "g")),
                unit="t/yr",
                split_name="Good",
            ),
            IamcVariable(
                variable_name="Material Stock|Iron and Steel|Steel",  # PRISMA nomenclature
                calculation_function=lambda mfa: mfa.stocks["in_use"].stock.sum_to(("t", "r", "g")),
                unit="t",
                split_name="Good",
            ),
            IamcVariable(
                variable_name="Scrap|Iron and Steel|Steel",  # PRISMA nomenclature
                calculation_function=SteelDataExporter._steel_scrap,
                unit="t/yr",
                split_name="Good",
            ),
        ]
