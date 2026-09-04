import pathlib
from dataclasses import dataclass

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
FIGURE_OUTPUT_DIR = SCRIPT_DIR / "png"

LAST_HISTORICAL_YEAR_CEMENT = 2023
LAST_HISTORICAL_YEAR_PLASTICS = 2024
LAST_HISTORICAL_YEAR_STEEL = 2022

REGION_DISPLAY_NAMES = {
    "CAZ": "Canada, NZ, Australia",
    "CHA": "China",
    "EUR": "EU 28",
    "IND": "India",
    "JPN": "Japan",
    "LAM": "Latin America",
    "MEA": "Mdl. East & N. Africa",
    "NEU": "Non-EU28 Europe",
    "OAS": "Other Asia",
    "REF": "Former Soviet Union",
    "SSA": "Sub-Saharan Africa",
    "USA": "USA",
}
REMIND_REGION_ORDER = list(REGION_DISPLAY_NAMES)

AGG_REGIONS = {
    "CAZ": "OECD",
    "CHA": "China",
    "EUR": "OECD",
    "IND": "S & SE Asia",
    "JPN": "OECD",
    "LAM": "Rest of the World",
    "MEA": "Rest of the World",
    "NEU": "OECD",
    "OAS": "S & SE Asia",
    "REF": "Rest of the World",
    "SSA": "Sub-Saharan Africa",
    "USA": "OECD",
}

AGG_REGION_ORDER = [
    "Sub-Saharan Africa",
    "S & SE Asia",
    "Rest of the World",
    "China",
    "OECD",
]

VIRIDIS_MOD_5 = [
    "#EECF69",
    "#99BB63",
    "#2C9688",
    "#415A9E",
    "#6B2F2B",
]
OKABE_ITO_5 = [
    "#0072B2",  # blue
    "#009E73",  # bluish green
    "#D6C73D",
    "#E69F00",  # orange
    # "#D55E00",  # vermillion
    "#CC79A7",  # reddish purple
]
# ONLY FOR REFERENCE
OKABE_ITO_8 = [
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#009E73",  # bluish green
    "#F0E442",  # yellow
    "#0072B2",  # blue
    "#CC79A7",  # reddish purple
    "#D55E00",  # vermillion
    "#000000",  # black
]
# CMAP_5 = OKABE_ITO_5
CMAP_5 = VIRIDIS_MOD_5

AGG_COLOR_PALETTE = dict(zip(AGG_REGION_ORDER, CMAP_5))

COLOR_PALETTE_1 = [
    "#6929c4",  # Purple
    "#1192e8",  # Cyan
    "#005d5d",  # Teal
    "#9c456b",  # Magenta
    "#fa4d56",  # Red
    "#570408",  # Dark red
    "#198038",  # Green
    "#002d9c",  # Blue
    "#ee538b",  # Magenta
    "#b28600",  # Yellow
    "#009d9a",  # Teal
    "#012749",  # Dark cyan
]

COLOR_PALETTE_2 = [
    "#e41a1c",
    "#377eb8",
    "#4daf4a",
    "#984ea3",
    "#ff7f00",
    "#0032BC",
    "#a65628",
    "#f781bf",
    "#999999",
    "#1b9e77",
    "#d95f02",
    "#7570b3",
]

# 6 hues x 2 brightness levels, chosen to stay distinct and readable on white backgrounds.
COLOR_PALETTE_3 = [
    "#4C9FD6",  # blue light
    "#1F6FA8",  # blue dark
    "#F2A541",  # orange light
    "#C77900",  # orange dark
    "#36B39A",  # teal light
    "#007F6A",  # teal dark
    "#C97DB1",  # magenta light
    "#9B4F83",  # magenta dark
    "#9FAE4C",  # olive light
    "#6F7F1E",  # olive dark
    "#9A7A52",  # brown light
    "#6B4F2A",  # brown dark
]

