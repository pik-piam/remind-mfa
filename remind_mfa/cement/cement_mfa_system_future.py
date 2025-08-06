import numpy as np
import flodym as fd

from remind_mfa.common.assumptions_doc import add_assumption_doc


class StockDrivenCementMFASystem(fd.MFASystem):

    def compute(self, stock_projection: fd.FlodymArray):
        """
        Perform all computations for the MFA system.
        """
        self.compute_in_use_stock(stock_projection)
        self.compute_flows()
        self.compute_other_stocks()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    def compute_in_use_stock(self, cement_stock_projection: fd.FlodymArray):
        prm = self.parameters
        stk = self.stocks

        stk["in_use"].stock = cement_stock_projection * prm["cement_use_split"] / prm["cement_ratio"]
        
        stk["in_use"].lifetime_model.set_prms(
            mean=prm["future_use_lifetime_mean"],
            std=0.4 * prm["future_use_lifetime_mean"],
        )
        add_assumption_doc(
            type="expert guess",
            value=0.4,
            name="Standard deviation of future use lifetime",
            description="The standard deviation of the future use lifetime is set to 20 percent of the mean.",
        )
        stk["in_use"].compute()

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows
        stk = self.stocks

        # go backwards from in-use stock
        flw["prod_product => use"][...] = stk["in_use"].inflow

        add_assumption_doc(
            type="ad-hoc fix",
            name="Regional product production is actually apparent consumption.",
            description=(
                "The concrete stock considers both cement production and trade. "
                "The concrete production is constructed by concrete stock. "
                "The regional concrete production does not consider trade, "
                "therefore, it is actually apparent consumption. "
                "With this fix, we do not have any regional production jumps "
                "between historical and future data, as trade is not yet modeled in the future."
                "This fix propagates through to cement and clinker production."
            ),
        )

        flw["prod_cement => prod_product"][...] = (
            flw["prod_product => use"] * prm["cement_ratio"] 
        )
        flw["prod_clinker => prod_cement"][...] = (
            flw["prod_cement => prod_product"] * prm["clinker_ratio"]
        )
        # sysenv flows for mass balance
        flw["sysenv => prod_cement"][...] = flw["prod_cement => prod_product"] * (
            1 - prm["clinker_ratio"]
        )
        flw["sysenv => prod_product"][...] = flw["prod_product => use"] * (
            1 - prm["cement_ratio"]
        )

    def compute_other_stocks(self):
        flw = self.flows
        stk = self.stocks
        prm = self.parameters

        # eol
        flw["use => eol"][...] = stk["in_use"].outflow
        stk["eol"].inflow[...] = flw["use => eol"]
        stk["eol"].outflow[...] = fd.FlodymArray(dims=self.dims["t", "r", "s", "e"])
        stk["eol"].compute()
        flw["eol => sysenv"][...] = stk["eol"].outflow

        # emissions
        flw["prod_clinker => atmosphere"][...] = (
            flw["prod_clinker => prod_cement"] * self.parameters["cao_ratio"] * prm["cao_emission_factor"]
        )
        stk["atmosphere"].inflow = flw["prod_clinker => atmosphere"]
        flw["sysenv => prod_clinker"][...] = (
            flw["prod_clinker => prod_cement"] + flw["prod_clinker => atmosphere"]
        )

        # carbonation
        # f is fraction of cao in the end-use product
        dims = stk["in_use"].dims.drop("t")
        # TODO add propper clinker ratio in here
        f = np.expand_dims((prm["cao_ratio"] * 0.85 * prm["cement_ratio"] * prm["cao_emission_factor"]).cast_to(dims).values, 0) #prm["clinker_ratio"]
        k = np.expand_dims(prm["carbonation_rate"].cast_to(dims).values, 0)
        thickness = np.expand_dims(prm["product_thickness"].cast_to(dims).values, 0)
        density = np.expand_dims(prm["product_density"].cast_to(dims).values, 0)

        carbonation = np.zeros(stk["in_use"].dims.shape)
        
        for t in range(1, stk["in_use"]._n_t):
            
            # differentiate stock by age cohorts
            ages, mass = stk["in_use"].get_stock_age_histogram(t)
            # mass is shape (t + 1, stocks.shape without time)
            # ages needs to be reshaped to match all other variables (first dimension is age, rest empty)
            ages = ages.reshape((-1,) + (1,) * dims.ndim)

            # area available for carbonation
            area = mass / (density * thickness)
            
            # already carbonated depth (from previous year)
            d = np.sqrt(np.maximum(ages - 1, 0)) * k

            # additional depth after one year of carbonation
            d_add = np.sqrt(ages) * k - d
            
            # maximum available depth for carbonation
            d_available = np.maximum(thickness - d, 0)

            # fill co2 in avaiable depth if previously calculated additional depth is too large
            d_add = np.where(d_add > d_available, d_available, d_add)

            # calculated co2 removed from atmosphere by carbonation
            added_co2 = d_add * f * area

            # sum over all age cohorts
            carbonation[t] = added_co2.sum(axis=(0))

        carbonation = fd.FlodymArray(dims=stk["in_use"].dims, values=carbonation)
        
        flw["atmosphere => carbonation"][...] = carbonation
        stk["carbonated_co2"].inflow[...] = flw["atmosphere => carbonation"]
        stk["carbonated_co2"].outflow[...] = fd.FlodymArray(dims=self.dims["t", "r", "e"])
        stk["atmosphere"].outflow[...] = stk["carbonated_co2"].inflow
        stk["atmosphere"].compute()
        stk["carbonated_co2"].compute()