from src.read_data.read_mueller_stocks import load_mueller_stocks
from src.read_data.read_pauliuk_stocks import load_pauliuk_stocks
from src.tools.tools import get_steel_category_total
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REGION_COLORS = {'LAM': 'green',
                 'OAS': 'red',
                 'SSA': 'yellow',
                 'EUR': 'blue',
                 'NEU': 'black',
                 'MEA': 'brown',
                 'REF': 'orange',
                 'CAZ': 'purple',
                 'CHA': 'gray',
                 'IND': 'lightgreen',
                 'JPN': 'lightblue',
                 'USA': 'cyan',
                 'World': 'blue'}

def make_stocks_fig(df: pd.DataFrame):
    plt.figure()
    for index, row in df.iterrows():
        region = index
        data = np.array(row[50:109])
        plt.scatter(range(1950,2009), data, color = REGION_COLORS[region], label=region)
    plt.xlabel('Time in years')
    plt.ylabel("Steel stock pC (t)")
    plt.title('Steel stock pc over time Pauliuk data')
    plt.legend(loc='upper left')
    plt.show()


def visualize_mueller_stocks_regions():
    df_pauliuk = load_pauliuk_stocks(country_specific=True, per_capita=True)
    df_pauliuk = get_steel_category_total(df_pauliuk)
    make_stocks_fig(df_pauliuk)


def main():
    visualize_mueller_stocks_regions()


if __name__=='__main__':
    main()