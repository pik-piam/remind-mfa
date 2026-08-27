"""Extract the input data of the configured revision at image build time.

The madrat archive has to be extracted into remind_mfa_data/input_data.
Doing that at runtime would require a writable input folder (which we do not want to
provide in the container), so we extract the input data at build time.

Creating a model triggers the extraction (in CommonDataReader) and additionally validates
that all parameter files the model needs are present.
"""

from remind_mfa.common.config_loader import load_config
from remind_mfa.common.helpers import ModelNames, init_model

for model in ModelNames:
    init_model(cfg=load_config(["default", "mrindustry"], model))

print("Input data extracted and validated for all models")
