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
        "sysenv": "System<br>environment",
        "feedfoss": "Feedstock<br>(fossil)",
        "feedbio": "Feedstock<br>(biomass)",
        "feeddaccu": "Feedstock<br>(DACCU)",
        "feedccu": "Feedstock<br>(CCU)",
        "HVC_input": "High value chemicals input",
        "C4_input": "C4 input",
        "other_reactants": "Other reactants",
        "polymerization": "Polymerization",
        "losses": "Losses",
        "processing": "Processing",
        "fabrication": "Fabrication",
        "reclmech": "Mechanical<br>recycling",
        "reclchem": "Chemical<br>recycling",
        "use": "Use phase",
        "eol": "EoL",
        "collected": "Collected",
        "mismanaged": "Uncollected",
        "incineration": "Incineration",
        "landfill": "Landfilled",
        "uncontrolled": "Uncontrolled",
        "emission": "Emissions",
        "captured": "Captured",
        "atmosphere": "Atmosphere",
        "waste_market": "Waste market",
        "primary_market": "Primary<br>market",
        "intermediate_market": "Intermediate<br>market",
        "good_market": "Good market",
        "imports": "Imports",
        "exports": "Exports",
    }
