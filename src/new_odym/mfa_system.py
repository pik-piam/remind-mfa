import numpy as np
from src.new_odym.named_dim_arrays import Flow, Stock, Parameter, Process
from src.new_odym.dimensions import Dimension, DimensionSet


class MFASystem():
    """
    An MFASystem class handles the definition, setup and calculation of a Material Flow Analysis system,
    which consists of a set of processes, flows, stocks defined over a set of dimensions.
    For the concrete definition of the system, a subclass of MFASystem must be implemented.
    """

    def __init__(self):
        """
        Define and set up the MFA system and load all required data.
        Does not compute stocks or flows yet.
        """
        self.set_up_definition()
        self.set_up_dimensions()
        self.initialize_processes()
        self.initialize_flows()
        self.initialize_stocks()
        self.initialize_parameters()

    def compute(self, dsms):
        """
        Perform all computations for the MFA system.
        """
        self.compute_flows(dsms)
        self.compute_stocks(dsms)
        self.check_mass_balance()

    def set_up_definition(self):
        """
        Wrapper for the fill_definition routine defined in the subclass
        """
        self.definition = MFADefinition()
        self.fill_definition()
        self.definition.check_complete()

    def fill_definition(self):
        raise Exception("This is a dummy in the parent class: Please implement in subclass")

    def compute_flows(self, dsms):
        raise Exception("This is a dummy in the parent class: Please implement in subclass")

    def compute_stocks(self, dsms):
        raise Exception("This is a dummy in the parent class: Please implement in subclass")

    def set_up_dimensions(self):
        """
        Given the dimension definition in the subclass,
        which includes file names for loading of a list of elements of each dimension,
        this function loads a DimensionSet object, which includes loading of the elements along each dimension.
        The mandatory Time dimension gets additional special treatment, to handle past and future.
        """
        dim_constructor_args = [d | {'do_load': True} for d in self.definition.dimensions]
        self.dims = DimensionSet(arg_dicts_for_dim_constructors=dim_constructor_args)
        self.set_up_years()
        self.check_consistency()

    def set_up_years(self):
        """
        Load historic years from file, and deduct future years as non-historic years from the Time dimension.
        Get indices for all historic and future years for array slicing.
        """
        self.years = self.dims._dict['Time']
        self.historic_years = Dimension(name='historic_years')
        self.historic_years.load_items(dtype=int)
        self.future_years = Dimension(name='future_years')
        self.future_years.set_items([y for y in self.dims['Time'].items if y not in self.historic_years.items])
        self.i_historic = np.arange(self.historic_years.len)
        self.i_future = np.arange(self.historic_years.len, self.dims['Time'].len)

    def check_consistency(self):
        pass
        #TODO:
        # - all dimensions must have values
        # - certain dimensions must be present (time, element, region)
        # - Do we require a certain order?

    def initialize_processes(self):
        """Convert the process definition list to dict of Process objects, indexed by name."""
        self.processes = {name: Process(name, id) for id, name in enumerate(self.definition.processes)}

    def initialize_flows(self):
        """
        Convert the flow definition list to dict of Process objects initialized with value 0., indexed by name.
        Flow names are deducted from the processes they connect.
        """
        flow_list = [Flow(**arg_dict) for arg_dict in self.definition.flows]
        self.flows = {f.name: f for f in flow_list}
        for f in self.flows.values():
            f.init_dimensions(self.dims)
            f.attach_to_processes(self.processes)

    def initialize_stocks(self):
        self.stocks = {sd['name']: Stock(**sd) for sd in self.definition.stocks}
        for s in self.stocks.values():
            s.init_dimensions(self.dims)
            s.attach_to_process(self.processes)

    def initialize_parameters(self):
        self.parameters = {prd['name']: Parameter(**prd) for prd in self.definition.parameters}
        for p in self.parameters.values():
            p.init_dimensions(self.dims)
            p.load_values()
            #TODO: calculate correct input parameter, such that this quickfix becomes obsolete
            if p.name == 'material_shares_in_goods':
                # correct values
                p.values[...] = p.values / np.sum(p.values, axis=0, keepdims=True)

    def get_mass_balance(self):
        """
        Determines a mass balance for each process of the MFA system.

        The mass balance of a process is calculated as the sum of
        - all flows entering and leaving the process
        - stock inflows and outflows connected to the process.
        To obtain a homogenous shape, the flows and stocks are summed over all dimensions except the mandatory time and element dimensions.

        The process with ID 0 is the system boundary. Its mass balance serves as a mass balance of the whole system.
        """

        balance = np.zeros((self.dims['Time'].len, self.dims['Element'].len, len(self.processes)))

        # Add flows to mass balance
        for flow in self.flows.values():
            flow_value = flow.sum_values_to((self.dims['Time'].letter, self.dims['Element'].letter))
            balance[:,:,flow.from_process.id] -= flow_value # Subtract flow from start process
            balance[:,:,flow.to_process.id]   += flow_value # Add flow to end process

        # Add stock changes to the mass balance
        for stock in self.stocks.values():
            stock_value = stock.sum_values_to((self.dims['Time'].letter, self.dims['Element'].letter))
            if  stock.type == 1: # addition to stock; or net stock change
                balance[:,:,stock.process.id] -= stock_value
                balance[:,:,0] += stock_value # add stock changes to process with number 0 (system boundary) for mass balance of whole system
            elif stock.type == 2: # removal/release from stock
                balance[:,:,stock.process.id] += stock_value
                balance[:,:,0] -= stock_value # add stock changes to process with number 0 (system boundary) for mass balance of whole system

        return balance

    def check_mass_balance(self):
        """
        Compute mass balance, and check whether it is within a certain tolerance.
        Throw an error if it isn't.
        """

        print("Checking mass balance...")
        # returns array with dim [t, process, e]
        balance = self.get_mass_balance()
        error_sum_by_process = np.abs(balance).sum(axis=(0,1))
        id_failed = error_sum_by_process > 1.
        names_failed = [p.name for p in self.processes.values() if id_failed[p.id]]
        if names_failed:
                raise RuntimeError(f"Error, Mass Balance fails for processes {', '.join(names_failed)}")
        else:
            print("Success - Mass balance consistent!")
        return


class MFADefinition():
    """
    Empty container for all information needed to define an MFA system, in the form of lists and dictionaries.
    Is filled by the fill_definition routine in the subclass of MFASystem, which defines the system layout.
    """

    def __init__(self):
        self.dimensions = None
        self.processes = None
        self.flows = None
        self.stocks = None
        self.parameters = None

    def check_complete(self):
        assert self.dimensions
        assert self.processes
        assert self.flows
        assert self.stocks
        assert self.parameters
