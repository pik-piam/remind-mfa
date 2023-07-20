import os
from src.tools.config import cfg
from src.tools.tools import read_processed_data, group_country_data_to_regions, transform_per_capita
from src.read_data.read_mueller_stocks import get_mueller_country_stocks
from src.read_data.read_pauliuk_stocks import get_pauliuk_country_stocks
from src.read_data.read_UN_population import load_un_pop
from src.read_data.read_IMF_gdp import get_imf_gdp_countries
from src.read_data.read_REMIND_regions import get_REMIND_regions
from src.read_data.read_WorldSteel_trade import load_world_steel_trade
from src.read_data.read_USGS_prices import load_usgs_prices


# -- MAIN DATA LOADING FUNCTIONS BY DATA TYPE --


def load_stocks(stock_source=None, country_specific=False, per_capita=True):
    if stock_source is None:
        cfg.customize()
        stock_source = cfg.steel_data_source
    if stock_source == 'Mueller':
        return _load_mueller_stocks(country_specific=country_specific, per_capita=per_capita)
    elif stock_source == 'IEDatabase':
        return _load_pauliuk_stocks(country_specific=country_specific, per_capita=per_capita)
    else:
        raise ValueError(f'{stock_source} is not a valid stock data source.')


def load_pop(pop_source=None, country_specific=False):
    if pop_source is None:
        cfg.customize()
        pop_source = cfg.pop_data_source
    if pop_source == 'UN':
        return load_un_pop(country_specific=country_specific)
    else:
        raise ValueError(f'{pop_source} is not a valid population data source.')


def load_gdp(gdp_source=None, country_specific=False, per_capita=True):
    if gdp_source is None:
        cfg.customize()
        gdp_source = cfg.pop_data_source
    if gdp_source == 'IMF':
        return _load_imf_gdp(country_specific=country_specific, per_capita=per_capita)
    else:
        raise ValueError(f'{gdp_source} is not a valid GDP data source.')


def load_regions(region_source=None):
    if region_source is None:
        cfg.customize()
        region_source = cfg.region_data_source
    if region_source == 'REMIND':
        return get_REMIND_regions()
    else:
        raise ValueError(f'{region_source} is not a valid GDP data source.')


def load_prices(price_source=None):
    if price_source is None:
        cfg.customize()
        price_source = cfg.price_data_source
    if price_source == 'UN':
        return load_usgs_prices()
    else:
        raise ValueError(f'{price_source} is not a valid price data source.')


def load_trade(trade_source=None):
    if trade_source is None:
        cfg.customize()
        trade_source = cfg.trade_data_source
    if trade_source == 'UN':
        return load_world_steel_trade()
    else:
        raise ValueError(f'{trade_source} is not a valid trade data source.')


# -- DATA LOADER --


def _data_loader(file_base_name, recalculate_function, country_specific, is_per_capita, group_by_subcategories=False):
    file_name_end = 'countries' if country_specific else f'{cfg.region_data_source}_regions'
    file_name = f"{file_base_name}_{file_name_end}.csv"
    file_path = os.path.join(cfg.data_path, 'processed', file_name)
    if os.path.exists(file_path) and not cfg.recalculate_data:
        df = read_processed_data(file_path)
        df = df.reset_index()
    else:  # recalculate and store
        if country_specific:
            df = recalculate_function()
        else: # region specific
            df = _data_loader(file_base_name, recalculate_function, country_specific=True, is_per_capita=is_per_capita,
                              group_by_subcategories=group_by_subcategories)
            df = group_country_data_to_regions(df, is_per_capita=is_per_capita,
                                group_by_subcategories=group_by_subcategories)
        df.to_csv(file_path)

    indices = list(df.select_dtypes(include='object')) # select all columns that aren't numbers
    df = df.set_index(indices)

    if not is_per_capita:
        df = transform_per_capita(df, total_from_per_capita=True, country_specific=country_specific)

    return df


# -- SPECIFIC DATA LOADING FUNCTIONS BY DATA TYPE AND SOURCE --


def _load_mueller_stocks(country_specific, is_per_capita):
    df = _data_loader(file_base_name='mueller_stocks',
                      recalculate_function=get_mueller_country_stocks,
                      country_specific=country_specific,
                      is_per_capita=is_per_capita,
                      group_by_subcategories=True)
    return df


def _load_pauliuk_stocks(country_specific, is_per_capita):
    df = _data_loader(file_base_name='pauliuk_stocks',
                      recalculate_function=get_pauliuk_country_stocks,
                      country_specific=country_specific,
                      is_per_capita=is_per_capita,
                      group_by_subcategories=True)
    return df


def _load_imf_gdp(country_specific, is_per_capita):
    df = _data_loader(file_base_name='imf_gdp',
                      recalculate_function=get_imf_gdp_countries,
                      country_specific=country_specific,
                      is_per_capita=is_per_capita,)
    return df



df = _load_pauliuk_stocks(country_specific=True, is_per_capita=True)
print(df)