import flodym as fd

class InflowDrivenHistoricCementMFASystem(fd.MFASystem):
    
    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.compute_flows()
        self.compute_in_use_stock()
        self.check_mass_balance()

    def compute_flows(self):
        pass

    def compute_in_use_stock(self):
        pass





