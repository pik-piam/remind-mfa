import numpy as np
import flodym as fd

from simson.common.common_cfg import CommonCfg
from simson.cement.cement_definition import get_definition
from simson.cement.cement_mfa_system_historic import InflowDrivenHistoricCementMFASystem

class CementModel:

    def __init__(self, cfg: CommonCfg):
        self.cfg = cfg
        self.definition = get_definition(self.cfg)

    def run(self):
        self.historic_mfa = self.make_historic_mfa()
        self.historic_mfa.compute()

        # TODO future mfa

    def make_historic_mfa(self) -> InflowDrivenHistoricCementMFASystem:

        historic_dim_letters = tuple([d for d in self.dims.letters if d != "t"])
        historic_dims = self.dims[historic_dim_letters]
        historic_processes = [

        ]
        processes = fd.make_processes(historic_processes)
        flows = fd.make_empty_flows(
            processes=processes,
            flow_definitions=[f for f in self.definition.flows if "h" in f.dim_letters],
            dims=historic_dims,
        )
        stocks = fd.make_empty_stocks(
            processes=processes,
            stock_definitions=[s for s in self.definition.stocks if "h" in s.dim_letters],
            dims=historic_dims,
        )

        return InflowDrivenHistoricCementMFASystem(
            cfg=self.cfg,
            parameters=self.parameters,
            processes=processes,
            dims=historic_dims,
            flows=flows,
            stocks=stocks,
        )
    