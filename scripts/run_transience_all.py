"""Run the MFA model for all CE scenario x trade scenario combinations."""

import argparse
import copy
import logging
import sys
import yaml

sys.path.insert(0, ".")

from remind_mfa.steel.steel_model import SteelModel
from remind_mfa.plastics.plastics_model import PlasticsModel

CE_SCENARIOS = {
    "steel": [
        "Downsizing_Conservative_Steel_01_06_2026",
        "Downsizing_Highly_Ambitious_Steel_result_01_06_2026",
        "Redesign_ Conservative_Steel",
        "Redesign_ Highly_Ambitious_Steel",
        "Remanufacturing_Conservative_Steel",
        "Remanufacturing_Highly_Ambitious_Steel",
        "AHSS & HSS_ Conservative_Steel",
        "AHSS & HSS_ Highly_Ambitious_Steel",
        "Combined_Conservative_Steel",
        "Combined_Highly_Ambitious_Steel",
    ],
    "plastics": [
        "CE-PET_fd_plastics_S1",
        "CE-PET_fd_plastics_S2",
    ],
}

TRADE_SCENARIOS = ["default", "fix_supply_alpha0", "fix_supply_alpha1"]

MODEL_CLASS = {
    "steel": SteelModel,
    "plastics": PlasticsModel,
}

DEFAULT_CONFIG = {
    "steel": "config/steel.yml",
    "plastics": "config/plastics.yml",
}


def run_all(base_cfg_file: str, material: str):
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )

    with open(base_cfg_file, "r") as f:
        base_cfg = yaml.safe_load(f)

    baseline_pickle_path = base_cfg.get("transience", {}).get("baseline_pickle_path")
    ce_scenarios = CE_SCENARIOS[material]
    ModelClass = MODEL_CLASS[material]

    total = len(ce_scenarios) * len(TRADE_SCENARIOS)
    failed = []

    for i, ce_scenario in enumerate(ce_scenarios):
        for j, trade_scenario in enumerate(TRADE_SCENARIOS):
            run_num = i * len(TRADE_SCENARIOS) + j + 1
            logging.info(
                f"=== Run {run_num}/{total}: CE={ce_scenario!r}, trade={trade_scenario!r} ==="
            )

            cfg = copy.deepcopy(base_cfg)
            cfg["transience"]["transience_scenario"] = ce_scenario
            cfg["transience"]["trade_scenario"] = trade_scenario
            cfg["transience"]["baseline_pickle_path"] = (
                None if trade_scenario == "default" else baseline_pickle_path
            )

            try:
                model = ModelClass(cfg=cfg)
                model.run()
                model.export()
                model.visualize()
                logging.info(f"Completed run {run_num}/{total}")
            except Exception as e:
                logging.error(
                    f"Failed run {run_num}/{total} ({ce_scenario}, {trade_scenario}): {e}"
                )
                failed.append((ce_scenario, trade_scenario))

    if failed:
        logging.warning(f"{len(failed)} run(s) failed:")
        for ce, trade in failed:
            logging.warning(f"  CE={ce!r}, trade={trade!r}")
    else:
        logging.info("All runs completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run all transience scenarios for a material.")
    parser.add_argument("material", choices=["steel", "plastics"])
    parser.add_argument(
        "cfg_file", nargs="?", default=None, help="Config file (default: config/<material>.yml)"
    )
    args = parser.parse_args()

    cfg_file = args.cfg_file or DEFAULT_CONFIG[args.material]
    run_all(cfg_file, args.material)
