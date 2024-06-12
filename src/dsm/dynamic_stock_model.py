# -*- coding: utf-8 -*-
"""
Class DynamicStockModel
Check https://github.com/IndEcol/ODYM for latest version.

Methods for efficient handling of dynamic stock models (DSMs)

Created on Mon Jun 30 17:21:28 2014

@author: Stefan Pauliuk, NTNU Trondheim, Norway, later Uni Freiburg, Germany
with contributions from
Sebastiaan Deetman, CML, Leiden, NL
Tomer Fishman, IDC Herzliya, IL
Chris Mutel, PSI, Villingen, CH

standard abbreviation: DSM or dsm

dependencies:
    numpy >= 1.9
    scipy >= 0.14

Repository for this class, documentation, and tutorials: https://github.com/IndEcol/ODYM


ADAPTED FOR USE IN SIMSON PROJECT

"""

import numpy as np
import scipy.stats

def __version__():
    """Return a brief version string and statement for this class."""
    return str('1.0'), str('Class DynamicStockModel, dsm. Version 1.0. Last change: July 25th, 2019. Check https://github.com/IndEcol/ODYM for latest version.')


class DynamicStockModel(object):

    def __init__(self, t, inflow=None, outflow=None, stock=None, lifetime=None, stock_by_cohort=None, outflow_by_cohort=None, pdf=None, sf=None):
        """ Init function. Assign the input data to the instance of the object."""
        self.n_t = len(t)

        self.inflow = inflow
        self.stock = stock
        self.stock_by_cohort = stock_by_cohort
        self.outflow = outflow
        self.outflow_by_cohort = outflow_by_cohort

        if lifetime is not None:
            for key in lifetime.keys():
                # If we have the same scalar lifetime, stdDev, etc., for all cohorts,
                # replicate this value to full length of the time vector
                if key != 'Type':
                    if np.array(lifetime[key]).shape[0] == 1:
                        lifetime[key] = np.tile(lifetime[key], self.n_t)
        self.lifetime = lifetime

        self.pdf = pdf
        self.sf  = sf

    def compute_stock_driven(self):
        self.compute_stock_driven_model()
        self.compute_outflow_total()
        self.check_stock_balance()

    def compute_inflow_driven(self):
        self.compute_s_c_inflow_driven()
        self.compute_o_c_from_s_c()
        self.compute_stock_total()
        self.compute_outflow_total()
        self.check_stock_balance()

    def compute_stock_change(self):
        """ Determine stock change from time series for stock. Formula: stock_change(t) = stock(t) - stock(t-1)."""
        return np.diff(self.stock, prepend=0)

    def check_stock_balance(self):
        balance = self.get_stock_balance()
        balance = np.abs(balance).sum()
        if balance > 1:  # 1 tonne accuracy
            raise RuntimeError("Stock balance for dynamic stock model is too high: " + str(balance))
        elif balance > 0.001:
            print("Stock balance for model dynamic stock model is noteworthy: " + str(balance))

    def get_stock_balance(self):
        """ Check wether inflow, outflow, and stock are balanced. If possible, the method returns the vector 'Balance', where Balance = inflow - outflow - stock_change"""
        return self.inflow - self.outflow - self.compute_stock_change()

    def compute_stock_total(self):
        """Determine total stock as row sum of cohort-specific stock."""
        self.stock = self.stock_by_cohort.sum(axis=1)
        return self.stock

    def compute_outflow_total(self):
        """Determine total outflow as row sum of cohort-specific outflow."""
        self.outflow = self.outflow_by_cohort.sum(axis=1)
        return self.outflow

    def compute_outflow_from_mb(self):
        """Compute outflow from process via mass balance.
           Needed in cases where lifetime is zero."""
        self.outflow = self.inflow - self.compute_stock_change()
        return self.outflow

    """ Part 2: Lifetime model. """

    def compute_outflow_pdf(self):
        """
        Lifetime model. The method compute outflow_pdf returns an array year-by-cohort of the probability of a item added to stock in year m (aka cohort m) leaves in in year n. This value equals pdf(n,m).
        The pdf is computed from the survival table sf, where the type of the lifetime distribution enters.
        The shape of the output pdf array is NoofYears * NoofYears, but the meaning is years by age-cohorts.
        The method does nothing if the pdf alreay exists.
        """
        self.compute_sf() # computation of pdfs moved to this method: compute survival functions sf first, then calculate pdfs from sf.
        self.pdf = np.zeros((self.n_t, self.n_t))
        self.pdf[np.diag_indices(self.n_t)] = np.ones(self.n_t) - self.sf.diagonal(0)
        for m in range(0,self.n_t):
            self.pdf[np.arange(m+1,self.n_t),m] = -1 * np.diff(self.sf[np.arange(m,self.n_t),m])
        return self.pdf


    def compute_sf(self): # survival functions
        """
        Survival table self.sf(m,n) denotes the share of an inflow in year n (age-cohort) still present at the end of year m (after m-n years).
        The computation is self.sf(m,n) = ProbDist.sf(m-n), where ProbDist is the appropriate scipy function for the lifetime model chosen.
        For lifetimes 0 the sf is also 0, meaning that the age-cohort leaves during the same year of the inflow.
        The method compute outflow_sf returns an array year-by-cohort of the surviving fraction of a flow added to stock in year m (aka cohort m) in in year n. This value equals sf(n,m).
        This is the only method for the inflow-driven model where the lifetime distribution directly enters the computation. All other stock variables are determined by mass balance.
        The shape of the output sf array is NoofYears * NoofYears, and the meaning is years by age-cohorts.
        The method does nothing if the sf alreay exists. For example, sf could be assigned to the dynamic stock model from an exogenous computation to save time.
        """
        self.sf = np.zeros((self.n_t, self.n_t))
        # Perform specific computations and checks for each lifetime distribution:

        if self.lifetime['Type'] == 'Fixed': # fixed lifetime, age-cohort leaves the stock in the model year when the age specified as 'Mean' is reached.
            for m in range(0, self.n_t):  # cohort index
                self.sf[m::,m] = np.multiply(1, (np.arange(0,self.n_t-m) < self.lifetime['Mean'][m])) # converts bool to 0/1
            # Example: if Lt is 3.5 years fixed, product will still be there after 0, 1, 2, and 3 years, gone after 4 years.

        if self.lifetime['Type'] == 'Normal': # normally distributed lifetime with mean and standard deviation. Watch out for nonzero values
            # for negative ages, no correction or truncation done here. Cf. note below.
            for m in range(0, self.n_t):  # cohort index
                if self.lifetime['Mean'][m] != 0:  # For products with lifetime of 0, sf == 0
                    self.sf[m::,m] = scipy.stats.norm.sf(np.arange(0,self.n_t-m), loc=self.lifetime['Mean'][m], scale=self.lifetime['StdDev'][m])
                    # NOTE: As normal distributions have nonzero pdf for negative ages, which are physically impossible,
                    # these outflow contributions can either be ignored (violates the mass balance) or
                    # allocated to the zeroth year of residence, the latter being implemented in the method compute compute_o_c_from_s_c.
                    # As alternative, use lognormal or folded normal distribution options.

        if self.lifetime['Type'] == 'FoldedNormal': # Folded normal distribution, cf. https://en.wikipedia.org/wiki/Folded_normal_distribution
            for m in range(0, self.n_t):  # cohort index
                if self.lifetime['Mean'][m] != 0:  # For products with lifetime of 0, sf == 0
                    self.sf[m::,m] = scipy.stats.foldnorm.sf(np.arange(0,self.n_t-m), self.lifetime['Mean'][m]/self.lifetime['StdDev'][m], 0, scale=self.lifetime['StdDev'][m])
                    # NOTE: call this option with the parameters of the normal distribution mu and sigma of curve BEFORE folding,
                    # curve after folding will have different mu and sigma.

        if self.lifetime['Type'] == 'LogNormal': # lognormal distribution
            # Here, the mean and stddev of the lognormal curve,
            # not those of the underlying normal distribution, need to be specified! conversion of parameters done here:
            for m in range(0, self.n_t):  # cohort index
                if self.lifetime['Mean'][m] != 0:  # For products with lifetime of 0, sf == 0
                    # calculate parameter mu    of underlying normal distribution:
                    lt_ln = np.log(self.lifetime['Mean'][m] / np.sqrt(1 + self.lifetime['Mean'][m] * self.lifetime['Mean'][m] / (self.lifetime['StdDev'][m] * self.lifetime['StdDev'][m])))
                    # calculate parameter sigma of underlying normal distribution:
                    sg_ln = np.sqrt(np.log(1 + self.lifetime['Mean'][m] * self.lifetime['Mean'][m] / (self.lifetime['StdDev'][m] * self.lifetime['StdDev'][m])))
                    # compute survial function
                    self.sf[m::,m] = scipy.stats.lognorm.sf(np.arange(0,self.n_t-m), s=sg_ln, loc = 0, scale=np.exp(lt_ln))
                    # values chosen according to description on
                    # https://docs.scipy.org/doc/scipy-0.13.0/reference/generated/scipy.stats.lognorm.html
                    # Same result as EXCEL function "=LOGNORM.VERT(x;LT_LN;SG_LN;TRUE)"

        if self.lifetime['Type'] == 'Weibull': # Weibull distribution with standard definition of scale and shape parameters
            for m in range(0, self.n_t):  # cohort index
                if self.lifetime['Shape'][m] != 0:  # For products with lifetime of 0, sf == 0
                    self.sf[m::,m] = scipy.stats.weibull_min.sf(np.arange(0,self.n_t-m), c=self.lifetime['Shape'][m], loc = 0, scale=self.lifetime['Scale'][m])




    """
    Part 3: Inflow driven model
    Given: inflow, lifetime dist.
    Default order of methods:
    1) determine stock by cohort
    2) determine total stock
    2) determine outflow by cohort
    3) determine total outflow
    4) check mass balance.
    """

    def compute_s_c_inflow_driven(self):
        """ With given inflow and lifetime distribution, the method builds the stock by cohort.
        """
        self.compute_sf()
        self.stock_by_cohort = np.einsum('c,tc->tc', self.inflow, self.sf) # See numpy's np.einsum for documentation.
        # This command means: s_c[t,c] = i[c] * sf[t,c] for all t, c
        # from the perspective of the stock the inflow has the dimension age-cohort,
        # as each inflow(t) is added to the age-cohort c = t
        return self.stock_by_cohort

    def compute_o_c_from_s_c(self):
        """Compute outflow by cohort from stock by cohort."""
        self.outflow_by_cohort = np.zeros(self.stock_by_cohort.shape)
        self.outflow_by_cohort[1::,:] = -1 * np.diff(self.stock_by_cohort,n=1,axis=0)
        self.outflow_by_cohort[np.diag_indices(self.n_t)] = self.inflow - np.diag(self.stock_by_cohort) # allow for outflow in year 0 already
        return self.outflow_by_cohort

    def compute_i_from_s(self, initial_stock):
        """Given a stock at t0 broken down by different cohorts tx ... t0, an "initial stock".
           This method calculates the original inflow that generated this stock.
           Example:
        """
        assert len(initial_stock) == self.n_t
        self.inflow = np.zeros(self.n_t)
        # construct the sf of a product of cohort tc surviving year t
        # using the lifetime distributions of the past age-cohorts
        self.compute_sf()
        for cohort in range(0, self.n_t):
            if self.sf[-1,cohort] != 0:
                self.inflow[cohort] = initial_stock[cohort] / self.sf[-1,cohort]
            else:
                self.inflow[cohort] = 0  # Not possible with given lifetime distribution
        return self.inflow


    """
    Part 4: Stock driven model
    Given: total stock, lifetime dist.
    Default order of methods:
    1) determine inflow, outflow by cohort, and stock by cohort
    2) determine total outflow
    3) determine stock change
    4) check mass balance.
    """

    def compute_stock_driven_model(self, do_correct_negative_inflow = False):
        """ With given total stock and lifetime distribution,
            the method builds the stock by cohort and the inflow.
        """
        self.stock_by_cohort = np.zeros((self.n_t, self.n_t))
        self.outflow_by_cohort = np.zeros((self.n_t, self.n_t))
        self.inflow = np.zeros(self.n_t)
        # construct the sf of a product of cohort tc remaining in the stock in year t
        self.compute_sf() # Computes sf if not present already.
        # First year:
        if self.sf[0, 0] != 0: # Else, inflow is 0.
            self.inflow[0] = self.stock[0] / self.sf[0, 0]
        self.stock_by_cohort[:, 0] = self.inflow[0] * self.sf[:, 0] # Future decay of age-cohort of year 0.
        self.outflow_by_cohort[0, 0] = self.inflow[0] - self.stock_by_cohort[0, 0]
        # all other years:
        for m in range(1, self.n_t):  # for all years m, starting in second year
            # 1) Compute outflow from previous age-cohorts up to m-1
            self.outflow_by_cohort[m, 0:m] = self.stock_by_cohort[m-1, 0:m] - self.stock_by_cohort[m, 0:m] # outflow table is filled row-wise, for each year m.
            # 2) Determine inflow from mass balance:
            if not do_correct_negative_inflow: # if no correction for negative inflows is made
                if self.sf[m,m] != 0: # Else, inflow is 0.
                    self.inflow[m] = (self.stock[m] - self.stock_by_cohort[m, :].sum()) / self.sf[m,m] # allow for outflow during first year by rescaling with 1/sf[m,m]
                # 3) Add new inflow to stock and determine future decay of new age-cohort
                self.stock_by_cohort[m::, m] = self.inflow[m] * self.sf[m::, m]
                self.outflow_by_cohort[m, m]   = self.inflow[m] * (1 - self.sf[m, m])
            # 2a) Correct remaining stock in cases where inflow would be negative:
            else: # if the stock declines faster than according to the lifetime model, this option allows to extract additional stock items.
                # The negative inflow correction implemented here was developed in a joined effort by Sebastiaan Deetman and Stefan Pauliuk.
                inflow_test = self.stock[m] - self.stock_by_cohort[m, :].sum()
                if inflow_test < 0: # if stock-driven model would yield negative inflow
                    delta = -1 * inflow_test # Delta > 0!
                    self.inflow[m] = 0 # Set inflow to 0 and distribute mass balance gap onto remaining cohorts:
                    if self.stock_by_cohort[m,:].sum() != 0:
                        delta_percent = delta / self.stock_by_cohort[m,:].sum()
                        # Distribute gap equally across all cohorts (each cohort is adjusted by the same %, based on surplus with regards to the prescribed stock)
                        # Delta_percent is a % value <= 100%
                    else:
                        delta_percent = 0 # stock in this year is already zero, method does not work in this case.
                    # correct for outflow and stock in current and future years
                    # adjust the entire stock AFTER year m as well, stock is lowered in year m, so future cohort survival also needs to decrease.
                    self.outflow_by_cohort[m, :] = self.outflow_by_cohort[m, :] + (self.stock_by_cohort[m, :] * delta_percent)  # increase outflow according to the lost fraction of the stock, based on Delta_c
                    self.stock_by_cohort[m::,0:m] = self.stock_by_cohort[m::,0:m] * (1-delta_percent) # shrink future description of stock from previous age-cohorts by factor Delta_percent in current AND future years.
                else: # If no negative inflow would occur
                    if self.sf[m,m] != 0: # Else, inflow is 0.
                        self.inflow[m] = (self.stock[m] - self.stock_by_cohort[m, :].sum()) / self.sf[m,m] # allow for outflow during first year by rescaling with 1/sf[m,m]
                    # Add new inflow to stock and determine future decay of new age-cohort
                    self.stock_by_cohort[m::, m] = self.inflow[m] * self.sf[m::, m]
                    self.outflow_by_cohort[m, m]   = self.inflow[m] * (1 - self.sf[m, m])
                # NOTE: This method of negative inflow correction is only of of many plausible methods of increasing the outflow to keep matching stock levels.
                # It assumes that the surplus stock is removed in the year that it becomes obsolete. Each cohort loses the same fraction.
                # Modellers need to try out whether this method leads to justifiable results.
                # In some situations it is better to change the lifetime assumption than using the NegativeInflowCorrect option.

        return self.stock_by_cohort, self.outflow_by_cohort, self.inflow
