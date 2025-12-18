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
        "virginfoss": "Feedstock(fossil)",
        "virginbio": "Feedstock(biomass)",
        "virgindaccu": "Feedstock(daccu)",
        "virginccu": "Feedstock(ccu)",
        "virgin": "Virgin Production",
        "processing": "Processing",
        "fabrication": "Fabrication",
        "reclmech": "Mechanical Recycling",
        "reclchem": "Chemical Recycling",
        "use": "Use Phase",
        "eol": "EoL",
        "collected": "Collected",
        "mismanaged": "Uncollected",
        "incineration": "Incineration",
        "landfill": "Landfilled",
        "uncontrolled": "Uncontrolled",
        "emission": "Emissions",
        "captured": "Captured",
        "atmosphere": "Atmosphere",
        "waste_market": "Waste Market",
        "primary_market": "Primary Market",
        "intermediate_market": "Intermediate Market",
        "good_market": "Good Market",
    }
