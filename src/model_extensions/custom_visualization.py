import logging
import os

from matplotlib import pyplot as plt
import plotly.graph_objects as go

from sodym.classes.mfa_system import MFASystem
from sodym.export.data_writer import DataWriter
from sodym.export.helper import visualize_array


class CustomDataVisualizer(DataWriter):

    output_path: str
    do_save_figs: bool = True
    do_show_figs: bool = True
    do_export: dict = {'pickle': True, 'csv': True}
    production: dict = {'do_visualize': True}
    stock: dict = {'do_visualize': True}

    def export_mfa(self, mfa: MFASystem):
        if self.do_export.get('pickle', False):
            self.export_mfa_to_pickle(mfa=mfa, export_path=self.export_path('mfa.pickle'))
        if self.do_export.get('csv', False):
            dir_out = os.path.join(self.export_path(), 'flows')
            self.export_mfa_flows_to_csv(mfa=mfa, export_directory=dir_out)

    def export_path(self, filename: str = None):
        path_tuple = (self.output_path, 'export')
        if filename is not None:
            path_tuple += (filename,)
        return os.path.join(*path_tuple)

    def figure_path(self, filename: str):
        return os.path.join(self.output_path, 'figures', filename)

    def _show_and_save_pyplot(self, fig, name):
        if self.do_save_figs:
            plt.savefig(self.figure_path(f"{name}.png"))
        if self.do_show_figs:
            plt.show()

    def _show_and_save_plotly(self, fig: go.Figure, name):
        if self.do_save_figs:
            fig.write_image(self.figure_path(f"{name}.png"))
        if self.do_show_figs:
            fig.show()

    def visualize_results(self, mfa: MFASystem):
        if self.production['do_visualize']:
            self.visualize_production(mfa=mfa)
        if self.stock['do_visualize']:
            logging.info('Stock visualization functionality unavailable')
            #self.visualize_stock()
        if self.sankey['do_visualize']:
            fig = self.visualize_sankey(mfa=mfa)
            self._show_and_save_plotly(fig, name="sankey")

    def visualize_production(self, mfa: MFASystem):
        fig, ax = visualize_array(
            mfa.stocks['in_use'].inflow,
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
        self._show_and_save_pyplot(fig, 'production')

    def visualize_stock(self, gdppc, historic_gdppc, stocks, historic_stocks, stocks_pc, historic_stocks_pc):

        if self.stock['per_capita']:
            stocks_plot = stocks_pc
            historic_stocks_plot = historic_stocks_pc
        else:
            stocks_plot = stocks
            historic_stocks_plot = historic_stocks

        if self.stock['over'] == 'time':
            x_array, x_array_hist = None, None
        elif self.stock['over'] == 'gdppc':
            x_array = gdppc
            x_array_hist = historic_gdppc

        fig, ax = visualize_array(
            stocks_plot,
            intra_line_dim='Time',
            x_array=x_array,
            tile_dim='Good',
            slice_dict={'r': 'World'},
            label_in='Modeled')
        fig, ax = visualize_array(
            historic_stocks_plot,
            intra_line_dim='Historic Time',
            x_array=x_array_hist,
            tile_dim='Good',
            slice_dict={'r': 'World'},
            label_in='Historic',
            fig_ax=(fig, ax))
        self._show_and_save_pyplot(fig, 'stock')
