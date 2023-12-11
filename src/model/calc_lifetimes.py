import os
import pandas as pd
import numpy as np
from src.read_data.read_pauliuk_lifetimes_approach_c import get_pauliuk_lifetimes_approach_c
from src.read_data.load_data import load_stocks, load_regions, load_region_names_list
from src.tools.config import cfg


def load_np_lifetimes(lifetime_source=cfg.lifetime_data_source, country_specific=False):
    if lifetime_source == 'Pauliuk_c':
        df = get_pauliuk_lifetimes_approach_c()
        return df
    elif lifetime_source == 'Wittig':
        mean, sd = get_wittig_lifetimes(country_specific)
    elif lifetime_source == 'Pauliuk':
        mean, sd = get_pauliuk_normal_lifetimes_country_level(country_specific)
    return mean, sd
    cpau = get_lifetimes('Pauliuk_c')
    npau = get_lifetimes('Pauliuk')
    wittig = get_lifetimes('Wittig')
    #print(cpau)
    print(npau)
    #print(wittig)



def get_lifetimes(lifetime_source):
    if lifetime_source == 'Pauliuk_c':
        df = get_pauliuk_lifetimes_approach_c()
        return df
    elif lifetime_source == 'Wittig':
        lifetime_path = os.path.join(cfg.data_path, 'original', 'Wittig', 'Wittig_lifetimes.csv')
    elif lifetime_source == 'Pauliuk':
        return get_pauliuk_normal_lifetimes_country_level()
    df = pd.read_csv(lifetime_path)

    return df


def get_wittig_lifetimes(country_specific):
    areas = get_stock_data_countries() if country_specific else load_region_names_list()
    df = _read_wittig_lifetimes()
    df = df.set_index('category')
    df = df.transpose()

    lifetimes = df.to_numpy()
    lifetimes = np.repeat(lifetimes[:,:,np.newaxis], len(areas), axis=2)
    mean = lifetimes[0]
    sd = lifetimes[1]

    return mean, sd


def get_lifetime_np_from_df_mean(df_mean):
    mean = df_mean.to_numpy()
    sd = cfg.default_lifetime_sd_pct_of_mean * mean
    return mean, sd



def get_pauliuk_normal_lifetimes_country_level(country_specific):
    df_mean = _read_pauliuk_lifetimes()
    if not country_specific and cfg.region_data_source=='Pauliuk':
        df_mean = df_mean.set_index('region')
        return get_lifetime_np_from_df_mean(df_mean)
    df_region = load_regions(region_source='Pauliuk')
    df_mean = pd.merge(df_region.reset_index(), df_mean, on='region')
    df_mean = df_mean.set_index('country').drop(columns='region')
    df_average = pd.DataFrame(df_mean.mean()).transpose()


    missing_countries = _get_missing_countries_for_stock_data(df_mean)
    for country in missing_countries:
        df_mean.loc[country] = df_average.loc[0]
    df_mean = df_mean.sort_index()

    stock_index = get_stock_data_countries()
    df_mean = df_mean[df_mean.index.isin(stock_index)]
    if not (df_mean.index==stock_index).all():  # indexes are not completely aligned, there is some mistakt
        raise RuntimeError('Mistake when aligning pauliuk lifetimes to stock index. Needs to be equal before '
                           'transferring to numpy.')
    df_sd = df_mean * 0.3
    print(df_sd)



    return df_mean, df_sd

def _get_missing_countries_for_stock_data(df):
    stock_index = get_stock_data_countries()
    missing_countries = stock_index.difference(df.index)
    return missing_countries


def _read_pauliuk_lifetimes():
    pauliuk_normal_path = os.path.join(cfg.data_path, 'original', 'Pauliuk', 'Pauliuk_lifetimes.csv')
    df = pd.read_csv(pauliuk_normal_path)
    return df


def _read_wittig_lifetimes():
    wittig_path = os.path.join(cfg.data_path, 'original', 'Wittig', 'Wittig_lifetimes.csv')
    df = pd.read_csv(wittig_path)
    return df


def get_stock_data_countries():
    df_stocks = load_stocks(country_specific=True)
    return df_stocks.index.get_level_values(0).unique()


def _test():
    mean, sd = load_np_lifetimes(lifetime_source='Pauliuk', country_specific=False)
    print(mean)
    print(sd)
    print(mean.shape)
    print(sd.shape)



if __name__=='__main__':
    _test()