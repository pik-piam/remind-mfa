import flodym as fd

from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.cement.cement_definition import get_cement_definition
from remind_mfa.cement.cement_mfa_system_historic import InflowDrivenHistoricCementMFASystem
from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.cement.cement_mappings import CementDimensionFiles, CementDisplayNames
from remind_mfa.cement.cement_export import CementDataExporter
from remind_mfa.cement.cement_visualization import CementVisualizer
from remind_mfa.common.common_model import CommonModel
from remind_mfa.cement.cement_definition import scenario_parameters as cement_scn_prm_def
from remind_mfa.cement.cement_parameter_reconciliation import CementParameterReconciliation
from remind_mfa.common.data_blending import CriticallyDampedBlender


class CementModel(CommonModel):

    ConfigCls = CementCfg
    DimensionFilesCls = CementDimensionFiles
    DataExporterCls = CementDataExporter
    VisualizerCls = CementVisualizer
    DisplayNamesCls = CementDisplayNames
    HistoricMFASystemCls = InflowDrivenHistoricCementMFASystem
    FutureMFASystemCls = StockDrivenCementMFASystem
    ParameterReconciliationCls = CementParameterReconciliation
    custom_scn_prm_def = cement_scn_prm_def
    get_definition = staticmethod(get_cement_definition)

    # TODO: unify, then delete
    end_use_good_letter: str = "s"
    historic_stock_name: str = "in_use"

    def modify_parameters(self):
        # copy/rename for use in common model
        self.parameters["sector_split_limit"] = self.parameters["stock_type_split"]

        # construct lifetime std from mean and relative std
        lifetime_std = fd.Parameter(dims=self.parameters["lifetime_mean"].dims)
        lifetime_std[...] = self.parameters["lifetime_mean"] * self.parameters["lifetime_rel_std"]
        self.parameters["lifetime_std"] = lifetime_std

        # TODO add cement ratio as parameter here, or rather in mrmfa?
    
    def set_material_specific_variables(self):
        # TODO here, things like concrete mask, concrete application dim, etc could be stored
        # TODO function has to be added to common_model
        pass

    def compute_combined_mfa(self):
        # TODO should this go in separate combined MFA class?
        # Bottom up MFA
        td_stock = self.future_mfa.stocks["in_use"].stock.copy()

        # build bottom up stock
        prm = self.parameters
        bu_concrete_stock = self.ParameterReconciliationCls.calc_bottom_up_stock(prm, stock_type_letter=self.end_use_good_letter)
        bu_stock = bu_concrete_stock * StockDrivenCementMFASystem.product_split(prm)

        # 
        # bottom-up stock only available for concrete (constraining m and a), and Res/Com (constraining s)
        concrete_mask = {'m': 'concrete'}
        concrete_application_mask = prm["product_material_application_transform"][concrete_mask].values == 1
        concrete_application_dim_items = [item for i, item in enumerate(prm["product_material_application_transform"].dims['a'].items) if concrete_application_mask[i]]
        concrete_application_dim = fd.Dimension(name='Concrete Application', letter='x', items=concrete_application_dim_items)
    
        reduced_dim_mask = {
            'm': 'concrete',
            'a': concrete_application_dim,
            's': self.parameter_reconciliation._reduced_stock_type,
        }

        reduced_bu_stock = bu_stock[reduced_dim_mask]
        reduced_td_stock = td_stock[reduced_dim_mask][{'t': self.dims["h"]}]

        # blend smoothly between historic td and future bu
        blender = CriticallyDampedBlender(
            time=self.dims["t"].items,
            historical=reduced_td_stock.values,
            prediction=reduced_bu_stock.values,
            # TODO set lifetime here,
        )
        blended_stock = fd.FlodymArray.full_like(
            other=reduced_bu_stock,
            fill_value=blender.blend(),
        )

        # prepare combined stock
        combined_stock = td_stock.copy()
        combined_stock[reduced_dim_mask] = blended_stock

        # compute combined mfa
        self.combined_mfa = self.make_mfa(historic=False)
        self.combined_mfa.compute(combined_stock, self.historic_trade, stock_is_cement=False)

        return self.combined_mfa

