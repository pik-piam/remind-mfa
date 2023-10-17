from src.read_data.load_data import load_stocks, load_gdp
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np


def _test3():
    df_mueller = load_stocks(stock_source='Mueller', per_capita=True, country_specific=True)
    df_pauliuk = load_stocks(stock_source='IEDatabase', per_capita=True, country_specific=True)
    df_gdp = load_gdp(country_specific=True)

    gdp = get_np_from_df(df_gdp, data_split_into_categories=False)
    stocks_mueller = get_np_from_df(df_mueller, data_split_into_categories=True)
    stocks_pauliuk = get_np_from_df(df_pauliuk, data_split_into_categories=True)

    mueller_countries = list(df_mueller.index.get_level_values(0).unique())
    pauliuk_countries = list(df_pauliuk.index.get_level_values(0).unique())
    gdp_countries = list(df_gdp.index)


    print(df_gdp.shape)

    pauliuk_data = []
    mueller_data = []
    gdp_data = []
    colors = ['r', 'g', 'b']
    countries = ['CHN', 'IND', 'USA']
    start_year_idx = 0
    end_year_idx = 109
    years = range(start_year_idx+1900, end_year_idx+1900)
    for iso in countries:
        mueller_data.append(np.sum(stocks_mueller[mueller_countries.index(iso),:,start_year_idx:end_year_idx], axis=0))
        pauliuk_data.append(np.sum(stocks_pauliuk[pauliuk_countries.index(iso), :, start_year_idx:end_year_idx], axis=0))
        gdp_data.append(gdp[gdp_countries.index(iso), start_year_idx:end_year_idx])

    for i, region_name in enumerate(countries):
        plt.plot(gdp_data[i], mueller_data[i], f'{colors[i]}--', label=f'Mueller Carbon Emissions: {region_name}')
        plt.plot(gdp_data[i], pauliuk_data[i], f'{colors[i]}', label=f'IEDatabase: {region_name}')
    plt.xlabel('GDP ($)')
    plt.ylabel('Steel (kT)')
    plt.legend(loc="upper left")
    plt.title('Steel stocks per capita over GDP')
    plt.show()


def _test2():
    df_mueller = load_stocks(stock_source='Mueller', per_capita=True, country_specific=False)
    df_pauliuk = load_stocks(stock_source='IEDatabase', per_capita=True, country_specific=False)
    mueller_countries = list(df_mueller.index.get_level_values(0).unique())
    pauliuk_countries = list(df_pauliuk.index.get_level_values(0).unique())
    stocks_mueller = get_np_from_df(df_mueller, data_split_into_categories=True)
    stocks_pauliuk = get_np_from_df(df_pauliuk, data_split_into_categories=True)

    start_year_idx = 0
    end_year_idx = 109
    years = range(start_year_idx + 1900, end_year_idx + 1900)

    mueller_data = np.sum(stocks_mueller, axis=1)[:,start_year_idx:end_year_idx]
    pauliuk_data = np.sum(stocks_pauliuk, axis=1)[:, start_year_idx:end_year_idx]

    for i, date in enumerate(mueller_data):
        plt.plot(years, date, label=mueller_countries[i])
    plt.xlabel('Years (y)')
    plt.ylabel('Steel (kT')
    plt.legend(loc="upper left")
    plt.title('Steel stocks per capita: Carbon Emissions Mueller')
    plt.show()

    for i, date in enumerate(pauliuk_data):
        plt.plot(years, date, label=pauliuk_countries[i])
    plt.xlabel('Years (y)')
    plt.ylabel('Steel (kT')
    plt.legend(loc="upper left")
    plt.title('Steel stocks per capita: IEDatabase')
    plt.show()



    return



def _test():
    df_mueller = load_stocks(stock_source='Mueller', per_capita=True, country_specific=True)
    df_pauliuk = load_stocks(stock_source='IEDatabase', per_capita=True, country_specific=True)
    mueller_countries = list(df_mueller.index.get_level_values(0).unique())
    pauliuk_countries = list(df_pauliuk.index.get_level_values(0).unique())
    stocks_mueller = get_np_from_df(df_mueller, data_split_into_categories=True)
    stocks_pauliuk = get_np_from_df(df_pauliuk, data_split_into_categories=True)

    pauliuk_data = []
    mueller_data = []
    colors = ['r', 'g', 'b','y']
    countries = ['CHN', 'IND', 'USA', 'JPN']
    start_year_idx = 0
    end_year_idx = 109
    years = range(start_year_idx+1900, end_year_idx+1900)
    for iso in countries:
        mueller_data.append(np.sum(stocks_mueller[mueller_countries.index(iso),:,start_year_idx:end_year_idx], axis=0))
        pauliuk_data.append(np.sum(stocks_pauliuk[pauliuk_countries.index(iso), :, start_year_idx:end_year_idx], axis=0))


    for i, region_name in enumerate(countries):
        plt.plot(years, mueller_data[i], f'{colors[i]}--', label=f'Mueller Carbon Emissions: {region_name}')
        plt.plot(years, pauliuk_data[i], f'{colors[i]}', label=f'IEDatabase: {region_name}')
    plt.xlabel('Years (y)')
    plt.ylabel('Steel (kT')
    plt.legend(loc="upper left")
    plt.title('Steel stocks per capita')
    plt.show()


def get_np_from_df(df: pd.DataFrame, data_split_into_categories):
    df = df.sort_index()
    np_array = df.to_numpy()
    if data_split_into_categories:
        np_array = np.reshape(np_array, df.index.levshape + np_array.shape[-1:])
    return np_array

if __name__=='__main__':
    _test()
    #_test2()
    #_test3()