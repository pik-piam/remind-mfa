"""Run the steel model for all CE scenario x trade scenario combinations."""

import copy
import logging
import sys
import yaml

sys.path.insert(0, ".")

from remind_mfa.common.helpers import ModelNames
from remind_mfa.steel.steel_model import SteelModel


CE_SCENARIOS = [
    "Downsizing_Conservative_Steel_01_06_2026",
    "Downsizing_Highly_Ambitious_Steel_result_01_06_2026",
    "Redesign_ Conservative_Steel",
    "Redesign_ Highly_Ambitious_Steel",
    "Remanufacturing_Conservative_Steel",
    "Remanufacturing_Highly_Ambitious_Steel",
    'AHSS & HSS_ Conservative_Steel', 
    'AHSS & HSS_ Highly_Ambitious_Steel',
    "Combined_Conservative_Steel",
    "Combined_Highly_Ambitious_Steel",
]

TRADE_SCENARIOS = ["default", "fix_supply_alpha0", "fix_supply_alpha1"]


def run_all(base_cfg_file: str):
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )

    with open(base_cfg_file, "r") as f:
        base_cfg = yaml.safe_load(f)

    baseline_pickle_path = base_cfg["transience"]["baseline_pickle_path"]

    total = len(CE_SCENARIOS) * len(TRADE_SCENARIOS)
    failed = []

    for i, ce_scenario in enumerate(CE_SCENARIOS):
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
                model = SteelModel(cfg=cfg)
                model.run()
                model.export()
                model.visualize()
                logging.info(f"Completed run {run_num}/{total}")
            except Exception as e:
                logging.error(f"Failed run {run_num}/{total} ({ce_scenario}, {trade_scenario}): {e}")
                failed.append((ce_scenario, trade_scenario))

    if failed:
        logging.warning(f"{len(failed)} run(s) failed:")
        for ce, trade in failed:
            logging.warning(f"  CE={ce!r}, trade={trade!r}")
    else:
        logging.info("All runs completed successfully.")


if __name__ == "__main__":
    cfg_file = sys.argv[1] if len(sys.argv) > 1 else "config/steel.yml"
    run_all(cfg_file)
