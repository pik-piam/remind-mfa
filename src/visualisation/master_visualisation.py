import matplotlib.pyplot as plt
import numpy as np
from src.model.mfa_all_regions import load_simson_model
import src.model.load_DSMs as dynamic_stock_models
from src.read_data.load_data import load_regions

REGIONS = list(load_regions()['region'].unique())

def show_primary_stock(main_model, regions_to_use):
    for region in regions_to_use:
        region_id = REGIONS.index(region)
        plt.plot(range(1901, 2101), main_model.FlowDict['F_0_1'].Values[1:, 0, region_id])
        # year 1900 is excluded due to dynamic stock model construction
    plt.legend(regions_to_use)
    plt.xlabel("Time (y)")
    plt.ylabel("Primary per capita steel production (t)")
    plt.title("Primary per capita steel production in tonnes")
    plt.show()


def show_scrap_share_production(main_model, regions_to_use):
    for region in regions_to_use:
        region_id = REGIONS.index(region)
        scrap = main_model.FlowDict['F_3_1'].Values[1:, 0, region_id]
        production = main_model.FlowDict['F_1_2'].Values[1:, 0, region_id]
        # year 1900 is excluded due to dynamic stock model construction
        plt.plot(range(1901, 2101), np.divide(scrap, production))
    plt.legend(regions_to_use)
    plt.xlabel("Time (y)")
    plt.ylabel("Scrap/Production (%)")
    plt.title("Scrap share of production percent")
    plt.show()


def show_waste_stock(main_model, regions_to_use):
    for region in regions_to_use:
        region_id = REGIONS.index(region)
        plt.plot(range(1901, 2101), main_model.StockDict['S_6'].Values[:, 0, region_id][
                                    1:])  # year 1900 is excluded due to dynamic stock model construction
    plt.legend(regions_to_use)
    plt.xlabel("Time (y)")
    plt.ylabel("Waste Stock (t)")
    plt.title("Development of Waste Stock in tonnes")
    plt.show()


def show_inflow_by_category(main_model, regions_to_use):
    for region in regions_to_use:
        region_id = REGIONS.index(region)
        mfa_flows = main_model.FlowDict
        time = range(1901, 2101)
        plt.stackplot(time,
                      [mfa_flows['F_2_4'].Values[1:, 0, region_id, 0], mfa_flows['F_2_4'].Values[1:, 0, region_id, 1],
                       mfa_flows['F_2_4'].Values[1:, 0, region_id, 2], mfa_flows['F_2_4'].Values[1:, 0, region_id, 3]],
                      labels=['Transport', 'Machinery', 'Construction', 'Product'])
        plt.legend(loc=2, fontsize='large')
        plt.xlabel("Time (y)")
        plt.ylabel("Steel inflows (t)")
        plt.title('Steel Inflows of ' + region + ' in tonnes')
        plt.show()


def show_net_trade(main_model, regions_to_use):
    net_trade = np.zeros(200, dtype='f4')
    for region in regions_to_use:
        region_id = REGIONS.index(region)
        flows = main_model.FlowDict
        print(flows.keys())
        net_trade += abs(flows['F_0_2'].Values[:, 0, region_id][1:])  # Imports
        net_trade += abs(flows['F_2_0'].Values[:, 0, region_id][1:])  # Exports
    plt.plot(range(1901, 2101), net_trade)
    plt.xlabel("Time (y)")
    plt.ylabel("Trade (t)")
    plt.title("Total trade of new steel (Imports+Exports) in tonnes")
    plt.legend(["All regions"])
    plt.show()


def show_production(main_model, regions_to_use):
    usa_worldsteel = np.array([98658, 97427, 101803, 90104, 91587, 93677, 99681, 94897, 98557, 98102])
    eur_worldsteel = np.array([191057, 182185, 193387, 187452, 188246, 192511, 202478, 195580, 206965, 209732])
    ref_worldsteel = np.array([73950, 85657, 98489, 99699, 101214, 106470, 113362, 113206, 119906, 124169])
    fig, ax = plt.subplots()
    plt.plot(range(1998, 2008), usa_worldsteel * 1000, 'b--')
    plt.plot(range(1998, 2008), eur_worldsteel * 1000, 'r--')
    plt.plot(range(1998, 2008), ref_worldsteel * 1000, 'g--')
    colors = ['r', 'b', 'g']
    counter = 0
    for region in regions_to_use:
        region_id = REGIONS.index(region)
        plt.plot(range(1998, 2008), main_model.FlowDict['F_1_2'].Values[:, 0, region_id][98:108], colors[counter])
        counter += 1
    plt.legend(regions_to_use)
    plt.xlabel("Time (y)")
    plt.ylabel("Production (t)")
    plt.title("Production of steel in tonnes: Model (solid) vs. WS-Data (dashes)")
    plt.show()


