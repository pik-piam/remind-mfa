from os.path import join
import pandas as pd
from src.tools.config import cfg


def load_excel_dicts():
    df = _load_excel()
    dicts = _translate_df_dicts(df)
    _adapt_dicts_config_format(dicts)
    return dicts


def _adapt_dicts_config_format(dicts):
    in_use_categories = [x.lower() for x in cfg.in_use_categories]
    dict_keys_to_delete = ['steel_price_change_ssp1', 'steel_price_change_ssp2', 'steel_price_change_ssp3',
                           'steel_price_change_ssp4', 'steel_price_change_ssp5', 'do_change_steel_price_by_scenario',
                           'steel_price_change_all_scenarios', 'inflow_change_ssp1', 'inflow_change_ssp2',
                           'inflow_change_ssp3', 'inflow_change_ssp4', 'inflow_change_ssp5',
                           'do_change_inflow_by_scenario', 'inflow_change_all_scenarios', 'inflow_change_transport',
                           'inflow_change_machinery', 'inflow_change_construction', 'inflow_change_products',
                           'do_change_inflow_by_category', 'inflow_change_all_categories', 'reuse_change_ssp1',
                           'reuse_change_ssp2', 'reuse_change_ssp3', 'reuse_change_ssp4',
                           'reuse_change_ssp5', 'do_change_reuse_by_scenario', 'reuse_change_all_scenarios',
                           'reuse_change_transport', 'reuse_change_machinery', 'reuse_change_construction',
                           'reuse_change_products', 'do_change_reuse_by_category', 'reuse_change_all_categories']
    for dict in dicts:
        dict['steel_price_change_by_scenario'] = [dict[f'steel_price_change_ssp{i}'] for i in range(1, 6)] \
            if dict['do_change_steel_price_by_scenario'] else dict['steel_price_change_all_scenarios']

        dict['inflow_change_by_scenario'] = [dict[f'inflow_change_ssp{i}'] for i in range(1, 6)] \
            if dict['do_change_inflow_by_scenario'] else dict['inflow_change_all_scenarios']

        dict['inflow_change_by_category'] = [dict[f'inflow_change_{cat}'] for cat in in_use_categories] \
            if dict['do_change_inflow_by_category'] else dict['inflow_change_all_categories']

        dict['reuse_change_by_scenario'] = [dict[f'reuse_change_ssp{i}'] for i in range(1, 6)] \
            if dict['do_change_reuse_by_scenario'] else dict['reuse_change_all_scenarios']

        dict['reuse_change_by_category'] = [dict[f'reuse_change_{cat}'] for cat in in_use_categories] \
            if dict['do_change_reuse_by_category'] else dict['reuse_change_all_categories']

        for key in dict_keys_to_delete:
            del dict[key]


def _translate_df_dicts(df):
    dicts = [df[column].to_dict() for column in df.columns]
    return dicts


def _load_excel():
    df = _load_excel_original()
    df = _clean_excel(df)
    return df


def _clean_excel(df):
    default = df['Default']
    for column in df.columns:
        df[column] = df[column].fillna(default)

    df = df.drop(df.columns[:2], axis=1)
    df = df.drop(columns='Default')
    df = df.set_index('Python Name')

    df = df.dropna(axis='index', how='all')

    return df


def _load_excel_original():
    excel_path = join('simulation', 'interface', 'excel', 'simson_simulation_interface.xlsx')
    df = pd.read_excel(excel_path,
                       skiprows=2)
    return df


def _test():
    dicts = load_excel_dicts()
    for dict in dicts:
        print(dict['simulation_name'])


if __name__ == '__main__':
    _test()
