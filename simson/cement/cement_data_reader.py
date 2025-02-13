from simson.common.custom_data_reader import CustomDataReader

class CementDataReader(CustomDataReader):
    dimension_map = {
        "Historic Time": "historic_years",
        "Region": "regions",
        "Stock Type": "stock_types"
    }