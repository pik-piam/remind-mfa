from remind_mfa.common.common_mappings import CommonDimensionFiles, CommonDisplayNames


class CementDimensionFiles(CommonDimensionFiles):
    _own_mapping = {
        "End Use": "end_uses",
        "Common End Use": "common_end_uses",
        "Bottom-up End Use": "bottom_up_end_uses",
        "Dwelling Type": "dwelling_types",
        "Extended End Use": "extended_end_uses",
        "Product Material": "product_materials",
        "Product Application": "product_applications",
        "Material Constituent": "material_constituents",
        "Waste Type": "waste_types",
        "Waste Size": "waste_sizes",
        "Carbonation Location": "carbonation_locations",
        "Structure": "structures",
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
        "market_clinker": "Market: Clinker",
        "market_cement": "Market: Cement",
    }
