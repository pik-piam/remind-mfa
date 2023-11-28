import csv
import os
import numpy as np
from matplotlib import pyplot as plt
from src.economic_model.simson_econ_model import load_simson_econ_model, _get_flow_values
from src.model.simson_base_model import BOF_PID, EAF_PID, FORM_PID, FABR_PID, USE_PID
from src.tools.config import cfg

def _test():
    model = load_simson_econ_model(country_specific=False)
    bof_production = _get_flow_values(model, BOF_PID, FORM_PID)
    eaf_production = _get_flow_values(model, EAF_PID, FORM_PID)
    production = bof_production + eaf_production
    forming = _get_flow_values(model, FORM_PID, FABR_PID)
    fabrication = _get_flow_values(model, FABR_PID, USE_PID)
    fabrication = np.sum(fabrication, axis=-2)

    region_names = ['China', 'India', 'USA']
    regions = [1,3,11]
    scenario = 1  # SSP_2
    start_year = 1999
    end_year = 2009
    start_idx = start_year - 1900
    end_idx = end_year - 1900
    data = [production[start_idx:end_idx,0,region_idx,scenario]/1000 for region_idx in regions]
    form = [forming[start_idx:end_idx,0,region_idx,scenario]/1000 for region_idx in regions]
    fabr = [fabrication[start_idx:end_idx,0,region_idx,scenario]/1000 for region_idx in regions]

    ws_data_path = os.path.join(cfg.data_path, '..', 'src', 'visualisation', 'test_visualisations', 'Book1.csv')
    with open(ws_data_path) as csv_file:
        ws_reader = csv.reader(csv_file, delimiter=',')
        ws_list = list(ws_reader)
        ws_data = [np.array([float(num) for num in line[1:]]) for line in ws_list[1:]]

    years = range(start_year, end_year)
    colors = ['r', 'g', 'b']
    labels = []

    world_data = ws_data[-1]
    world_inflow = fabrication[start_idx:end_idx,0,:,scenario]/1000
    world_inflow = np.sum(world_inflow, axis=-1)
    plt.plot(years, world_data, 'b', label='World Steel Production')
    plt.plot(years, world_inflow, 'g', label='Model inflow')
    plt.xlabel('Years (y)')
    plt.ylabel('Crude Steel (kT)')
    plt.legend(loc="upper left")
    plt.title('Comparison of World Steel worldwide scaler vs Model worldwide inflow In-Use')
    plt.show()

    ws_data = ws_data[:-1]


    for i, region_name in enumerate(region_names):
        plt.plot(years, data[i], f'{colors[i]}--', label=f'Model: {region_name}')
        plt.plot(years, ws_data[i], f'{colors[i]}', label=f'WS: {region_name}')
    plt.xlabel('Years (y)')
    plt.ylabel('Crude Steel (kT)')
    plt.legend(loc="upper left")
    plt.title('Comparison of Crude Steel Production in Model vs WorldSteel data')
    plt.show()

    for i, region_name in enumerate(region_names):
        plt.plot(years, fabr[i], f'{colors[i]}--', label=f'Model inflow: {region_name}')
        plt.plot(years, ws_data[i], f'{colors[i]}', label=f'WS: {region_name}')
    plt.xlabel('Years (y)')
    plt.ylabel('Crude Steel (kT)')
    plt.legend(loc="upper left")
    plt.title('Comparison of Model Inflow In-Use vs WorldSteel data')
    plt.show()







if __name__=='__main__':
    _test()