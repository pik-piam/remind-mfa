from remind_mfa.common.common_data_reader import CommonDataReader


class SteelDataReader(CommonDataReader):
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
