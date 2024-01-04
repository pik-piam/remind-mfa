import os
import pandas as pd
from src.tools.config import cfg
from src.tools.tools import read_processed_data, group_country_data_to_regions, transform_per_capita


# -- MAIN DATA LOADING FUNCTIONS BY DATA TYPE --


def load_stocks(stock_source=None, country_specific=False, per_capita=True, recalculate=False):
    if stock_source is None:
        stock_source = cfg.steel_data_source
    if stock_source == 'Mueller':
        return _load_mueller_stocks(country_specific=country_specific, per_capita=per_capita, recalculate=recalculate)
    elif stock_source == 'IEDatabase':
        return _load_pauliuk_stocks(country_specific=country_specific, per_capita=per_capita, recalculate=recalculate)
    else:
        raise ValueError(f'{stock_source} is not a valid stock data source.')


def load_pop(pop_source=None, country_specific=False, recalculate=False):
    if pop_source is None:
        pop_source = cfg.pop_data_source
    if pop_source == 'UN':
        return _load_un_pop(country_specific=country_specific, recalculate=recalculate)
    elif pop_source == 'KC-Lutz':
        return _load_kc_lutz_pop(country_specific=country_specific, recalculate=recalculate)
    else:
        raise ValueError(f'{pop_source} is not a valid population data source.')


def load_gdp(gdp_source=None, country_specific=False, per_capita=True, recalculate=False):
    if gdp_source is None:
        gdp_source = cfg.gdp_data_source
    if gdp_source == 'IMF':
        return _load_imf_gdp(country_specific=country_specific, per_capita=per_capita, recalculate=recalculate)
    elif gdp_source == 'Koch-Leimbach':
        return _load_koch_leimbach_gdp(country_specific=country_specific,
                                       per_capita=per_capita,
                                       recalculate=recalculate)
    else:
        raise ValueError(f'{gdp_source} is not a valid GDP data source.')


def load_regions(region_source=None, recalculate=False):
    if region_source is None:
        region_source = cfg.region_data_source
    if region_source == 'World':
        regions = pd.DataFrame.from_dict({'region': ['World']})
    elif region_source == 'REMIND':
        regions = _load_remind_regions()
    elif region_source == 'REMIND_EU':
        regions = _load_remind_eu_regions()
    else:
        raise ValueError(f'{region_source} is not a valid region data source.')
    return regions


def load_region_names_list():
    df_regions = load_regions()
    regions_list = list(df_regions['region'].unique())
    regions_list.sort()
    return regions_list


def load_production(country_specific, production_source=None, recalculate=False):
    if production_source is None:
        production_source = cfg.production_data_source
    if production_source == 'geyer':
        return _load_geyer_production(country_specific=country_specific, recalculate=recalculate)
    else:
        raise ValueError(f'{production_source} is not a valid production data source.')


def load_use_1970_2021(country_specific, use_source=None, recalculate=False):
    if use_source is None:
        use_source = cfg.use_data_source
    if use_source == 'WorldSteel':
        return _load_worldsteel_use_1970_2021(country_specific=country_specific, recalculate=recalculate)
    else:
        raise ValueError(f'{use_source} is not a valid (apparent) use data source.')


def load_scrap_trade_1971_2022(country_specific, scrap_trade_source=None, recalculate=False):
    if scrap_trade_source is None:
        scrap_trade_source = cfg.scrap_trade_data_source
    if scrap_trade_source == 'WorldSteel':
        df_scrap_imports = _load_worldsteel_scrap_imports_1970_2021(country_specific=country_specific,
                                                                    recalculate=recalculate)
        df_scrap_exports = _load_worldsteel_scrap_exports_1970_2021(country_specific=country_specific,
                                                                    recalculate=recalculate)
        return df_scrap_imports, df_scrap_exports
    else:
        raise ValueError(f'{scrap_trade_source} is not a valid (apparent) scrap trade source.')


