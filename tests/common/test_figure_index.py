from pathlib import Path

from remind_mfa.common.figure_index import (
    FigureEntry,
    collect_figures,
    write_figure_index,
)


def make_figure(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<html></html>", encoding="utf-8")


def test_collect_figures_groups_by_run_and_encodes_hrefs(tmp_path: Path):
    make_figure(tmp_path / "ci_steel_SSP2_h12" / "figures" / "production_Steel production.html")
    make_figure(tmp_path / "ci_steel_SSP2_h12" / "figures" / "gdppc.html")
    make_figure(tmp_path / "ci_plastics_SSP2_h12" / "figures" / "sankey.html")
    (tmp_path / "ci_steel_SSP2_h12" / "figures" / "plotly.min.js").write_text("", encoding="utf-8")
    (tmp_path / "ci_steel_SSP2_h12" / "model.pickle").write_bytes(b"")

    entries = collect_figures(tmp_path)

    assert entries == [
        FigureEntry(
            run="ci_plastics_SSP2_h12",
            name="sankey",
            href="ci_plastics_SSP2_h12/figures/sankey.html",
        ),
        FigureEntry(
            run="ci_steel_SSP2_h12", name="gdppc", href="ci_steel_SSP2_h12/figures/gdppc.html"
        ),
        FigureEntry(
            run="ci_steel_SSP2_h12",
            name="production_Steel production",
            href="ci_steel_SSP2_h12/figures/production_Steel%20production.html",
        ),
    ]


def test_collect_figures_directly_under_root(tmp_path: Path):
    make_figure(tmp_path / "figures" / "stocks.html")
    (tmp_path / "index.html").write_text("", encoding="utf-8")

    entries = collect_figures(tmp_path)

    assert entries == [FigureEntry(run="", name="stocks", href="figures/stocks.html")]


def test_write_figure_index_links_all_figures(tmp_path: Path):
    make_figure(tmp_path / "ci_steel_SSP2_h12" / "figures" / "production_Steel production.html")
    make_figure(tmp_path / "ci_cement_SSP2_h12" / "figures" / "a&b.html")

    index_path = write_figure_index(tmp_path, title="Test <figures>")
    content = index_path.read_text(encoding="utf-8")

    assert index_path == tmp_path / "index.html"
    assert "<title>Test &lt;figures&gt;</title>" in content
    assert 'data-src="ci_steel_SSP2_h12/figures/production_Steel%20production.html"' in content
    assert 'data-src="ci_cement_SSP2_h12/figures/a%26b.html"' in content
    assert ">a&amp;b</a>" in content
    assert "<summary>ci_steel_SSP2_h12" in content
    assert "<summary>ci_cement_SSP2_h12" in content
    # Regenerating must not pick up the index itself.
    write_figure_index(tmp_path)
    assert len(collect_figures(tmp_path)) == 2


def test_write_figure_index_without_figures(tmp_path: Path):
    index_path = write_figure_index(tmp_path / "empty")

    assert index_path.exists()
    assert "No figures found" in index_path.read_text(encoding="utf-8")
