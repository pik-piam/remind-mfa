from remind_mfa.common.custom_data_reader import CustomDataReader


class CementDataReader(CustomDataReader):
    dimension_map = {
        "Time": "time_in_years",
        "Historic Time": "historic_years",
        "Region": "regions",
        "Stock Type": "stock_types",
        "Structure": "structures",
        "Function": "functions",
    }
