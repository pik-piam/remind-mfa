import os
from sodym.mfa_system import MFASystem
from sodym.export.array_plotter import PlotlyArrayPlotter
from simson.common.custom_export import CustomDataExporter
from simson.common.data_transformations import transform_t_to_hist


class SteelDataExporter(CustomDataExporter):
    scrap_demand_supply: dict = {'do_visualize': True}

    def visualize_results(self, mfa: MFASystem):
        super().visualize_results(mfa)
        if self.scrap_demand_supply['do_visualize']:
            self.visualise_scrap_demand_supply(mfa)

    def visualise_scrap_demand_supply(self, mfa: MFASystem):
        flw = mfa.flows
        prm = mfa.parameters
        scp = mfa.scalar_parameters

        production = prm['production']
        total_production = flw['forming => ip_market'] / prm['forming_yield'] / scp['production_yield']
        dri = (prm['dri_production'] + prm['dri_imports'] - prm['dri_exports'])
        pigiron = (prm['pigiron_production'] + prm['pigiron_imports'] - prm['pigiron_exports'] - prm['pigiron_to_cast'])

        total_production = transform_t_to_hist(total_production, dims=mfa.dims)
        scrap_demand = total_production - pigiron - dri
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
            display_names=self.display_names
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
            display_names=self.display_names
        )

        fig = ap_demand.plot()

        ap_supply = PlotlyArrayPlotter(
            array=scrap_supply,
            intra_line_dim='Historic Time',
            line_label='Scrap Supply',
            fig=fig,
            xlabel='Year',
            ylabel='Scrap [t]',
            display_names=self.display_names
        )

        save_path = os.path.join(self.output_path, 'figures',
                                 'scrap_demand_supply_global.png') if self.do_save_figs else None
        ap_supply.plot(save_path=save_path, do_show=self.do_show_figs)

    def visualize_production(self, mfa: MFASystem):
        ap_modeled = PlotlyArrayPlotter(
            array=mfa.stocks['in_use'].inflow['World'].sum_nda_over(('m', 'e')),
            intra_line_dim='Time',
            subplot_dim='Good',
            line_label='Modeled',
            display_names=self.display_names
        )
        fig = ap_modeled.plot()
        ap_historic = PlotlyArrayPlotter(
            array=mfa.parameters['production']['World'],
            intra_line_dim='Historic Time',
            subplot_dim='Good',
            line_label='Historic Production',
            fig=fig,
            xlabel='Year',
            ylabel='Production [t]',
            display_names=self.display_names
        )
        save_path = os.path.join(self.output_path, 'figures', 'production.png') if self.do_save_figs else None
        ap_historic.plot(save_path=save_path, do_show=self.do_show_figs)
