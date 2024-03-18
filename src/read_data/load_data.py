import numpy as np
from src.tools.config import cfg
from src.tools.tools import get_np_from_df, group_country_data_to_regions, transform_per_capita_df
from src.read_data.read_geyer import get_geyer_production, get_geyer_lifetimes, get_geyer_shares
from src.tools.tools import get_np_from_df, group_country_data_to_regions, load_or_recalculate
from src.read_data.read_remind import get_remind_regions, get_remind_eu_regions
from src.read_data.read_remind import get_remind_gdp, get_remind_pop
from src.read_data.read_excel import *


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
    elif type == 'good_and_material_shares':
        if source == 'geyer':
            read_function = get_geyer_shares
            raw_regions = None
    elif type == 'daccu_production_rate':
        if source == 'excel':
            read_function = get_excel_daccu_production_rate
            raw_regions = None
    elif type == 'bio_production_rate':
        if source == 'excel':
            read_function = get_excel_bio_production_rate
            raw_regions = None
    elif type == 'uncontrolled_losses_rate':
        if source == 'excel':
            read_function = get_excel_uncontrolled_losses_rate
            raw_regions = None
    elif type == 'incineration_rate':
        if source == 'excel':
            read_function = get_excel_incineration_rate
            raw_regions = None
    elif type == 'mechanical_recycling_rate':
        if source == 'excel':
            read_function = get_excel_mechanical_recycling_rate
            raw_regions = None
    elif type == 'chemical_recycling_rate':
        if source == 'excel':
            read_function = get_excel_chemical_recycling_rate
            raw_regions = None
    elif type == 'solvent_recycling_rate':
        if source == 'excel':
            read_function = get_excel_solvent_recycling_rate
            raw_regions = None
    elif type == 'mechanical_recycling_yield':
        if source == 'excel':
            read_function = get_excel_mechanical_recycling_yield
            raw_regions = None
    elif type == 'reclmech_loss_uncontrolled_rate':
        if source == 'excel':
            read_function = get_excel_reclmech_loss_uncontrolled_rate
            raw_regions = None
    elif type == 'emission_capture_rate':
        if source == 'excel':
            read_function = get_excel_emission_capture_rate
            raw_regions = None
    elif type == 'carbon_content_materials':
        if source == 'excel':
            read_function = get_excel_carbon_content_materials
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
    # if source == 'UN':
    #     pop = get_pop_countries()
    if source == 'remind':
        pop = get_remind_pop()
    return pop


if __name__ == '__main__':
    print()
