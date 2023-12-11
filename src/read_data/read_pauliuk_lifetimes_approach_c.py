import os
import pandas as pd
from src.tools.config import cfg
from src.tools.country_mapping import map_iso3_codes, split_joint_country_data_for_parameters


def get_pauliuk_lifetimes_approach_c():
    df = _read_pauliuk_lifetimes_approach_c_original()
    df = _clean_pauliuk_lifetimes_approach_c(df)
    return df


def _clean_pauliuk_lifetimes_approach_c(df):
    df = df.rename(columns={
        'Country name': 'country_name',
        'Transportation.1': 'Transportation',
        'Machinery.1': 'Machinery',
        'Construction.1': 'Construction',
        'Products.1': 'Products'
    })

    df = map_iso3_codes(df)
    df = split_joint_country_data_for_parameters(df)
    return df


def _read_pauliuk_lifetimes_approach_c_original():
    splits_path = os.path.join(cfg.data_path, 'original', 'Pauliuk', 'Supplementary_Table_23.xlsx')
    df_lifetimes = pd.read_excel(splits_path,
                                 engine='openpyxl',
                                 sheet_name='Supplementray_Table_23',
                                 skiprows=3,
                                 usecols='A,F:I')

    return df_lifetimes


def _test():
    df = get_pauliuk_lifetimes_approach_c()
    print(df)


if __name__ == '__main__':
    _test()
