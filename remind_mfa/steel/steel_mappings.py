from remind_mfa.common.common_mappings import CommonDimensionFiles, CommonDisplayNames


class SteelDimensionFiles(CommonDimensionFiles):
    _own_mapping = {
        "Material": "materials",
        "Good": "goods_in_use",
        "Intermediate": "intermediate_products",
        "Scenario": "scenarios",
    }

class SteelDisplayNames(CommonDisplayNames):
    _own_mapping = {
        "sysenv": "System environment",
        "losses": "Losses",
        "imports": "Imports",
        "exports": "Exports",
        "extraction": "Ore<br>Extraction",
        "bof_production": "Production<br>from ores",
        "eaf_production": "Production<br>(EAF)",
        "forming": "Forming",
        "ip_market": "Intermediate<br>products",
        "fabrication": "Fabrication",
        "good_market": "Good Market",
        "in_use": "Use phase",
        "use": "Use phase",
        "obsolete": "Obsolete<br>stocks",
        "eol_market": "End of life<br>products",
        "recycling": "Recycling",
        "scrap_market": "Scrap<br>market",
        "excess_scrap": "Excess<br>scrap",
        "intermediate": "Intermediate Products",
        "indirect": "Indirect (Goods)",
        "scrap": "Scrap",
    }