def load_indirect_trade_2001_2019(country_specific, indirect_trade_source=None, recalculate=False):
    if indirect_trade_source is None:
        indirect_trade_source = cfg.indirect_trade_source
    if indirect_trade_source == 'WorldSteel':
        df_indirect_imports = _load_worldsteel_indirect_imports_2001_2019(country_specific=country_specific,
                                                                          recalculate=recalculate)
        df_indirect_exports = _load_worldsteel_indirect_exports_2001_2019(country_specific=country_specific,
                                                                          recalculate=recalculate)
        return df_indirect_imports, df_indirect_exports
    else:
        raise ValueError(f'{indirect_trade_source} is not a valid (apparent) scrap trade source.')


def load_indirect_trade_category_quantities(country_specific, recalculate=False):
    df = _load_worldsteel_indirect_trade_category_quantities(country_specific, recalculate)
    return df


def load_lifetimes(lifetime_source=None):
    # TODO make real lifetime load functions with recalculate!
    if lifetime_source is None:
        lifetime_source = cfg.lifetime_data_source
    if lifetime_source == 'Wittig':
        lifetime_path = os.path.join(cfg.data_path, 'original', 'Wittig', 'Wittig_lifetimes.csv')
    elif lifetime_source == 'Pauliuk':
        lifetime_path = os.path.join(cfg.data_path, 'original', 'Pauliuk', 'Pauliuk_lifetimes.csv')
    else:
        raise ValueError(f'{lifetime_source} is not a valid lifetime data source.')
    df = pd.read_csv(lifetime_path)
    df = df.set_index('category')
    mean = df['Mean'].to_numpy()
    std_dev = df['Standard Deviation'].to_numpy()
    return mean, std_dev


def load_lifetimes_beta(lifetime_source=None):
    # TODO Finish different lifetime load functions, replace
    if lifetime_source is None:
        lifetime_source = cfg.lifetime_data_source
    if lifetime_source == 'Pauliuk_c':
        from src.read_data.read_pauliuk_lifetimes_approach_c import get_pauliuk_lifetimes_approach_c
        df = get_pauliuk_lifetimes_approach_c()
        return
    if lifetime_source == 'Wittig':
        lifetime_path = os.path.join(cfg.data_path, 'original', 'Wittig', 'Wittig_lifetimes.csv')
    elif lifetime_source == 'Pauliuk':
        lifetime_path = os.path.join(cfg.data_path, 'original', 'Pauliuk', 'Pauliuk_lifetimes.csv')
    else:
        raise ValueError(f'{lifetime_source} is not a valid lifetime data source.')
    df = pd.read_csv(lifetime_path)
    df = df.set_index('category')
    mean = df['Mean'].to_numpy()
    std_dev = df['Standard Deviation'].to_numpy()
    return mean, std_dev


# -- DATA LOADER --


def _data_loader(file_base_name, recalculate_function, country_specific,
                 data_stored_per_capita, return_per_capita, data_split_into_categories=False,
                 recalculate=False, is_yearly_data=True):
    file_name_end = '_countries' if country_specific else f'_{cfg.region_data_source}_regions'
    if country_specific is None:
        file_name_end = ""
    file_name = f"{file_base_name}{file_name_end}.csv"
    file_path = os.path.join(cfg.data_path, 'processed', file_name)
    if os.path.exists(file_path) and not recalculate:
        df = read_processed_data(file_path, is_yearly_data)
        df = df.reset_index()
        indices = list(df.select_dtypes(include='object'))  # select all columns that aren't numbers
        df = df.set_index(indices)
    else:  # recalculate and store
        if country_specific or country_specific is None:
            df = recalculate_function()
        else:  # region specific
            df = _data_loader(file_base_name, recalculate_function, country_specific=True,
                              data_stored_per_capita=data_stored_per_capita,
                              return_per_capita=data_stored_per_capita,
                              data_split_into_categories=data_split_into_categories,
                              recalculate=recalculate,
                              is_yearly_data=is_yearly_data)
            df = group_country_data_to_regions(df, is_per_capita=data_stored_per_capita,
                                               data_split_into_categories=data_split_into_categories)
        df.to_csv(file_path)

    if country_specific is not None:
        if data_stored_per_capita and not return_per_capita:
            df = transform_per_capita(df, total_from_per_capita=True, country_specific=country_specific)
        if not data_stored_per_capita and return_per_capita:
            df = transform_per_capita(df, total_from_per_capita=False, country_specific=country_specific)

    df = df.sort_index()

    return df


