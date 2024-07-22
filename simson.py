from src.tools.config import cfg
from src.model_definitions import init_mfa
from src.tools.visualize import visualize_mfa_sankey
from src.tools.export import export_to_dict


cfg.set_from_yml('config/plastics.yml')

mfa = init_mfa()
mfa.compute()

if cfg.do_visualize['sankey']:
    visualize_mfa_sankey(mfa)
export_to_dict(mfa, 'data/plastics/output/mfa.pickle')
