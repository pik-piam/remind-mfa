import flodym as fd

from simson.common.custom_export import CustomDataExporter

class CementDataExporter(CustomDataExporter):
    # TODO: understand why this is not imported from cement.yml
    clinker_production: dict = {"do_visualize": True}
    cement_production: dict = {"do_visualize": True}
    concrete_production: dict = {"do_visualize": True}
    use_stock: dict = {"do_visualize": True}
    eol_stock: dict = {"do_visualize": True}

    _display_names: dict = {
        "sysenv": "System environment",
        "raw_meal_preparation": "Raw meal preparation",
        "clinker_production": "Clinker production",
        "cement_grinding": "Cement grinding",
        "concrete_production": "Concrete production",
        "use": "Use phase",
        "eol": "End of life",
    }

    def visualize_results(self, mfa: fd.MFASystem):
        if self.clinker_production["do_visualize"]:
            self.visualize_clinker_production(mfa)
        if self.cement_production["do_visualize"]:
            self.visualize_cement_production(mfa)
        if self.concrete_production["do_visualize"]:
            self.visualize_concrete_production(mfa)
        # if self.use_stock["do_visualize"]:
        #     self.visualize_use_stock(mfa)
        # if self.eol_stock["do_visualize"]:
        #     self.visualize_eol_stock(mfa)
        if self.sankey["do_visualize"]:
            self.visualize_sankey(mfa)
        self.stop_and_show()

    def visualize_production(self, production: fd.Flow, name: str):

        # ap_production = self.plotter_class(
        #     array=production,
        #     intra_line_dim="Historic Time",
        #     subplot_dim="Region",
        #     line_label=f"{name} Production",
        #     display_names=self._display_names,
        #     xlabel="Year",
        #     ylabel="Production [t]",
        #     title=f"Regional {name} Production",
        # )

        # self.plot_and_save_figure(ap_production, f"{name}_production_regional.png")

        # TODO fix global production
        if "r" in production.dims.letters:
            global_production = production.sum_over("r")
        else:
            global_production = production

        ap_global_production = self.plotter_class(
            array=global_production,
            intra_line_dim="Historic Time",
            line_label=f"{name} Production",
            display_names=self._display_names,
            xlabel="Year",
            ylabel="Production [t]",
            title=f"Global {name} Production",
        )

        self.plot_and_save_figure(ap_global_production, f"{name}_production_global.png")


    def visualize_clinker_production(self, mfa: fd.MFASystem):
        production = mfa.flows["clinker_production => cement_grinding"]
        self.visualize_production(production, "Clinker")
    
    def visualize_cement_production(self, mfa: fd.MFASystem):
        production = mfa.flows["cement_grinding => concrete_production"]
        self.visualize_production(production, "Cement")

    def visualize_concrete_production(self, mfa: fd.MFASystem):
        production = mfa.flows["concrete_production => use"].sum_over("s")
        self.visualize_production(production, "Concrete")