from ODYM.odym.modules import dynamic_stock_model as dsm
from src.model.load_dsms import load_dsms
from src.tools.config import cfg


def load_econ_dsms(country_specific, p_st, p_0_st):
    dsms = load_dsms(country_specific)
    factor = (p_st/p_0_st)**cfg.elasticity_steel
    for category_dsms in dsms:
        for old_category_dsm in category_dsms:
            old_category_dsm.i[cfg.econ_base_year-cfg.start_year+1:]*=factor
            new_category_dsm = DSM_Inflow = dsm.DynamicStockModel(t = old_category_dsm.t,
                                                                  i = old_category_dsm.i,
                                                                  lt = old_category_dsm.lt)
            new_category_dsm.compute_s_c_inflow_driven()
            new_category_dsm.compute_o_c_from_s_c()
            new_category_dsm.compute_stock_total()
            new_category_dsm.compute_outflow_total()
            new_category_dsm.compute_stock_change()
            old_category_dsm.i=new_category_dsm.i
            old_category_dsm.o = new_category_dsm.o
            old_category_dsm.o_c = new_category_dsm.o_c
            old_category_dsm.s = new_category_dsm.s
            old_category_dsm.s_c = new_category_dsm.s_c
    return dsms


def _test():
    orig_dsms = load_econ_dsms(country_specific=False, p_st=10, p_0_st=5)


if __name__=='__main__':
    _test()