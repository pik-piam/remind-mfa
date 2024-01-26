import numpy as np
from src.tools.config import cfg
from src.tools.tools import get_np_from_df, group_country_data_to_regions, transform_per_capita_df
from src.read_data.read_UN_population import get_pop_countries
from src.read_data.read_geyer import get_geyer_production, get_geyer_lifetimes, get_geyer_shares
from src.tools.tools import get_np_from_df, group_country_data_to_regions, load_or_recalculate
from src.read_data.read_REMIND_regions import get_remind_regions, get_remind_eu_regions
from src.read_data.read_UN_population import get_pop_countries
from src.read_data.read_remind_gdp import get_remind_gdp
from src.read_data.read_dummy import get_dummy_mechanical_recycling_rates, get_dummy_mechanical_recycling_yields


def load_data(type, source = 'cfg', regions = 'cfg', percapita = False, format = 'np'):
    if source == 'cfg':
        source = cfg.data_sources[type]
    if regions == 'cfg':
        regions = cfg.data_sources['regions']

    read_function, source_regions, source_percapita = get_reader_function(type, source)

    read_function.__name__ = f"load_{type}"
    data = load_or_recalculate(read_function)()

    if regions is not None and source_regions is not None and regions != source_regions:
        data = group_country_data_to_regions(data, source_percapita)
    if percapita != source_percapita:
        data = transform_per_capita_df(data, source_percapita)
    if format == 'np':
        data = get_np_from_df(data)
    return data


def get_reader_function(type, source):
    # defaults
    raw_percapita = False
    raw_regions = 'countries'
    if type == 'gdp':
        if source == 'remind':
            read_function = get_remind_gdp
            raw_percapita = False
    elif type == 'production':
        if source == 'geyer':
            read_function = get_geyer_production
            raw_regions = 'World'
    elif type == 'lifetime':
        if source == 'geyer':
            read_function = get_geyer_lifetimes
            raw_regions = None
    elif type == 'good_and_element_shares':
        if source == 'geyer':
            read_function = get_geyer_shares
            raw_regions = None
    elif type == 'mechanical_recycling_rates':
        if source == 'dummy':
            read_function = get_dummy_mechanical_recycling_rates
            raw_regions = None
    elif type == 'mechanical_recycling_yields':
        if source == 'dummy':
            read_function = get_dummy_mechanical_recycling_yields
            raw_regions = None
    else:
        raise ValueError(f'No reader function known for type {type} and source {source}.')
    return read_function, raw_regions, raw_percapita


def setup():
    cfg.data = load_setup()


@load_or_recalculate
def load_setup():
    cfg.data.df_region_mapping = load_region_mapping()
    cfg.data.region_list = np.sort(cfg.data.df_region_mapping['Region'].unique())

    cfg.data.df_pop_countries = load_pop()
    cfg.data.df_pop = group_country_data_to_regions(cfg.data.df_pop_countries)

    cfg.data.np_pop = get_np_from_df(cfg.data.df_pop)

    return cfg.data # decorator expects return argument


def load_region_mapping(source = 'cfg'):
    if source == 'cfg':
        source = cfg.data_sources['regions']
    if source == 'REMIND':
        regions = get_remind_regions()
    elif source == 'REMIND_EU':
        regions = get_remind_eu_regions()
    elif source == 'World':
        regions = get_remind_regions()
        regions['Region'] = 'World'
    return regions


def load_pop(source = 'cfg'):
    if source == 'cfg':
        source = cfg.data_sources['pop']
    if source == 'UN':
        pop = get_pop_countries()
    return pop


if __name__ == '__main__':
    print()
