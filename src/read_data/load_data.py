import os
import pandas as pd
from src.tools.config import cfg
from src.tools.tools import read_processed_data, group_country_data_to_regions, transform_per_capita


# -- MAIN DATA LOADING FUNCTIONS BY DATA TYPE --


def load_stocks(stock_source=None, country_specific=False, per_capita=True):
    if stock_source is None:
        stock_source = cfg.steel_data_source
    if stock_source == 'Mueller':
        return _load_mueller_stocks(country_specific=country_specific, per_capita=per_capita)
    elif stock_source == 'IEDatabase':
        return _load_pauliuk_stocks(country_specific=country_specific, per_capita=per_capita)
    else:
        raise ValueError(f'{stock_source} is not a valid stock data source.')


def load_pop(pop_source=None, country_specific=False):
    if pop_source is None:
        pop_source = cfg.pop_data_source
    if pop_source == 'UN':
        return _load_un_pop(country_specific=country_specific)
    elif pop_source == 'KC-Lutz':
        return _load_kc_lutz_pop(country_specific=country_specific)
    else:
        raise ValueError(f'{pop_source} is not a valid population data source.')


def load_gdp(gdp_source=None, country_specific=False, per_capita=True):
    if gdp_source is None:
        gdp_source = cfg.gdp_data_source
    if gdp_source == 'IMF':
        return _load_imf_gdp(country_specific=country_specific, per_capita=per_capita)
    elif gdp_source == 'Koch-Leimbach':
        return _load_koch_leimbach_gdp(country_specific=country_specific, per_capita=per_capita)
    else:
        raise ValueError(f'{gdp_source} is not a valid GDP data source.')


def load_regions(region_source=None):
    if region_source is None:
        region_source = cfg.region_data_source
    if region_source == 'REMIND':
        return _load_remind_regions()
    elif region_source == 'Pauliuk':
        return _load_pauliuk_regions()
    elif region_source == 'REMIND_EU':
        return _load_remind_eu_regions()
    else:
        raise ValueError(f'{region_source} is not a valid region data source.')


def load_steel_prices(steel_price_source=None):
    if steel_price_source is None:
        steel_price_source = cfg.steel_price_data_source
    if steel_price_source == 'USGS':
        return _load_usgs_steel_prices()
    else:
        raise ValueError(f'{steel_price_source} is not a valid steel price data source.')


def load_scrap_prices(scrap_price_source=None):
    if scrap_price_source is None:
        scrap_price_source = cfg.scrap_price_data_source
    if scrap_price_source == 'USGS':
        return _load_usgs_scrap_prices()
    else:
        raise ValueError(f'{scrap_price_source} is not a valid scrap price data source.')


def load_trade_factor(trade_source=None, country_specific=False):
    if trade_source is None:
        trade_source = cfg.trade_data_source
    if trade_source == 'WorldSteel':
        df_trade_factor = _load_worldsteel_trade_factor(country_specific=country_specific)
        return df_trade_factor
    else:
        raise ValueError(f'{trade_source} is not a valid trade data source.')


def load_scrap_trade_factor(trade_source=None, country_specific=False):
    if trade_source is None:
        trade_source = cfg.trade_data_source
    if trade_source == 'WorldSteel':
        df_scrap_trade_factor = _load_worldsteel_scrap_trade_factor(country_specific=country_specific)
        return df_scrap_trade_factor
    else:
        raise ValueError(f'{trade_source} is not a valid trade data source.')


def load_lifetimes(lifetime_source=None):
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


# -- DATA LOADER --


def _data_loader(file_base_name, recalculate_function, country_specific,
                 data_stored_per_capita, return_per_capita, data_split_into_categories=False):
    file_name_end = '_countries' if country_specific else f'_{cfg.region_data_source}_regions'
    if country_specific is None:
        file_name_end = ""
    file_name = f"{file_base_name}{file_name_end}.csv"
    file_path = os.path.join(cfg.data_path, 'processed', file_name)
    if os.path.exists(file_path) and not cfg.recalculate_data:
        df = read_processed_data(file_path)
        df = df.reset_index()
        indices = list(df.select_dtypes(include='object'))  # select all columns that aren't numbers
        df = df.set_index(indices)
    else:  # recalculate and store
        if country_specific or country_specific is None:
            df = recalculate_function()
        else:  # region specific
            df = _data_loader(file_base_name, recalculate_function, country_specific=True,
                              data_stored_per_capita=data_stored_per_capita,
                              return_per_capita=return_per_capita,
                              data_split_into_categories=data_split_into_categories)
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


