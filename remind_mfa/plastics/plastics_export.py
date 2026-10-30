from typing import TYPE_CHECKING, Optional

import flodym as fd
from pydantic import PrivateAttr

from remind_mfa.common.common_export import (
    CommonDataExporter,
    IamcVariable,
    RemindInputVariable,
)

if TYPE_CHECKING:
    from remind_mfa.plastics.plastics_model import PlasticsModel


class PlasticsDataExporter(CommonDataExporter):
    _model: Optional["PlasticsModel"] = PrivateAttr(default=None)

    @staticmethod
    def _plastic_waste(mfa: fd.MFASystem) -> fd.FlodymArray:
        """Plastic waste available for recycling."""
        return (mfa.flows["sorting => reclmech"] + mfa.flows["sorting => reclchem"]).sum_to(
            ("t", "r", "p")
        )

    @staticmethod
    def _plastics_fabrication_demand(mfa: fd.MFASystem) -> fd.FlodymArray:
        """Demand for primary plastics."""
        return (mfa.flows["primary_market => manufacturing"]).sum_to(("t", "r", "p"))

    @staticmethod
    def _plastics_primary_production(mfa: fd.MFASystem) -> fd.FlodymArray:
        """Production of primary plastics."""
        return (
            mfa.flows["polymerization => primary_market"]
            + mfa.flows["aux_recyclate_market => primary_market"]
        ).sum_to(("t", "r", "p"))

    def get_mrindustry_variables(self) -> list[RemindInputVariable]:
        def hvc_production(mfa: fd.MFASystem) -> fd.FlodymArray:
            """HVC production for plastics production"""
            return mfa.flows["hvc_production => polymerization"].sum_to(("t", "r"))

        return [
            RemindInputVariable(
                name="hvc_production",
                calculation_function=hvc_production,
                unit="t/yr",
            ),
            RemindInputVariable(
                name="p37_plasticWaste",
                calculation_function=PlasticsDataExporter._plastic_waste,
                unit="t/yr",
            ),
        ]

    def get_atlas_variables(self) -> list[RemindInputVariable]:
        return [
            RemindInputVariable(
                name="plastics_demand",
                calculation_function=PlasticsDataExporter._plastics_fabrication_demand,
                unit="t/yr",
            ),
            RemindInputVariable(
                name="plastics_production",
                calculation_function=PlasticsDataExporter._plastics_primary_production,
                unit="t/yr",
            ),
        ]

    def export_custom(self):
        if self.cfg.csv.do_export:
            self.export_eol_data_by_region_and_year(mfa=self._model.future_mfa)
            self.export_use_data_by_region_and_year(mfa=self._model.future_mfa)
            self.export_recycling_data_by_region_and_year(mfa=self._model.future_mfa)

    def export_eol_data_by_region_and_year(self, mfa: fd.MFASystem):
        eol_data = (
            mfa.flows["eol_management => sorting"]
            + mfa.flows["waste_market => sorting"]
            - mfa.flows["sorting => waste_market"]
        )
        df = eol_data.sum_to(("t", "r", "p")).to_df(index=True)
        df.to_csv(self.export_path("csv", "eol_by_region_year.csv"), index=True)

    def export_use_data_by_region_and_year(self, mfa: fd.MFASystem):
        df = mfa.stocks["use"].inflow.sum_to(("t", "r")).to_df(index=True)
        df.to_csv(self.export_path("csv", "use_by_region_year.csv"), index=True)

    def export_recycling_data_by_region_and_year(self, mfa: fd.MFASystem):
        df = PlasticsDataExporter._plastic_waste(mfa).to_df(index=True)
        df.to_csv(self.export_path("csv", "recycling_by_region_year.csv"), index=True)

    def iamc_variables(self) -> list[IamcVariable]:
        return [
            # production
            IamcVariable(
                variable_name="Production|Chemicals|Plastics|Primary",  # PRISMA nomenclature
                calculation_function=lambda mfa: (
                    mfa.flows["polymerization => primary_market"].sum_to(("t", "r"))
                    - mfa.flows["aux_recl_feedstock_market => hvc_production"]
                ),
                unit="t/yr",
            ),
            IamcVariable(
                variable_name="Production|Chemicals|Plastics|Secondary",  # PRISMA nomenclature
                calculation_function=lambda mfa: (
                    mfa.flows["aux_recyclate_market => primary_market"]
                    + mfa.flows["aux_recl_feedstock_market => hvc_production"]
                ).sum_to(("t", "r")),
                unit="t/yr",
            ),
            # demand by end use
            IamcVariable(
                variable_name="Material Demand|Chemicals|Plastics",  # PRISMA nomenclature
                calculation_function=lambda mfa: mfa.stocks["use"].inflow.sum_to(("t", "r", "u")),
                unit="t/yr",
                split_name="End Use",
            ),
            # demand by polymer type
            # Same parent as the "by end use" split above (orthogonal breakdown), so opt out of
            # summing these children back into the parent to avoid double-counting the total.
            # The MFA system does not resolve the polymer type dimension, so the polymer-resolved
            # demand is re-expanded to it via the polymer type mapping.
            IamcVariable(
                variable_name="Material Demand|Chemicals|Plastics",
                calculation_function=lambda mfa: (
                    mfa.stocks["use"].inflow.sum_to(("t", "r", "p"))
                    * mfa.parameters["polymer_type_mapping"]
                ).sum_to(("t", "r", "P")),
                unit="t/yr",
                split_name="Polymer Type",
                aggregate_parent=False,
            ),
            # demand per capita
            IamcVariable(
                variable_name="Material Demand|Chemicals|Plastics|Per Capita",
                calculation_function=lambda mfa: (
                    mfa.stocks["use"].inflow / mfa.parameters["population"]
                ).sum_to(("t", "r")),
                unit="t/cap/yr",
                region_weight="Population",
            ),
            # trade
            IamcVariable(
                variable_name="Import|Industry|Chemicals|Plastics|Primary Forms",  # CIRCOMOD nomenclature (further differentiated by stage)
                calculation_function=lambda mfa: mfa.flows["imports => primary_market"].sum_to(
                    ("t", "r")
                ),
                unit="t/yr",
            ),
            IamcVariable(
                variable_name="Export|Industry|Chemicals|Plastics|Primary Forms",  # CIRCOMOD nomenclature (further differentiated by stage)
                calculation_function=lambda mfa: mfa.flows["primary_market => exports"].sum_to(
                    ("t", "r")
                ),
                unit="t/yr",
            ),
            IamcVariable(
                variable_name="Import|Industry|Chemicals|Plastics|Goods",  # CIRCOMOD nomenclature (further differentiated by stage)
                calculation_function=lambda mfa: mfa.flows[
                    "imports => manufactured_products_market"
                ].sum_to(("t", "r", "u")),
                unit="t/yr",
                split_name="End Use",
            ),
            IamcVariable(
                variable_name="Export|Industry|Chemicals|Plastics|Goods",  # CIRCOMOD nomenclature (further differentiated by stage)
                calculation_function=lambda mfa: mfa.flows[
                    "manufactured_products_market => exports"
                ].sum_to(("t", "r", "u")),
                unit="t/yr",
                split_name="End Use",
            ),
        ]

    def iamc_aggregates(self) -> list[str]:
        # Primary + Secondary are separate specs (no `per`), so their parent must be
        # aggregated explicitly. "Material Demand|Chemicals|Plastics" is handled
        # automatically via its "by end use" split, which owns the parent total; the
        # orthogonal "by Polymer Type" split opts out via aggregate_parent=False.
        return ["Production|Chemicals|Plastics"]
