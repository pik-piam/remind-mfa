import pandas as pd
from src.read_data.read_mueller_stocks import _get_current_mueller_stocks
from src.read_data.load_data import load_gdp
from src.read_data.read_pauliuk_stocks import _read_pauliuk_aggregated_original
#from src.visualisation.visualize_stocks_per_capita import make_stocks_figs_all
from src.tools.tools import transform_per_capita

TO_TEST = ['DEU', 'USA', 'CAN', 'RUS', 'FRA']

def make_graphs(data_source, df_stocks, df_gdp, is_per_capita : bool):
    # reduce to relevant countries

    df_stocks = df_stocks[df_stocks.index.isin(TO_TEST)]
    df_gdp = df_gdp[df_gdp.index.isin(TO_TEST)]
    #make_stocks_figs_all(data_source, is_per_capita=is_per_capita, df_stocks=df_stocks, df_gdp=df_gdp)

def main():
    df_gdp_total = load_gdp(country_specific=True, per_capita=False)
    df_gdp_pc = load_gdp(country_specific=True, per_capita=True)
    df_mueller_pc = _get_current_mueller_stocks()
    df_pauliuk_total = _read_pauliuk_aggregated_original()
    df_pauliuk_pc = transform_per_capita(df_pauliuk_total, total_from_per_capita=False, country_specific=True)

    make_graphs('Mueller', df_mueller_pc, df_gdp_pc, is_per_capita=True)
    make_graphs('IEDatabase', df_pauliuk_total, df_gdp_total, is_per_capita=False)
    make_graphs('IEDatabase_modPC', df_pauliuk_pc, df_gdp_pc, is_per_capita=True)


if __name__=='__main__':
    main()

