# -*- coding: utf-8 -*-
# File for running a metashape workflow

import argparse
import os
import re
from argparse import RawTextHelpFormatter
from src.metashape_workflow_functions_lefolab import MetashapeWorkflowLefolab
from src.utilis import calculate_median_coordinates, calculate_utm_epsg
from src.model.config import load_config

# ---- If this is a first run from the standalone python module, need to copy the license file from the full metashape install: from python import metashape_license_setup

# Define where to get the config file
script_dir = os.path.dirname(os.path.abspath(__file__))
default_config_file = os.path.join(script_dir, "config", "config_lefolab_default.yml")

def parse_args():
    parser = argparse.ArgumentParser(formatter_class=RawTextHelpFormatter)
    parser.add_argument(
        "-i",
        "--images-path",
        help="Path to load photos from.",
    )
    parser.add_argument(
        "-c",
        "--config-file",
        default=default_config_file,
        help="Path to a yaml config file.\n"
        + "If not provided, default is 'config/config_lefolab_default.yml'.",
    )
    parser.add_argument(
        "-p",
        "--project-path",
        help="Path to save Metashape project file (.psx). Will be created if does not exist.\n"
        + "If not provided, default is 'conrad/labolaliberte_metashape_projects/<yyyy>/<missionid>/'.",
    )
    parser.add_argument(
        "-o",
        "--output-path",
        help="Path for exports (e.g., cloudpoint, DSM, orthomosaic). Will be created if does not exist.\n"
        + "If not provided, default is '<project_path>/metashape/'.",
    )
    parser.add_argument(
        "-id",
        "--mission-id",
        help="The identifier for the run. Will be used in naming output files.\n"
        + "It should be in the format: '<yyyymmdd>_<site>_<optional free text; no space, no special chars>_<sensor>'.\n"
        + "If not provided, it will be extracted from the images path.",
    )
    parser.add_argument(
        "--input-crs",
        help="CRS EPSG code for input photos.\n"
        + "By default, set to EPSG::4326.\n"
        + "To change in rare cases where RTK or NTRIP provider used a different datum.",
    )
    parser.add_argument(
        "-crs",
        "--project-crs",
        help="CRS EPSG code that project outputs should be in.\n"
        + "It should be in the format: 'EPSG::<EPSG code>'.\n"
        + "If not provided, it will be calculated from the median coordinates of the images (using UTM).",
    )
    parser.add_argument(
        "-cam",
        "--camera-calibration-path",
        help="Path to a camera calibration file (.xml).",
    )
    parser.add_argument(
        "-g",
        "--gcps",
        action="store_true",
        help="Pause processing after photos alignment to allow GCPs to be added using the GUI, then rerun with --gcps to continue.",
    )
    parser.add_argument(
        "-l",
        "--load-project",
        help="Path to a Metashape project file (.psx) to load.",
    )
    parser.add_argument(
        "-q",
        "--quick-process",
        action="store_true",
        help="Faster processing by disabling High quality and Disable filtering options (HighDis).\n"
        + "By default, High quality and Disable filtering options are enabled.",
    )
    parser.add_argument(
        "--delete-project",
        action="store_true",
        help="Delete project file after processing. Kept by default.",
    )

    args = parser.parse_args()

    if args.config_file == default_config_file and args.images_path and args.mission_id is None:
        # Extract the last part of the images path to use as mission_id if not provided
        images_path = args.images_path
        mission_id = os.path.basename(os.path.normpath(images_path))
        mission_id_pattern = r"^(?!_)\d{8}_[0-9a-z]{2,16}(?:_[0-9a-z]{2,16}){0,1}_[0-9a-z]{2,16}$"
        if not re.match(mission_id_pattern, mission_id):
            raise ValueError(
                f"Could not extract valid mission_id from images path: '{mission_id}'."
                "mission_id should be in the format: '<yyyymmdd>_<site>_<optional>_<sensor>'."
                "Please specify a valid mission_id using --mission-id."
            )
        else:
            args.mission_id = mission_id

    return args

args = parse_args()

# Check if required parameters are provided or appropriate config file is used
required_params = {
    "images_path": "Error: No images path provided. Please specify --images-path or use an appropriate config file.",
}

if args.config_file == default_config_file:
    for param, error_message in required_params.items():
        if getattr(args, param) is None:
            raise ValueError(error_message)

# Validate config using Pydantic model
try:
    # Only apply CLI overrides when using default config
    if args.config_file == default_config_file:
        validated_config, config_dict = load_config(
            config_file=args.config_file,
            override_dict=args.__dict__
        )
    else:
        # Don't apply CLI overrides when using custom config
        validated_config, config_dict = load_config(
            config_file=args.config_file,
            override_dict=None
        )
except Exception as e:
    print(f"\nConfiguration validation failed: {e}\n")
    raise

# Initialize the workflow instance with validated config dictionary
meta = MetashapeWorkflowLefolab(config_file=config_dict)

# Run the Metashape workflow
meta.run()