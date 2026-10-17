import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full")


@app.cell
def _():
    # Start as rendered web application (recommended):
    # uv run marimo run notebooks/compare_runs.py
    return


@app.cell
def _():
    from pathlib import Path

    import marimo as mo

    from remind_mfa.common import run_comparison as rc

    return Path, mo, rc


@app.cell
def _(mo):
    mo.md("""
    # Compare runs
    """)
    return


@app.cell
def _(Path):
    repo_root = next(
        path for path in (Path.cwd(), *Path.cwd().parents) if (path / "pyproject.toml").exists()
    )
    data_root = repo_root / "data_out"
    return (data_root,)


@app.cell
def _(data_root, mo, rc):
    discovered = rc.discover_runs(data_root)
    # By default the two newest runs (with the same model)
    newest_model = discovered[0].model if discovered else None
    defaults = [run for run in discovered if run.model == newest_model][:2]

    run_picker = mo.ui.multiselect(
        options={run.display_path(data_root): run for run in discovered},
        value=[run.display_path(data_root) for run in defaults],
    )
    extra_run_picker = mo.ui.file_browser(
        initial_path=data_root,
        selection_mode="all",
        multiple=True,
    )
    mo.vstack(
        [
            mo.md("## Runs to compare"),
            mo.md("Runs found under `data_out`:"),
            run_picker,
            mo.md("Additional runs (e.g. fetched from the HPC)"),
            extra_run_picker,
        ]
    )
    return extra_run_picker, run_picker


@app.cell
def _(Path, data_root, extra_run_picker, mo, rc, run_picker):
    selected_runs: list[rc.RunInfo] = list(run_picker.value) + [
        rc.RunInfo.from_path(Path(selected.path)) for selected in extra_run_picker.value
    ]
    mo.stop(not selected_runs, mo.md("**Select at least one run above.**"))

    label_inputs = mo.ui.array(
        [
            mo.ui.text(value=label, label=run.display_path(data_root), full_width=True)
            for run, label in zip(
                selected_runs, rc.unique_labels([run.label for run in selected_runs])
            )
        ],
        label="Labels",
    )
    mo.vstack([mo.md("## Labels for the runs"), label_inputs])
    return label_inputs, selected_runs


@app.cell
def _(label_inputs, mo, rc, selected_runs: "list[rc.RunInfo]"):
    _runs = {
        run_label: run_info
        for run_info, run_label in zip(selected_runs, rc.unique_labels(list(label_inputs.value)))
    }
    _runs_as_dict, load_failures = rc.load_runs(_runs)
    runs = _runs_as_dict.values()

    mo.stop(
        not runs,
        mo.md("**None of the selected runs could be read.**\n" + "\n".join(load_failures)),
    )
    if load_failures:
        callout = mo.callout(
            mo.md(
                "**Could not read the runs -> Skipped**\n\n"
                + "\n".join(f"- {key}: \n\n    {error}" for key, error in load_failures.items())
            ),
            kind="danger",
        )
    else:
        callout = mo.callout("All runs loaded successfully.", kind="success")
    callout
    return (runs,)


@app.cell
def _(mo, rc, runs):
    all_variables = rc.common_variables(runs)
    mo.stop(
        not all_variables,
        mo.md("**The selected runs have no variables in common.**"),
    )

    variable_picker = mo.ui.multiselect(
        options=all_variables,
        value=all_variables[:1],
    )
    mo.vstack([mo.md("## Variables to compare"), variable_picker])
    return (variable_picker,)


@app.cell
def _(mo, rc, runs, variable_picker):
    variables = list(variable_picker.value)
    mo.stop(not variables, mo.md("**Select at least one variable.**"))
    df = rc.with_world(rc.build_frame(runs, variables))
    dimensions = [column for column in rc.dimension_columns(df) if column != rc.RUN_COLUMN]
    return df, dimensions, variables


