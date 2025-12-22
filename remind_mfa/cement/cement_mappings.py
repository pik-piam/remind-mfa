from remind_mfa.common.common_mappings import CommonDimensionFiles, CommonDisplayNames


class CementDimensionFiles(CommonDimensionFiles):
    _own_mapping = {
        "Stock Type": "stock_types",
        "Product Material": "product_materials",
        "Product Application": "product_applications",
        "Waste Type": "waste_types",
        "Waste Size": "waste_sizes",
        "Carbonation Location": "carbonation_locations",
    }


class CementDisplayNames(CommonDisplayNames):
    _own_mapping = {
        "sysenv": "System environment",
        "prod_clinker": "Production: Clinker",
        "prod_cement": "Production: Cement",
        "prod_product": "Production: Product",
        "use": "Use phase",
        "eol": "End of life",
        "atmosphere": "Atmosphere",
        "carbonation": "Carbonation",
    }
