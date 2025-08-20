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
        self.compute_carbon_flow()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    def compute_in_use_stock(self, cement_stock_projection: fd.FlodymArray):
        prm = self.parameters
        stk = self.stocks
        # TODO calculate cement_ratio directly in mrindustry
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
        flw["prod_cement => sysenv"][...] = (
            flw["prod_cement => prod_product"] * (prm["cement_losses"] / (1 - prm["cement_losses"]))
        )
        flw["prod_clinker => prod_cement"][...] = (
            (flw["prod_cement => prod_product"] + flw["prod_cement => sysenv"]) * prm["clinker_ratio"]
        )
        flw["prod_clinker => sysenv"][...] = (
            flw["prod_clinker => prod_cement"] * prm["clinker_losses"]
        )
        # sysenv flows for mass balance
        flw["sysenv => prod_cement"][...] = (
            (flw["prod_cement => prod_product"] + flw["prod_cement => sysenv"]) * (1 - prm["clinker_ratio"])
        )
        flw["sysenv => prod_product"][...] = flw["prod_product => use"] * (
            1 - cement_ratio
        )

    def compute_other_stocks(self):
        flw = self.flows
        stk = self.stocks

        # eol
        flw["use => eol"][...] = stk["in_use"].outflow
        stk["eol"].inflow[...] = flw["use => eol"]
        stk["eol"].lifetime_model.set_prms(mean=np.inf)
        stk["eol"].compute()
        flw["eol => sysenv"][...] = stk["eol"].outflow

    def compute_carbon_flow(self):
        flw = self.flows
        stk = self.stocks
        prm = self.parameters

        # emissions
        flw["prod_clinker => atmosphere"][...] = (
            (flw["prod_clinker => prod_cement"] * prm["clinker_cao_ratio"] # clinker
            + flw["prod_clinker => sysenv"] * prm["ckd_cao_ratio"]) # CKD
            * prm["cao_emission_factor"]
        )
        stk["atmosphere"].inflow = flw["prod_clinker => atmosphere"]
        flw["sysenv => prod_clinker"][...] = (
            flw["prod_clinker => prod_cement"] + flw["prod_clinker => atmosphere"] + flw["prod_clinker => sysenv"]
        )
        
        # carbonation
        carbonation = self.calc_carbonation()
        flw["atmosphere => carbonation"][...] = carbonation
        stk["carbonated_co2"].inflow[...] = flw["atmosphere => carbonation"]
        stk["carbonated_co2"].lifetime_model.set_prms(mean=np.inf)
        stk["carbonated_co2"].compute()

        stk["atmosphere"].outflow[...] = stk["carbonated_co2"].inflow
        stk["atmosphere"].compute()
        
    
    def calc_carbonation(self) -> fd.FlodymArray:
        f = self.get_available_cao()
        k_free = self.get_eff_carbonation_rate(type="free")
        k_buried = self.get_eff_carbonation_rate(type="buried")

        uptake = fd.FlodymArray(dims=self.stocks["carbonated_co2"].dims)

        uptake["CKD"] = self.uptake_CKD()
        uptake["Construction Waste"] = self.uptake_construction_waste()
        uptake["In-Use Stock"] = self.uptake_in_use(f_in=f, k_free_in=k_free)
        uptake["End-of-Life Stock"] = self.uptake_eol(f_in=f, k_free_in=k_free, k_buried_in=k_buried)

        return uptake

    def uptake_CKD(self):
        """
        Assumes that 100 % of CaO in CKD is available for carbonation.
        Assumes that full carbonation takes 1 year.
        """
        prm = self.parameters
        ckd_prod = self.flows["prod_cement => sysenv"]
        uptake = ckd_prod * prm["ckd_landfill_share"] * prm["ckd_cao_ratio"] * prm["cao_emission_factor"]
        return uptake

    def uptake_construction_waste(self):
        """
        Calculated in terms of cement.
        Assumes that full carbonation takes 5 years and happens uniformly over that time.
        """
        prm = self.parameters
        cwaste_prod = self.flows["prod_cement => sysenv"]

        # calculate uptake in one year
        annual_carbonation_fraction = 0.2
        cao_content = cwaste_prod * prm["clinker_ratio"] * prm["clinker_cao_ratio"]
        uptake_one_year = cao_content * annual_carbonation_fraction  * prm["cao_carbonation_share"] * prm["cao_emission_factor"]

        # sum uptake over 5 years
        window_size = int(1/annual_carbonation_fraction)
        uptake_one_year_arr = uptake_one_year.cast_values_to(self.stocks["atmosphere"].dims)
        uptake_five_years_arr = self.rolling_sum(uptake_one_year_arr, window_size)
        uptake_five_years = fd.FlodymArray(dims=self.stocks["atmosphere"].dims, values=uptake_five_years_arr)
                
        return uptake_five_years

    @staticmethod
    def rolling_sum(arr: np.ndarray, window: int):
        if window <= 1:
            return arr
        c = np.cumsum(arr, axis=0)
        # the first entries are already correct
        out = c.copy()
        # for the rest, subtract everything before the window
        out[window:] = c[window:] - c[:-window]
        return out

    def uptake_in_use(self, f_in: fd.FlodymArray, k_free_in: fd.FlodymArray) -> fd.FlodymArray:
        stk = self.stocks["in_use"]
        stk_dims = stk.dims

        # Numpy calculations are unfortunately necessary. Therefore, we convert all flodym arrays to numpy arrays.
        # To ensure that the dimensions are correct, we cast them to the stock dimensions.

        # f describes the available density of CaO in product available for carbonation 
        f_in_arr = f_in.cast_values_to(stk_dims)
        # k is the carbonation rate (mm/sqrt(year))
        k_free_in_arr = k_free_in.cast_values_to(stk_dims)
        thickness_arr = self.parameters["product_thickness"].cast_values_to(stk_dims)

        carbonation = np.zeros(stk.dims.shape)
        
        for t in range(1, stk._n_t):
            
            # differentiate stock by age cohorts
            ages, mass = self.get_age_distribution(stk, t)
            # mass is shape (t + 1, stocks.shape without time)

            # select only cohorts that are younger than (or equal to) t
            # TODO remove first cohort, adjust ages/mass from get_age_distribution accordingly
            # We can do this because in first cohort, age is 0, so no carbonation has happened yet.
            f = f_in_arr[:t + 1, ...]
            k = k_free_in_arr[:t + 1, ...]
            thickness = thickness_arr[:t + 1, ...]

            # area available for carbonation
            area_density = mass / thickness
            
            # already carbonated depth (from previous year)
            # TODO this calculation could be taken from previous step in loop
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

        uptake = fd.FlodymArray(dims=stk_dims, values=carbonation)

        return uptake
    
    def get_available_cao(self) -> fd.FlodymArray:
        """
        Returns the available CaO for carbonation in the in-use stock.
        """
        prm = self.parameters
        cement_ratio = prm["product_cement_content"] / prm["product_density"]
        f = cement_ratio * prm["clinker_ratio"] * prm["clinker_cao_ratio"] * prm["cao_emission_factor"] * prm["cao_carbonation_share"]
        return f
        
    
    def get_eff_carbonation_rate(self, type) -> fd.FlodymArray:
        """
        Returns the effective carbonation rate for the in-use stock.
        """
        prm = self.parameters

        if type == "free":
            rate = self.parameters["carbonation_rate"]
            multiplier = prm["carbonation_rate_coating"] * prm["carbonation_rate_additives"] * prm["carbonation_rate_co2"]
        elif type == "buried":
            rate = self.parameters["carbonation_rate_buried"]
            multiplier = 1
        else:
            raise ValueError(f"Unknown carbonation type: {type}. Must be either 'free' or 'buried'.")
        
        k = rate * multiplier
        return k


    @staticmethod
    def get_age_distribution(stock: fd.DynamicStockModel, t: int, data_type: str = "stock") -> tuple[np.ndarray, np.ndarray]:
        """
        Returns the histogram of ages of either stock or outflow at time step t.
        
        Parameters
        ----------
        stock : fd.DynamicStockModel
            The stock model object
        t : int
            The time step to analyze
        data_type : str, optional
            Type of data to retrieve: "stock" or "outflow", by default "stock"
            
        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            A tuple containing (ages, values_by_age)
        """
        
        if data_type == "stock":
            data_by_cohort = stock.get_stock_by_cohort()
        elif data_type == "outflow":
            data_by_cohort = stock.get_outflow_by_cohort()
        else:
            raise ValueError(f"Unknown data_type: {data_type}. Must be either 'stock' or 'outflow'")
        
        # check if there are any cohorts older than system age
        if not np.all(data_by_cohort[t, t+1:, ...] == 0):
            raise RuntimeError(f"Nonzero {data_type} found at t={t} for cohorts older than system age!")

        # select time t and all cohorts up to t from data
        data_by_age = data_by_cohort[t, : t + 1, ...]

        # Only consider cohorts c <= t
        ages = np.arange(t + 1)[::-1]  # age 0 is newest, t is oldest
        # reshape to match data dimensions
        ages = ages.reshape((-1,) + (1,) * (data_by_age.ndim - 1))

        return ages, data_by_age

    def uptake_eol(self, f_in: fd.FlodymArray, k_free_in: fd.FlodymArray, k_buried_in: fd.FlodymArray) -> fd.FlodymArray:
        # consider only left over volume after carbonation durin in-use and demolition
        # I could have fixed lifetime for demolition

        # TODO add differentiation of carbonation rate by recycled/buried
        # waste is either recycled (= going to new concret as filler) or buried (= landfill/road base, asphalt)
        # recycled = X88, buried = 1 - recycled

        # (1) get outflow by cohort
        # (2) get carbonation depth by cohort
        # (3) calculate uncarbonated fraction by cohort
        # (4) calculate carbonation following spherical particle model

        # particles smaller than 2d are carbonated fully (size measured by diameter)
        # particles with min smaller than 2d but max larger than 2d:
            # until 2d carbonated fully (1)
            # 2d - max carbonated in shell
        # particles with min larger than 2d: carbonated in shell

        prm = self.parameters
        stk_in_use = self.stocks["in_use"]
        k_free_arr = k_free_in.cast_values_to(stk_in_use.dims)
        f_in_arr = f_in.cast_values_to(stk_in_use.dims)
        thickness_in = self.parameters["product_thickness"].cast_values_to(stk_in_use.dims)

        uncarbonated_inflow = np.zeros(stk_in_use.dims.shape)

        for t in range(1, self.stocks["in_use"]._n_t):
            
            # (1) get outflow by cohort
            ages, inflow = self.get_age_distribution(self.stocks["in_use"], t, data_type="outflow")

            # (2) get carbonation depth by cohort
            k_free = k_free_arr[:t + 1, ...]
            d_in_use = np.sqrt(np.maximum(ages - 1, 0)) * k_free

            # (3) calculate uncarbonated mass by cohort
            thickness = thickness_in[:t + 1, ...]
            d_available = np.maximum(thickness - d_in_use, 0)
            uncarbonated_fraction = d_available / thickness

            # sum over all age cohorts, convert to flodym array
            uncarbonated_inflow[t] = (inflow * uncarbonated_fraction).sum(axis=(0))
        
        uncarbonated_inflow = fd.FlodymArray(dims=stk_in_use.dims, values=uncarbonated_inflow)

        new_dims = self.stocks["eol"].dims.union_with(prm["waste_size_min"].dims)
        sum_dims = self.stocks["eol"].dims.intersect_with(new_dims)
        uncarbonated_inflow = uncarbonated_inflow.sum_to(sum_dims)
        # waste size share is given by mass
        mass = (uncarbonated_inflow * prm["waste_type_split"] * prm["waste_size_share"]).cast_values_to(new_dims)
        
        uncarbonated_inflow.cast_values_to(new_dims)
        a = prm["waste_size_min"].cast_values_to(new_dims)
        b = prm["waste_size_max"].cast_values_to(new_dims)
        k_buried_arr = k_buried_in.cast_values_to(new_dims)
        k_free_arr = k_free_in.cast_values_to(new_dims)
        f_in_arr = f_in.cast_values_to(new_dims)

        carbonation = np.zeros(self.stocks["eol"].dims.shape)

        # (4) calculate carbonation following spherical particle model
        for t in range(1, self.stocks["in_use"]._n_t):

            ages = np.arange(1, t + 1)[::-1]
            ages = ages.reshape((-1,) + (1,) * (new_dims.ndim - 1))
            
            # TODO separate this into a function
            k_free = k_free_arr[1:t + 1, ...] # TODO actually use this for recycled concrete.
            k_buried = k_buried_arr[1:t + 1, ...]
            f_in_use = f_in_arr[1:t + 1, ...]

            # integrate demolition uptake: for demolition_time, carbonation is happening freely, then buried
            demolition_time = 0.4 # years, based on Cao2024
            np.full_like(ages, demolition_time, dtype=np.float64)
            ages = ages - demolition_time

            # already carbonated depth (from previous year).
            previous_ages = np.maximum(ages - 1, 0)
            # demolition_time only applies if cohort is old enough
            previous_demolition_time = np.where(previous_ages >= 0, demolition_time, np.maximum(ages - 1 + demolition_time, 0))
            d = np.sqrt(previous_demolition_time * k_free ** 2 + previous_ages * k_buried ** 2)
            # additional depth after one year of carbonation
            d_add = np.sqrt(demolition_time * k_free ** 2 + ages * k_buried ** 2) - d

            a_cut = a[1:t + 1, ...]
            b_cut = b[1:t + 1, ...]
            new_carbonated_volume = self.get_volume_sphere_slice(a_cut, b_cut, d, d_add)
            new_carbonated_share = new_carbonated_volume / self.get_volume_sphere(a_cut, b_cut)
            new_carbonated_mass = new_carbonated_share * mass[t]
            added_co2 = new_carbonated_mass * f_in_use
            carbonation[t] = added_co2.sum(axis=(0,-2, -1))

        return fd.FlodymArray(dims=self.stocks["eol"].dims, values=carbonation)
    
    @staticmethod
    def get_volume_sphere_slice(a : np.ndarray, b: np.ndarray, d: np.ndarray, dadd: np.ndarray) -> np.ndarray:
        """
        Calculate the volume of a spherical shell with thickness dadd,
        which is located a distance d from the outside of the sphere.
        The sphere radius is distributed unifomly between a/2 and b/2.
        """
        rmin = a/2
        rmax = b/2

        # sanity checks
        if np.any(rmin < 0) or np.any(rmax < 0) or np.any(d < 0) or np.any(dadd < 0):
            raise ValueError("All parameters must be non-negative.")
        if (rmin >= rmax).any():
            raise ValueError("rmin must be smaller than rmax.")

        factor = np.pi / (3 * (rmax - rmin))
        large_sphere = np.maximum(rmax - d, 0) ** 4 - np.maximum(rmin - d, 0) ** 4
        small_sphere = np.maximum(rmax - d - dadd, 0) ** 4 - np.maximum(rmin - d - dadd, 0) ** 4
        return factor * (large_sphere - small_sphere)
    
    @staticmethod
    def get_volume_sphere(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """
        Calculate the volume of a sphere with radius distributed uniformly between a/2 and b/2.
        """
        rmin = a / 2
        rmax = b / 2

        # sanity checks
        if np.any(rmin < 0) or np.any(rmax < 0):
            raise ValueError("All parameters must be non-negative.")
        if (rmin >= rmax).any():
            raise ValueError("rmin must be smaller than rmax.")

        factor = np.pi / (3 * (rmax - rmin))
        return factor * (rmax ** 4 - rmin ** 4)