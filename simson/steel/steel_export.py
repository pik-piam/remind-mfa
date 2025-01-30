import logging
import flodym as fd

from simson.common.custom_export import CustomDataExporter
from simson.common.data_transformations import transform_t_to_hist


class SteelDataExporter(CustomDataExporter):

    scrap_demand_supply: dict = {'do_visualize': True}
    sector_splits: dict = {'do_visualize': True}

    # Dictionary of variable names vs names displayed in figures. Used by visualization routines.
    _display_names: dict = {
        'sysenv': 'System environment',
        'bof_production': 'Production (BF/BOF)',
        'eaf_production': 'Production (EAF)',
        'forming': 'Forming',
        'ip_market': 'Intermediate product market',
        # 'ip_trade': 'Intermediate product trade',  # todo decide whether to incorporate, depending on trade balancing
        'fabrication': 'Fabrication',
        # 'indirect_trade': 'Indirect trade', # todo decide whether to incorporate, depending on trade balancing
        'in_use': 'Use phase',
        'obsolete': 'Obsolete stocks',
        'eol_market': 'End of life product market',
        # 'eol_trade': 'End of life trade', # todo decide whether to incorporate, depending on trade balancing
        'recycling': 'Recycling',
        'scrap_market': 'Scrap market',
        'excess_scrap': 'Excess scrap'
    }

    def visualize_results(self, mfa: fd.MFASystem):
        if self.production['do_visualize']:
            self.visualize_production(mfa=mfa)
        if self.stock['do_visualize']:
            self.visualize_stock(mfa=mfa)
        if self.scrap_demand_supply['do_visualize']:
            self.visualize_scrap_demand_supply(mfa)
        if self.sector_splits['do_visualize']:
            self.visualize_sector_splits(mfa)
        if self.sankey['do_visualize']:
            self.visualize_sankey(mfa)
        self.stop_and_show()

    def visualize_production(self, mfa: fd.MFASystem):
        flw = mfa.flows
        production = flw['bof_production => forming'] + flw['eaf_production => forming']
        production = production.sum_over('e')

        # visualize regional production
        ap_production = self.plotter_class(
            array=production,
            intra_line_dim='Time',
            subplot_dim='Region',
            line_label='Production',
            display_names=self._display_names,
            xlabel='Year',
            ylabel='Production [t]',
            title='Regional Steel Production'
        )

        self.plot_and_save_figure(ap_production, 'production_by_region.png')

        # visualize global production
        production = production.sum_over('r')

        ap_production = self.plotter_class(
            array=production,
            intra_line_dim='Time',
            line_label='Production',
            display_names=self._display_names,
            xlabel='Year',
            ylabel='Production [t]',
            title='Global Steel Production'
        )

        self.plot_and_save_figure(ap_production, 'production_global.png')

    def visualize_stock(self, mfa: fd.MFASystem):
        over_gdp = self.stock['over_gdp']
        per_capita = self.stock['per_capita']

        stock = mfa.stocks['use'].stock
        population = mfa.parameters['population']
        x_array = None

        pc_str = ' pC' if per_capita else ''
        x_label = 'Year'
        y_label = f'Stock{pc_str}[t]'
        title = f"Stocks{pc_str}"
        if over_gdp:
            title = title + f"over GDP{pc_str}"

        if over_gdp:
            x_array = mfa.parameters['gdppc']
            x_label = f'GDP/PPP{pc_str}[2005 USD]'

        self.visualize_regional_stock(stock, x_array, population, x_label, y_label, title, per_capita, over_gdp)
        self.visiualize_global_stock(stock, x_array, population, x_label, y_label, title, per_capita, over_gdp)

    def visualize_regional_stock(self, stock, x_array, population, x_label, y_label, title, per_capita, over_gdp):
        if per_capita:
            stock = stock / population
        else:
            if over_gdp:
                x_array = x_array * population

        ap_stock = self.plotter_class(
            array=stock,
            intra_line_dim='Time',
            subplot_dim='Region',
            linecolor_dim='Good',
            display_names=self._display_names,
            xlabel=x_label,
            x_array=x_array,
            ylabel=y_label,
            title=f'{title} (regional)',
            area=True
        )

        self.plot_and_save_figure(ap_stock, 'stocks_by_region.png')

    def visiualize_global_stock(self, stock, x_array, population, x_label, y_label, title, per_capita, over_gdp):
        if over_gdp:
            x_array = x_array * population
            x_array = x_array.sum_over('r')
            if per_capita:
                # get global GDP per capita
                x_array = x_array / population.sum_over('r')

        self.visualize_global_stock_by_good(stock, x_array, population, x_label, y_label, title, per_capita)
        self.visualize_global_stock_by_region(stock, x_array, x_label, y_label, title, per_capita)

    def visualize_global_stock_by_good(self, stock, x_array, population, x_label, y_label, title, per_capita):
        stock = stock.sum_over('r')
        stock = stock / population.sum_over('r') if per_capita else stock

        ap_stock = self.plotter_class(
            array=stock,
            intra_line_dim='Time',
            linecolor_dim='Good',
            display_names=self._display_names,
            x_array=x_array,
            xlabel=x_label,
            ylabel=y_label,
            title=f'{title} (global by good)',
            area=True
        )

        self.plot_and_save_figure(ap_stock, 'stocks_global_by_good.png')

    def visualize_global_stock_by_region(self, stock, x_array, x_label, y_label, title, per_capita):
        if per_capita:
            logging.info('Global stocks by region can not be implemented per capita. Skipping...')
            return

        stock = stock.sum_over('g')

        ap_stock = self.plotter_class(
            array=stock,
            intra_line_dim='Time',
            linecolor_dim='Region',
            display_names=self._display_names,
            x_array=x_array,
            xlabel=x_label,
            ylabel=y_label,
            title=f'{title} (global by region)',
            area=True
        )

        self.plot_and_save_figure(ap_stock, 'stocks_global_by_region.png')

    def visualize_scrap_demand_supply(self, mfa: fd.MFASystem):
        flw = mfa.flows
        prm = mfa.parameters

        total_production = flw['forming => ip_market'] / prm['forming_yield'] / prm['production_yield']
        dri = (prm['dri_production'] + prm['dri_imports'] - prm['dri_exports'])
        pigiron = (prm['pigiron_production'] + prm['pigiron_imports'] - prm['pigiron_exports'] - prm['pigiron_to_cast'])

        total_production = transform_t_to_hist(total_production, dims=mfa.dims)
        scrap_demand = total_production - pigiron - dri
        # scrap is also used in pig iron and dri production
        scrap_demand += prm['pigiron_production'] * 0.15 + prm['dri_production'] * 0.06
        scrap_supply = (flw['recycling => scrap_market'] +
                        flw['forming => scrap_market'] +
                        flw['fabrication => scrap_market'])
        scrap_supply = transform_t_to_hist(scrap_supply, dims=mfa.dims).sum_over('e')

        ap_demand = self.plotter_class(
            array=scrap_demand,
            intra_line_dim='Historic Time',
            subplot_dim='Region',
            line_label='Scrap Demand',
            display_names=self._display_names
        )

        fig = ap_demand.plot()

        ap_production = self.plotter_class(
            array=total_production.sum_to(('h', 'r')),
            intra_line_dim='Historic Time',
            subplot_dim='Region',
            line_label='Total Production',
            fig=fig)

        fig = ap_production.plot()

        ap_supply = self.plotter_class(
            array=scrap_supply,
            intra_line_dim='Historic Time',
            subplot_dim='Region',
            line_label='Scrap Supply',
            fig=fig,
            xlabel='Year',
            ylabel='Scrap [t]',
            display_names=self._display_names,
            title='Regional Scrap Demand and Supply'
        )

        self.plot_and_save_figure(ap_supply, 'scrap_demand_supply_regional.png')

        # plot global demand and supply
        scrap_demand = scrap_demand.sum_over('r')
        scrap_supply = scrap_supply.sum_over('r')

        ap_demand = self.plotter_class(
            array=scrap_demand,
            intra_line_dim='Historic Time',
            line_label='Scrap Demand',
            display_names=self._display_names,
        )

        fig = ap_demand.plot()

        ap_supply = self.plotter_class(
            array=scrap_supply,
            intra_line_dim='Historic Time',
            line_label='Scrap Supply',
            fig=fig,
            xlabel='Year',
            ylabel='Scrap [t]',
            display_names=self._display_names,
            title='Global Scrap Demand and Supply'
        )

        self.plot_and_save_figure(ap_supply, 'scrap_demand_supply_global.png')

    def visualize_sector_splits(self, mfa: fd.MFASystem):
        flw = mfa.flows

        fabrication = flw['fabrication => use']
        fabrication = fabrication.sum_over(('e',))
        sector_splits = fabrication.get_shares_over('g')

        ap_sector_splits = self.plotter_class(
            array=sector_splits,
            intra_line_dim='Time',
            subplot_dim='Region',
            linecolor_dim='Good',
            xlabel='Year',
            ylabel='Sector Splits [%]',
            display_names=self._display_names,
            title='Regional Fabrication Sector Splits'
        )

        self.plot_and_save_figure(ap_sector_splits, 'sector_splits_regional.png')

        # plot global sector splits
        fabrication = fabrication.sum_over('r')
        sector_splits = fabrication.get_shares_over('g')

        ap_sector_splits = self.plotter_class(
            array=sector_splits,
            intra_line_dim='Time',
            linecolor_dim='Good',
            xlabel='Year',
            ylabel='Sector Splits [%]',
            display_names=self._display_names,
            title='Global Fabrication Sector Splits'
        )

        self.plot_and_save_figure(ap_sector_splits, 'sector_splits_global.png')
