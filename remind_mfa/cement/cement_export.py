from typing import TYPE_CHECKING, Optional

import flodym as fd
from pydantic import PrivateAttr

from remind_mfa.common.common_export import (
    CommonDataExporter,
    IamcVariable,
    RemindInputVariable,
)

if TYPE_CHECKING:
    from remind_mfa.cement.cement_model import CementModel


def _sum_to_end_use_split(arr: fd.FlodymArray) -> fd.FlodymArray:
    """Sum to (t, r, end use), where end use is the end-use-like dimension the array carries:
    u in top-down runs (4 items) or e in combined/reconciled runs (5 items).
    An extended-end-use result is relabeled to "End Use" so the IAMC split column is uniform
    across run modes (downstream consumers see 4 or 5 end uses depending on the run).
    """
    letter = "e" if "e" in arr.dims.letters else "u"
    out = arr.sum_to(("t", "r", letter))
    if letter == "e":
        end_use_dim = fd.Dimension(name="End Use", letter="u", items=list(out.dims["e"].items))
        out = fd.FlodymArray(dims=out.dims.replace("e", end_use_dim), values=out.values)
    return out


class CementDataExporter(CommonDataExporter):
    _model: Optional["CementModel"] = PrivateAttr(default=None)

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
                calculation_function=lambda mfa: _sum_to_end_use_split(
                    mfa.flows["market_cement => prod_product"]
                ),
                unit="t/yr",
                split_dims=["End Use"],
            ),
            IamcVariable(
                variable_name="Material Stock|Non-Metallic Minerals|Cement",  # PRISMA nomenclature
                calculation_function=lambda mfa: _sum_to_end_use_split(
                    mfa.stocks["in_use"].stock[{"k": "cement"}]
                ),
                unit="t",
                split_dims=["End Use"],
            ),
            IamcVariable(
                variable_name="Scrap|Non-Metallic Minerals|Cement",  # PRISMA nomenclature
                calculation_function=lambda mfa: _sum_to_end_use_split(
                    mfa.stocks["in_use"].outflow[{"k": "cement"}]
                ),
                unit="t/yr",
                split_dims=["End Use"],
            ),
        ]
