from matplotlib import pyplot as plt
import numpy as np
from src.tools.config import cfg
from ODYM.odym.modules.ODYM_Classes import MFAsystem
import plotly.graph_objects as go
import plotly as pl


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


def visualize_mfa_sankey(mfa: MFAsystem):
    exclude_nodes = ['System Environment']
    exclude_flows = []
    year = 2020

    nodes = [p for p in mfa.ProcessList if p.Name not in exclude_nodes]
    exclude_node_ids = [p.ID for p in mfa.ProcessList if p.Name in exclude_nodes]
    flows = {fn: f for fn, f in mfa.FlowDict.items() if (fn not in exclude_flows
                                                         and f.P_Start not in exclude_node_ids
                                                         and f.P_End not in exclude_node_ids)}
    id_mapping = {p.ID: i for i, p in enumerate(nodes)}
    # colors = pl.colors.qualitative.Antique[:cfg.n_elements]
    # colors = pl.colors.sample_colorscale('Viridis', cfg.n_elements + 1, colortype='rgb')

    fig = go.Figure(go.Sankey(
        arrangement = "snap",
        node = {
            "label": [p.Name for p in nodes],
            "color": ['gray' for p in nodes], # 'rgb(50, 50, 50)'
            # "x": [0.2, 0.1, 0.5, 0.7, 0.3, 0.5],
            # "y": [0.7, 0.5, 0.2, 0.4, 0.2, 0.3],
            'pad':10},  # 10 Pixels
        link = {
            "label": [fn for e in cfg.elements for fn in flows.keys()],
            "source": [id_mapping[f.P_Start] for e in cfg.elements for f in flows.values()],
            "target": [id_mapping[f.P_End] for e in cfg.elements for f in flows.values()],
            # "color": [c for c in colors for f in flows],
            "color": [f'hsv({10 * i + 200},40,150)' for i in range(cfg.n_elements) for f in flows],
            "value": [np.einsum(f"{f.Indices.replace(',', '')}->ter", f.Values)[cfg.y_id(year),i,0] for i in range(cfg.n_elements) for f in flows.values()]}))

    fig.show()
