import numpy as np
from matplotlib import pyplot as plt
from src.model.simson_base_model import load_simson_base_model, PRIM_PID, USE_PID, EOL_PID, MECH_RECYCLE_PID, INCINERATION_PID
from src.tools.config import cfg
from src.read_data.load_data import load_region_names_list
from src.economic_model.simson_econ_model import load_simson_econ_model
from src.predict.calc_steel_stocks import get_np_pop_data

# MAIN PARAMETERS

do_flow_not_stock = True
flow_origin_process = FABR_PID
flow_destination_process = USE_PID
stock_process = USE_PID
dimension = 'region'  # Options (depending on flow): 'region', 'scenario', 'good', 'waste'

default_scenario = 'SSP2'  # If dimension is not 'scenario', only data from this scenario is considered.
default_region = 'EUR'  # If dimension is not 'region', only data from this region is considered.
# 'World' denotes the entire world data, hence a sum is given for all world regions.
# Default region must be in region names list of 'region_data_source'.

# SPECIFIC PARAMETERS

do_load_econ_model = False
region_data_source = 'Pauliuk'  # Options: REMIND, Pauliuk, REMIND_EU
steel_data_source = 'IEDatabase'  # Options: Mueller, IEDatabase
curve_strategy = 'Pauliuk'  # Options: Pauliuk, Pehl, Duerrwaechter
per_capita = False
ignore_1900 = False

limit_regions = False
regions_to_use_remind = ['CHA', 'USA', 'EUR']
regions_to_use_pauliuk = ['NAM']

limit_time = False
start_year = 2000
end_year = 2050

# If getting wrong results it might be that recalculating model and dsms help.
# This is especially relevant when config has been changed after last load of model.
force_recalculate = False


def visualise():
    model = _get_model_for_visualisation()
    flow_or_stock = _get_flow_or_stock(model)
    name = flow_or_stock.Name
    regions = load_region_names_list()
    legend = _get_legend(regions)
    used_labels = _get_used_labels(legend)
    values = _prepare_values(flow_or_stock, name, regions)

    years = cfg.years if not limit_time else range(start_year, end_year + 1)
    if ignore_1900 and not limit_time:
        values = values[:, 1:]
        years = years[1:]
    for i, line in enumerate(values):
        label = legend[i]
        if limit_regions:
            if label not in used_labels:
                continue
        plt.plot(years, line, label=label)
    plt.legend()
    flow_or_stock_string = 'flow' if do_flow_not_stock else 'stock'
    title = f"{name} {flow_or_stock_string} by '{dimension}'\n"
    if not dimension == 'region':
        title += f"default region '{default_region}'"
    if not dimension == 'scenario':
        title += f", default scenario '{default_scenario}'"
    plt.title(title)
    plt.xlabel('Time (y)')
    plt.ylabel('Steel (t)')
    plt.show()


def _get_flow_or_stock(model):
    if do_flow_not_stock:
        return model.get_flow(flow_origin_process, flow_destination_process)
    else:
        return model.get_stock(stock_process)


def _get_used_labels(legend):
    if dimension == 'region' and limit_regions:
        if region_data_source == 'REMIND':
            return regions_to_use_remind
        elif region_data_source == 'Pauliuk':
            return regions_to_use_pauliuk
        else:
            raise RuntimeError(f"For region data source '{region_data_source}', "
                               f"limit region functionality is not defined.")
    else:
        return legend


def _prepare_values(flow, name, regions):
    flow_dims = flow.Indices
    wanted_dim = dimension[0]
    if wanted_dim not in flow_dims:
        raise RuntimeError(
            f"Dimension '{dimension}' with index '{wanted_dim}' not in {name} flow indices ('{flow_dims}')."
            f"\nChoose one of 'region', 'scenario', 'good' or 'waste' depending on flow indices.")
    flow_dims = flow_dims.replace(",", "")
    n_dims = len(flow_dims)
    dim_idx = flow_dims.index(wanted_dim)
    values = flow.Values

    # if per_capita:
    #    values = _transfer_flows_to_per_capita(values, flow_dims, cfg.include_gdp_and_pop_scenarios_in_prediction)

    if not wanted_dim == 's':
        # select default scenario
        default_scenario_idx = cfg.scenarios.index(default_scenario)
        values = np.moveaxis(values, -1, 0)
        values = values[default_scenario_idx]
        n_dims -= 1
    if not wanted_dim == 'r':
        # select default region
        if default_region == 'World':
            values = np.sum(values, axis=2)
        else:
            default_region_idx = regions.index(default_region)
            values = values[:, :, default_region_idx]
        dim_idx -= 1
        n_dims -= 1
    values = np.moveaxis(values, dim_idx, 0)  # move dimension that we are looking at to the first index
    axes_to_sum = tuple(range(2, n_dims))  # sum
    values = np.sum(values, axis=axes_to_sum)

    new_flow_dims = wanted_dim + 't'
    if per_capita:
        values = _transfer_flows_to_per_capita(values,
                                               new_flow_dims,
                                               cfg.include_gdp_and_pop_scenarios_in_prediction,
                                               regions)

    if limit_time:
        start_year_idx = start_year - cfg.start_year
        end_year_idx = end_year - cfg.start_year + 1
        values = values[:, start_year_idx:end_year_idx]

    return values


def _transfer_flows_to_per_capita(values, flow_dims, include_gdp_and_pop_scenarios, regions):
    pop = get_np_pop_data(country_specific=False, include_gdp_and_pop_scenarios=include_gdp_and_pop_scenarios)
    pop_dims = 'tr'
    if not dimension == 'region':
        # use default region
        if default_region == 'World':
            pop = np.sum(pop, axis=1)
        else:
            default_region_idx = regions.index(default_region)
            pop = pop[:, default_region_idx]
        pop_dims = 't'
    if include_gdp_and_pop_scenarios:
        # scenarios are included
        if dimension == 'scenario':
            pop_dims += 's'
        else:
            # use default scenario
            default_scenario_idx = cfg.scenarios.index(default_scenario)
            pop = np.moveaxis(pop, -1, 0)
            pop = pop[default_scenario_idx]
    pop_inv = 1 / pop
    values = np.einsum(f'{flow_dims},{pop_dims}->{flow_dims}', values, pop_inv)
    return values


def _get_model_for_visualisation():
    recalculate = force_recalculate
    cfg.region_data_source = region_data_source
    if not steel_data_source == cfg.steel_data_source:
        cfg.steel_data_source = steel_data_source
        recalculate = True
    if not curve_strategy == cfg.curve_strategy:
        cfg.curve_strategy = curve_strategy
        recalculate = True

    if do_load_econ_model:
        return load_simson_econ_model(recalculate=recalculate, recalculate_dsms=recalculate)
    else:
        return load_simson_base_model(recalculate=recalculate, recalculate_dsms=recalculate)


def _get_legend(regions):
    if dimension == 'region':
        return regions
    elif dimension == 'scenario':
        return cfg.scenarios
    elif dimension == 'good':
        return sorted(cfg.in_use_categories)
    elif dimension == 'waste':
        return sorted(cfg.recycling_categories)
    else:
        raise RuntimeError(f"Dimension {dimension} not accepted. Use 'region', 'scenario', 'good' or 'waste'.")


if __name__ == '__main__':
    visualise()
