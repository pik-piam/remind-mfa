import flodym as fd
from copy import deepcopy

from remind_mfa.common.common_parameter_reconciliation import CommonParameterReconciliation
from remind_mfa.cement.cement_mfa_system_historic import InflowDrivenHistoricCementMFASystem


class CementParameterReconciliation(CommonParameterReconciliation):

    def prepare_dims(self):
        dims = self.ref_mfa.dims
        self.input_dims = deepcopy(dims)
        self.dims = dims.replace("s", self._reduced_stock_type)

    def prepare_prms(self):
        prms = self.ref_mfa.parameters
        self.input_prms = deepcopy(prms)
        self.prms: dict[str, fd.Parameter] = {}
        self.prms_adj_dims: dict[str, fd.DimensionSet] = {}
        ref_prms = self.output_prms if hasattr(self, "output_prms") else prms
        for key, val in ref_prms.items():
            # reduce stock type dimension
            if "s" in val.dims.letters:
                val = val[{"s": self._reduced_stock_type}]
            # remove time dimension
            if key in ["floorspace"]:
                val = val[{"t": self._year_of_reconciliation}]
            self.prms[key] = val
            self.prms_adj_dims[key] = self.remove_fd_dims_if_present(
                val.dims, self._no_correction_dim_letters
            )

    def prepare_flws(self):
        flws = self.ref_mfa.flows
        self.input_flws = deepcopy(flws)
        self.flws: dict[str, fd.Flow] = {}
        for key, val in flws.items():
            val = deepcopy(val)
            if "s" in val.dims.letters:
                val = val[{"s": self._reduced_stock_type}]
            self.flws[key] = val

    def prepare_stks(self):
        stks = self.ref_mfa.stocks
        self.input_stks = deepcopy(stks)
        self.stks: dict[str, fd.Stock] = {}
        for key, val in stks.items():
            val = deepcopy(val)
            if "s" in val.dims.letters:
                val.inflow = val.inflow[{"s": self._reduced_stock_type}]
                val.outflow = val.outflow[{"s": self._reduced_stock_type}]
                val.stock = val.stock[{"s": self._reduced_stock_type}]
                val.dims = val.inflow.dims
                if hasattr(val, "lifetime_model"):
                    val.lifetime_model.dims = val.inflow.dims
            self.stks[key] = val

    def calc_top_down_stock(self, prm: dict[str, fd.FlodymArray]):
        """Top-down stock calculation for reconciliaton."""

        # 1. Compute product stock from hisoric MFA
        cement_stock = InflowDrivenHistoricCementMFASystem.compute_cement_stock(
            prm, self.trds, self.flws, self.stks
        )
        product_stock = cement_stock * prm["product_material_split"] / prm["cement_ratio"]

        # 2. Reduce dimensions to match bottom-up stock dimensions
        # 2.1 Use only reconciliation year
        product_stock = product_stock[{"h": self._year_of_reconciliation}]

        # 2.2 Use only material (m) concrete [no mortar]
        concrete_mask = {"m": "concrete"}
        concrete_stock = product_stock[concrete_mask]

        return concrete_stock

    @staticmethod
    def calc_bottom_up_stock(prm: dict[str, fd.FlodymArray], stock_type_letter: str = "u"):
        """Bottom-up stock calculation for reconciliation."""

        # 1. Compute concrete stock through bottom-up calculation
        concrete_stk = (
            prm["floorspace"]
            * prm["function_buildings_split"]
            * prm["structure_buildings_split"]
            * prm["concrete_building_mi"]
        )

        # 2. Reduce dimensions to match top-down stock dimensions
        # 2.1 Remove building function
        reduced_cement_stock = fd.FlodymArray(dims=concrete_stk.dims.drop("f"))
        reduced_cement_stock[{stock_type_letter: "Res"}] = (
            concrete_stk[{"f": "RS", stock_type_letter: "Res"}]
            + concrete_stk[{"f": "RM", stock_type_letter: "Res"}]
        )
        reduced_cement_stock[{stock_type_letter: "Com"}] = concrete_stk[
            {"f": "Com", stock_type_letter: "Com"}
        ]

        # 2.2 Remove building structure
        reduced_cement_stock = reduced_cement_stock.sum_over("b")

        # TODO move this to mrmfa as a parameter
        # Scale up Chinese building stock to account for hibernating stock
        # 17.4% unused buildings from https://www.nature.com/articles/s41558-025-02527-3?fromPaywallRec=false#Fig3
        reduced_cement_stock[{"r": "CHA"}] = reduced_cement_stock[{"r": "CHA"}] / (1.0 - 0.174)

        return reduced_cement_stock
