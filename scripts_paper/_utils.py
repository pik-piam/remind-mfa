import pickle
import colorsys
from scripts_paper._constants import (
    AGG_COLOR_PALETTE,
    AGG_REGIONS,
    AGG_REGION_ORDER,
    COLOR_PALETTE,
    REGION_DISPLAY_NAMES,
    REMIND_REGION_ORDER,
)


def get_column_name(df, target_name: str) -> str:
    for column in df.columns:
        if str(column).strip().lower() == target_name.lower():
            return column
    raise KeyError(f"Could not find column '{target_name}' in dataframe columns {list(df.columns)}")


def map_region(region: str, aggregate_regions: bool = True) -> str:
    region = str(region)
    if not aggregate_regions:
        return region
    return AGG_REGIONS.get(region, region)


def aggregate_region_timeseries(
    df,
    time_col: str,
    region_col: str,
    value_col: str,
    aggregate_regions: bool = True,
):
    aggregated = df.copy()
    aggregated[region_col] = aggregated[region_col].map(
        lambda region: map_region(region, aggregate_regions=aggregate_regions)
    )
    group_cols = [time_col, region_col]
    preserve_cols = [
        col for col in aggregated.columns if col not in {time_col, region_col, value_col}
    ]
    if preserve_cols:
        group_cols.extend(preserve_cols)
    return aggregated.groupby(group_cols, as_index=False)[value_col].sum().sort_values(group_cols)


def ordered_regions(present_regions, reverse: bool = False, aggregate_regions: bool = True):
    base_order = AGG_REGION_ORDER if aggregate_regions else REMIND_REGION_ORDER
    ordered_from_config = base_order[::-1] if reverse else base_order
    present = [str(region) for region in present_regions]
    configured = [region for region in ordered_from_config if region in present]
    remainder = sorted(region for region in present if region not in set(base_order))
    if reverse:
        remainder = remainder[::-1]
    return configured + remainder


def get_region_color(region: str, region_colors: dict, aggregate_regions: bool = True) -> str:
    if region not in region_colors:
        if aggregate_regions:
            region_colors[region] = AGG_COLOR_PALETTE.get(
                region, COLOR_PALETTE[len(region_colors) % len(COLOR_PALETTE)]
            )
        else:
            region_colors[region] = COLOR_PALETTE[len(region_colors) % len(COLOR_PALETTE)]
    return region_colors[region]


def get_region_label(region: str, aggregate_regions: bool = True) -> str:
    region = str(region)
    if aggregate_regions:
        return region
    return REGION_DISPLAY_NAMES.get(region, region)


def region_mode_suffix(use_h12: bool) -> str:
    return "h12" if use_h12 else "agg5"


def run_pickle_path(directory, run_name: str):
    return directory / f"{run_name}.pickle"


def load_model(directory, run_name: str):
    pickle_path = run_pickle_path(directory, run_name)
    if not pickle_path.exists():
        raise FileNotFoundError(f"Missing run pickle: {pickle_path}")
    with pickle_path.open("rb") as file_handle:
        return pickle.load(file_handle)


def load_future_mfa(directory, run_name: str):
    return load_model(directory, run_name).future_mfa


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