def _load_un_pop(country_specific):
    from src.read_data.read_UN_population import get_pop_countries
    df = _data_loader(file_base_name='UN_pop',
                      recalculate_function=get_pop_countries,
                      country_specific=country_specific,
                      data_stored_per_capita=False,
                      return_per_capita=False)
    return df


def _load_kc_lutz_pop(country_specific):
    from src.read_data.read_kc_lutz_population import get_kc_lutz_pop_countries
    df = _data_loader(file_base_name='KC_Lutz_pop',
                      recalculate_function=get_kc_lutz_pop_countries,
                      country_specific=country_specific,
                      data_stored_per_capita=False,
                      return_per_capita=False,
                      data_split_into_categories=True)

    return df


def _load_mueller_stocks(country_specific, per_capita):
    from src.read_data.read_mueller_stocks import get_mueller_country_stocks
    df = _data_loader(file_base_name='mueller_stocks',
                      recalculate_function=get_mueller_country_stocks,
                      country_specific=country_specific,
                      data_stored_per_capita=True,
                      return_per_capita=per_capita,
                      data_split_into_categories=True)
    return df


def _load_pauliuk_stocks(country_specific, per_capita):
    from src.read_data.read_pauliuk_stocks import get_pauliuk_country_stocks
    df = _data_loader(file_base_name='pauliuk_stocks',
                      recalculate_function=get_pauliuk_country_stocks,
                      country_specific=country_specific,
                      data_stored_per_capita=True,
                      return_per_capita=per_capita,
                      data_split_into_categories=True)
    return df


def _load_imf_gdp(country_specific, per_capita):
    from src.read_data.read_IMF_gdp import get_imf_gdp_countries
    df = _data_loader(file_base_name='imf_gdp',
                      recalculate_function=get_imf_gdp_countries,
                      country_specific=country_specific,
                      data_stored_per_capita=True,
                      return_per_capita=per_capita)
    return df


def _load_koch_leimbach_gdp(country_specific, per_capita):
    from src.read_data.read_koch_leimbach_gdp import get_koch_leimbach_gdp_countries
    df = _data_loader(file_base_name='koch_leimbach_gdp',
                      recalculate_function=get_koch_leimbach_gdp_countries,
                      country_specific=country_specific,
                      data_stored_per_capita=False,
                      return_per_capita=per_capita,
                      data_split_into_categories=True)
    return df


def _load_usgs_steel_prices():
    from src.read_data.read_USGS_prices import get_usgs_steel_prices
    df = _data_loader(file_base_name='usgs_steel_prices',
                      recalculate_function=get_usgs_steel_prices,
                      country_specific=None,
                      data_stored_per_capita=False,
                      return_per_capita=False)

    return df


def _load_usgs_scrap_prices():
    from src.read_data.read_USGS_prices import get_usgs_scrap_prices
    df = _data_loader(file_base_name='usgs_scrap_prices',
                      recalculate_function=get_usgs_scrap_prices,
                      country_specific=None,
                      data_stored_per_capita=False,
                      return_per_capita=False)

    return df


def _load_worldsteel_trade_factor(country_specific):
    from src.read_data.read_WorldSteel_trade import get_worldsteel_trade_factor
    df = _data_loader(file_base_name='worldsteel_trade_factor',
                      recalculate_function=get_worldsteel_trade_factor,
                      country_specific=country_specific,
                      data_stored_per_capita=True,
                      return_per_capita=True)

    return df


def _load_worldsteel_scrap_trade_factor(country_specific):
    from src.read_data.read_WorldSteel_trade import get_worldsteel_scrap_trade_factor
    df = _data_loader(file_base_name='worldsteel_scrap_trade_factor ',
                      recalculate_function=get_worldsteel_scrap_trade_factor,
                      country_specific=country_specific,
                      data_stored_per_capita=True,
                      return_per_capita=True)

    return df


def _load_pauliuk_regions():
    from src.read_data.read_pauliuk_regions import get_pauliuk_regions
    return get_pauliuk_regions()


def _load_remind_regions():
    from src.read_data.read_REMIND_regions import get_REMIND_regions
    return get_REMIND_regions()


def _load_remind_eu_regions():
    from src.read_data.read_REMIND_regions import get_REMIND_EU_regions
    return get_REMIND_EU_regions()
