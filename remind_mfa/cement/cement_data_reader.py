from remind_mfa.common.mrindustry_data_reader import MrindustryDataReader


class CementDataReader(MrindustryDataReader):
    dimension_map = {
        "Time": "time_in_years",
        "Historic Time": "historic_years",
        "Region": "regions",
        "Stock Type": "stock_types",
    }
