import logging
import os
from sodym.mfa_system import MFASystem
from sodym.export.array_plotter import PlotlyArrayPlotter
from simson.common.custom_export import CustomDataExporter
from simson.common.data_transformations import transform_t_to_hist


class SteelDataExporter(CustomDataExporter):
    scrap_demand_supply: dict = {'do_visualize': True}
    sector_splits: dict = {'do_visualize': True}

    def visualize_results(self, mfa: MFASystem):
        super().visualize_results(mfa)
        if self.scrap_demand_supply['do_visualize']:
            self.visualize_scrap_demand_supply(mfa)
        if self.sector_splits['do_visualize']:
            self.visualize_sector_splits(mfa)

    def visualize_production(self, mfa: MFASystem):
        flw = mfa.flows
        production = flw['bof_production => forming'] + flw['eaf_production => forming']
        production = production.sum_nda_over('e')

        # visualize regional production
        ap_production = PlotlyArrayPlotter(
            array=production,
            intra_line_dim='Time',
            subplot_dim='Region',
            line_label='Production',
            display_names=self.display_names,
            xlabel='Year',
            ylabel='Production [t]',
            title='Regional Steel Production'
        )

        save_path = os.path.join(self.output_path, 'figures',
                                 'production_by_region.png') if self.do_save_figs else None
        ap_production.plot(save_path=save_path, do_show=self.do_show_figs)

        # visualize global production
        production = production.sum_nda_over('r')

        ap_production = PlotlyArrayPlotter(
            array=production,
            intra_line_dim='Time',
            line_label='Production',
            display_names=self.display_names,
            xlabel='Year',
            ylabel='Production [t]',
            title='Global Steel Production'
        )

        save_path = os.path.join(self.output_path, 'figures',
                                 'production_global.png') if self.do_save_figs else None
        ap_production.plot(save_path=save_path, do_show=self.do_show_figs)

    def visualize_stock(self, mfa: MFASystem):
        over_gdp = self.stock['over_gdp']
        per_capita = self.stock['per_capita']

        stock = mfa.stocks['use'].stock
        population = mfa.parameters['population']
        x_array = None

        x_label = 'Year'
        y_label = f'Stock{' pC' if per_capita else ''}[t]'
        title = f'Stocks{' per capita' if per_capita else ''}' \
                f'{f' over GDP{' pC' if per_capita else ''}' if over_gdp else ''}'

        if over_gdp:
            x_array = mfa.parameters['gdppc']
            x_label = f'GDP/PPP{' per capita' if per_capita else ''}[2005 USD]'

        self.visualize_regional_stock(stock, x_array, population, x_label, y_label, title, per_capita, over_gdp)
        self.visiualize_global_stock(stock, x_array, population, x_label, y_label, title, per_capita, over_gdp)

    def visualize_regional_stock(self, stock, x_array, population, x_label, y_label, title, per_capita, over_gdp):
        if per_capita:
            stock = stock / population
        else:
            if over_gdp:
                x_array = x_array * population

        ap_stock = PlotlyArrayPlotter(
            array=stock,
            intra_line_dim='Time',
            subplot_dim='Region',
            linecolor_dim='Good',
            display_names=self.display_names,
            xlabel=x_label,
            x_array=x_array,
            ylabel=y_label,
            title=f'{title} (regional)',
            area=True
        )

        save_path = os.path.join(self.output_path, 'figures',
                                 f'stocks_by_region.png') if self.do_save_figs else None
        ap_stock.plot(save_path=save_path, do_show=self.do_show_figs)

    def visiualize_global_stock(self, stock, x_array, population, x_label, y_label, title, per_capita, over_gdp):
        if over_gdp:
            x_array = x_array * population
            x_array = x_array.sum_nda_over('r')
            if per_capita:
                # get global GDP per capita
                x_array = x_array / population.sum_nda_over('r')

        self.visualize_global_stock_by_good(stock, x_array, population, x_label, y_label, title, per_capita)
        self.visualize_global_stock_by_region(stock, x_array, x_label, y_label, title, per_capita)

    def visualize_global_stock_by_good(self, stock, x_array, population, x_label, y_label, title, per_capita):
        stock = stock.sum_nda_over('r')
        stock = stock / population.sum_nda_over('r') if per_capita else stock

        ap_stock = PlotlyArrayPlotter(
            array=stock,
            intra_line_dim='Time',
            linecolor_dim='Good',
            display_names=self.display_names,
            x_array=x_array,
            xlabel=x_label,
            ylabel=y_label,
            title=f'{title} (global by good)',
            area=True
        )

        save_path = os.path.join(self.output_path, 'figures',
                                 f'stocks_global_by_good.png') if self.do_save_figs else None
        ap_stock.plot(save_path=save_path, do_show=self.do_show_figs)

    def visualize_global_stock_by_region(self, stock, x_array, x_label, y_label, title, per_capita):
        if per_capita:
            logging.info('Global stocks by region can not be implemented per capita. Skipping...')
            return

        stock = stock.sum_nda_over('g')

        ap_stock = PlotlyArrayPlotter(
            array=stock,
            intra_line_dim='Time',
            linecolor_dim='Region',
            display_names=self.display_names,
            x_array=x_array,
            xlabel=x_label,
            ylabel=y_label,
            title=f'{title} (global by region)',
            area=True
        )

        save_path = os.path.join(self.output_path, 'figures',
                                 f'stocks_global_by_region.png') if self.do_save_figs else None
        ap_stock.plot(save_path=save_path, do_show=self.do_show_figs)

    def visualize_scrap_demand_supply(self, mfa: MFASystem):
        flw = mfa.flows
        prm = mfa.parameters
        scp = mfa.scalar_parameters

        total_production = flw['forming => ip_market'] / prm['forming_yield'] / scp['production_yield']
        dri = (prm['dri_production'] + prm['dri_imports'] - prm['dri_exports'])
        pigiron = (prm['pigiron_production'] + prm['pigiron_imports'] - prm['pigiron_exports'] - prm['pigiron_to_cast'])

        total_production = transform_t_to_hist(total_production, dims=mfa.dims)
        scrap_demand = total_production - pigiron - dri
        # scrap is also used in pig iron and dri production
        scrap_demand += prm['pigiron_production'] * 0.15 + prm['dri_production'] * 0.06
        scrap_supply = (flw['recycling => scrap_market'] +
                        flw['forming => scrap_market'] +
                        flw['fabrication => scrap_market'])
        scrap_supply = transform_t_to_hist(scrap_supply, dims=mfa.dims).sum_nda_over('e')

        ap_demand = PlotlyArrayPlotter(
            array=scrap_demand,
            intra_line_dim='Historic Time',
            subplot_dim='Region',
            line_label='Scrap Demand',
            display_names=self.display_names
        )

        fig = ap_demand.plot()

        ap_supply = PlotlyArrayPlotter(
            array=scrap_supply,
            intra_line_dim='Historic Time',
            subplot_dim='Region',
            line_label='Scrap Supply',
            fig=fig,
            xlabel='Year',
            ylabel='Scrap [t]',
            display_names=self.display_names,
            title='Regional Scrap Demand and Supply'
        )

        save_path = os.path.join(self.output_path, 'figures',
                                 'scrap_demand_supply_by_region.png') if self.do_save_figs else None
        ap_supply.plot(save_path=save_path, do_show=self.do_show_figs)

        # plot global demand and supply
        scrap_demand = scrap_demand.sum_nda_over('r')
        scrap_supply = scrap_supply.sum_nda_over('r')

        ap_demand = PlotlyArrayPlotter(
            array=scrap_demand,
            intra_line_dim='Historic Time',
            line_label='Scrap Demand',
            display_names=self.display_names,
        )

        fig = ap_demand.plot()

        ap_supply = PlotlyArrayPlotter(
            array=scrap_supply,
            intra_line_dim='Historic Time',
            line_label='Scrap Supply',
            fig=fig,
            xlabel='Year',
            ylabel='Scrap [t]',
            display_names=self.display_names,
            title='Global Scrap Demand and Supply'
        )

        save_path = os.path.join(self.output_path, 'figures',
                                 'scrap_demand_supply_global.png') if self.do_save_figs else None
        ap_supply.plot(save_path=save_path, do_show=self.do_show_figs)

    def visualize_sector_splits(self, mfa: MFASystem):
        flw = mfa.flows

        fabrication = flw['fabrication => use']
        fabrication = fabrication.sum_nda_over(('e',))
        sector_splits = fabrication.get_shares_over('g')

        ap_sector_splits = PlotlyArrayPlotter(
            array=sector_splits,
            intra_line_dim='Time',
            subplot_dim='Region',
            linecolor_dim='Good',
            xlabel='Year',
            ylabel='Sector Splits [%]',
            display_names=self.display_names,
            title='Regional Fabrication Sector Splits'
        )

        save_path = os.path.join(self.output_path, 'figures',
                                 'sector_splits_regional.png') if self.do_save_figs else None
        ap_sector_splits.plot(save_path=save_path, do_show=self.do_show_figs)

        # plot global sector splits
        fabrication = fabrication.sum_nda_over('r')
        sector_splits = fabrication.get_shares_over('g')

        ap_sector_splits = PlotlyArrayPlotter(
            array=sector_splits,
            intra_line_dim='Time',
            linecolor_dim='Good',
            xlabel='Year',
            ylabel='Sector Splits [%]',
            display_names=self.display_names,
            title='Global Fabrication Sector Splits'
        )

        save_path = os.path.join(self.output_path, 'figures',
                                 'sector_splits_global.png') if self.do_save_figs else None
        ap_sector_splits.plot(save_path=save_path, do_show=self.do_show_figs)
