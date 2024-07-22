import os
import pickle
from src.tools.config import cfg
from src.new_odym.mfa_system import MFASystem


def export(mfa: MFASystem, base_path: str):
    if cfg.do_export.get('pickle', False):
        export_to_pickle(mfa, base_path)
    if cfg.do_export.get('csv', False):
        export_to_csv(mfa, base_path)


def export_to_pickle(mfa: MFASystem, base_path: str):
    dict_out = convert_to_dict(mfa)
    path_out = os.path.join(base_path, 'mfa.pickle')
    pickle.dump(dict_out, open(path_out, "wb"))


def export_to_csv(mfa: MFASystem, base_path: str):
    for flow_name, flow in mfa.flows.items():
        df = flow.to_df()
        dir_out = os.path.join(base_path, 'flows')
        if not os.path.exists(dir_out):
            os.makedirs(dir_out)
        path_out = os.path.join(dir_out, f'{flow_name.replace(" => ", "__2__")}.csv')
        df.to_csv(path_out, index=False)


def convert_to_dict(mfa: MFASystem):
    dict_out = {}
    dict_out['dimension_names'] = {d.letter: d.name for d in mfa.dims}
    dict_out['dimension_items'] = {d.name: d.items for d in mfa.dims}
    dict_out['flows'] = {n: f.values for n, f in mfa.flows.items()}
    dict_out['flow_dimensions'] = {n: f.dims.letters for n, f in mfa.flows.items()}
    return dict_out
