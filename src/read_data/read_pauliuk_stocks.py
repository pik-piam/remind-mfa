import pandas as pd
from src.read_data.read_UN_population import load_un_pop
from src.read_data.read_mueller_country_codes import load_country_names_and_codes
from src.tools.tools import Years
from src.tools.config import cfg


def load_pauliuk_to_dfs(years: Years):

    # TODO:
    # - print countries that are in remind, but not in Pauliuk
    # - correct country summing; drop regions that are not in list (REF?)

    pop_dict = load_un_pop()

    df_pauliuk = load_stocks()
    df_all = add_country_codes(df_pauliuk)
    df_all = add_regions_and_pop(df_all, pop_dict, years)

    df_global, df_regional = aggregate_countries(df_all)

    for df in [df_global, df_regional]:
        df['stock_pc'] = df['stock'] / df['population']

    return df_global, df_regional


def load_stocks():
    # load steel stocks
    df_pauliuk = pd.read_excel(
        io=cfg.data_path + '/original/Pauliuk/2_IUS_steel_200R.xlsx',
        engine='openpyxl',
        sheet_name='Data',
        usecols=['aspect 3 : time', 'aspect 5 : region', 'value'])

    # clean up
    df_pauliuk = df_pauliuk.rename(columns={'aspect 3 : time': 'Year',
                                            'aspect 5 : region': 'country',
                                            'value': 'stock'})
    df_pauliuk['country'] = df_pauliuk['country'].replace('United States', 'USA')
    df_pauliuk['stock'] = df_pauliuk['stock'] * 1000.
    return df_pauliuk


def add_country_codes(df_pauliuk: pd.DataFrame):
    country_names_and_codes = load_country_names_and_codes()
    df_all = pd.merge(df_pauliuk, country_names_and_codes, how='left', on='country')

    # debug output: If a country is not in Mueller, then the ccode is NaN in that row
    pauliuk_countries_not_in_mueller = df_all['country'][df_all['ccode'].isna()].unique()
    print("Countries found in Pauliuk, but not in Mueller:\n",
          pauliuk_countries_not_in_mueller)
    return df_all


def add_regions_and_pop(df_all: pd.DataFrame, pop_dict: dict, years: Years):
    population = pd.concat([
        pd.DataFrame.from_dict({
            'ccode': [ccode for _ in years.ids],
            'region': [region for _ in years.ids],
            'population': pop[years.ids],
            'Year': years.calendar})
        for region, ccodes in pop_dict.items() if region != 'Total'
        for ccode, pop in ccodes.items() if ccode != 'Total'])
    df_all = pd.merge(df_all, population, how='left', on=['ccode', 'Year'])
    return df_all


def aggregate_countries(df_all: pd.DataFrame):
    # sum over countries
    df_regional = df_all \
        .groupby(['region', 'Year'], as_index=False) \
        .aggregate({'stock': 'sum', 'population': 'sum'}) \
        .reset_index()
    df_global = df_regional \
        .groupby('Year') \
        .aggregate({'stock': 'sum', 'population': 'sum'})
    # add region
    df_global['region'] = 'World'
    return df_global, df_regional
