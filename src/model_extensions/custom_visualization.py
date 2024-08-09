import logging

from sodym.export.data_writer import DataWriter
from sodym.export.helper import visualize_array


class CustomDataVisualizer(DataWriter):
    production: dict = {'do_visualize': True}
    stock: dict = {'do_visualize': True}

    def visualize_results(self):
        if self.production['do_visualize']:
            self.visualize_production()
        if self.stock['do_visualize']:
            logging.info('Stock visualization functionality unavailable')
            #self.visualize_stock()
        if self.sankey['do_visualize']:
            self.visualize_sankey()

    def visualize_production(self):
        fig, ax = visualize_array(
            self.mfa.stocks['in_use'].inflow,
            intra_line_dim='Time',
            tile_dim='Good',
            slice_dict={'r': 'World'},
            summed_dims=['m', 'e'],
            label_in='Modeled')
        fig, ax = visualize_array(self.mfa.parameters['production'],
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
