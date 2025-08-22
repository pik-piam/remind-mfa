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
        # TODO carbon flow calculation should be made optional du to computational cost
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
        # cement losses are on top of the inflow of stock, but are relative to total cement production
        flw["prod_cement => sysenv"][...] = (
            flw["prod_cement => prod_product"] * (prm["cement_losses"] / (1 - prm["cement_losses"]))
        )
        # clinker production is based on cement production
        flw["prod_clinker => prod_cement"][...] = (
            (flw["prod_cement => prod_product"] + flw["prod_cement => sysenv"]) * prm["clinker_ratio"]
        )
        # clinker losses (CKD) are on top of clinker production.
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

        # emissions (process only)
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
        # get parameters for calculation
        f = self.get_available_cao()
        k_free = self.get_eff_carbonation_rate(type="free")
        k_buried = self.get_eff_carbonation_rate(type="buried")

        # collect uptake from all sources
        uptake = fd.FlodymArray(dims=self.stocks["carbonated_co2"].dims)
        uptake["CKD"] = self.uptake_CKD()
        uptake["Construction Waste"] = self.uptake_construction_waste()
        uptake["In-Use Stock"] = self.uptake_in_use(f_in=f, k_free_in=k_free)
        # TODO potentially differentiate between demolition and eol
        uptake["End-of-Life Stock"] = self.uptake_eol(f_in=f, k_free_in=k_free, k_buried_in=k_buried)

        return uptake

    def uptake_CKD(self):
        """
        Assumes that 100 % of CaO in CKD is available for carbonation.
        Assumes that full carbonation takes 1 year.
        """
        prm = self.parameters
        ckd_prod = self.flows["prod_clinker => sysenv"]
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
        uptake_five_years_arr = self.windowed_sum(uptake_one_year_arr, window_size)
        uptake_five_years = fd.FlodymArray(dims=self.stocks["atmosphere"].dims, values=uptake_five_years_arr)
                
        return uptake_five_years

    @staticmethod
    def windowed_sum(arr: np.ndarray, window: int):
        """
        Calculates the rolling sum over axis 0 with window size `window`, i.e. only entries within window are cumulated.
        For the first window-1 rows, returns the cumulative sum (partial window).
        """
        if window <= 1:
            return arr
        c = np.cumsum(arr, axis=0)
        # the first entries are already correct
        out = c.copy()
        # for the rest, subtract everything before the window
        out[window:] = c[window:] - c[:-window]
        return out

    def uptake_in_use(self, f_in: fd.FlodymArray, k_free_in: fd.FlodymArray) -> fd.FlodymArray:
        """
        Uptake of CO2 by the in-use stock.
        Product mass is assumed to be distributed over thickness, leaving a free surface for carbonation.
        The carbonation depth is calculated following Fick's diffusion law, but cannot exceed the product thickness.
        The total carbonation in each year is calculated by collecting all contributions from previous years.
        """
        # TODO can in-use and eol uptake share code?
        
        stk = self.stocks["in_use"]
        stk_dims = stk.dims

        # create age dimension
        ages = [i for i in range(stk._n_t)][::-1]
        agedim = fd.Dimension(name="age", letter="u", items=ages, dtype=int)
        agedimset = fd.DimensionSet(dim_list=[agedim])
        age = fd.FlodymArray(dims=agedimset, values=np.array(ages), dtype=float)

        # (I) prepare relative carbonation per age
        # carbonation depth as per Fick's law
        d = age.apply(np.sqrt) * k_free_in
        # additional depth per year of aging (minus needed as ages are moving oldest to youngest)
        d_add = - d.apply(np.diff, kwargs={"append": 0, "axis": d.dims.index("u")})
        # available thickness that has not been carbonated yet
        thickness = self.parameters["product_thickness"].cast_to(d.dims)
        d_available = (thickness - d).maximum(0)
        self.shift_with_zero(d_available, axis="u", inplace=True)
        # correct d_add by available thickness
        d_add = d_add.minimum(d_available)
        # share of product that carbonates for each age
        rel_add = d_add / self.parameters["product_thickness"]

        # (II) calculate carbonation for each time step
        # TODO: vectorize this to improve performance
        carbonation = fd.FlodymArray(dims=stk_dims)

        for t in range(1, stk._n_t):
            # prepare dimension slices according to the current time step
            # TODO dynamically select dimension letters based on what is available
            sliced_age_dim = fd.Dimension(name="sliced age", letter="n", items=ages[len(ages)-t-1:], dtype=int)
            sliced_agedimset = fd.DimensionSet(dim_list=[sliced_age_dim])
            sliced_t_dim = fd.Dimension(name="sliced time", letter="o", items=stk_dims["t"].items[:t+1], dtype=int)

            # TODO rewrite age disribution since age might not be needed anymore?
            # get age cohort of products at time t
            _, mass_values = self.get_age_distribution(stk, t)
            mass_dims = sliced_agedimset.union_with(stk.dims).drop("t")
            mass = fd.FlodymArray(dims=mass_dims, values=mass_values)

            # slice parameters as necessary
            rel_add_sliced = rel_add[{"u": sliced_age_dim}]
            f_sliced = f_in[{"t": sliced_t_dim}] # time dimension from time-dependent clinker ratio
            f_sliced.dims.replace("o", sliced_age_dim, inplace=True)

            # calculate carbonated mass convert to CO2
            carbonated_mass = mass * rel_add_sliced
            carbonated_co2 = carbonated_mass * f_sliced
            carbonation[{"t": stk_dims["t"].items[t]}] = carbonated_co2.sum_over("n")

        return carbonation
    
    @staticmethod
    def shift_with_zero(a: fd.FlodymArray, axis: str, direction: str = "backward", inplace: bool = False) -> fd.FlodymArray:
        """
        Shift FlodymArray inplace by one along axis, inserting zeros.
        direction="forward": result[1:] = a[:-1]
        direction="backward": result[:-1] = a[1:]
        """
        axis = a.dims.index(axis)
        out = np.zeros_like(a.values)
        tgt = [slice(None)] * out.ndim
        src = [slice(None)] * out.ndim
        if direction == "forward":
            tgt[axis] = slice(1, None)
            src[axis] = slice(0, -1)
        elif direction == "backward":
            tgt[axis] = slice(0, -1)
            src[axis] = slice(1, None)
        else:
            raise ValueError("direction must be 'forward' or 'backward'")
        out[tuple(tgt)] = a.values[tuple(src)]

        if inplace:
            a.values = out
            return
        else:
            return fd.FlodymArray(dims=a.dims, values=out)
        
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
        """
        Carbonation of end-of-life stock.
        First (I), outflow from in-use stock is calculated that has not been carbonated yet.
        Then (II), carbonation during end-of-life is calculated.
        Here, the concrete is assumed to be crushed into spherical particles.
        First, for 0.4 years, particles are assumed to be exposed to air (demolition).
        After that, they are used for different waste categories, where they are either recycled or buried.
        This influences their carbonation rate (k).
        """

        prm = self.parameters
        stk_in_use = self.stocks["in_use"]
        k_free_arr = k_free_in.cast_values_to(stk_in_use.dims)
        thickness_in = self.parameters["product_thickness"].cast_values_to(stk_in_use.dims)

        uncarbonated_inflow = np.zeros(stk_in_use.dims.shape)

        for t in range(1, self.stocks["in_use"]._n_t):
            
            # (I1) get outflow by cohort
            ages, inflow = self.get_age_distribution(self.stocks["in_use"], t, data_type="outflow")

            # (I2) get carbonation depth by cohort
            k_free = k_free_arr[:t + 1, ...]
            d_in_use = np.sqrt(np.maximum(ages - 1, 0)) * k_free

            # (I3) calculate uncarbonated mass by cohort
            thickness = thickness_in[:t + 1, ...]
            d_available = np.maximum(thickness - d_in_use, 0)
            uncarbonated_fraction = d_available / thickness

            # (I4) sum over all age cohorts, convert to flodym array
            uncarbonated_inflow[t] = (inflow * uncarbonated_fraction).sum(axis=(0))
        
        uncarbonated_inflow = fd.FlodymArray(dims=stk_in_use.dims, values=uncarbonated_inflow)

        # (II) calculate further carbonation in EOL stock

        eol_dims = self.stocks["eol"].dims
        # split inflow by waste type and size, reduce unnecessary dimensions
        uncarbonated_inflow = uncarbonated_inflow.sum_to(eol_dims) * prm["waste_type_split"] * prm["waste_size_share"]

        # create new age dimension
        # TODO: replace ages creation with np.arange() but fd.DimensionSet fails as it doesn't accept it as int
        # when dtype = np.int64 selcted, the printing agedim becomes very ugly 
        ages = [i for i in range(self.stocks["in_use"]._n_t)][::-1]
        agedim = fd.Dimension(name="age", letter="u", items=ages, dtype=int)
        agedimset = fd.DimensionSet(dim_list=[agedim])
        age = fd.FlodymArray(dims=agedimset, values=np.array(ages), dtype=float)
        
        # TODO like in uptake_in_use, the zeroth year should not see carbonation, implement this using shift_with_zero
        # (II1) calculate t from demolition
        demolition_time = 0.4  # years, based on Cao2024
        demolition_age = fd.FlodymArray(dims=agedimset, values=np.full_like(ages, demolition_time, dtype=float))
        
        # equivalent age after demolition that the waste would have needed if carbonated buried
        equivalent_demolition_age = demolition_age * (k_free_in / k_buried_in) ** 2
        age_after_demolition = equivalent_demolition_age + age - demolition_time

        # (II2) calculated d from carbonation during eol
        # create effective k with waste dimension: recycled concrete is exposed to air, rest buried
        k = k_buried_in.cast_to(k_buried_in.dims.union_with(fd.DimensionSet(dim_list=[prm["waste_type_split"].dims["w"]])))
        k["new concrete"] = k_free_in
        d = k * age_after_demolition.apply(np.sqrt)

        # (II3) calculate added carbonation depth beteen two time steps
        d_add = - d.apply(np.diff, kwargs={"append":0, "axis":d.dims.index("u")})  # append 0 to match dimensions

        # (II4) convert carbonation depth to volume by spherical particle model
        a = prm["waste_size_min"]
        b = prm["waste_size_max"]
        sphere_volume = self.get_volume_sphere(a, b)
        carbonation_volume = self.get_volume_sphere_slice(a, b, d, d_add)
        carbonation_share = carbonation_volume / sphere_volume

        # (II5) calc carbonated product mass in each year by hard-coded convolution and subsequently convert to CO2
        new_carbonated_mass = fd.FlodymArray(dims=eol_dims)
        for i, t in enumerate(eol_dims["t"].items):
            # prepare dimensions accoring to the current time step
            sliced_age_dim = fd.Dimension(name="sliced age", letter="n", items=carbonation_share.dims["u"].items[len(ages) - i - 1:], dtype=int)
            sliced_t_dim = fd.Dimension(name="sliced time", letter="o", items=eol_dims["t"].items[:i+1], dtype=int)

            # slice with new dimensions
            sliced_carbonation_share = carbonation_share[{"u": sliced_age_dim}]
            # time of inflow can be directly translated to age (earliest inflow, oldest age)
            sliced_uncarbonated_inflow = uncarbonated_inflow[{"t": sliced_t_dim}]
            sliced_uncarbonated_inflow.dims.replace("o", sliced_age_dim, inplace=True)

            # calculate carbonated mass and sum over cohorts
            carbonated_mass = sliced_carbonation_share * sliced_uncarbonated_inflow
            new_carbonated_mass[{"t": t}] = carbonated_mass.sum_over("n")
        
        # (II6) translate carbonated product mass to co2, sum frequently to reduce dimension overhead
        added_co2 = new_carbonated_mass.sum_to(eol_dims.union_with(f_in.dims)) * f_in
        uptake = added_co2.sum_to(eol_dims)

        return uptake
        
    def get_volume_sphere_slice(self, a : fd.FlodymArray, b: fd.FlodymArray, d: fd.FlodymArray, dadd: fd.FlodymArray) -> fd.FlodymArray:
        """
        Calculate the volume of a spherical shell with thickness dadd,
        which is located a distance d from the outside of the sphere.
        The sphere radius is distributed unifomly between a/2 and b/2.
        """
        # get all inputs to the same dimensions
        dims = a.dims.union_with(b.dims).union_with(d.dims).union_with(dadd.dims)
        a = a.cast_to(dims)
        b = b.cast_to(dims)
        d = d.cast_to(dims)
        dadd = dadd.cast_to(dims)

        # radii from diameters
        rmin = a/2
        rmax = b/2

        # sanity checks
        if np.any(rmin.values < 0) or np.any(rmax.values < 0) or np.any(d.values < 0) or np.any(dadd.values < 0):
            raise ValueError("All parameters must be non-negative.")
        if (rmin.values >= rmax.values).any():
            raise ValueError("rmin must be smaller than rmax.")

        factor = np.pi / (3 * (rmax - rmin))
        large_sphere = (rmax - d).maximum(0) ** 4 - (rmin - d).maximum(0) ** 4
        small_sphere = (rmax - d - dadd).maximum(0) ** 4 -(rmin - d - dadd).maximum(0) ** 4
        return factor * (large_sphere - small_sphere)
    
    @staticmethod
    def get_volume_sphere(a: fd.FlodymArray, b: fd.FlodymArray) -> fd.FlodymArray:
        """
        Calculate the volume of a sphere with radius distributed uniformly between a/2 and b/2.
        """
        rmin = a / 2
        rmax = b / 2

        # sanity checks
        if np.any(rmin.values < 0) or np.any(rmax.values < 0):
            raise ValueError("All parameters must be non-negative.")
        if (rmin.values >= rmax.values).any():
            raise ValueError("rmin must be smaller than rmax.")

        factor = np.pi / (3 * (rmax - rmin))
        return factor * (rmax ** 4 - rmin ** 4)