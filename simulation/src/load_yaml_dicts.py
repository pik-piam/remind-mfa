import os
import yaml


def load_yaml_dicts():
    yaml_folder_path = os.path.join('simulation', 'interface', 'yaml')
    yaml_folder_files = os.listdir(yaml_folder_path)
    dicts = []
    for fname in yaml_folder_files:
        suffix = fname[fname.rfind('.'):]
        if suffix == '.yml' or suffix == '.yaml':
            fpath = os.path.join(yaml_folder_path, fname)
            with open(fpath, 'r') as f:
                config_dict = yaml.safe_load(f)
            dicts.append(config_dict)
    return dicts


def _test():
    configs = load_yaml_dicts()
    print(configs[0]['simulation_name'])


if __name__ == '__main__':
    _test()
