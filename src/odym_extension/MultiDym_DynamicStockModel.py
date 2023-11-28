import numpy as np
from ODYM.odym.modules.dynamic_stock_model import DynamicStockModel
from src.model.calc_steel_stocks import get_np_steel_stocks_with_prediction
from src.read_data.load_data import load_stocks, load_lifetimes
from src.tools.config import cfg


# TODO: unfinished - decide whether to implement or leave it


class MultiDym_DynamicStockModel(DynamicStockModel):

    def __init__(self, stocks, stock_indices, lt_type, lt_mean, lt_sd, lt_indices):
        time_idx = stock_indices.index('t')
        time = np.arange(stocks.shape[time_idx])

        self.dsms_list = []

        for dim, index in enumerate(stock_indices):
            if index=='t':
                continue



def _test():
    country_specific=False
    df_stocks = load_stocks(country_specific=country_specific, per_capita=True)
    stocks_data = get_np_steel_stocks_with_prediction(df_stocks, country_specific=country_specific)
    stocks_data = stocks_data[:,0,:,0]
    #stocks_data = stocks_data.transpose()
    mean, std_dev = load_lifetimes()
    mean = mean.reshape(1,4)
    print(stocks_data.shape)
    print(mean.shape)
    time = np.array(range(cfg.n_years))
    steel_stock_dsm = DynamicStockModel(t=time,
                                        s=stocks_data,
                                        lt={'Type': 'Normal', 'Mean': mean, 'StdDev': std_dev})
    #print(steel_stock_dsm.i[0])
    #print(steel_stock_dsm.s[0])
    #print(steel_stock_dsm.sf[0,0])
    steel_stock_dsm.compute_stock_driven_model()
    print(steel_stock_dsm)


if __name__=='__main__':
    _test()