from remind_mfa.common.mrindustry_data_reader import MrindustryDataReader


class CementDataReader(MrindustryDataReader):
    dimension_map = {
        "Time": "time_in_years",
        "Historic Time": "historic_years",
        "Region": "regions",
        "Stock Type": "stock_types",
        "Product Material": "product_materials",
        "Product Application": "product_applications",
        "Waste Type": "waste_types",
        "Waste Size": "waste_sizes",
        "Carbonation Location": "carbonation_locations",
    }
