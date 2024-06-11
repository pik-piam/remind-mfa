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

"""

import numpy as np
import scipy.stats

def __version__():
    """Return a brief version string and statement for this class."""
    return str('1.0'), str('Class DynamicStockModel, dsm. Version 1.0. Last change: July 25th, 2019. Check https://github.com/IndEcol/ODYM for latest version.')


class DynamicStockModel(object):

    """ Class containing a dynamic stock model

    Attributes
    ----------
    t : Series of years or other time intervals
    i : Discrete time series of inflow to stock

    o : Discrete time series of outflow from stock
    o_c :Discrete time series of outflow from stock, by cohort

    s_c : dynamic stock model (stock broken down by year and age- cohort)
    s : Discrete time series for stock, total

    lt : lifetime distribution: dictionary

    pdf: probability density function, distribution of outflow from a specific age-cohort

    sf: survival function for different age-cohorts, year x age-cohort table


    name : string, optional
        Name of the dynamic stock model, default is 'DSM'
    """

    """
    Basic initialisation and dimension check methods
    """

    def __init__(self, t=None, i=None, o=None, s=None, lt=None, s_c=None, o_c=None, name='DSM', pdf=None, sf=None):
        """ Init function. Assign the input data to the instance of the object."""
        self.t = t  # optional

        self.i = i  # optional

        self.s = s  # optional
        self.s_c = s_c  # optional

        self.o = o  # optional
        self.o_c = o_c  # optional

        if lt is not None:
            for ThisKey in lt.keys():
                # If we have the same scalar lifetime, stdDev, etc., for all cohorts,
                # replicate this value to full length of the time vector
                if ThisKey != 'Type':
                    if np.array(lt[ThisKey]).shape[0] == 1:
                        lt[ThisKey] = np.tile(lt[ThisKey], len(t))

        self.lt = lt  # optional
        self.name = name  # optional

        self.pdf = pdf # optional
        self.sf  = sf # optional

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
        return np.diff(self.s, prepend=0)

    def check_stock_balance(self):
        balance = self.get_stock_balance()
        balance = np.abs(balance).sum()
        if balance > 1:  # 1 tonne accuracy
            raise RuntimeError("Stock balance for dynamic stock model is too high: " + str(balance))
        elif balance > 0.001:
            print("Stock balance for model dynamic stock model is noteworthy: " + str(balance))

    def get_stock_balance(self):
        """ Check wether inflow, outflow, and stock are balanced. If possible, the method returns the vector 'Balance', where Balance = inflow - outflow - stock_change"""
        return self.i - self.o - self.compute_stock_change()

    def compute_stock_total(self):
        """Determine total stock as row sum of cohort-specific stock."""
        self.s = self.s_c.sum(axis=1)
        return self.s

    def compute_outflow_total(self):
        """Determine total outflow as row sum of cohort-specific outflow."""
        self.o = self.o_c.sum(axis=1)
        return self.o

    def compute_outflow_from_mb(self):
        """Compute outflow from process via mass balance.
           Needed in cases where lifetime is zero."""
        self.o = self.i - self.compute_stock_change()
        return self.o

    """ Part 2: Lifetime model. """

    def compute_outflow_pdf(self):
        """
        Lifetime model. The method compute outflow_pdf returns an array year-by-cohort of the probability of a item added to stock in year m (aka cohort m) leaves in in year n. This value equals pdf(n,m).
        The pdf is computed from the survival table sf, where the type of the lifetime distribution enters.
        The shape of the output pdf array is NoofYears * NoofYears, but the meaning is years by age-cohorts.
        The method does nothing if the pdf alreay exists.
        """
        if self.pdf is None:
            self.compute_sf() # computation of pdfs moved to this method: compute survival functions sf first, then calculate pdfs from sf.
            self.pdf   = np.zeros((len(self.t), len(self.t)))
            self.pdf[np.diag_indices(len(self.t))] = np.ones(len(self.t)) - self.sf.diagonal(0)
            for m in range(0,len(self.t)):
                self.pdf[np.arange(m+1,len(self.t)),m] = -1 * np.diff(self.sf[np.arange(m,len(self.t)),m])
            return self.pdf
        else:
            # pdf already exists
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
        self.sf = np.zeros((len(self.t), len(self.t)))
        # Perform specific computations and checks for each lifetime distribution:

        if self.lt['Type'] == 'Fixed': # fixed lifetime, age-cohort leaves the stock in the model year when the age specified as 'Mean' is reached.
            for m in range(0, len(self.t)):  # cohort index
                self.sf[m::,m] = np.multiply(1, (np.arange(0,len(self.t)-m) < self.lt['Mean'][m])) # converts bool to 0/1
            # Example: if Lt is 3.5 years fixed, product will still be there after 0, 1, 2, and 3 years, gone after 4 years.

        if self.lt['Type'] == 'Normal': # normally distributed lifetime with mean and standard deviation. Watch out for nonzero values
            # for negative ages, no correction or truncation done here. Cf. note below.
            for m in range(0, len(self.t)):  # cohort index
                if self.lt['Mean'][m] != 0:  # For products with lifetime of 0, sf == 0
                    self.sf[m::,m] = scipy.stats.norm.sf(np.arange(0,len(self.t)-m), loc=self.lt['Mean'][m], scale=self.lt['StdDev'][m])
                    # NOTE: As normal distributions have nonzero pdf for negative ages, which are physically impossible,
                    # these outflow contributions can either be ignored (violates the mass balance) or
                    # allocated to the zeroth year of residence, the latter being implemented in the method compute compute_o_c_from_s_c.
                    # As alternative, use lognormal or folded normal distribution options.

        if self.lt['Type'] == 'FoldedNormal': # Folded normal distribution, cf. https://en.wikipedia.org/wiki/Folded_normal_distribution
            for m in range(0, len(self.t)):  # cohort index
                if self.lt['Mean'][m] != 0:  # For products with lifetime of 0, sf == 0
                    self.sf[m::,m] = scipy.stats.foldnorm.sf(np.arange(0,len(self.t)-m), self.lt['Mean'][m]/self.lt['StdDev'][m], 0, scale=self.lt['StdDev'][m])
                    # NOTE: call this option with the parameters of the normal distribution mu and sigma of curve BEFORE folding,
                    # curve after folding will have different mu and sigma.

        if self.lt['Type'] == 'LogNormal': # lognormal distribution
            # Here, the mean and stddev of the lognormal curve,
            # not those of the underlying normal distribution, need to be specified! conversion of parameters done here:
            for m in range(0, len(self.t)):  # cohort index
                if self.lt['Mean'][m] != 0:  # For products with lifetime of 0, sf == 0
                    # calculate parameter mu    of underlying normal distribution:
                    LT_LN = np.log(self.lt['Mean'][m] / np.sqrt(1 + self.lt['Mean'][m] * self.lt['Mean'][m] / (self.lt['StdDev'][m] * self.lt['StdDev'][m])))
                    # calculate parameter sigma of underlying normal distribution:
                    SG_LN = np.sqrt(np.log(1 + self.lt['Mean'][m] * self.lt['Mean'][m] / (self.lt['StdDev'][m] * self.lt['StdDev'][m])))
                    # compute survial function
                    self.sf[m::,m] = scipy.stats.lognorm.sf(np.arange(0,len(self.t)-m), s=SG_LN, loc = 0, scale=np.exp(LT_LN))
                    # values chosen according to description on
                    # https://docs.scipy.org/doc/scipy-0.13.0/reference/generated/scipy.stats.lognorm.html
                    # Same result as EXCEL function "=LOGNORM.VERT(x;LT_LN;SG_LN;TRUE)"

        if self.lt['Type'] == 'Weibull': # Weibull distribution with standard definition of scale and shape parameters
            for m in range(0, len(self.t)):  # cohort index
                if self.lt['Shape'][m] != 0:  # For products with lifetime of 0, sf == 0
                    self.sf[m::,m] = scipy.stats.weibull_min.sf(np.arange(0,len(self.t)-m), c=self.lt['Shape'][m], loc = 0, scale=self.lt['Scale'][m])




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
        self.s_c = np.einsum('c,tc->tc', self.i, self.sf) # See numpy's np.einsum for documentation.
        # This command means: s_c[t,c] = i[c] * sf[t,c] for all t, c
        # from the perspective of the stock the inflow has the dimension age-cohort,
        # as each inflow(t) is added to the age-cohort c = t
        return self.s_c

    def compute_o_c_from_s_c(self):
        """Compute outflow by cohort from stock by cohort."""
        self.o_c = np.zeros(self.s_c.shape)
        self.o_c[1::,:] = -1 * np.diff(self.s_c,n=1,axis=0)
        self.o_c[np.diag_indices(len(self.t))] = self.i - np.diag(self.s_c) # allow for outflow in year 0 already
        return self.o_c

    def compute_i_from_s(self, InitialStock):
        """Given a stock at t0 broken down by different cohorts tx ... t0, an "initial stock".
           This method calculates the original inflow that generated this stock.
           Example:
        """
        assert len(InitialStock) == len(self.t)
        self.i = np.zeros(len(self.t))
        # construct the sf of a product of cohort tc surviving year t
        # using the lifetime distributions of the past age-cohorts
        self.compute_sf()
        for Cohort in range(0, len(self.t)):
            if self.sf[-1,Cohort] != 0:
                self.i[Cohort] = InitialStock[Cohort] / self.sf[-1,Cohort]
            else:
                self.i[Cohort] = 0  # Not possible with given lifetime distribution
        return self.i

    def compute_evolution_initialstock(self,InitialStock,SwitchTime):
        """ Assume InitialStock is a vector that contains the age structure of the stock at time t0,
        and it covers as many historic cohorts as there are elements in it.
        This method then computes the future stock and outflow from the year SwitchTime onwards.
        Only future years, i.e., years after SwitchTime, are computed.
        NOTE: This method ignores and deletes previously calculated s_c and o_c.
        The InitialStock is a vector of the age-cohort composition of the stock at SwitchTime, with length SwitchTime"""
        self.s_c = np.zeros((len(self.t), len(self.t)))
        self.o_c = np.zeros((len(self.t), len(self.t)))
        self.compute_sf()
        # Extract and renormalize array describing fate of initialstock:
        Shares_Left = self.sf[SwitchTime,0:SwitchTime].copy()
        self.s_c[SwitchTime,0:SwitchTime] = InitialStock # Add initial stock to s_c
        self.s_c[SwitchTime::,0:SwitchTime] = np.tile(InitialStock.transpose(),(len(self.t)-SwitchTime,1)) * self.sf[SwitchTime::,0:SwitchTime] / np.tile(Shares_Left,(len(self.t)-SwitchTime,1))
        return self.s_c



    """
    Part 4: Stock driven model
    Given: total stock, lifetime dist.
    Default order of methods:
    1) determine inflow, outflow by cohort, and stock by cohort
    2) determine total outflow
    3) determine stock change
    4) check mass balance.
    """

    def compute_stock_driven_model(self, NegativeInflowCorrect = False):
        """ With given total stock and lifetime distribution,
            the method builds the stock by cohort and the inflow.
        """
        self.s_c = np.zeros((len(self.t), len(self.t)))
        self.o_c = np.zeros((len(self.t), len(self.t)))
        self.i = np.zeros(len(self.t))
        # construct the sf of a product of cohort tc remaining in the stock in year t
        self.compute_sf() # Computes sf if not present already.
        # First year:
        if self.sf[0, 0] != 0: # Else, inflow is 0.
            self.i[0] = self.s[0] / self.sf[0, 0]
        self.s_c[:, 0] = self.i[0] * self.sf[:, 0] # Future decay of age-cohort of year 0.
        self.o_c[0, 0] = self.i[0] - self.s_c[0, 0]
        # all other years:
        for m in range(1, len(self.t)):  # for all years m, starting in second year
            # 1) Compute outflow from previous age-cohorts up to m-1
            self.o_c[m, 0:m] = self.s_c[m-1, 0:m] - self.s_c[m, 0:m] # outflow table is filled row-wise, for each year m.
            # 2) Determine inflow from mass balance:
            if NegativeInflowCorrect is False: # if no correction for negative inflows is made
                if self.sf[m,m] != 0: # Else, inflow is 0.
                    self.i[m] = (self.s[m] - self.s_c[m, :].sum()) / self.sf[m,m] # allow for outflow during first year by rescaling with 1/sf[m,m]
                # 3) Add new inflow to stock and determine future decay of new age-cohort
                self.s_c[m::, m] = self.i[m] * self.sf[m::, m]
                self.o_c[m, m]   = self.i[m] * (1 - self.sf[m, m])
            # 2a) Correct remaining stock in cases where inflow would be negative:
            if NegativeInflowCorrect is True: # if the stock declines faster than according to the lifetime model, this option allows to extract additional stock items.
                # The negative inflow correction implemented here was developed in a joined effort by Sebastiaan Deetman and Stefan Pauliuk.
                InflowTest = self.s[m] - self.s_c[m, :].sum()
                if InflowTest < 0: # if stock-driven model would yield negative inflow
                    Delta = -1 * InflowTest # Delta > 0!
                    self.i[m] = 0 # Set inflow to 0 and distribute mass balance gap onto remaining cohorts:
                    if self.s_c[m,:].sum() != 0:
                        Delta_percent = Delta / self.s_c[m,:].sum()
                        # Distribute gap equally across all cohorts (each cohort is adjusted by the same %, based on surplus with regards to the prescribed stock)
                        # Delta_percent is a % value <= 100%
                    else:
                        Delta_percent = 0 # stock in this year is already zero, method does not work in this case.
                    # correct for outflow and stock in current and future years
                    # adjust the entire stock AFTER year m as well, stock is lowered in year m, so future cohort survival also needs to decrease.
                    self.o_c[m, :] = self.o_c[m, :] + (self.s_c[m, :] * Delta_percent)  # increase outflow according to the lost fraction of the stock, based on Delta_c
                    self.s_c[m::,0:m] = self.s_c[m::,0:m] * (1-Delta_percent) # shrink future description of stock from previous age-cohorts by factor Delta_percent in current AND future years.
                else: # If no negative inflow would occur
                    if self.sf[m,m] != 0: # Else, inflow is 0.
                        self.i[m] = (self.s[m] - self.s_c[m, :].sum()) / self.sf[m,m] # allow for outflow during first year by rescaling with 1/sf[m,m]
                    # Add new inflow to stock and determine future decay of new age-cohort
                    self.s_c[m::, m] = self.i[m] * self.sf[m::, m]
                    self.o_c[m, m]   = self.i[m] * (1 - self.sf[m, m])
                # NOTE: This method of negative inflow correction is only of of many plausible methods of increasing the outflow to keep matching stock levels.
                # It assumes that the surplus stock is removed in the year that it becomes obsolete. Each cohort loses the same fraction.
                # Modellers need to try out whether this method leads to justifiable results.
                # In some situations it is better to change the lifetime assumption than using the NegativeInflowCorrect option.

        return self.s_c, self.o_c, self.i
