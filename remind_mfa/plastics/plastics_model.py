from .plastics_mfa_system import PlasticsMFASystemFuture
from .plastics_mfa_system_historic import PlasticsMFASystemHistoric
from .plastics_export import PlasticsDataExporter
from .plastics_definition import get_plastics_definition
from remind_mfa.plastics.plastics_definition import scenario_parameters as plastics_scn_prm_def
from .plastics_data_reader import PlasticsDataReader
from remind_mfa.plastics.plastics_config import PlasticsCfg
from remind_mfa.common.common_model import CommonModel


class PlasticsModel(CommonModel):

    ConfigCls = PlasticsCfg
    DataReaderCls = PlasticsDataReader
    DataExporterCls = PlasticsDataExporter
    HistoricMFASystemCls = PlasticsMFASystemHistoric
    FutureMFASystemCls = PlasticsMFASystemFuture
    get_definition = staticmethod(get_plastics_definition)
    custom_scn_prm_def = plastics_scn_prm_def

    def set_definition(self, *args, **kwargs):
        return get_plastics_definition(*args, **kwargs)
