from src.tools.config import cfg
from src.model_definitions import init_mfa
from src.tools.visualize import visualize_mfa_sankey
from src.tools.export import export


cfg.set_from_yml('config/plastics.yml')

mfa = init_mfa()
mfa.compute()

if cfg.do_visualize['sankey']:
    visualize_mfa_sankey(mfa)
export(mfa, 'data/plastics/output')
