from matplotlib import pyplot as plt
import numpy as np
from src.tools.config import cfg
from src.tools.paths import figure_path
from src.new_odym.mfa_system import MFASystem
from src.new_odym.named_dim_arrays import NamedDimArray
import plotly.graph_objects as go
import plotly as pl


def visualize_mfa(mfa):
    if cfg.visualize['sankey']['do_visualize']:
        visualize_mfa_sankey(mfa)
    if cfg.visualize['production']['do_visualize']:
        visualize_production(mfa)

def visualize_stock(gdppc, historic_gdppc, stocks, historic_stocks, stocks_pc, historic_stocks_pc):
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

def show_and_save_pyplot(fig, name):
    if cfg.do_save_figs:
        plt.savefig(figure_path(f"{name}.png"))
    if cfg.do_show_figs:
        plt.show()

def show_and_save_plotly(fig: pl.graph_objs.Figure, name):
    if cfg.do_save_figs:
        fig.write_image(figure_path(f"{name}.png"))
    if cfg.do_show_figs:
        fig.show()

def visualize_array(array: NamedDimArray, intra_line_dim, x_array: NamedDimArray=None, tile_dim=None, linecolor_dim=None, slice_dict=None, summed_dims=None, fig_ax=None, title=None, label_in=None):

    assert not (linecolor_dim is not None and label_in is not None), "Either dim_lines or label_in can be given, but not both."

    fig, ax, nx, ny = get_fig_ax(array, tile_dim, fig_ax)

    fig.suptitle(title if title is not None else array.name)

    array_reduced = sum_and_slice(array, slice_dict, summed_dims)
    arrays_tile = list_of_slices(array_reduced, tile_dim)

    if x_array is not None:
        x_array = x_array.cast_to(array.dims)
        x_array = sum_and_slice(x_array, slice_dict, summed_dims)
    x_tiles = list_of_slices(x_array, tile_dim, len(arrays_tile))

    for i_tile, (array_tile, x_tile) in enumerate(zip(arrays_tile, x_tiles)):
        ax_tile = ax[i_tile // nx, i_tile % nx]
        item_tile = dim_item_name_by_index(array, tile_dim, i_tile)
        plot_tile(ax_tile, array_tile, x_tile, intra_line_dim, linecolor_dim, label_in, tile_dim, item_tile)
    handles, labels = ax[0,0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center')
    return fig, ax


def plot_tile(ax_tile, array_tile, x_tile, intra_line_dim, linecolor_dim, label_in, tile_dim, item_tile):
    if tile_dim is not None:
        ax_tile.set_title(f'{tile_dim}={item_tile}')

    arrays_line = list_of_slices(array_tile, linecolor_dim)
    x_lines = list_of_slices(x_tile, linecolor_dim)
    for j, (array_line, x_line) in enumerate(zip(arrays_line, x_lines)):
        label = get_label(array_line, linecolor_dim, j, label_in)
        assert array_line.dims.names == (intra_line_dim,), "All dimensions of array must be given exactly once. Either as x_dim / tile_dim / linecolor_dim, or in slice_dict or summed_dims."
        if x_line is not None:
            x = x_line.values
        else:
            x = array_line.dims[intra_line_dim].items
        ax_tile.plot(x, array_line.values, label=label)
    ax_tile.set_xlabel(intra_line_dim)

def dim_item_name_by_index(array: NamedDimArray, dim_name, i_item):
    if dim_name is None:
        return None
    else:
        return array.dims[dim_name].items[i_item]

def sum_and_slice(array: NamedDimArray, slice_dict, summed_dims):
    array = array.slice_obj(slice_dict).to_nda()
    if summed_dims is not None:
        array = array.sum_nda_over(summed_dims)
    return array

def list_of_slices(array, dim_to_slice, n_return_none=1):
    if array is None:
        return [None] * n_return_none
    elif dim_to_slice is not None:
        arrays_tile = [array.slice_obj({array.dims[dim_to_slice].letter: item}).to_nda() for item in array.dims[dim_to_slice].items]
    else:
        arrays_tile = [array]
    return arrays_tile

def get_label(array: NamedDimArray, linecolor_dim, j, label_in):
    if label_in is not None:
        label = label_in
    else:
        label = dim_item_name_by_index(array, linecolor_dim, j)
    return label

def get_fig_ax(array, dim_tiles, fig_ax):
    if fig_ax is None:
        if dim_tiles is None:
            fig, ax = plt.subplots(1, 1, figsize=(10, 9))
            nx, ny = 1, 1
        else:
            nx, ny = get_tiles(array, dim_tiles)
            fig, ax = plt.subplots(nx, ny, figsize=(10, 9))
    else:
        fig, ax = fig_ax
        nx, ny = ax.shape
    return fig, ax, nx, ny

def get_tiles(array, dim_tiles):
    n_tiles = array.dims[dim_tiles].len
    nx = int(np.ceil(np.sqrt(n_tiles)))
    ny = int(np.ceil(n_tiles / nx))
    return nx, ny


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


# Here, some general, non-model-specific display names can be set
display_names = {
    'my_variable': 'My Variable',
}
display_names_model = {}

def set_display_names_model(mfa):
    global display_names_model
    display_names_model = mfa.display_names

def dn(st):
    display_names_loc = display_names | display_names_model
    return display_names_loc[st] if st in display_names_loc else st


def visualize_mfa_sankey(mfa: MFASystem):
    # exclude_nodes = ['sysenv', 'atmosphere', 'emission', 'captured']
    exclude_nodes = ['sysenv']
    exclude_flows = []
    year = 2050
    region_id = 0
    carbon_only = True
    color_scheme = 'blueish'

    set_display_names_model(mfa)
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

    show_and_save_plotly(fig, 'sankey')
