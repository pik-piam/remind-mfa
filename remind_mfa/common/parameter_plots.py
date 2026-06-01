import itertools
import logging
import math
from typing import Optional

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import flodym as fd

logger = logging.getLogger(__name__)

# 12 perceptually distinct colors (tab10 + yellow + burgundy)
_COLORS = [
    "#1f77b4",  # blue
    "#ff7f0e",  # orange
    "#2ca02c",  # green
    "#d62728",  # red
    "#9467bd",  # purple
    "#8c564b",  # brown
    "#e377c2",  # pink
    "#7f7f7f",  # gray
    "#bcbd22",  # olive
    "#17becf",  # cyan
    "#f0e442",  # yellow
    "#800020",  # burgundy
]
_LINESTYLES = ["-", "--", ":", "-."]


def _get_style(idx: int):
    return _COLORS[idx % len(_COLORS)], _LINESTYLES[(idx // len(_COLORS)) % 4]


def _iter_split(arr: Optional[fd.FlodymArray], dim_letter: Optional[str]) -> dict:
    """Split FlodymArray by dim_letter; return {"": arr} when dim not present or None."""
    if arr is None:
        return {}
    if dim_letter is None or dim_letter not in arr.dims.letters:
        return {"": arr}
    return arr.split(dim_letter)


def _get_from_split(split_dict: dict, key: str) -> Optional[fd.FlodymArray]:
    """Look up key, falling back to "" (broadcast) if the key is missing."""
    return split_dict.get(key, split_dict.get(""))


class ParameterPlotsExporter:
    def __init__(self, output_path: str, last_hist_year: Optional[float] = None):
        self.output_path = output_path
        self.last_hist_year = last_hist_year

    def export(
        self,
        future_params: dict,
        historic_params: Optional[dict],
        descriptions: dict,
    ):
        with PdfPages(self.output_path) as pdf:
            for name in sorted(future_params):
                future_param = future_params[name]
                historic_param = (historic_params or {}).get(name)
                description = descriptions.get(name) or ""
                self._plot_parameter(pdf, name, future_param, historic_param, description)

    # ── role assignment ──────────────────────────────────────────────────

    def _assign_roles(self, param: fd.Parameter) -> Optional[dict]:
        letters = list(param.dims.letters)
        if not letters:
            return None  # scalar

        for x_letter in ("t", "h", "r"):
            if x_letter in letters:
                break
        else:
            x_letter = letters[0]

        remaining = [l for l in letters if l != x_letter]
        region_dim = "r" if "r" in remaining else None
        if region_dim:
            remaining.remove("r")

        color_dim = remaining.pop(0) if remaining else None
        # all further remaining dims → one PDF page per item combination
        page_dims = remaining

        return dict(x=x_letter, region=region_dim, color=color_dim, page_dims=page_dims)

    # ── main plotting ────────────────────────────────────────────────────

    def _plot_parameter(
        self,
        pdf: PdfPages,
        name: str,
        future_param: fd.Parameter,
        historic_param: Optional[fd.Parameter],
        description: str,
    ):
        roles = self._assign_roles(future_param)
        if roles is None:
            self._plot_scalar_page(pdf, name, future_param, description)
            return

        x_letter = roles["x"]
        region_dim = roles["region"]
        color_dim = roles["color"]
        page_dims = roles["page_dims"]

        is_time_x = x_letter in ("t", "h")
        show_historic = (
            is_time_x
            and x_letter == "t"
            and historic_param is not None
            and ("h" in historic_param.dims.letters or "t" in historic_param.dims.letters)
        )
        if show_historic and "h" in historic_param.dims.letters:
            hist_x_letter = "h"
        elif show_historic:
            hist_x_letter = "t"
        else:
            hist_x_letter = None

        # figure grid dimensions (region subpanels only — no extra-dim rows)
        n_region = len(future_param.dims[region_dim].items) if region_dim else 1
        if region_dim:
            ncols = min(4, n_region)
            nrows = math.ceil(n_region / ncols)
        else:
            nrows, ncols = 1, 1

        dim_info = ", ".join(
            f"{l} ({future_param.dims[l].name})" for l in future_param.dims.letters
        )

        if show_historic and hist_x_letter == "h":
            last_hist_year = float(historic_param.dims["h"].items[-1])
        elif self.last_hist_year is not None and is_time_x:
            last_hist_year = self.last_hist_year
        else:
            last_hist_year = None

        if is_time_x:
            x_range = list(future_param.dims[x_letter].items)
            if show_historic:
                x_range = list(historic_param.dims[hist_x_letter].items) + x_range
            shared_xlim = (min(x_range), max(x_range))
        else:
            shared_xlim = None

        # iterate over all page-dim combinations (one PDF page per combination)
        page_combos = (
            list(itertools.product(*[list(future_param.dims[d].items) for d in page_dims]))
            if page_dims
            else [()]
        )

        for page_combo in page_combos:
            fix = {d: v for d, v in zip(page_dims, page_combo)}

            page_arr = future_param[fix] if fix else future_param
            if show_historic and historic_param is not None:
                hist_fix = {d: v for d, v in fix.items() if d in historic_param.dims.letters}
                hist_page_arr = historic_param[hist_fix] if hist_fix else historic_param
            else:
                hist_page_arr = None

            page_suffix = (
                ("  —  " + ", ".join(f"{future_param.dims[d].name}: {v}" for d, v in fix.items()))
                if fix
                else ""
            )

            # y-axis locking
            all_vals = page_arr.values.ravel()
            finite_vals = all_vals[np.isfinite(all_vals)]
            if len(finite_vals) > 0:
                vmin, vmax = float(np.nanmin(finite_vals)), float(np.nanmax(finite_vals))
                lock_y = vmin > 0 and vmax / vmin < 10
                shared_ylim = (vmin * 0.95, vmax * 1.05) if lock_y else None
            else:
                shared_ylim = None

            fig, axes = plt.subplots(
                nrows=nrows,
                ncols=ncols,
                figsize=(16, 4 * nrows + 1.5),
                squeeze=False,
            )

            title_line = name + page_suffix
            style_note = "(—— extrapolated  |  - - pre-extrapolation)" if show_historic else ""
            fig.suptitle(
                f"{title_line}\nDimensions: {dim_info}\n{description}\n{style_note}",
                fontsize=9,
                y=1.0,
                va="top",
            )

            for r_idx, (region_label, region_arr) in enumerate(
                _iter_split(page_arr, region_dim).items()
            ):
                hist_regions = _iter_split(hist_page_arr, region_dim)
                hist_region_arr = _get_from_split(hist_regions, region_label)

                ax = axes[r_idx // ncols, r_idx % ncols] if region_dim else axes[0, 0]
                subplot_title = region_label if region_dim else ""
                if subplot_title:
                    ax.set_title(subplot_title, fontsize=8)

                for c_idx, (color_label, color_arr) in enumerate(
                    _iter_split(region_arr, color_dim).items()
                ):
                    hist_colors = _iter_split(hist_region_arr, color_dim)
                    hist_color_arr = _get_from_split(hist_colors, color_label)

                    color, ls = _get_style(c_idx)
                    legend_label = color_label if (color_dim and color_label) else None

                    if x_letter in color_arr.dims.letters:
                        x_vals = np.array(color_arr.dims[x_letter].items)
                        y_vals = color_arr.values
                        if last_hist_year is not None:
                            in_hist = x_vals <= last_hist_year
                            if np.any(in_hist):
                                ax.plot(
                                    x_vals[in_hist],
                                    y_vals[in_hist],
                                    color=color,
                                    linestyle=ls,
                                    alpha=0.5,
                                    linewidth=1.2,
                                )
                            in_future = ~in_hist
                            if np.any(in_future):
                                ax.plot(
                                    x_vals[in_future],
                                    y_vals[in_future],
                                    color=color,
                                    linestyle=ls,
                                    alpha=0.9,
                                    linewidth=1.2,
                                    label=legend_label,
                                )
                        else:
                            ax.plot(
                                x_vals,
                                y_vals,
                                color=color,
                                linestyle=ls,
                                alpha=0.9,
                                linewidth=1.2,
                                label=legend_label,
                            )

                    if (
                        hist_color_arr is not None
                        and hist_x_letter is not None
                        and hist_x_letter in hist_color_arr.dims.letters
                        and all(l == hist_x_letter for l in hist_color_arr.dims.letters)
                    ):
                        hx_vals = np.array(hist_color_arr.dims[hist_x_letter].items)
                        hy_vals = hist_color_arr.values
                        if hist_x_letter == "t" and last_hist_year is not None:
                            mask = hx_vals <= last_hist_year
                            hx_vals, hy_vals = hx_vals[mask], hy_vals[mask]
                        ax.plot(
                            hx_vals,
                            hy_vals,
                            color=color,
                            linestyle="--",
                            alpha=0.9,
                            linewidth=1.8,
                        )

                if last_hist_year is not None:
                    ax.axvline(
                        x=last_hist_year, color="gray", linestyle=":", alpha=0.6, linewidth=0.8
                    )

                if shared_xlim:
                    ax.set_xlim(*shared_xlim)
                if shared_ylim:
                    ax.set_ylim(*shared_ylim)
                ax.tick_params(labelsize=7)
                handles, _ = ax.get_legend_handles_labels()
                if handles:
                    ax.legend(fontsize=6, loc="best")

            # hide unfilled grid cells
            if region_dim:
                for idx in range(n_region, nrows * ncols):
                    axes[idx // ncols, idx % ncols].set_visible(False)

            fig.tight_layout(rect=[0, 0, 1, 0.95])
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

    def _plot_scalar_page(
        self,
        pdf: PdfPages,
        name: str,
        param: fd.Parameter,
        description: str,
    ):
        scalar_val = float(param.values) if param.values.ndim == 0 else param.values.item()
        fig, ax = plt.subplots(figsize=(16, 3))
        ax.axis("off")
        ax.text(
            0.5,
            0.5,
            f"{name}\n\nDimensions: (scalar)\n{description}\n\nValue: {scalar_val}",
            ha="center",
            va="center",
            fontsize=11,
            transform=ax.transAxes,
        )
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)