# -- SPECIFIC DATA LOADING FUNCTIONS BY DATA TYPE AND SOURCE --


def _load_un_pop(country_specific, recalculate):
    from src.read_data.read_UN_population import get_pop_countries
    df = _data_loader(file_base_name='UN_pop',
                      recalculate_function=get_pop_countries,
                      country_specific=country_specific,
                      data_stored_per_capita=False,
                      return_per_capita=False,
                      recalculate=recalculate)
    return df


def _load_kc_lutz_pop(country_specific, recalculate):
    from src.read_data.read_kc_lutz_population import get_kc_lutz_pop_countries
    df = _data_loader(file_base_name='KC_Lutz_pop',
                      recalculate_function=get_kc_lutz_pop_countries,
                      country_specific=country_specific,
                      data_stored_per_capita=False,
                      return_per_capita=False,
                      data_split_into_categories=True,
                      recalculate=recalculate)

    return df


def _load_mueller_stocks(country_specific, per_capita, recalculate):
    from src.read_data.read_mueller_stocks import get_mueller_country_stocks
    df = _data_loader(file_base_name='mueller_stocks',
                      recalculate_function=get_mueller_country_stocks,
                      country_specific=country_specific,
                      data_stored_per_capita=True,
                      return_per_capita=per_capita,
                      data_split_into_categories=True,
                      recalculate=recalculate)
    return df


def _load_pauliuk_stocks(country_specific, per_capita, recalculate):
    from src.read_data.read_pauliuk_stocks import get_pauliuk_country_stocks
    df = _data_loader(file_base_name='pauliuk_stocks',
                      recalculate_function=get_pauliuk_country_stocks,
                      country_specific=country_specific,
                      data_stored_per_capita=True,
                      return_per_capita=per_capita,
                      data_split_into_categories=True,
                      recalculate=recalculate)
    return df


def _load_imf_gdp(country_specific, per_capita, recalculate):
    from src.read_data.read_IMF_gdp import get_imf_gdp_countries
    df = _data_loader(file_base_name='imf_gdp',
                      recalculate_function=get_imf_gdp_countries,
                      country_specific=country_specific,
                      data_stored_per_capita=True,
                      return_per_capita=per_capita,
                      recalculate=recalculate)
    return df


def _load_koch_leimbach_gdp(country_specific, per_capita, recalculate):
    from src.read_data.read_koch_leimbach_gdp import get_koch_leimbach_gdp_countries
    df = _data_loader(file_base_name='koch_leimbach_gdp',
                      recalculate_function=get_koch_leimbach_gdp_countries,
                      country_specific=country_specific,
                      data_stored_per_capita=False,
                      return_per_capita=per_capita,
                      data_split_into_categories=True,
                      recalculate=recalculate)
    return df


def _load_usgs_steel_prices(recalculate):
    from src.read_data.read_USGS_prices import get_usgs_steel_prices
    df = _data_loader(file_base_name='usgs_steel_prices',
                      recalculate_function=get_usgs_steel_prices,
                      country_specific=None,
                      data_stored_per_capita=False,
                      return_per_capita=False,
                      recalculate=recalculate)
    return df


def _load_usgs_scrap_prices(recalculate):
    from src.read_data.read_USGS_prices import get_usgs_scrap_prices
    df = _data_loader(file_base_name='usgs_scrap_prices',
                      recalculate_function=get_usgs_scrap_prices,
                      country_specific=None,
                      data_stored_per_capita=False,
                      return_per_capita=False,
                      recalculate=recalculate)

    return df


