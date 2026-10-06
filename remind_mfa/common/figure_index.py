"""Static index page for figures exported as standalone HTML files."""

import html
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

INDEX_FILENAME = "index.html"
FIGURES_DIRNAME = "figures"


@dataclass(frozen=True)
class FigureEntry:
    """One exported figure found below the index root."""

    run: str
    """Name of the run folder holding the ``figures`` directory; empty if it sits directly under the root."""
    name: str
    """Figure name (file stem)."""
    href: str
    """Percent-encoded path of the figure relative to the index root."""


def collect_figures(root: Path) -> list[FigureEntry]:
    """Find exported HTML figures below ``root``.

    Looks in ``root/figures/*.html`` and ``root/*/figures/*.html``, sorted by run folder and
    figure name.

    Args:
        root: Directory the index page will be written to.

    Returns:
        Figure entries with hrefs relative to ``root``.
    """
    candidates = sorted(root.glob(f"{FIGURES_DIRNAME}/*.html")) + sorted(
        root.glob(f"*/{FIGURES_DIRNAME}/*.html")
    )
    entries = []
    for path in candidates:
        if path.name == INDEX_FILENAME:
            continue
        run_dir = path.parent.parent
        run = run_dir.name if run_dir != root else ""
        href = quote(path.relative_to(root).as_posix())
        entries.append(FigureEntry(run=run, name=path.stem, href=href))
    return entries


def _anchor_id(entry: FigureEntry) -> str:
    return f"{entry.run}/{entry.name}" if entry.run else entry.name


def _render_sidebar(entries: list[FigureEntry]) -> str:
    if not entries:
        return "<p class='empty'>No figures found.</p>"
    runs: dict[str, list[FigureEntry]] = {}
    for entry in entries:
        runs.setdefault(entry.run, []).append(entry)
    parts = []
    for run, run_entries in runs.items():
        links = "\n".join(
            f'<li><a href="#{html.escape(quote(_anchor_id(entry)))}" '
            f'data-src="{html.escape(entry.href)}" '
            f'data-run="{html.escape(entry.run)}" '
            f'data-name="{html.escape(entry.name)}">{html.escape(entry.name)}</a></li>'
            for entry in run_entries
        )
        summary = html.escape(run) if run else "Figures"
        parts.append(
            f"<details open><summary>{summary} <span class='count'>({len(run_entries)})"
            f"</span></summary>\n<ul>\n{links}\n</ul>\n</details>"
        )
    return "\n".join(parts)


def render_figure_index(entries: list[FigureEntry], title: str = "REMIND-MFA figures") -> str:
    """Render the index page as an HTML document string.

    Args:
        entries: Figures to list, as returned by :func:`collect_figures`.
        title: Page title.

    Returns:
        Complete HTML document.
    """
    sidebar = _render_sidebar(entries)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{ --sidebar: 320px; --border: #d9d9d9; --bg: #f7f7f7; --accent: #1f77b4; }}
  * {{ box-sizing: border-box; }}
  html, body {{ height: 100%; margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; font-size: 14px; }}
  body {{ display: grid; grid-template-columns: var(--sidebar) 1fr; grid-template-rows: auto 1fr; height: 100vh; }}
  nav {{ grid-row: 1 / span 2; border-right: 1px solid var(--border); background: var(--bg); overflow-y: auto; padding: 0 0 1rem; }}
  nav h1 {{ font-size: 1.1rem; margin: 0; padding: 0.9rem 1rem; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--bg); }}
  nav details {{ margin: 0.5rem 0 0; }}
  nav summary {{ cursor: pointer; padding: 0.35rem 1rem; font-weight: 600; }}
  nav .count, nav .empty {{ color: #777; font-weight: normal; }}
  nav .empty {{ padding: 1rem; }}
  nav ul {{ list-style: none; margin: 0; padding: 0; }}
  nav li a {{ display: block; padding: 0.25rem 1rem 0.25rem 1.75rem; color: inherit; text-decoration: none; overflow-wrap: anywhere; }}
  nav li a:hover {{ background: #ececec; }}
  nav li a.active {{ background: var(--accent); color: white; }}
  header {{ display: flex; align-items: baseline; gap: 1rem; padding: 0.6rem 1rem; border-bottom: 1px solid var(--border); }}
  header .run {{ color: #777; }}
  header .name {{ font-weight: 600; }}
  header a {{ margin-left: auto; color: var(--accent); white-space: nowrap; }}
  iframe {{ width: 100%; height: 100%; border: 0; display: block; }}
  main {{ min-height: 0; }}
</style>
</head>
<body>
<nav>
<h1>{html.escape(title)}</h1>
{sidebar}
</nav>
<header>
  <span class="run" id="current-run"></span>
  <span class="name" id="current-name">Select a figure</span>
  <a id="open-link" href="#" target="_blank" rel="noopener" hidden>Open in new tab</a>
</header>
<main><iframe id="figure" title="Figure"></iframe></main>
<script>
(function () {{
  var links = Array.prototype.slice.call(document.querySelectorAll("nav li a"));
  var frame = document.getElementById("figure");
  var runLabel = document.getElementById("current-run");
  var nameLabel = document.getElementById("current-name");
  var openLink = document.getElementById("open-link");

  function select(link) {{
    links.forEach(function (other) {{ other.classList.toggle("active", other === link); }});
    frame.src = link.dataset.src;
    runLabel.textContent = link.dataset.run;
    nameLabel.textContent = link.dataset.name;
    openLink.href = link.dataset.src;
    openLink.hidden = false;
  }}

  function decode(value) {{
    try {{ return decodeURIComponent(value); }} catch (error) {{ return value; }}
  }}

  function selectFromHash() {{
    if (!links.length) {{ return; }}
    var hash = decode(window.location.hash);
    var match = links.filter(function (link) {{ return decode(link.getAttribute("href")) === hash; }})[0];
    select(match || links[0]);
  }}

  window.addEventListener("hashchange", selectFromHash);
  selectFromHash();
}})();
</script>
</body>
</html>
"""


def write_figure_index(root: Path, title: str = "REMIND-MFA figures") -> Path:
    """Write ``index.html`` into ``root`` listing all HTML figures found below it.

    Args:
        root: Directory to scan and to write the index into.
        title: Page title.

    Returns:
        Path of the written index file.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / INDEX_FILENAME
    index_path.write_text(render_figure_index(collect_figures(root), title), encoding="utf-8")
    return index_path
