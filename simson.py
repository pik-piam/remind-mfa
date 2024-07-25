from src.tools.config import cfg
from src.model_definitions import init_mfa
from src.tools.visualize import visualize_mfa
from src.tools.export import export

cfg.set_from_yml('config/steel.yml')

mfa = init_mfa()
mfa.compute()

visualize_mfa(mfa)
export(mfa)
