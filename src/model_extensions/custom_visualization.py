import os
from sodym.tools.config import cfg
from sodym.tools.visualize.vistools import visualize_if_set_in_config
from sodym.tools.visualize.plot_array import ArrayPlotter
from sodym.classes.mfa_system import MFASystem


@visualize_if_set_in_config('production')
def visualize_production(mfa: MFASystem):
    ap_modeled = ArrayPlotter(array=mfa.stocks['in_use'].inflow['World'].sum_nda_over(('m', 'e')),
                              intra_line_dim='Time',
                              subplot_dim='Good',
                              label_in='Modeled')
    fig, ax = ap_modeled.plot()
    ap_historic = ArrayPlotter(array = mfa.parameters['production']['World'],
                              intra_line_dim='Historic Time',
                              subplot_dim='Good',
                              label_in='Historic Production',
                              fig_ax=(fig, ax),
                              xlabel='Year',
                              ylabel='Production [t]')
    save_path = os.path.join(cfg.output_path, 'figures', 'production.png') if cfg.do_save_figs else None
    ap_historic.plot(save_path=save_path, do_show=cfg.do_show_figs)


@visualize_if_set_in_config('stock')
def visualize_stock(mfa, gdppc, historic_gdppc, stocks, historic_stocks, stocks_pc, historic_stocks_pc):
    if not cfg.visualize['stock']['do_visualize']:
        return

    if cfg.visualize['stock']['per_capita']:
        stocks_plot = stocks_pc['World']
        historic_stocks_plot = historic_stocks_pc['World']
    else:
        stocks_plot = stocks['World']
        historic_stocks_plot = historic_stocks['World']

    if cfg.visualize['stock']['over'] == 'time':
        x_array, x_array_hist = None, None
        xlabel = 'Year'
    elif cfg.visualize['stock']['over'] == 'gdppc':
        x_array = gdppc['World']
        x_array_hist = historic_gdppc['World']
        xlabel = 'GDP per capita [USD]'

    ap_modeled = ArrayPlotter(array=stocks_plot,
                              intra_line_dim='Time',
                              x_array=x_array,
                              subplot_dim='Good',
                              label_in='Modeled')
    fig, ax = ap_modeled.plot()
    ap_historic = ArrayPlotter(array=historic_stocks_plot,
                               intra_line_dim='Historic Time',
                               x_array=x_array_hist,
                               subplot_dim='Good',
                               label_in='Historic',
                               fig_ax=(fig, ax),
                               xlabel=xlabel,
                               ylabel='Stock [t]')
    save_path = os.path.join(cfg.output_path, 'figures', 'stock.png') if cfg.do_save_figs else None
    ap_historic.plot(save_path=save_path, do_show=cfg.do_show_figs)
