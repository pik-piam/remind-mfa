import logging
from typing import Dict
import numpy as np
from scipy.optimize import least_squares

from sodym import (
    StockArray, Stock, DynamicStockModel,
    MFASystem, DimensionSet, NamedDimArray, Process, Parameter
)
from sodym.stock_helper import create_dynamic_stock


class InflowDrivenHistoric_StockDrivenFuture():
    """
    Extension of the MFASystem class to calculate in-use stock based on historic production data,
    which is extrapolated to future years based on GDP pC.

    Assumes dimensions
    - time (t) or historic time (h)
    - region (r)
    - good (g)
    """
    def __init__(
            self, parameters: Dict[str, Parameter], dims: DimensionSet, process: Process, ldf_type, curve_strategy,
        ) -> None:
        if process.name != 'use':
            raise ValueError("Only valid process is 'use'.")
        self.process = process
        self.parameters = parameters
        self.dims = dims
        self.ldf_type = ldf_type
        self.curve_strategy = curve_strategy

    def get_new_array(self, **kwargs) -> NamedDimArray:
        dims = self.dims.get_subset(kwargs["dim_letters"]) if "dim_letters" in kwargs else self.dims
        return NamedDimArray(dims=dims, **kwargs)

    def get_subset_transformer(self, dim_letters: tuple):
        """Get a Parameter/NamedDimArray which transforms between two dimensions, one of which is a subset of the
        other."""
        assert len(dim_letters) == 2, "Only two dimensions are allowed"
        dims = self.dims.get_subset(dim_letters)
        assert set(dims[0].items).issubset(set(dims[1].items)) or set(dims[1].items).issubset(
            set(dims[0].items)
        ), f"Dimensions '{dims[0].name}' and '{dims[1].name}' are not subset and superset or vice versa."
        out = NamedDimArray(name=f"transform_{dims[0].letter}_<->_{dims[1].letter}", dims=dims)
        # set all values to 1 if first axis item equals second axis item
        for i, item in enumerate(dims[0].items):
            if item in dims[1].items:
                out.values[i, dims[1].index(item)] = 1
        return out

    def compute_in_use_stock(self):
        hist_stk = self.compute_historic_from_demand()
        stock = self.get_extrapolation(hist_stk.stock)
        stk = self.compute_future_demand(stock)
        return self.prepare_stock_for_mfa(stk)

    def compute_historic_from_demand(self):

        inflow = StockArray(
            dims=self.dims.get_subset(('h', 'r', 'g')),
            values=self.parameters['production'].values,
            name='in_use_inflow'
        )
        hist_stk = create_dynamic_stock(
            name='in_use', process=self.process, ldf_type=self.ldf_type,
            inflow=inflow, lifetime_mean=self.parameters['lifetime_mean'],
            lifetime_std=self.parameters['lifetime_std'],
        )
        hist_stk.compute()

        return hist_stk

    def get_extrapolation(self, historic_stocks):
        """
        Interfaces to the extrapolation function, by performing the per-capita transformation and the
        NamedDimArray <-> numpy array transformation.
        """

        # transform to per capita
        pop = self.parameters['population']
        transform_t_thist  = self.get_subset_transformer(('t', 'h'))
        historic_pop       = self.get_new_array(dim_letters=('h','r'))
        historic_gdppc     = self.get_new_array(dim_letters=('h','r'))
        historic_stocks_pc = self.get_new_array(dim_letters=('h','r','g'))
        stocks_pc          = self.get_new_array(dim_letters=('t','r','g'))
        stocks             = self.get_new_array(dim_letters=('t','r','g'))

        historic_pop[...] = pop * transform_t_thist
        historic_gdppc[...] = self.parameters['gdppc'] * transform_t_thist
        historic_stocks_pc[...] = historic_stocks / historic_pop

        self.extrapolate_stock(
            curve_strategy=self.curve_strategy,
            historic_stocks=historic_stocks_pc.values,
            gdppc=self.parameters['gdppc'].values,
            prediction_out=stocks_pc.values
        )

        # transform back to total stocks
        stocks[...] = stocks_pc * pop

        #visualize_stock(self, self.parameters['gdppc'], historic_gdppc, stocks, historic_stocks, stocks_pc, historic_stocks_pc)

        return stocks

    def extrapolate_stock(self, curve_strategy, historic_stocks, gdppc, prediction_out):
        """
        wrapper to choose extrapolation strategy from config
        """
        if curve_strategy == "GDP_regression":
            self.gdp_regression(historic_stocks,
                           gdppc,
                          prediction_out)
        else:
            raise RuntimeError(f"Prediction strategy {curve_strategy} is not defined. "
                            f"It needs to be 'GDP_regression'.")
        return

    @staticmethod
    def gdp_regression(historic_stocks_pc, gdppc, prediction_out):

        shape_out = prediction_out.shape
        assert len(shape_out) == 3, "Prediction array must have 3 dimensions: Time, Region, Good"
        pure_prediction = np.zeros_like(prediction_out)
        n_historic = historic_stocks_pc.shape[0]
        i_lh = n_historic - 1

        for i_region in range(shape_out[1]):
            for i_good in range(shape_out[2]):
                def fitting_function(prms):
                    return prms[0] / (1. + np.exp(prms[1]/gdppc[:n_historic,i_region])) - historic_stocks_pc[:,i_region,i_good]
                        # Lagrangian multiplier to ensure matching last point:
                        # + prms[2] * prms[0] / (1. + np.exp(prms[1]/gdppc[i_lh,0])) - stocks_pc[-1,0,i] )
                prms_out = least_squares(fitting_function, x0=np.array([2.*gdppc[i_lh,i_region],historic_stocks_pc[-1,i_region,i_good]]), gtol=1.e-12)
                assert prms_out.success

                pure_prediction[:,i_region,i_good] = prms_out.x[0] / (1. + np.exp(prms_out.x[1]/gdppc[:,i_region]))

            # def fitting_function(prms):
            #     return 2.*gdppc[i_lh,0] / (1. + np.exp(prms[0]/gdppc[cfg.i_historic,0])) - stocks_pc[:,0,i]
            # prms_out = least_squares(fitting_function, x0=np.array([stocks_pc[-1,0,i]]))
            # prediction = 2.*gdppc[i_lh,0] / (1. + np.exp(prms_out.x[0]/gdppc[:,0]))

        # fit b to last historic value
        prediction_out[...] = pure_prediction - (pure_prediction[i_lh,:,:] - historic_stocks_pc[i_lh,:,:])
        prediction_out[:n_historic,:,:] = historic_stocks_pc

        # if cfg.do_visualize["stock_prediction"]:
        #     visualize_stock_prediction(gdppc, historic_stocks_pc, pure_prediction)
        return

    def compute_future_demand(self, stock: StockArray):
        stk = create_dynamic_stock(
            name='in_use', process=self.process, ldf_type=self.ldf_type,
            stock=stock, lifetime_mean=self.parameters['lifetime_mean'],
            lifetime_std=self.parameters['lifetime_std'],
        )
        stk.compute()
        return stk

    def prepare_stock_for_mfa(self, stk: DynamicStockModel):
        # We use an auxiliary stock for the prediction step to save dimensions and computation time
        # Therefore, we have to transfer the result to the higher-dimensional stock in the MFA system
        prm = self.parameters
        stock_extd = stk.stock * prm['material_shares_in_goods'] * prm['carbon_content_materials']
        inflow = stk.inflow * prm['material_shares_in_goods'] * prm['carbon_content_materials']
        outflow = stk.outflow * prm['material_shares_in_goods'] * prm['carbon_content_materials']
        stock_dims = self.dims.get_subset(('t','r','g','m','e'))
        stock_extd = StockArray(values=stock_extd.values, name='in_use_stock', dims=stock_dims)
        inflow = StockArray(values=inflow.values, name='in_use_inflow', dims=stock_dims)
        outflow = StockArray(values=outflow.values, name='in_use_outflow', dims=stock_dims)
        stock = Stock(
            stock=stock_extd, inflow=inflow, outflow=outflow, name='in_use', process_name='use',
            process=self.process,
        )
        return stock


class MFASystemWithComputedStocks(MFASystem):
    def initialize_stocks(self, processes: Dict[str, Process]) -> Dict[str, Stock]:
        stocks = {}
        for stock_definition in self.definition.stocks:
            dims = self.dims.get_subset(stock_definition.dim_letters)
            try:
                process = processes[stock_definition.process_name]
            except KeyError:
                raise KeyError(f"Missing process required by stock definition {stock_definition}.")
            if stock_definition.process_name == 'use':
                logging.info('Computing in use stocks')
                stock = self.compute_in_use_stock(process=process)
            else:
                stock = Stock.from_definition(stock_definition, dims=dims, process=process)
            stocks[stock.name] = stock
        return stocks

    def compute_in_use_stock(self, process):
        stock_computer = InflowDrivenHistoric_StockDrivenFuture(
            parameters=self.parameters, process=process, dims=self.dims,
            ldf_type=self.ldf_type, curve_strategy=self.curve_strategy,
        )
        return stock_computer.compute_in_use_stock()
