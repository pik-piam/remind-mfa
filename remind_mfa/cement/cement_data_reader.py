from remind_mfa.common.custom_data_reader import CustomDataReader


class CementDataReader(CustomDataReader):
    dimension_map = {
        "Time": "time_in_years",
        "Historic Time": "historic_years",
        "Region": "regions",
        "Stock Type": "stock_types",
        "End-use Material": "end_use_materials",
        "Strength Class": "strength_classes",
    }
