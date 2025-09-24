from remind_mfa.common.custom_data_reader import REMINDMFAReader


class CementDataReader(REMINDMFAReader):
    dimension_map = {
        "Time": "time_in_years",
        "Historic Time": "historic_years",
        "Region": "regions",
        "Stock Type": "stock_types",
    }
