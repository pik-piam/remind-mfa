from matplotlib import pyplot as plt
import numpy as np
from src.tools.config import cfg


def visualize_future_production(dsms, historic_production):

    modeled_production = np.moveaxis(np.array([[d.i for d in r] for r in dsms]), -1, 0)

    f, ax = plt.subplots(2, 2, figsize=(10, 9))
    f.suptitle("Production over time")

    for i, sector in enumerate(cfg.in_use_categories):
        ax[i // 2, i % 2].plot(cfg.historic_years, historic_production[:,0,i], label='historic')
        ax[i // 2, i % 2].plot(cfg.years, modeled_production[:,0,i], label='modeled')
        ax[i // 2, i % 2].set_title(sector)
        ax[i // 2, i % 2].legend()
        ax[i // 2, i % 2].set_xlabel('Year')
        ax[i // 2, i % 2].set_ylabel('Global production [t]')

    plt.show()


def visualize_stock_prediction(gdppc, stocks_pc, prediction):
    plt.figure()
    plt.plot(cfg.historic_years, gdppc[cfg.i_historic], label='historic')
    plt.plot(cfg.future_years, gdppc[cfg.i_future,0], label='prediction')
    plt.xlabel('Year')
    plt.ylabel('GDP PPP pC [$2005]')
    plt.title('GDP over time')
    plt.legend()

    f_gdppc, ax_gdppc = plt.subplots(2, 2, figsize=(10, 9))
    f_gdppc.suptitle("Stocks per capita over time")

    f_time, ax_time = plt.subplots(2, 2, figsize=(10, 9))
    f_time.suptitle("Stocks per capita over GDP")

    for i, sector in enumerate(cfg.in_use_categories):

        ax_gdppc[i // 2, i % 2].plot(cfg.historic_years, stocks_pc[:,0,i], label='historic')
        ax_gdppc[i // 2, i % 2].plot(cfg.years, prediction[:,0,i], label='prediction')
        ax_gdppc[i // 2, i % 2].set_title(sector)
        ax_gdppc[i // 2, i % 2].legend()
        ax_gdppc[i // 2, i % 2].set_xlabel('Year')
        ax_gdppc[i // 2, i % 2].set_ylabel('Stock per capita [t]')

        ax_time[i // 2, i % 2].plot(gdppc[cfg.i_historic,0], stocks_pc[:,0,i], label='historic')
        ax_time[i // 2, i % 2].plot(gdppc[:,0], prediction[:,0,i], label='prediction')
        ax_time[i // 2, i % 2].set_title(sector)
        ax_time[i // 2, i % 2].legend()
        ax_time[i // 2, i % 2].set_xlabel('GDP PPP pC [$2005]')
        ax_time[i // 2, i % 2].set_ylabel('Stock per capita [t]')

    plt.show()