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
        cement_ratio = prm["product_cement_content"] / prm["product_density"]

        stk["in_use"].stock = (
            cement_stock_projection 
            * prm["product_material_split"]
            * prm["product_material_application_transform"]
            * prm["product_application_split"]
            / cement_ratio
        )

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
        cement_ratio = prm["product_cement_content"] / prm["product_density"]

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
            flw["prod_product => use"] * cement_ratio
        )
        flw["prod_clinker => prod_cement"][...] = (
            flw["prod_cement => prod_product"] * prm["clinker_ratio"]
        )
        # sysenv flows for mass balance
        flw["sysenv => prod_cement"][...] = flw["prod_cement => prod_product"] * (
            1 - prm["clinker_ratio"]
        )
        flw["sysenv => prod_product"][...] = flw["prod_product => use"] * (
            1 - cement_ratio
        )

    def compute_other_stocks(self):
        flw = self.flows
        stk = self.stocks
        prm = self.parameters

        # eol
        flw["use => eol"][...] = stk["in_use"].outflow
        stk["eol"].inflow[...] = flw["use => eol"]
        stk["eol"].outflow[...] = fd.FlodymArray(dims=self.dims["t", "r", "s", "m", "a"])
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
        carbonation = self.calc_carbonation()
        flw["atmosphere => carbonation"][...] = carbonation
        stk["carbonated_co2"].inflow[...] = flw["atmosphere => carbonation"]
        stk["carbonated_co2"].outflow[...] = fd.FlodymArray(dims=self.dims["t", "r", "m"])
        stk["atmosphere"].outflow[...] = stk["carbonated_co2"].inflow
        stk["atmosphere"].compute()
        stk["carbonated_co2"].compute()

    def calc_carbonation(self) -> fd.FlodymArray:
        stk = self.stocks
        prm = self.parameters
        
        dims = stk["in_use"].dims

        # Numpy calculations are unfortunately necessary. Therefore, we convert all flodym arrays to numpy arrays.
        # To ensure that the dimensions are correct, we cast them to the stock dimensions before.
        # f describes the available density of CaO in product available for carbonation 
        f_in = (prm["cao_ratio"] * prm["product_cement_content"] * prm["clinker_ratio"] * prm["cao_emission_factor"] * prm["cao_carbonation_share"]).cast_to(dims).values
        # k is the carbonation rate (mm/sqrt(year))
        k_in = (prm["carbonation_rate"] * prm["carbonation_rate_coating"] * prm["carbonation_rate_additives"] * prm["carbonation_rate_co2"]).cast_to(dims).values
        thickness_in = prm["product_thickness"].cast_to(dims).values

        carbonation = np.zeros(stk["in_use"].dims.shape)
        
        for t in range(1, stk["in_use"]._n_t):
            
            # differentiate stock by age cohorts
            ages, mass = self.get_stock_age_histogram(stk["in_use"], t)
            # mass is shape (t + 1, stocks.shape without time)

            # select only cohorts that are younger than (or equal to) t
            f = f_in[:t + 1, ...]
            k = k_in[:t + 1, ...]
            thickness = thickness_in[:t + 1, ...]

            # area available for carbonation
            area_density = mass / thickness
            
            # already carbonated depth (from previous year)
            d = np.sqrt(np.maximum(ages - 1, 0)) * k

            # additional depth after one year of carbonation
            d_add = np.sqrt(ages) * k - d
            
            # maximum available depth for carbonation
            d_available = np.maximum(thickness - d, 0)

            # fill co2 in avaiable depth if previously calculated additional depth is too large
            d_add = np.where(d_add > d_available, d_available, d_add)

            # calculated co2 removed from atmosphere by carbonation
            added_co2 = d_add * f * area_density

            # sum over all age cohorts
            carbonation[t] = added_co2.sum(axis=(0))

        carbonation = fd.FlodymArray(dims=stk["in_use"].dims, values=carbonation)

        return carbonation

    @ staticmethod
    def get_stock_age_histogram(stock: fd.DynamicStockModel, t: int) -> tuple[np.ndarray, np.ndarray]:
        """
        Returns the histogram of ages of the stock at time step t.
        """
        
        stock_by_cohort = stock.get_stock_by_cohort()

        # check if there are any cohorts older than system age
        if not np.all(stock_by_cohort[t, t+1:, ...] == 0):
            raise RuntimeError(f"Nonzero stock found at t={t} for cohorts older than system age!")

        # select time t and all cohorts up to t from stock
        stock_by_age = stock_by_cohort[t, : t + 1, ...]

        # Only consider cohorts c <= t
        ages = np.arange(t + 1)[::-1]  # age 0 is newest, t is oldest
        # reshape to match stock dimensions
        ages = ages.reshape((-1,) + (1,) * (stock_by_age.ndim - 1))

        return ages, stock_by_age
    
    @staticmethod
    def uptake_CKD(CKD, clinker_to_cement_ratio, cao_ratio, landfilled_ratio, cao_carbonation_proportion, cao_emission_factor):
        return CKD * clinker_to_cement_ratio * cao_ratio * landfilled_ratio * cao_carbonation_proportion * cao_emission_factor

    @staticmethod
    def uptake_construction_waste():
        return None