def _load_worldsteel_production(country_specific, recalculate):
    from src.read_data.read_WorldSteel_production import get_worldsteel_production_1900_2022
    df = _data_loader(file_base_name='worldsteel_production',
                      recalculate_function=get_worldsteel_production_1900_2022,
                      country_specific=country_specific,
                      data_stored_per_capita=False,
                      return_per_capita=False,
                      recalculate=recalculate)
    return df


def _load_worldsteel_use_1970_2021(country_specific, recalculate):
    from src.read_data.read_WorldSteel_use import get_world_steel_use_1970_2021
    df = _data_loader(file_base_name='worldsteel_use',
                      recalculate_function=get_world_steel_use_1970_2021,
                      country_specific=country_specific,
                      data_stored_per_capita=False,
                      return_per_capita=False,
                      recalculate=recalculate)
    return df


def _load_worldsteel_scrap_imports_1970_2021(country_specific, recalculate):
    from src.read_data.read_WorldSteel_scrap_trade import get_world_steel_scrap_imports_1970_2022
    df = _data_loader(file_base_name='worldsteel_scrap_imports',
                      recalculate_function=get_world_steel_scrap_imports_1970_2022,
                      country_specific=country_specific,
                      data_stored_per_capita=False,
                      return_per_capita=False,
                      recalculate=recalculate)
    return df


def _load_worldsteel_scrap_exports_1970_2021(country_specific, recalculate):
    from src.read_data.read_WorldSteel_scrap_trade import get_world_steel_scrap_exports_1970_2022
    df = _data_loader(file_base_name='worldsteel_scrap_exports',
                      recalculate_function=get_world_steel_scrap_exports_1970_2022,
                      country_specific=country_specific,
                      data_stored_per_capita=False,
                      return_per_capita=False,
                      recalculate=recalculate)
    return df


def _load_worldsteel_indirect_imports_2001_2019(country_specific, recalculate):
    from src.read_data.read_WorldSteel_indirect_trade import get_world_steel_indirect_imports_2001_2019
    df = _data_loader(file_base_name='worldsteel_indirect_imports',
                      recalculate_function=get_world_steel_indirect_imports_2001_2019,
                      country_specific=country_specific,
                      data_stored_per_capita=False,
                      return_per_capita=False,
                      recalculate=recalculate)
    return df


def _load_worldsteel_indirect_exports_2001_2019(country_specific, recalculate):
    from src.read_data.read_WorldSteel_indirect_trade import get_world_steel_indirect_exports_2001_2019
    df = _data_loader(file_base_name='worldsteel_indirect_exports',
                      recalculate_function=get_world_steel_indirect_exports_2001_2019,
                      country_specific=country_specific,
                      data_stored_per_capita=False,
                      return_per_capita=False,
                      recalculate=recalculate)
    return df


def _load_worldsteel_indirect_trade_category_quantities(country_specific, recalculate):
    from src.read_data.read_WorldSteel_indirect_category_shares import \
        get_worldsteel_net_indirect_trade_category_quantities_2013
    df = _data_loader(file_base_name='worldsteel_indirect_trade_category_quantities',
                      recalculate_function=get_worldsteel_net_indirect_trade_category_quantities_2013,
                      country_specific=country_specific,
                      data_stored_per_capita=False,
                      return_per_capita=False,
                      recalculate=recalculate,
                      is_yearly_data=False)

    return df


def _load_pauliuk_regions():
    from src.read_data.read_pauliuk_regions import get_pauliuk_regions
    return get_pauliuk_regions()


def _load_remind_regions():
    from src.read_data.read_REMIND_regions import get_remind_regions
    return get_remind_regions()


def _load_remind_eu_regions():
    from src.read_data.read_REMIND_regions import get_remind_eu_regions
    return get_remind_eu_regions()

if __name__ == '__main__':
    # regions = load_regions(region_source='World', recalculate=True)
    regions = load_regions(region_source='REMIND', recalculate=True)
    print(regions)