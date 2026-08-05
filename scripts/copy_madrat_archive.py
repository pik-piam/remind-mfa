"""Copy the selected rev<revision>_<region>_*_mfa.tgz archive from a remote machine into the configured madrat_output_path via scp."""

import argparse
import shlex
import subprocess
from pathlib import Path

import yaml
from dotenv import load_dotenv

from remind_mfa.common.common_config import InputCfg
from remind_mfa.common.common_data_reader import CommonDataReader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy the selected rev<revision>_<region>_*_mfa.tgz archive from a remote "
            "machine into the configured madrat_output_path via scp."
        )
    )
    parser.add_argument("config", help="Path to a remind-mfa YAML config file.")
    parser.add_argument(
        "remote_host",
        help="Remote SSH target, for example user@host or an SSH config host alias.",
    )
    parser.add_argument(
        "remote_dir",
        help="Remote directory that contains the rev*_mfa.tgz archives.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the selected source and destination without running scp.",
    )
    return parser.parse_args()


def read_input_cfg(config_path: str) -> InputCfg:
    with open(config_path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    if not isinstance(config, dict) or "input" not in config:
        raise ValueError(f"Config file '{config_path}' does not contain an 'input' section.")

    return InputCfg.model_validate(config["input"])


def resolve_destination_path(input_cfg: InputCfg) -> Path:
    destination_path = Path(input_cfg.resolved_madrat_output_path).expanduser()
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


def copy_archive(remote_host: str, remote_archive_path: str, destination_dir: Path):
    subprocess.run(
        ["scp", f"{remote_host}:{remote_archive_path}", str(destination_dir)],
        check=True,
    )


def main():
    load_dotenv()
    args = parse_args()
    input_cfg = read_input_cfg(args.config)
    destination_dir = resolve_destination_path(input_cfg)
    pattern = CommonDataReader.build_target_tgz_pattern(
        input_cfg.input_data_revision, input_cfg.region_mapping
    )
    remote_archive_path = find_remote_archive(args.remote_host, args.remote_dir, pattern)

    print(f"Selected remote archive: {args.remote_host}:{remote_archive_path}")
    print(f"Destination directory: {destination_dir}")

    if args.dry_run:
        return

    copy_archive(args.remote_host, remote_archive_path, destination_dir)
    print("Archive copy completed.")


if __name__ == "__main__":
    main()
