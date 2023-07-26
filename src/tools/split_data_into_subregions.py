import pandas as pd
from src.read_data.load_data import load_gdp

def split_areas_by_gdp(df : pd.DataFrame, areas : list, df_iso3_map : pd.DataFrame):
    df_areas = _get_df_areas_to_normalize(df_iso3_map, areas)
    df_gdp = load_gdp(country_specific=True, is_per_capita=False)
    df_area_gdp_share = _get_gdp_shares_in_areas(df_gdp, df_areas)


def _get_df_areas_to_normalize(df_iso3_map: pd.DataFrame, areas : list):
    df_areas = pd.DataFrame.from_dict({'area': areas})
    print(df_areas)
    df_areas = pd.merge(df_areas, df_iso3_map, left_on='area', right_on='country_name')
    print(df_areas)
    df_areas = df_areas.drop(columns=['country_name'])
    df_areas = df_areas.set_index('country')

    return df_areas

def _get_gdp_shares_in_areas(df_gdp: pd.DataFrame, df_areas : pd.DataFrame):
    df_gdp = pd.merge(df_areas, df_gdp, on='country')
    gk_gdp = df_gdp.groupby('area')
    df_gdp_sums = gk_gdp.transform('sum', numeric_only=True)
    df_gdp = df_gdp / df_gdp_sums
    df_area_gdp_share = df_gdp
    df_area_gdp_share = df_area_gdp_share.drop(columns=['area'])

    return df_area_gdp_share