import flodym as fd
import pandas as pd
from typing import TYPE_CHECKING

from remind_mfa.common.common_export import CommonDataExporter, IamcVariable

if TYPE_CHECKING:
    from remind_mfa.plastics.plastics_model import PlasticsModel


class PlasticsDataExporter(CommonDataExporter):

    def export_custom(self, model: "PlasticsModel"):
        if self.cfg.csv.do_export:
            self.export_eol_data_by_region_and_year(mfa=model.future_mfa)
            self.export_use_data_by_region_and_year(mfa=model.future_mfa)
            self.export_recycling_data_by_region_and_year(mfa=model.future_mfa)
            self.export_stock_extrapolation(model=model)

    def export_stock_extrapolation(self, model: "PlasticsModel"):
        model.stock_handler.pure_parameters.to_df().to_csv(
            self.export_path("csv", "stock_extrapolation_parameters.csv")
        )
        model.stock_handler.bound_list.bound_list[0].upper_bound.to_df().to_csv(
            self.export_path("csv", "stock_extrapolation_saturationLevel.csv")
        )

    def export_eol_data_by_region_and_year(self, mfa: fd.MFASystem):
        eol_data = (
            mfa.flows["eol => collected"]
            + mfa.flows["waste_market => collected"]
            - mfa.flows["collected => waste_market"]
        )
        df = eol_data.sum_to(("t", "r", "m")).to_df(index=True)
        df.to_csv(self.export_path("csv", "eol_by_region_year.csv"), index=True)

    def export_use_data_by_region_and_year(self, mfa: fd.MFASystem):
        df = mfa.stocks["in_use"].inflow.sum_to(("t", "r")).to_df(index=True)
        df.to_csv(self.export_path("csv", "use_by_region_year.csv"), index=True)

    def export_recycling_data_by_region_and_year(self, mfa: fd.MFASystem):
        recl_data = mfa.flows["collected => reclmech"] + mfa.flows["collected => reclchem"]
        df = recl_data.sum_to(("t", "r", "m")).to_df(index=True)
        df.to_csv(self.export_path("csv", "recycling_by_region_year.csv"), index=True)

    def iamc_variables(self) -> list[IamcVariable]:
        return [
            # production
            IamcVariable(
                variable="Production|Chemicals|Plastics|Primary",
                getter=lambda mfa: (
                    mfa.flows["polymerization => primary_market"].sum_to(("t", "r"))
                    - mfa.flows["reclchem => HVC_input"]
                ),
                unit="t/yr",
            ),
            IamcVariable(
                variable="Production|Chemicals|Plastics|Secondary",
                getter=lambda mfa: (
                    mfa.flows["reclmech => primary_market"] + mfa.flows["reclchem => HVC_input"]
                ).sum_to(("t", "r")),
                unit="t/yr",
            ),
            # demand by good
            IamcVariable(
                variable="Material Demand|Chemicals|Plastics",
                getter=lambda mfa: mfa.stocks["in_use"].inflow.sum_to(("t", "r", "g")),
                unit="t/yr",
                per="Good",
            ),
            # demand per capita
            IamcVariable(
                variable="Material Demand|Chemicals|Plastics|Per Capita",
                getter=lambda mfa: (
                    mfa.stocks["in_use"].inflow / mfa.parameters["population"]
                ).sum_to(("t", "r")),
                unit="t/cap/yr",
                region_weight="Population",
            ),
            # trade
            IamcVariable(
                variable="Import|Industry|Chemicals|Plastics|Primary Forms",
                getter=lambda mfa: mfa.flows["imports => primary_market"].sum_to(("t", "r")),
                unit="t/yr",
            ),
            IamcVariable(
                variable="Export|Industry|Chemicals|Plastics|Primary Forms",
                getter=lambda mfa: mfa.flows["primary_market => exports"].sum_to(("t", "r")),
                unit="t/yr",
            ),
            IamcVariable(
                variable="Import|Industry|Chemicals|Plastics|Goods",
                getter=lambda mfa: mfa.flows["imports => good_market"].sum_to(("t", "r", "g")),
                unit="t/yr",
                per="Good",
            ),
            IamcVariable(
                variable="Export|Industry|Chemicals|Plastics|Goods",
                getter=lambda mfa: mfa.flows["good_market => exports"].sum_to(("t", "r", "g")),
                unit="t/yr",
                per="Good",
            ),
        ]

    def iamc_aggregates(self) -> list[str]:
        # Primary + Secondary are separate specs (no `per`), so their parent must be
        # aggregated explicitly. "Material Demand|Chemicals|Plastics" is handled
        # automatically via its `per="Good"` split.
        return ["Production|Chemicals|Plastics"]
