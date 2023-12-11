from src.read_data.read_WorldSteel_digitalized import read_worldsteel_yearbook_data
from src.tools.country_mapping import map_split_join_iso3


def get_worldsteel_net_indirect_trade_category_quantities_2013():
    df = _read_worldsteel_indirect_trade_categories()
    original_columns = df.columns
    df['Construction'] = 0
    df['Machinery'] = df['Mechanical Machinery']
    df['Products'] = df[['Electrical Equipment', 'Metal products', 'Domestic\nappliances']].sum(axis=1)
    df['Transport'] = df['Automotive'] + df['Other transport']
    df = df.drop(columns=original_columns)
    return df


def _read_worldsteel_indirect_trade_categories():
    filename = 'WSA_indirect_trade_categories_2013.xlsx'
    df = read_worldsteel_yearbook_data(filename)
    df = map_split_join_iso3(df)
    return df


def _test():
    df = get_worldsteel_net_indirect_trade_category_quantities_2013()
    print(df)


if __name__ == '__main__':
    _test()
