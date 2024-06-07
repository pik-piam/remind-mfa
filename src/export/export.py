import pickle
from src.tools.config import cfg
from src.odym_extension.SimsonMFASystem import SimsonMFASystem


def export_to_dict(mfa: SimsonMFASystem, path_out: str):
    dict_out = convert_to_dict(mfa)
    pickle.dump(dict_out, open(path_out, "wb"))


def convert_to_dict(mfa: SimsonMFASystem):
    dict_out = {}
    dict_out['dimension_names'] = {l: n for n, l in cfg.index_letters.items()}
    dict_out['dimension_items'] = cfg.items
    dict_out['flows'] = {n: f.Values for n, f in mfa.FlowDict.items()}
    dict_out['flow_dimensions'] = {n: f.Indices for n, f in mfa.FlowDict.items()}
    return dict_out