@app.cell
def _(dimensions, mo, rc, runs, variables):
    chart_picker = mo.ui.dropdown(
        options={chart.value: chart for chart in rc.ChartType},
        value=rc.ChartType.LINE.value,
        label="Chart type",
    )
    x_picker = mo.ui.dropdown(
        options=dimensions,
        value="Time" if "Time" in dimensions else dimensions[0],
        label="x axis",
    )
    color_picker = mo.ui.dropdown(
        options=dimensions,
        value=rc.VARIABLE_COLUMN if len(variables) > 1 else None,
        allow_select_none=True,
        label="Colour",
    )
    facet_picker = mo.ui.dropdown(
        options=dimensions,
        value=rc.REGION_COLUMN if rc.REGION_COLUMN in dimensions else None,
        allow_select_none=True,
        label="Subplots",
    )
    shares_picker = mo.ui.checkbox(label="Share of the colours' sum (%)")
    scale_picker = mo.ui.dropdown(
        options={"model unit": 1.0, "Mt (1e-6)": 1e-6, "Gt (1e-9)": 1e-9},
        value="model unit",
        label="Scale",
    )
    reference_picker = mo.ui.dropdown(
        options=[run.label for run in runs],
        value=next(iter(runs)).label,
        label="Reference run",
    )
    difference_picker = mo.ui.radio(
        options=["relative", "absolute"],
        value="relative",
        label="Difference",
        inline=True,
    )
    mo.vstack(
        [
            mo.md("## Chart"),
            mo.hstack(
                [chart_picker, x_picker, color_picker, facet_picker, scale_picker],
                justify="start",
                gap=2,
            ),
            mo.hstack([shares_picker, reference_picker, difference_picker], justify="start", gap=2),
        ]
    )
    return (
        chart_picker,
        color_picker,
        difference_picker,
        facet_picker,
        reference_picker,
        scale_picker,
        shares_picker,
        x_picker,
    )


@app.cell
def _(chart_picker, df, dimensions, mo, rc):
    is_bar = chart_picker.value in (rc.ChartType.BAR_STACKED, rc.ChartType.BAR_GROUPED)

    def default_items(column: str) -> list:
        items = rc.ordered_items(df[column])
        if not is_bar or column != "Time":
            return items
        # a bar chart with 200 year positions is unreadable, so start from a few milestones
        return [year for year in (2020, 2030, 2050, 2100) if year in items] or items[-1:]

    filter_controls = mo.ui.dictionary(
        {
            column: mo.ui.multiselect(
                options=rc.ordered_items(df[column]),
                value=default_items(column),
                label=column,
                full_width=True,
            )
            for column in dimensions
            if column != rc.VARIABLE_COLUMN
        }
    )
    mo.vstack([mo.md("## Restrict items"), *filter_controls.elements.values()])
    return (filter_controls,)


@app.cell
def _(
    chart_picker,
    color_picker,
    df,
    difference_picker,
    facet_picker,
    filter_controls,
    mo,
    rc,
    reference_picker,
    scale_picker,
    shares_picker,
    variables,
    x_picker,
):
    plot_data = rc.apply_filters(df, filter_controls.value)
    if shares_picker.value:
        unit_label = "share (%)"
    elif scale_picker.value != 1.0:
        plot_data = plot_data.assign(value=plot_data[rc.VALUE_COLUMN] * scale_picker.value)
        unit_label = scale_picker.selected_key
    else:
        unit_label = "value"
    try:
        figures = rc.frame_figures(
            plot_data,
            x=x_picker.value,
            color=color_picker.value,
            facet=facet_picker.value,
            chart_type=chart_picker.value,
            shares=shares_picker.value,
            title=", ".join(variables),
            ylabel=unit_label,
        )
    except ValueError as error:
        mo.stop(True, mo.callout(mo.md(f"**{error}**"), kind="danger"))

    # the reference goes first, the other runs keep their order
    labels = sorted(figures, key=lambda label: label != reference_picker.value)
    compared = [figures[label] for label in labels]
    overlay = rc.overlay_figures(compared, labels)
    difference = rc.difference_figure(
        compared, labels, relative=difference_picker.value == "relative"
    )
    mo.vstack([overlay] if difference is None else [overlay, difference])
    return


if __name__ == "__main__":
    app.run()
