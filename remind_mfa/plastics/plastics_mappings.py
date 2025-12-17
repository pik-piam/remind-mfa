from remind_mfa.common.common_mappings import CommonDimensionFiles, CommonDisplayNames


class PlasticsDimensionFiles(CommonDimensionFiles):
    _own_mapping = {
        "Element": "elements",
        "Material": "materials",
        "Good": "goods_in_use",
        "Scenario": "scenarios",
    }


class PlasticsDisplayNames(CommonDisplayNames):
    _own_mapping = {
        "sysenv": "System environment",
        "virginfoss": "Prim(fossil)",
        "virginbio": "Prim(biomass)",
        "virgindaccu": "Prim(daccu)",
        "virginccu": "Prim(ccu)",
        "virgin": "Prim(total)",
        "processing": "Proc",
        "fabrication": "Fabri",
        "reclmech": "Mech recycling",
        "reclchem": "Chem recycling",
        "use": "Use Phase",
        "eol": "EoL",
        "collected": "Collect",
        "mismanaged": "Uncollected",
        "incineration": "Incineration",
        "landfill": "Landfill",
        "uncontrolled": "Uncontrolled",
        "emission": "Emissions",
        "captured": "Captured",
        "atmosphere": "Atmosphere",
        "waste_market": "Waste Market",
        "primary_market": "Prim Market",
        "intermediate_market": "Inter Market",
        "good_market": "Good Market",
    }
