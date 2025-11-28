from remind_mfa.common.custom_data_reader import CustomDataReader


class PlasticsDataReader(CustomDataReader):
    dimension_map = {
        "Time": "time_in_years",
        "Historic Time": "historic_years",
        "Element": "elements",
        "Region": "regions",
        "Material": "materials",
        "Good": "goods_in_use",
        "Intermediate": "intermediate_products",
        "Scenario": "scenarios",
    }
