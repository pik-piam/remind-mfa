import os
import pandas as pd
import pickle
from simulation.src.load_excel_dicts import load_excel_dicts
from simulation.src.load_yaml_dicts import load_yaml_dicts
from src.tools.config import cfg
from src.model.simson_model import load_simson_model
from src.economic_model.simson_econ_model import load_simson_econ_model
from src.read_data.load_data import load_region_names_list
from src.visualisation.master_visualisation import get_scrap_share_china_plt, get_production_plt


def run_simulations():
    dicts = _load_dicts()
    for dict in dicts:
        _run_and_save_simulation(dict)


def _run_and_save_simulation(dict):
    sim_name = dict['simulation_name']
    cfg.customize(dict)
    # todo change false
    model = load_simson_econ_model(recalculate=True) if cfg.do_model_economy else load_simson_model(recalculate=True)
    _save_simulation(sim_name, model)


def _save_simulation(sim_name, model):
    sim_path = os.path.join('simulation', 'data', sim_name)
    sim_path, data_path, figure_path = _create_simulation_folder_structure(sim_path)
    _save_simulation_model(sim_path, sim_name, model)
    _save_simulation_data(sim_name, model, data_path)
    _save_simulation_figures(model, sim_name, figure_path)


def _save_simulation_model(sim_path, sim_name, model):
    file_name = f'{sim_name}_model.p'
    file_path = os.path.join(sim_path, file_name)
    pickle.dump(model, open(file_path, "wb"))


def _save_simulation_data(sim_name, model, data_path):
    flows = list(model.FlowDict.values())
    stocks = list(model.StockDict.values())
    flows_and_stocks = flows + stocks
    for flow_or_stock in flows_and_stocks:
        flow_or_stock_name = flow_or_stock.Name
        flow_or_stock_values = flow_or_stock.Values[:, 0]
        dim2 = 1
        for i in flow_or_stock_values.shape[1:]:
            dim2 *= i
        flow_or_stock_values = flow_or_stock_values.reshape(flow_or_stock_values.shape[0], dim2)

        multi_index = _get_multi_index_from_indices(flow_or_stock.Indices)

        df_values = pd.DataFrame(flow_or_stock_values, index=cfg.years, columns=multi_index)
        df_values = df_values.transpose()

        flow_or_stock_path = os.path.join(data_path, f'{sim_name}_{flow_or_stock_name}.csv')
        df_values.to_csv(flow_or_stock_path)


def _save_simulation_figures(model, sim_name, figure_path):
    plt_china_scrap_share_scenarios = get_scrap_share_china_plt(model)
    scrap_share_fig_path = _get_fig_path(figure_path, sim_name, 'scrap_share_china')
    plt_china_scrap_share_scenarios.savefig(scrap_share_fig_path)

    plt_production = get_production_plt(model)
    production_fig_path = _get_fig_path(figure_path, sim_name, 'production')
    plt_production.savefig(production_fig_path)


def _get_fig_path(figure_path, sim_name, fig_name):
    return os.path.join(figure_path, f'{sim_name}_{fig_name}.png')


def _get_multi_index_from_indices(flow_or_stock_indices):
    multi_index_array = []
    multi_index_names = []
    for char in flow_or_stock_indices[4:]:
        if char == 'r':
            multi_index_array.append(load_region_names_list())
            multi_index_names.append('Region')
        elif char == 'g':
            multi_index_array.append(cfg.using_categories)
            multi_index_names.append('In-Use category')
        elif char == 'w':
            multi_index_array.append(cfg.recycling_categories)
            multi_index_names.append('Recycling category')
        elif char == 's':
            multi_index_array.append(cfg.scenarios)
            multi_index_names.append('Scenario')
    return pd.MultiIndex.from_product(iterables=multi_index_array, names=multi_index_names)


def _create_simulation_folder_structure(sim_path):
    sim_path = _check_sim_path(sim_path)
    data_path = os.path.join(sim_path, 'data')
    figure_path = os.path.join(sim_path, 'figures')
    os.mkdir(sim_path)
    os.mkdir(data_path)
    os.mkdir(figure_path)
    return sim_path, data_path, figure_path


def _check_sim_path(sim_path):
    # folder numbering to index folders
    while os.path.exists(sim_path):
        pound_location = sim_path.rfind('#')
        if pound_location != -1 and sim_path[-1] != '#':
            past_pound = sim_path[pound_location + 1:]
            if past_pound.isnumeric():
                new_idx = int(past_pound) + 1
                sim_path = f'{sim_path[:pound_location]}#{new_idx}'
        else:
            sim_path += '#2'

    return sim_path

def _load_dicts():
    return load_excel_dicts() + load_yaml_dicts()


if __name__ == '__main__':
    run_simulations()
