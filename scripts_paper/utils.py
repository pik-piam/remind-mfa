import colorsys
from constants import AGG_COLOR_PALETTE, AGG_REGIONS, AGG_REGION_ORDER, COLOR_PALETTE


def get_column_name(df, target_name: str) -> str:
    for column in df.columns:
        if str(column).strip().lower() == target_name.lower():
            return column
    raise KeyError(f"Could not find column '{target_name}' in dataframe columns {list(df.columns)}")


def map_region(region: str) -> str:
    return AGG_REGIONS.get(str(region), str(region))


def aggregate_region_timeseries(df, time_col: str, region_col: str, value_col: str):
    aggregated = df.copy()
    aggregated[region_col] = aggregated[region_col].map(map_region)
    return (
        aggregated.groupby([time_col, region_col], as_index=False)[value_col]
        .sum()
        .sort_values([region_col, time_col])
    )


def ordered_regions(present_regions, reverse: bool = False):
    ordered_from_config = AGG_REGION_ORDER[::-1] if reverse else AGG_REGION_ORDER
    present = [str(region) for region in present_regions]
    configured = [region for region in ordered_from_config if region in present]
    remainder = sorted(region for region in present if region not in set(AGG_REGION_ORDER))
    if reverse:
        remainder = remainder[::-1]
    return configured + remainder


def get_region_color(region: str, region_colors: dict) -> str:
    if region not in region_colors:
        region_colors[region] = AGG_COLOR_PALETTE.get(
            region, COLOR_PALETTE[len(region_colors) % len(COLOR_PALETTE)]
        )
    return region_colors[region]


def _hex_to_rgb01(color: str):
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _rgb01_to_hex(rgb):
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in rgb)


def cap_color_brightness(color: str, maximum_brightness: float) -> str:
    if not color.startswith("#") or len(color) != 7:
        return color
    red, green, blue = _hex_to_rgb01(color)
    hue, saturation, brightness = colorsys.rgb_to_hsv(red, green, blue)
    capped_brightness = min(brightness, maximum_brightness)
    if capped_brightness == brightness:
        return color
    capped_rgb = colorsys.hsv_to_rgb(hue, saturation, capped_brightness)
    return _rgb01_to_hex(capped_rgb)


def legend_name(label: str, color: str, maximum_brightness: float) -> str:
    legend_text_color = cap_color_brightness(color, maximum_brightness)
    return f'<span style="color:{legend_text_color}">{label}</span>'
