import numpy as np
from src.model.simson_model import load_simson_model
from src.read_data.load_data import load_steel_prices, load_stocks
import matplotlib.pyplot as plt

def _test():
    model = load_simson_model(country_specific=False)
    inflow = model.FlowDict['F_2_4'].Values[50:109,0,:,:,0]
    inflow = np.sum(inflow,axis=2)
    prices = load_steel_prices().to_numpy()[0,50:109]
    q2 = inflow[1:].transpose()
    q1 = inflow[:-1].transpose()
    p2 = prices[1:]
    p1 = prices[:1]

    areas = list(load_stocks(country_specific=False).index.get_level_values(0).unique())
    print(areas)

    e = ((q2-q1)/((q2+q1)/2))/((p2-p1)/((p2+p1)/2))
    average_region = np.average(e, axis=1)
    average_year = np.average(e, axis=0)
    average = np.average(e)

    plt.plot(range(1950,2008), average_year)
    plt.title('Average steel PED per year in Simson')
    plt.xlabel('Year')
    plt.ylabel('PED')
    plt.show()


    print(average.shape)
    print(average)
    for i, area in enumerate(areas):
        print(f'{area} avg PED: {average_region[i]}')

if __name__=='__main__':
    _test()