import pickle
from src.new_odym.mfa_system import MFASystem


def export_to_dict(mfa: MFASystem, path_out: str):
    dict_out = convert_to_dict(mfa)
    pickle.dump(dict_out, open(path_out, "wb"))


def convert_to_dict(mfa: MFASystem):
    dict_out = {}
    dict_out['dimension_names'] = {d.letter: d.name for d in mfa.dims}
    dict_out['dimension_items'] = {d.name: d.items for d in mfa.dims}
    dict_out['flows'] = {n: f.values for n, f in mfa.flows.items()}
    dict_out['flow_dimensions'] = {n: f.dims.letters for n, f in mfa.flows.items()}
    return dict_out
