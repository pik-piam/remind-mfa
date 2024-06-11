from matplotlib import pyplot as plt
import numpy as np
from src.tools.config import cfg
from src.new_odym.mfa_system import MFASystem
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

display_names = {
    'sysenv': 'System environment',
    'virginfoss': 'Virgin production (fossil)',
    'virginbio': 'Virgin production (biomass)',
    'virgindaccu': 'Virgin production (daccu)',
    'virginccu': 'Virgin production (ccu)',
    'virgin': 'Virgin production (total)',
    'fabrication': 'Fabrication',
    'recl': 'Recycling (total)',
    'reclmech': 'Mechanical recycling',
    'reclchem': 'Chemical recycling',
    'reclsolv': 'Solvent-based recycling',
    'use': 'Use Phase',
    'eol': 'End of Life',
    'incineration': 'Incineration',
    'landfill': 'Disposal',
    'uncontrolled': 'Uncontrolled release',
    'emission': 'Emissions',
    'captured': 'Captured',
    'atmosphere': 'Atmosphere'
}


def dn(st):
    return display_names[st] if st in display_names else st


def visualize_mfa_sankey(mfa: MFASystem):
    # exclude_nodes = ['sysenv', 'atmosphere', 'emission', 'captured']
    exclude_nodes = ['sysenv']
    exclude_flows = []
    year = 2050
    region_id = 0
    carbon_only = True
    color_scheme = 'blueish'

    nodes = [p for p in mfa.processes.values() if p.name not in exclude_nodes]
    ids_in_sankey = {p.id: i for i, p in enumerate(nodes)}
    exclude_node_ids = [p.id for p in mfa.processes.values() if p.name in exclude_nodes]
    flows = {f for f in mfa.flows.values() if (f.name not in exclude_flows
                                               and f.from_process_id not in exclude_node_ids
                                               and f.to_process_id not in exclude_node_ids)}
    if color_scheme == 'antique':
        material_colors = pl.colors.qualitative.Antique[:mfa.dims['Material'].len]
    elif color_scheme == 'viridis':
        material_colors = pl.colors.sample_colorscale('Viridis', mfa.dims['Material'].len + 1, colortype='rgb')
    elif color_scheme == 'blueish':
        material_colors = [f'hsv({10 * i + 200},40,150)' for i in range(mfa.dims['Material'].len)]
    else:
        raise Exception('invalid color scheme')

    link_dict = {"label": [], "source": [], "target": [], "color": [], "value": []}

    def add_link(**kwargs):
        for key, value in kwargs.items():
            link_dict[key].append(value)

    for f in flows:
        source = ids_in_sankey[f.from_process_id]
        target = ids_in_sankey[f.to_process_id]
        label = dn(f.name)

        id_orig = f.dims.string
        has_materials = 'm' in id_orig
        id_target = f"ter{'m' if has_materials else ''}"
        values = np.einsum(f"{id_orig}->{id_target}", f.values)

        if carbon_only:
            values = values[:,0,...]
        else:
            values = np.sum(values, axis = 1)

        values = values[mfa.dims['Time'].index(year),region_id,...]

        if has_materials:
            for im, c in enumerate(material_colors):
                add_link(label=label, source=source, target=target, color=c, value=values[im])
        else:
            add_link(label=label, source=source, target=target, color='hsl(230,20,70)', value=values)


    fig = go.Figure(go.Sankey(
        arrangement = "snap",
        node = {
            "label": [dn(p.name) for p in nodes],
            "color": ['gray' for p in nodes], # 'rgb(50, 50, 50)'
            # "x": [0.2, 0.1, 0.5, 0.7, 0.3, 0.5],
            # "y": [0.7, 0.5, 0.2, 0.4, 0.2, 0.3],
            'pad':10},  # 10 Pixels
        link = link_dict ))

    fig.show()
