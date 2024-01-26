import os
import numpy as np
import pandas as pd
import pickle
import functools
from copy import copy
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
        #TODO: real arbitrary mapping
        data = group_country_data_to_regions(data, source_percapita)
    if percapita != source_percapita:
        data = transform_per_capita_df(data, source_percapita)
    if format == 'np':
        data = get_np_from_df(data)
    return data


    # # abuse decorator
    # def loader():
    #     data = read_function()
    #     if regions is not None and source_regions is not None and regions != source_regions:
    #         #TODO: real arbitrary mapping
    #         data = group_country_data_to_regions(data, source_percapita)
    #     if percapita != source_percapita:
    #         data = transform_per_capita_df(data, source_percapita)
    #     if format == 'np':
    #         data = get_np_from_df(data)
    #     return data

    # loader.__name__ = f"load_{type}___{source}_{regions}_{'pc' if percapita else 'abs'}_{format}"
    # data = load_or_recalculate(loader)()




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

    # cfg.data.df_gdp_countries = load_data('gdp', regions='countries')
    # cfg.data.df_gdp = load_data('gdp')
    # sdc_self.df_gdppc = None

    cfg.data.np_pop = get_np_from_df(cfg.data.df_pop)
    # cfg.data.np_gdp = get_np_from_df(cfg.data.df_gdp)

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
    # elif source == 'KC-Lutz':
    #     pop = get_kc_lutz_pop_countries()
    return pop


# def _data_loader(file_base_name, recalculate_function, country_specific,
#                  data_stored_per_capita, return_per_capita, data_split_into_categories=False,
#                  recalculate=False, is_yearly_data=True):
#     file_name_end = '_countries' if country_specific else f'_{cfg.region_data_source}_regions'
#     if country_specific is None:
#         file_name_end = ""
#     file_name = f"{file_base_name}{file_name_end}.csv"
#     file_path = os.path.join(cfg.data_path, 'processed', file_name)
#     if os.path.exists(file_path) and not recalculate:
#         df = pd.read_csv(file_path)
#         df = df.reset_index()
#         indices = list(df.select_dtypes(include='object'))  # select all columns that aren't numbers
#         df = df.set_index(indices)
#     else:  # recalculate and store
#         if country_specific or country_specific is None:
#             df = recalculate_function()
#         else:  # region specific
#             df = _data_loader(file_base_name, recalculate_function, country_specific=True,
#                               data_stored_per_capita=data_stored_per_capita,
#                               return_per_capita=data_stored_per_capita,
#                               data_split_into_categories=data_split_into_categories,
#                               recalculate=recalculate,
#                               is_yearly_data=is_yearly_data)
#             df = group_country_data_to_regions(df, is_per_capita=data_stored_per_capita,
#                                                data_split_into_categories=data_split_into_categories)
#         df.to_csv(file_path)

#     if country_specific is not None:
#         if data_stored_per_capita and not return_per_capita:
#             df = transform_per_capita(df, total_from_per_capita=True, country_specific=country_specific)
#         if not data_stored_per_capita and return_per_capita:
#             df = transform_per_capita(df, total_from_per_capita=False, country_specific=country_specific)

#     df = df.sort_index()

#     return df



# --------------------------------------------------
# RELOAD DATA IMPLEMENTATION
# --------------------------------------------------

# Lastenheft
# regions:
#   cases:
#   - data has no region dimension -> can stay without
#   - data is country-specific and should be left country-specific
#   - data is in some non-country regional resolution
#   region default should be cfg.regions?
#   deduct regions from "Region" column?
#   does not "Region" column mean world?
#   enable splitting non-region (world) data to regions? (should not be default behaviour)
# percapita
#   may not be needed at all, apart from gdp
#   after to_np?
# other dimensions
#   treat like regions? (transform by mapping)
# to_numpy
#   should be part of this
# reload
#   yes, but maybe only raw

# def id_str(steps):
#     return '_'.join([s.step_name + '-' + s.value_str for s in steps])


# def fpath(steps):
#     return id_str(steps) + '.csv'


# def redo_steps(done_steps, steps_to_do, *args, **kwargs):
#     if not done_steps:
#         # first step is to read raw data
#         first_step = steps_to_do.pop(0)
#         obj = first_step.func()
#     else:
#         # load from last available processing step
#         obj = pickle.load(open(fpath(done_steps), 'r'))

#     # execute remaining steps
#     for step in steps_to_do:
#         obj = step.func(obj)
#         done_steps += [step]
#         pickle.dump(obj, open(fpath(done_steps), "w"))
#     return obj


# class LoadingStep():

#     def __init__(self, step_name, func, value_str, *args, **kwargs):
#         self.step_name = step_name
#         self.value_str = value_str
#         self.func = func
#         self.args = args
#         self.kwargs = kwargs


# def get_steps_left_to_do(steps: list):
#     """
#     check which loading steps from above have to be done and which can be skipped as data can be re-loaded from previous runs
#     """
#     done_steps = copy(steps)
#     steps_to_do = []
#     while not os.path.exists(fpath(done_steps)):
#         steps_to_do.insert(0, done_steps.pop(-1))
#     return done_steps, steps_to_do

# def group_regions()
#     regions = cfg.regions
#     bla

# def load_pop()
#     bla
#     group_regions()

# def load_gdp()
#     regions = cfg.regions
#     pop = cfg.pop
#     bla

# def load_data(type, source=None, regions=None, percapita = False, objtype='np'):
#     """
#     load, group by country, transform to numpy
#     """
#     if source is None:
#         source = cfg.data_source[type]
#     if regions is None:
#         regions = cfg.region_data_source

#     try:
#         src_cfg = source_config_dict[type][source]
#     except KeyError:
#         raise Exception(f'{source} is not a valid {type} data source.')

#     steps = [LoadingStep(type,
#                          source,
#                          src_cfg.read_func)]
#     if src_cfg.regions != regions:
#         steps += [LoadingStep('regi',
#                               regions,
#                               group_country_data_to_regions,
#                               is_per_capita=src_cfg.percapita)]
#     if src_cfg.percapita != percapita:
#         steps += [LoadingStep('percapita',
#                               str(percapita),
#                               transform_per_capita_df,
#                               total_from_per_capita=src_cfg.percapita)]
#     if src_cfg.objtype != objtype:
#         steps += [LoadingStep('objtype',
#                               objtype,
#                               get_np_from_df)]

#     # check which loading steps from above have to be done and which can be skipped as data can be re-loaded from previous runs
#     if not cfg.recalculate_data:
#         done_steps = []
#         get_steps_left_to_do = steps
#     else:
#         done_steps, get_steps_left_to_do = get_steps_left_to_do(steps)

#     obj = redo_steps(done_steps, get_steps_left_to_do)
#     return obj



if __name__ == '__main__':
    # regions = load_regions(region_source='World', recalculate=True)
    # pop = load_pop(pop_source=None, country_specific=False, recalculate=True)
    # lifetime = load_lifetimes(recalculate=True)
    production = load_historic_production(recalculate=True)
    print()