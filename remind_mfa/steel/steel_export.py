from typing import TYPE_CHECKING, Optional

import flodym as fd
from pydantic import PrivateAttr

from remind_mfa.common.common_export import (
    CommonDataExporter,
    IamcVariable,
    RemindInputVariable,
)

if TYPE_CHECKING:
    from remind_mfa.steel.steel_model import SteelModel


class SteelDataExporter(CommonDataExporter):
    _model: Optional["SteelModel"] = PrivateAttr(default=None)

    @staticmethod
    def _total_steel_production(mfa: fd.MFASystem) -> fd.FlodymArray:
        """Total steel output after production and forming losses, before trade."""
        return mfa.flows["forming => steel_market"].sum_to(("t", "r"))

    @staticmethod
    def _secondary_steel_production(mfa: fd.MFASystem) -> fd.FlodymArray:
        """Secondary steel output. For the moment, this is steel produced from scrap in the EAF."""
        return mfa.flows["steel_production_scrap_based => forming"].sum_to(("t", "r"))

    @staticmethod
    def _eol_scrap_potential(mfa: fd.MFASystem) -> fd.FlodymArray:
        """End-of-life scrap available before collection and trade."""
        return mfa.stocks["use"].outflow.sum_to(("t", "r", "u"))

    @staticmethod
    def _total_available_scrap(mfa: fd.MFASystem) -> fd.FlodymArray:
        """Home and new scrap, plus old scrap after collection and trade, but before the model diverts any surplus to excess scrap."""
        return (
            mfa.flows["forming => scrap_pool"]
            + mfa.flows["manufacturing => scrap_pool"]
            + mfa.flows["recycling => scrap_pool"]
        )

    def get_mrindustry_variables(self) -> list[RemindInputVariable]:
        return [
            RemindInputVariable(
                name="steel_production_total",
                calculation_function=SteelDataExporter._total_steel_production,
                unit="t/yr",
            ),
            RemindInputVariable(
                name="steel_production_secondary",
                calculation_function=SteelDataExporter._secondary_steel_production,
                unit="t/yr",
            ),
            RemindInputVariable(
                name="steel_scrap",
                calculation_function=SteelDataExporter._total_available_scrap,
                unit="t/yr",
            ),
        ]

    def iamc_variables(self) -> list[IamcVariable]:
        return [
            IamcVariable(
                variable_name="Production|Iron and Steel|Steel",  # PRISMA nomenclature
                calculation_function=SteelDataExporter._total_steel_production,
                unit="t/yr",
            ),
            IamcVariable(
                variable_name="Material Demand|Iron and Steel|Steel",  # PRISMA nomenclature
                calculation_function=lambda mfa: (
                    mfa.flows["manufacturing => manufactured_products_market"]
                    / mfa.parameters["manufacturing_yield"]
                ).sum_to(("t", "r", "u")),
                unit="t/yr",
                split_name="End Use",
            ),
            IamcVariable(
                variable_name="Material Stock|Iron and Steel|Steel",  # PRISMA nomenclature
                calculation_function=lambda mfa: mfa.stocks["use"].stock.sum_to(("t", "r", "u")),
                unit="t",
                split_name="End Use",
            ),
            IamcVariable(
                variable_name="Scrap|Iron and Steel|Steel",  # PRISMA nomenclature
                calculation_function=SteelDataExporter._eol_scrap_potential,
                unit="t/yr",
                split_name="End Use",
            ),
        ]
