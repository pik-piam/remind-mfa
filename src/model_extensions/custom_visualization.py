from sodym.tools.config import cfg
from sodym.tools.visualize.vistools import show_and_save_pyplot, visualize_if_set_in_config
from sodym.tools.visualize.plot_array import visualize_array
from sodym.classes.mfa_system import MFASystem

@visualize_if_set_in_config('production')
def visualize_production(mfa: MFASystem):
    fig, ax = visualize_array(mfa.stocks['in_use'].inflow,
                              intra_line_dim='Time',
                              tile_dim='Good',
                              slice_dict={'r': 'World'},
                              summed_dims=['m', 'e'],
                              label_in='Modeled')
    fig, ax = visualize_array(mfa.parameters['production'],
                              intra_line_dim='Historic Time',
                              tile_dim='Good',
                              slice_dict={'r': 'World'},
                              label_in='Historic Production',
                              fig_ax=(fig, ax))
    show_and_save_pyplot(fig, 'production')


@visualize_if_set_in_config('stock')
def visualize_stock(mfa, gdppc, historic_gdppc, stocks, historic_stocks, stocks_pc, historic_stocks_pc):
    if not cfg.visualize['stock']['do_visualize']:
        return

    if cfg.visualize['stock']['per_capita']:
        stocks_plot = stocks_pc
        historic_stocks_plot = historic_stocks_pc
    else:
        stocks_plot = stocks
        historic_stocks_plot = historic_stocks

    if cfg.visualize['stock']['over'] == 'time':
        x_array, x_array_hist = None, None
    elif cfg.visualize['stock']['over'] == 'gdppc':
        x_array = gdppc
        x_array_hist = historic_gdppc

    fig, ax = visualize_array(stocks_plot,
                              intra_line_dim='Time',
                              x_array=x_array,
                              tile_dim='Good',
                              slice_dict={'r': 'World'},
                              label_in='Modeled')
    fig, ax = visualize_array(historic_stocks_plot,
                              intra_line_dim='Historic Time',
                              x_array=x_array_hist,
                              tile_dim='Good',
                              slice_dict={'r': 'World'},
                              label_in='Historic',
                              fig_ax=(fig, ax))
    show_and_save_pyplot(fig, 'stock')
