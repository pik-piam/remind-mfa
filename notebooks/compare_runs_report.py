import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full")


@app.cell
def _():
    # Start as rendered web application (recommended):
    # uv run marimo run notebooks/compare_runs_report.py
    # Headless use (mostly for CI):
    # uv run marimo export html notebooks/compare_runs_report.py -o out.html -- --reference <run>/model.pickle --other <run>/model.pickle
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
    # Compare a run against a reference
    """)
    return


@app.cell
def _(Path, mo, rc):
    repo_root = next(
        path for path in (Path.cwd(), *Path.cwd().parents) if (path / "pyproject.toml").exists()
    )
    data_root = repo_root / "data_out"

    _args = mo.cli_args()
    if _args.get("reference") is None and _args.get("other") is None:
        cli_runs = None
    else:
        if _args.get("reference") is None or _args.get("other") is None:
            raise ValueError("Both reference and run must be specified together.")

        cli_runs = {
            role: rc.RunInfo.from_path(
                (repo_root / str(_args.get(role))).resolve(),
                label=_args.get(f"{role}-label"),
            )
            for role in ("reference", "other")
        }
    cli_export_summary_path = (
        (repo_root / str(_args.get("summary"))).resolve()
        if _args.get("summary") is not None
        else None
    )
    return cli_export_summary_path, cli_runs, data_root


@app.cell
def _(cli_runs, data_root, mo, rc):
    _candidates = rc.discover_runs(data_root)
    mo.stop(
        len(_candidates) < 2,
        mo.md(f"At least two runs are required in {data_root} for comparison."),
    )

    _run_options = {candidate.display_path(data_root): candidate for candidate in _candidates}

    # By default, the newest run is compared against the newest earlier run of the same model
    _default_other = _candidates[0]
    _default_reference = next(
        (candidate for candidate in _candidates[1:] if candidate.model == _default_other.model),
        _candidates[1],
    )
    reference_picker = mo.ui.dropdown(
        options=_run_options,
        value=_default_reference.display_path(data_root),
        label="Reference run",
    )
    other_picker = mo.ui.dropdown(
        options=_run_options,
        value=_default_other.display_path(data_root),
        label="Compared run",
    )
    (
        mo.vstack(
            [
                mo.md("## Runs to compare"),
                mo.hstack([other_picker, reference_picker], justify="start", gap=2, widths="equal"),
            ]
        )
        if not cli_runs
        else None
    )
    return other_picker, reference_picker


@app.cell
def _(cli_runs, mo, other_picker, rc, reference_picker):
    mo.stop(
        (reference_picker.value is None or other_picker.value is None) and not cli_runs,
        mo.md("**Select both runs.**"),
    )
    _default_labels = rc.unique_labels([reference_picker.value.label, other_picker.value.label])
    reference_label_input = mo.ui.text(
        value=_default_labels[0], label="Reference run label", full_width=True
    )
    other_label_input = mo.ui.text(
        value=_default_labels[1], label="Compared run label", full_width=True
    )
    (
        mo.vstack(
            [
                mo.md("## Labels for the runs"),
                mo.hstack(
                    [other_label_input, reference_label_input],
                    justify="start",
                    gap=2,
                    widths="equal",
                ),
            ]
        )
        if not cli_runs
        else None
    )
    return other_label_input, reference_label_input


@app.cell
def _(
    cli_runs,
    mo,
    other_label_input,
    other_picker,
    rc,
    reference_label_input,
    reference_picker,
):
    runs = cli_runs or {
        "reference": rc.RunInfo.from_path(reference_picker.value.path, reference_label_input.value),
        "other": rc.RunInfo.from_path(other_picker.value.path, other_label_input.value),
    }
    loaded_runs, load_failures = rc.load_runs(runs)

    mo.stop(
        load_failures,
        mo.callout(
            mo.md(
                "**Could not read the runs**\n\n"
                + "\n".join(f"- {key}: \n\n    {error}" for key, error in load_failures.items())
            ),
            kind="danger",
        ),
    )
    reference_run, other_run = loaded_runs["reference"], loaded_runs["other"]
    mo.stop(
        not (reference_run.is_model and other_run.is_model),
        mo.callout(mo.md("**Only model pickles can be compared here.**"), kind="danger"),
    )
    mo.stop(
        reference_run.model_name != other_run.model_name,
        mo.callout(
            mo.md(
                f"**The runs belong to different models** "
                f"(reference: {reference_run.model_name} vs other: {other_run.model_name})."
            ),
            kind="danger",
        ),
    )
    mo.md(
        f"## Comparing runs \n - Run: **{other_run.label}** (`{other_run.path}`) \n - Reference: **{reference_run.label}** "
        f"(`{reference_run.path}`) \n\n Model: **{other_run.model_name}**."
    )
    return other_run, reference_run


@app.cell
def _(cli_export_summary_path, mo, other_run, rc, reference_run):
    changes = rc.regional_changes(reference_run, other_run)
    change_verdict = rc.summarize_changes(changes)
    verdict_text = change_verdict.as_markdown()
    if cli_export_summary_path is not None:
        # Add the model summary line that will later be shown as a PR comment
        cli_export_summary_path.parent.mkdir(parents=True, exist_ok=True)
        cli_export_summary_path.write_text(
            f"**{other_run.model_name}**: {verdict_text}\n", encoding="utf-8"
        )
    mo.vstack(
        [
            mo.md("## Summary"),
            mo.callout(
                mo.md(
                    f"{verdict_text}\n\n <small>A variable counts as changed if its global total or any "
                    f"region differs by more than {rc.RELATIVE_TOLERANCE:g} of its largest "
                    "reference value.</small>"
                ),
                kind="success" if change_verdict.identical else "warn",
            ),
        ]
    )
    return (changes,)


@app.cell
def _(changes, mo, other_run, rc, reference_run):
    _global_changes = (
        changes[changes[rc.REGION_COLUMN] == rc.WORLD]
        .drop(columns=rc.REGION_COLUMN)
        .sort_values(rc.CHANGE_COLUMN, key=abs, ascending=False, ignore_index=True)
    )
    mo.vstack(
        [
            mo.md(
                "### Largest changes globally\n"
                "<small>Largest change over all years relative to the largest reference value. Using the largest reference value as the scale prevents years with near-zero reference values from dominating.</small>"
            ),
            mo.ui.table(
                _global_changes,
                selection=None,
                page_size=15,
                format_mapping={
                    rc.CHANGE_COLUMN: rc.format_change,
                    reference_run.label: lambda value: f"{value:.4g}",
                    other_run.label: lambda value: f"{value:.4g}",
                },
            ),
        ]
    )
    return


@app.cell
def _(changes, mo, rc):
    mo.vstack(
        [
            mo.md(
                "### Largest changes by region\n"
                "<small>Largest change over all years relative to the largest reference value.</small>"
            ),
            rc.change_heatmap(changes),
        ]
    )
    return


@app.cell
def _(mo, other_run, rc, reference_run):
    visualization_cfg = rc.visualization_cfg(other_run.model.visualizer.cfg)
    figure_sets = {}
    figure_failures = []
    for run in (reference_run, other_run):
        try:
            figure_sets[run.label] = rc.standard_figures(run, visualization_cfg)
        except Exception as figure_error:
            # e.g. the current visualizer reads a model attribute an older run does not have
            figure_failures.append(f"- `{run.label}`: {figure_error!r}")
    mo.stop(
        figure_failures,
        mo.callout(
            mo.md("**The visualizer failed on:**\n" + "\n".join(figure_failures)),
            kind="danger",
        ),
    )
    reference_figures = figure_sets[reference_run.label]
    other_figures = figure_sets[other_run.label]
    return other_figures, reference_figures


@app.cell
def _(mo, other_figures, other_run, rc, reference_figures, reference_run):
    labels = [reference_run.label, other_run.label]
    relative = True
    compare_failures = []

    def compare(reference_figure, other_figure):
        """Overlay and difference of one figure; Sankey diagrams go side by side."""
        if rc.is_sankey(reference_figure):
            return mo.hstack(
                [
                    mo.vstack([mo.md(f"**{labels[0]}**"), reference_figure]),
                    mo.vstack([mo.md(f"**{labels[1]}**"), other_figure]),
                ],
                widths="equal",
            )
        figures = [reference_figure, other_figure]
        overlay = rc.overlay_figures(figures, labels)
        difference = rc.difference_figure(figures, labels, relative=relative)
        if difference is None:
            difference = mo.callout(
                mo.md(
                    "The runs' traces differ (e.g. other regions or goods), "
                    "so no difference figure is drawn."
                ),
                kind="info",
            )
        return mo.vstack([overlay, difference])

    def section(name, title, anchor=None):
        try:
            body = compare(reference_figures[name], other_figures[name])
        except Exception as compare_error:
            compare_failures.append(f"- `{name}`: {compare_error!r}")
            return None
        heading = mo.md(f"## {title}")
        if anchor is not None:
            heading = mo.vstack([mo.Html(f'<span id="{anchor}"></span>'), heading])
        return mo.vstack([heading, body])

    # sorting: figures with largest change on top, unchanged ones collapsed
    measured = {
        name: rc.figure_change(reference_figures[name], other_figure)
        for name, other_figure in other_figures.items()
        if name in reference_figures and not rc.is_sankey(other_figure)
    }
    changed_names = sorted(
        (name for name, change in measured.items() if change is None or rc.is_changed(change)),
        key=lambda name: (measured[name] is not None, -(measured[name] or 0.0)),
    )
    unchanged_names = [name for name in measured if name not in changed_names]
    sankey_names = [
        name for name in other_figures if name in reference_figures and name not in measured
    ]

    titles = {name: rc.section_title(name, measured[name]) for name in changed_names}
    anchors = {name: f"figure-{index}" for index, name in enumerate(changed_names)}
    contents = "\n".join(f"- [{titles[name]}](#{anchors[name]})" for name in changed_names)
    sections = [
        mo.md(
            "## Changed figures\n"
            + (contents or "None.")
            + f"\n\n{len(unchanged_names)} figures are unchanged and collapsed below."
        )
    ]
    sections += [
        built
        for name in changed_names
        if (built := section(name, titles[name], anchors[name])) is not None
    ]
    unchanged_sections = [
        built for name in unchanged_names if (built := section(name, name)) is not None
    ]
    if unchanged_sections:
        # lazy=False: a static export would otherwise ship the accordion empty
        sections.append(
            mo.accordion(
                {f"{len(unchanged_sections)} unchanged figures": mo.vstack(unchanged_sections)},
                lazy=False,
            )
        )
    sections += [built for name in sankey_names if (built := section(name, name)) is not None]
    for name in other_figures.keys() - reference_figures.keys():
        sections.append(
            mo.vstack(
                [
                    mo.md(f"## {name}"),
                    mo.callout(mo.md(f"Not produced for **{labels[0]}**."), kind="warn"),
                    other_figures[name],
                ]
            )
        )
    for name in reference_figures.keys() - other_figures.keys():
        sections.append(
            mo.vstack(
                [
                    mo.md(f"## {name}"),
                    mo.callout(mo.md(f"Not produced for **{labels[1]}**."), kind="warn"),
                    reference_figures[name],
                ]
            )
        )
    if compare_failures:
        sections.append(
            mo.callout(
                mo.md("**Some figures could not be compared:**\n" + "\n".join(compare_failures)),
                kind="warn",
            )
        )
    mo.vstack(sections)
    return


if __name__ == "__main__":
    app.run()
