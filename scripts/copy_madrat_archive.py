"""Copy the selected rev<revision>_<region>_*_mfa.tgz archive from a remote machine into the configured madrat_output_path via scp."""

import shlex
import subprocess
from pathlib import Path

import typer
import yaml
from dotenv import load_dotenv

from remind_mfa.common.common_config import InputCfg
from remind_mfa.common.common_data_reader import CommonDataReader

app = typer.Typer(add_completion=False)


def read_input_cfg(config_path: str) -> InputCfg:
    with open(config_path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    if not isinstance(config, dict) or "input" not in config:
        raise ValueError(f"Config file '{config_path}' does not contain an 'input' section.")

    return InputCfg.model_validate(config["input"])


def resolve_destination_path(input_cfg: InputCfg) -> Path:
    destination_path = Path(
        CommonDataReader.resolve_madrat_output_path(input_cfg.madrat_output_path)
    ).expanduser()
    destination_path.mkdir(parents=True, exist_ok=True)
    return destination_path


def find_remote_archive(remote_host: str, remote_dir: str, pattern: str) -> str:
    remote_command = (
        "find "
        f"{shlex.quote(remote_dir)} "
        "-maxdepth 1 -type f "
        f"-name {shlex.quote(pattern)} -print"
    )
    result = subprocess.run(
        ["ssh", remote_host, remote_command],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown ssh error"
        raise RuntimeError(f"Failed to query remote archives on {remote_host}: {stderr}")

    matches = sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})
    if not matches:
        raise FileNotFoundError(
            f"No matching tgz archive found in {remote_host}:{remote_dir} for pattern '{pattern}'."
        )
    if len(matches) > 1:
        raise ValueError(
            "Multiple matching tgz archives found for the selected revision/region mapping. "
            f"Matches: {matches}"
        )
    return matches[0]


def copy_archive(remote_host: str, remote_archive_path: str, destination_dir: Path) -> None:
    subprocess.run(
        ["scp", f"{remote_host}:{remote_archive_path}", str(destination_dir)],
        check=True,
    )


@app.command()
def main(
    config: str = typer.Argument(..., help="Path to a remind-mfa YAML config file."),
    remote_host: str = typer.Argument(
        ..., help="Remote SSH target, for example user@host or an SSH config host alias."
    ),
    remote_dir: str = typer.Argument(
        ..., help="Remote directory that contains the rev*_mfa.tgz archives."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the selected source and destination without running scp."
    ),
) -> None:
    """Copy the selected rev<revision>_<region>_*_mfa.tgz archive via scp."""
    load_dotenv()
    input_cfg = read_input_cfg(config)
    destination_dir = resolve_destination_path(input_cfg)
    pattern = CommonDataReader.build_target_tgz_pattern(
        input_cfg.input_data_revision, input_cfg.region_mapping
    )
    remote_archive_path = find_remote_archive(remote_host, remote_dir, pattern)

    typer.echo(f"Selected remote archive: {remote_host}:{remote_archive_path}")
    typer.echo(f"Destination directory: {destination_dir}")

    if dry_run:
        return

    copy_archive(remote_host, remote_archive_path, destination_dir)
    typer.echo("Archive copy completed.")


if __name__ == "__main__":
    app()
