import numpy as np
from src.new_odym.named_dim_arrays import Flow, Stock, Parameter, Process
from src.new_odym.dimensions import Dimension, DimensionSet


class MFASystem():

    """
    Class with the definition and methods for a system in ODYM
    """

    def __init__(self):
        self.set_up_definition()
        self.set_up_dimensions()
        self.initialize_processes()
        self.initialize_flows()
        self.initialize_stocks()
        self.initialize_parameters()

    def set_up_definition(self):
        self.definition = MFADefinition()
        self.fill_definition()
        self.definition.check_complete()

    def fill_definition(self):
        raise Exception("This is a dummy in the parent class: Please implement in subclass")

    def compute(self, dsms):
        self.compute_flows(dsms)
        self.compute_stocks(dsms)
        self.check_mass_balance()

    def compute_flows(self, dsms):
        raise Exception("This is a dummy in the parent class: Please implement in subclass")

    def compute_stocks(self, dsms):
        raise Exception("This is a dummy in the parent class: Please implement in subclass")

    def set_up_dimensions(self):
        self.dims = DimensionSet(defdicts=self.definition.dimensions, do_load=True)
        self.set_up_years()
        self.check_consistency()

    def set_up_years(self):
        """
        Years get an extrawurst, to handle past and future.
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

    def initialize_processes(self):
        self.processes = {name: Process(name, id) for id, name in enumerate(self.definition.processes)}

    def initialize_flows(self):
        flow_list = [Flow(**fd) for fd in self.definition.flows]
        self.flows = {f.name: f for f in flow_list}
        for f in self.flows.values():
            f.attach_to_dimensions(self.dims)
            f.attach_to_processes(self.processes)

    def initialize_stocks(self):
        self.stocks = {sd['name']: Stock(**sd) for sd in self.definition.stocks}
        for s in self.stocks.values():
            s.attach_to_dimensions(self.dims)
            s.attach_to_process(self.processes)

    def initialize_parameters(self):
        self.parameters = {prd['name']: Parameter(**prd) for prd in self.definition.parameters}
        for p in self.parameters.values():
            p.attach_to_dimensions(self.dims)
            p.load_values()
            #TODO: calculate correct input parameter, such that this quickfix becomes obsolete
            if p.name == 'material_shares_in_goods':
                # correct values
                p.values[...] = p.values / np.sum(p.values, axis=0, keepdims=True)

    def get_mass_balance(self):
        """
        Determines mass balance of MFAsystem
        We take the indices of each flow, e.g., 't,O,D,G,m,e', strip off the ',' to get 'tODGme',
        add a '->' and the index letters for time and element (here, t and e),
        and call the Einstein sum function np.einsum with the string 'tODGme->te',
        and apply it to the flow values.
        Sum to t and e is subtracted from process where flow is leaving from and added to destination process.
        """
        balance = np.zeros((self.dims['Time'].len, self.dims['Element'].len, len(self.processes))) # Balance array: years x process x element:
        #process position 0 is the balance for the system boundary, the other positions are for the processes,
        #element position 0 is the balance for the entire mass, the other are for the balance of the individual elements

        for flow in self.flows.values(): # Add all flows to mass balance
            flow_value = flow.sum_values_to((self.dims['Time'].letter, self.dims['Element'].letter))
            balance[:,:,flow.from_process.id] -= flow_value # Subtract flow from start process
            balance[:,:,flow.to_process.id]   += flow_value # Add flow to end process

        for stock in self.stocks.values(): # Add all stock changes to the mass balance
            stock_value = stock.sum_values_to((self.dims['Time'].letter, self.dims['Element'].letter))
            if  stock.type == 1:
                balance[:,:,stock.process.id] -= stock_value # 1: net stock change or addition to stock
                balance[:,:,0] += stock_value # add stock changes to process with number 0 ('system boundary, environment of system')
            elif stock.type == 2:
                balance[:,:,stock.process.id] += stock_value # 2: removal/release from stock
                balance[:,:,0] -= stock_value # add stock changes to process with number 0 ('system boundary, environment of system')

        return balance

    def check_mass_balance(self):
        """
        Checks if a given mass balance is plausible.
        :return: True if the mass balance for all processes is below 1t of steel, False otherwise.
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
