import flodym as fd

from remind_mfa.common.common_export import CommonDataExporter, IamcVariable


def _sum_to_good_split(arr: fd.FlodymArray) -> fd.FlodymArray:
    """Sum to (t, r, good), where good is the good-like dimension the array carries:
    g in top-down runs (4 items) or e in combined/reconciled runs (5 items).
    An extended-good result is relabeled to "Good" so the IAMC split column is uniform
    across run modes (downstream consumers see 4 or 5 goods depending on the run).
    """
    letter = "e" if "e" in arr.dims.letters else "g"
    out = arr.sum_to(("t", "r", letter))
    if letter == "e":
        good_dim = fd.Dimension(name="Good", letter="g", items=list(out.dims["e"].items))
        out = fd.FlodymArray(dims=out.dims.replace("e", good_dim), values=out.values)
    return out


class CementDataExporter(CommonDataExporter):

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
                calculation_function=lambda mfa: _sum_to_good_split(
                    mfa.flows["market_cement => prod_product"]
                ),
                unit="t/yr",
                split_name="Good",
            ),
            IamcVariable(
                variable_name="Material Stock|Non-Metallic Minerals|Cement",  # PRISMA nomenclature
                calculation_function=lambda mfa: _sum_to_good_split(
                    mfa.stocks["in_use"].stock[{"k": "cement"}]
                ),
                unit="t",
                split_name="Good",
            ),
            IamcVariable(
                variable_name="Scrap|Non-Metallic Minerals|Cement",  # PRISMA nomenclature
                calculation_function=lambda mfa: _sum_to_good_split(
                    mfa.stocks["in_use"].outflow[{"k": "cement"}]
                ),
                unit="t/yr",
                split_name="Good",
            ),
        ]
