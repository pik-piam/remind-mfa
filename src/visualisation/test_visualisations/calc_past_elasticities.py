import numpy as np
from src.model.simson_base_model import load_simson_base_model
from src.read_data.load_data import load_steel_prices, load_stocks
import matplotlib.pyplot as plt

def _test():
    model = load_simson_base_model(country_specific=False)
    inflow = model.FlowDict['F_2_4'].Values[50:109,0,:,:,0]
    inflow = np.sum(inflow,axis=2)
    prices = load_steel_prices().to_numpy()[0,50:109]
    ped_years = 5
    q2 = inflow[ped_years:].transpose()
    q1 = inflow[:-ped_years].transpose()
    p2 = prices[ped_years:]
    p1 = prices[:-ped_years]

    areas = list(load_stocks(country_specific=False).index.get_level_values(0).unique())

    e = ((q2-q1)/((q2+q1)/2))/((p2-p1)/((p2+p1)/2))
    e[np.isnan(e)]=0
    average_region = np.average(e, axis=1)
    average_year = np.average(e, axis=0)
    average = np.average(e)

    print(f'Average is: {average}')
    print(f'Median is: {np.median(e)}')
    for i, area in enumerate(areas):
        print(f'{area} avg PED: {average_region[i]}')

    plt.plot(range(1949+ped_years,2008), average_year)
    plt.title('Average steel PED per year in Simson')
    plt.xlabel('Year')
    plt.ylabel('PED')
    plt.show()

if __name__=='__main__':
    _test()