def show_use(main_model, regions_to_use):
    usa_worldsteel = np.array([135280, 127949, 133353, 114397, 118268, 105776, 123835, 113325, 128526, 114050])
    eur_worldsteel = np.array([177745, 173430, 184561, 179172, 176948, 185794, 189698, 181555, 207670, 220166])
    ref_worldsteel = np.array([28370, 29401, 39542, 42502, 39717, 42172, 45105, 48681, 57121, 65205])
    fig, ax = plt.subplots()
    plt.plot(range(1998, 2008), usa_worldsteel * 1000, 'b--')
    plt.plot(range(1998, 2008), eur_worldsteel * 1000, 'r--')
    plt.plot(range(1998, 2008), ref_worldsteel * 1000, 'g--')
    colors = ['r', 'b', 'g']
    counter = 0
    for region_id, region in enumerate(REGIONS):
        if region in regions_to_use:
            plt.plot(range(1998, 2008), np.sum(main_model.FlowDict['F_2_4'].Values[:, 0, region_id, :], axis=1)[98:108],
                     colors[counter])
            counter += 1
    plt.legend(regions_to_use)
    plt.xlabel("Time (y)")
    plt.ylabel("Use (t)")
    plt.title("Use of steel in tonnes: Model (solid) vs. WS-Data (dashes)")
    plt.show()


def show_use_dsms(main_model, regions):
    dsm_dict = dynamic_stock_models.load()
    categories = ['Transport', 'Machinery', 'Construction', 'Products']
    for region in regions:
        print(region)
        total = np.zeros(201)
        for cat in categories:
            total += dsm_dict[region][cat].i
        plt.plot(range(1998, 2008), total[98:108])
        print(region + ": " + str(list(total[98:108])))
    plt.legend(regions)
    plt.xlabel("Time (y)")
    plt.ylabel("Use (t)")
    plt.title("Use of steel in tonnes from LOAD_DSMS")
    plt.show()


def master_viz(main_model, primary_stock, scrap_share, waste_stock, inflow_categories, net_trade, production, use,
               use_dsms, regions=REGIONS):
    if primary_stock:
        show_primary_stock(main_model, regions)
    if scrap_share:
        show_scrap_share_production(main_model, regions)
    if waste_stock:
        show_waste_stock(main_model, regions)
    if inflow_categories:
        show_inflow_by_category(main_model, regions)
    if net_trade:
        show_net_trade(main_model, regions)
    if production:
        show_production(main_model, regions)
    if use:
        show_use(main_model, regions)
    if use_dsms:
        show_use_dsms(main_model, regions)


def get_region_indices(regions_to_use):
    region_indices = []
    for region_to_use in regions_to_use:
        region_indices.append(REGIONS.index(region_to_use))
    return region_indices


def main():
    """
    Creates matplotlib graphs of the changeable functions/variables for the changeable regions.
    To select which functions are required, just change Boolean values (True/False -> 1/0) and
    add required regions to region list. For net trade currently all regions are selected as a
    default.
    :return:
    """
    regions_to_use = ['EUR', 'USA', 'REF']
    main_model = load_simson_model()

    # Options: ['LAM','OAS','SSA','EUR','NEU','MEA','REF','CAZ','CHA','IND','JPN','USA']
    show_primary_steel_production = True
    show_scrap_share_in_production = True
    show_waste_stock = True
    show_inflow_by_categories = True
    show_net_trade = False
    production = False
    use = False
    use_dsms = False

    master_viz(main_model, show_primary_steel_production, show_scrap_share_in_production, show_waste_stock,
               show_inflow_by_categories, show_net_trade, production, use, use_dsms, regions_to_use)


if __name__ == '__main__':
    main()
