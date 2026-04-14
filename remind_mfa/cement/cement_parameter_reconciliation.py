import flodym as fd
from copy import deepcopy

from remind_mfa.common.common_parameter_reconciliation import CommonParameterReconciliation
from remind_mfa.cement.cement_mfa_system_historic import InflowDrivenHistoricCementMFASystem

class CementParameterReconciliation(CommonParameterReconciliation):
    
    def prepare_dims(self):
        dims = self.ref_mfa.dims
        self.input_dims = deepcopy(dims)
        self.dims = dims.replace('s', self._reduced_stock_type)

    def prepare_prms(self):
        prms = self.ref_mfa.parameters
        self.input_prms = deepcopy(prms)
        self.prms: dict[str, fd.Parameter] = {}
        self.prms_adj_dims: dict[str, fd.DimensionSet] = {}
        for key, val in prms.items():
            # reduce stock type dimension
            if "s" in val.dims.letters:
                val = val[{"s": self._reduced_stock_type}]
            # remove time dimension
            if key in ["floorspace"]:
                val = val[{"t": self._year_of_reconciliation}]
            self.prms[key] = val
            self.prms_adj_dims[key] = self.remove_fd_dims_if_present(val.dims, self._no_correction_dim_letters)
    
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
    
    def f1(self, prm: dict[str, fd.FlodymArray]):
        """Top-down stock calculation."""
        
        cement_stock = InflowDrivenHistoricCementMFASystem.compute_cement_stock(prm, self.trds, self.flws, self.stks)

        cement_stock = cement_stock[{"h": self._year_of_reconciliation}]

        # TODO harmonize output dims

        return cement_stock

    def f2(self, prm: dict[str, fd.FlodymArray]):
        """Bottom-up stock calculation."""

        concrete_stk = (
            prm["concrete_building_mi"]
            * prm["function_buildings_split"]
            * prm["structure_buildings_split"]
            * prm["floorspace"]
        )

        # TODO do this in prm adjustment
        concrete_mask = {'m': 'concrete'}
        concrete_application_mask = prm["product_material_application_transform"][concrete_mask].values == 1
        concrete_application_dim_items = [item for i, item in enumerate(prm["product_material_application_transform"].dims['a'].items) if concrete_application_mask[i]]
        concrete_application_dim = fd.Dimension(name='Concrete Application', letter='x', items=concrete_application_dim_items)
        
        cement_stock = (
            concrete_stk
            # split in materials and applications
            * prm["product_material_split"][concrete_mask]
            * prm["product_application_split"][{"a": concrete_application_dim}]
            # transform from product to cement stock
            * prm["product_density"][concrete_mask]
            / prm["product_cement_content"][{"a": concrete_application_dim}]
        )

        # harmonize output dims
        reduced_cement_stock = fd.FlodymArray(dims=cement_stock.dims.drop("f"))
        reduced_cement_stock[{'u': 'Res'}] = cement_stock[{'f': 'RS', 'u': "Res"}] + cement_stock[{'f': 'RM', 'u': "Res"}]
        reduced_cement_stock[{'u': 'Com'}] = cement_stock[{'f': 'Com', 'u': "Com"}]
        reduced_cement_stock = reduced_cement_stock.sum_over(('b', 'x'))

        return reduced_cement_stock