# 6 hues x 2 brightness levels, increased lightness differences and saturation
COLOR_PALETTE_4 = [
    "#8299FD",  # blue light
    "#4A37C2",  # blue dark
    "#CF8517",  # orange light
    "#B35A00",  # orange dark
    "#4DCCB8",  # teal light
    "#0063AF",  # teal dark
    "#CC79B7",  # magenta light
    "#7B2C65",  # magenta dark
    "#94A42A",  # olive light
    "#4D5F0A",  # olive dark
    "#B89968",  # brown light
    "#4D3412",  # brown dark
]

COLORS_REMIND = {
    "CAZ": "#f58231",
    "CHA": "#3cb44b",
    "MEA": "#4363d8",
    "LAM": "#96cfc8",
    "SSA": "#911eb4",
    "JPN": "#ff9999",
    "USA": "#e6194B",
    "OAS": "#800000",
    "IND": "#808000",
    "FRA": "#000075",
    "DEU": "#f032e6",
    "REF": "#9A6324",
    # "World": "#404040",
    "NEU": "#42d4f4",
    "EUR": "#ffd610",
}

COLOR_PALETTE = COLOR_PALETTE_1

SCENARIO_LABELS = {"SSP2": "SSP2", "SSP1": "SSP1-drivers", "SSP1_CE": "SSP1-CE"}
MATERIAL_ORDER = ("plastics", "steel", "cement")
MFA_REGION_MAPPINGS = ("h12", "iso249")


@dataclass(frozen=True)
class MaterialPlotConfig:
    material: str
    panel_label: str
    production_flow_name: str
    last_historical_year: int
    stock_index: str | None = None
    trade_imports_flow_name: str | None = None
    trade_exports_flow_name: str | None = None
    trade_demand_flow_name: str | None = None
    trade_supply_flow_name: str | None = None
    sankey_slice_dict: dict[str, str | int] | None = None


MATERIAL_CONFIGS = {
    "plastics": MaterialPlotConfig(
        material="plastics",
        panel_label="a) Plastics",
        production_flow_name="polymerization => primary_market",
        last_historical_year=LAST_HISTORICAL_YEAR_PLASTICS,
        trade_imports_flow_name="imports => primary_market",
        trade_exports_flow_name="primary_market => exports",
        trade_demand_flow_name="primary_market => fabrication",
        trade_supply_flow_name="polymerization => primary_market",
        sankey_slice_dict={"t": 2050, "e": "C"},
    ),
    "steel": MaterialPlotConfig(
        material="steel",
        panel_label="b) Steel",
        production_flow_name="forming => ip_market",
        last_historical_year=LAST_HISTORICAL_YEAR_STEEL,
        trade_imports_flow_name="imports => ip_market",
        trade_exports_flow_name="ip_market => exports",
        trade_demand_flow_name="ip_market => fabrication",
        trade_supply_flow_name="forming => ip_market",
        sankey_slice_dict={"t": 2050},
    ),
    "cement": MaterialPlotConfig(
        material="cement",
        panel_label="c) Cement",
        production_flow_name="prod_cement => market_cement",
        last_historical_year=LAST_HISTORICAL_YEAR_CEMENT,
        stock_index="cement",
        trade_imports_flow_name="imports => market_cement",
        trade_exports_flow_name="market_cement => exports",
        trade_demand_flow_name="market_cement => prod_product",
        trade_supply_flow_name="prod_cement => market_cement",
        sankey_slice_dict={"t": 2050},
    ),
}


def get_material_config(material: str) -> MaterialPlotConfig:
    try:
        return MATERIAL_CONFIGS[material.lower()]
    except KeyError as exc:
        valid = ", ".join(MATERIAL_CONFIGS)
        raise ValueError(f"Unknown material '{material}'. Expected one of: {valid}") from exc


def figure_output_path(filename: str) -> pathlib.Path:
    FIGURE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return FIGURE_OUTPUT_DIR / filename
