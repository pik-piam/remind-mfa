import pathlib


PATH_CEMENT = pathlib.Path("data/cement/output/export/pickle")
PATH_PLASTICS = pathlib.Path("data/plastics/output/export/pickle")
PATH_STEEL = pathlib.Path("data/steel/output/export/pickle")

# Default runs use SSP2 unless explicitly noted otherwise.
RUN_CEMENT = "model_cement_SSP2_h12_2026-03-31--17-00-45"
RUN_PLASTICS = "model_plastics_SSP2_h12_2026-03-31--17-03-32"
RUN_STEEL = "model_steel_SSP2_h12_2026-03-31--16-39-52"
RUN_STEEL_SSP1 = "model_steel_SSP1_h12_2026-04-01--14-31-04"
RUN_STEEL_SSP1_LD = "model_steel_SSP1_LD_h12_2026-04-01--14-31-31"

LAST_HISTORICAL_YEAR_CEMENT = 2023
LAST_HISTORICAL_YEAR_PLASTICS = 2019
LAST_HISTORICAL_YEAR_STEEL = 2022

REGION_DISPLAY_NAMES = {
	"CAZ": "Canada, NZ, Australia",
	"CHA": "China",
	"EUR": "EU 28",
	"IND": "India",
	"JPN": "Japan",
	"LAM": "Latin America and<br>the Caribbean",
	"MEA": "Middle East,<br>North Africa,<br>Central Asia",
	"NEU": "Non-EU28 Europe",
	"OAS": "Other Asia",
	"REF": "Countries from the<br>Reforming Economies of<br>the Former Soviet Union",
	"SSA": "Sub-Saharan Africa",
	"USA": "USA",
}

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
	"World": "#404040",
	"NEU": "#42d4f4",
	"EUR": "#ffd610",
}

COLOR_PALETTE = COLOR_PALETTE_1