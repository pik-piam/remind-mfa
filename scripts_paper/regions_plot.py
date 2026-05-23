"""Plot the country-to-region mapping as a discrete Plotly choropleth map.

The mapping is read from ``regionmapping.csv`` in the same directory. Each ISO3
country code is colored according to its REMIND region code.
"""

from __future__ import annotations

import pathlib

import pandas as pd
import plotly.graph_objects as go

from constants import REGION_DISPLAY_NAMES
from constants import COLORS_REMIND
# from constants import COLOR_PALETTE


CSV_PATH = pathlib.Path(__file__).with_name("regionmapping.csv")
OUTPUT_HTML = pathlib.Path(__file__).with_name("regions_plot.html")
OUTPUT_PNG = pathlib.Path(__file__).with_name("regions_plot.png")


def load_region_mapping(csv_path: pathlib.Path) -> pd.DataFrame:
	"""Load the mapping CSV into a normalized dataframe."""

	df = pd.read_csv(
		csv_path,
		sep=";",
		header=None,
		skiprows=1,
		names=["row_id", "country", "iso3", "region"],
		dtype=str,
	)

	df = df.dropna(subset=["iso3", "region"]).copy()
	df["country"] = df["country"].str.strip()
	df["iso3"] = df["iso3"].str.strip().str.upper()
	df["region"] = df["region"].str.strip().str.upper()
    # Remove Antarctica (ATA)
	df = df[df["iso3"] != "ATA"].copy()
	return df


def get_region_order(regions: pd.Series) -> list[str]:
	"""Return a stable region order matching the project defaults."""

	region_set = set(regions.dropna().unique())
	ordered = [region for region in REGION_DISPLAY_NAMES if region in region_set]
	remaining = sorted(region_set.difference(ordered))
	return ordered + remaining


def build_discrete_colorscale(colors: list[str]) -> list[list[float | str]]:
	"""Create a stepped colorscale for Plotly choropleths."""

	if not colors:
		raise ValueError("At least one color is required")

	if len(colors) == 1:
		return [[0.0, colors[0]], [1.0, colors[0]]]

	colorscale: list[list[float | str]] = []
	n_colors = len(colors)
	for index, color in enumerate(colors):
		start = index / n_colors
		end = (index + 1) / n_colors
		colorscale.append([start, color])
		colorscale.append([end, color])
	return colorscale


def build_figure(df: pd.DataFrame) -> go.Figure:
	"""Build the choropleth figure for the region mapping."""

	region_order = get_region_order(df["region"])
	region_to_id = {region: idx for idx, region in enumerate(region_order)}
	id_to_label = {
		region_to_id[region]: REGION_DISPLAY_NAMES.get(region, region) for region in region_order
	}

	# palette = [COLOR_PALETTE[i % len(COLOR_PALETTE)] for i in range(len(region_order))]
	palette = [COLORS_REMIND[region] for region in region_order]
	colorscale = build_discrete_colorscale(palette)

	plot_df = df.copy()
	plot_df["region_id"] = plot_df["region"].map(region_to_id)
	plot_df["region_label"] = plot_df["region"].map(lambda value: REGION_DISPLAY_NAMES.get(value, value))

	fig = go.Figure(
		go.Choropleth(
			locations=plot_df["iso3"],
			z=plot_df["region_id"],
			customdata=plot_df[["country", "region_label"]].to_numpy(),
			locationmode="ISO-3",
			colorscale=colorscale,
			zmin=-0.5,
			zmax=len(region_order) - 0.5,
			marker_line_color="white",
			marker_line_width=0.4,
			colorbar=dict(
				# title="Region",
				tickmode="array",
				tickvals=list(id_to_label.keys()),
				ticktext=list(id_to_label.values()),
				len=0.75,
			),
			hovertemplate=(
				"%{customdata[0]}<br>"
				"ISO3: %{location}<br>"
				"Region: %{customdata[1]}<extra></extra>"
			),
		)
	)

	fig.update_layout(
		# title="Country-to-region mapping",
		template="plotly_white",
		width=600,
		height=300,
		margin=dict(l=10, r=10, t=10, b=10),
	)
	fig.update_geos(
		showframe=False,
		showcoastlines=False,
		projection_type="natural earth",
		showland=True,
		landcolor="rgb(245, 245, 245)",
	)

	return fig


def main() -> None:
	"""Render the map and save HTML and PNG outputs."""

	df = load_region_mapping(CSV_PATH)
	fig = build_figure(df)
	fig.show()

	try:
		fig.write_image(OUTPUT_PNG, width=600, height=300, scale=2)
	except Exception as exc:  # pragma: no cover - optional export dependency
		print(f"Could not write PNG image: {exc}")


if __name__ == "__main__":
	main()
