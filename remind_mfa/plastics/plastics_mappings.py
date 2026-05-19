from remind_mfa.common.common_mappings import CommonDimensionFiles, CommonDisplayNames


class PlasticsDimensionFiles(CommonDimensionFiles):
    _own_mapping = {
        "Element": "elements",
        "Material": "materials",
        "Good": "goods_in_use",
        "Scenario": "scenarios",
        "EU-MFA_Good": "eu_mfa_goods",
        "EU-MFA_Material": "eu_mfa_materials",
        "EU-MFA_Time": "eu_mfa_time",
    }


class PlasticsDisplayNames(CommonDisplayNames):
    _own_mapping = {
        "sysenv": "System environment",
        "feedfoss": "Feedstock(fossil)",
        "feedbio": "Feedstock(biomass)",
        "feeddaccu": "Feedstock(daccu)",
        "feedccu": "Feedstock(ccu)",
        "HVC_input": "High Value Chemical input",
        "C4_input": "C4 input",
        "other_reactants": "Other Reactants",
        "polymerization": "Polymerization",
        "losses": "Losses",
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
        "imports": "Imports",
        "exports": "Exports",
    }
