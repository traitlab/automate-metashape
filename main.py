# -*- coding: utf-8 -*-
# File for running a metashape workflow

# Derek Young and Alex Mandel
# University of California, Davis
# 2021
# Adapted by Antoine Caron-Guay, for Lefolab, 2025

import argparse
import os
import re
from python.metashape_workflow_functions_lefolab import MetashapeWorkflowLefolab

# ---- If this is a first run from the standalone python module, need to copy the license file from the full metashape install: from python import metashape_license_setup

# Define where to get the config file
script_dir = os.path.dirname(os.path.abspath(__file__))
default_config_file = os.path.join(script_dir, "config", "config_lefolab_default.yml")

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config_file",
        default=default_config_file,
        help="Path to a yaml config file."
    )
    parser.add_argument(
        "-i",
        "--images-path",
        nargs="+",
        help="One or more absolute paths to load photos from, separated by spaces.",
    )
    parser.add_argument(
        "-p",
        "--project-path",
        help="Path to save Metashape project file (.psx). Will be created if does not exist."
        + "Default to 'conrad/labolaliberte_metashape_projects/<yyyy>/<missionid>/'.",
    )
    parser.add_argument(
        "-o",
        "--output-path",
        help="Path for exports (e.g., cloudpoint, DSM, orthomosaic) "
        + "Will be created if does not exist."
        + "Default to 'conrad/labolaliberte_upload/metashape/<yyyy>/<missionid>/'.",
    )
    parser.add_argument(
        "-id",
        "--mission-id",
        help="The identifier for the run. Will be used in naming output files."
        + "It should be in the format: '<yyyymmdd>_<site>_<optional free text; no space, no special chars>_<sensor>'."
        + "If not provided, it will be extracted from the images path.",
    )
    parser.add_argument(
        "-crs",
        "--project-crs",
        help="CRS EPSG code that project outputs should be in "
        + "(projection should be in meter units and intended for the project area). "
        + "It should be in the format: 'EPSG::<EPSG code>'.",
    )
    parser.add_argument(
        "-cam",
        "--camera-calibration-path",
        help="Path to a camera calibration file (.xml).",
    )
    parser.add_argument(
        "-quick",
        "--quick-process",
        action="store_true",
        help="Enable faster processing by disabling High quality and Disable filtering options (HighDis). "
        + "By default, High quality and Disable filtering options are enabled.",
    )
    parser.add_argument(
        "--delete-project",
        action="store_true",
        help="Delete project file after processing. Kept by default.",
    )

    args = parser.parse_args()

    # Extract the last part of the images path to use as mission_id if not provided
    if args.mission_id is None and args.images_path and len(args.images_path) == 1:
        images_path = args.images_path[0]
        mission_id = os.path.basename(os.path.normpath(images_path))
        # Validate mission_id format
        mission_id_pattern = r"^(?!_)\d{8}_[0-9a-z]{2,16}(?:_[0-9a-z]{2,16}){0,1}_[0-9a-z]{2,16}$"
        if not re.match(mission_id_pattern, mission_id):
            raise ValueError(
                f"Invalid mission_id format from images path: {mission_id}. "
                "The mission_id should be in the format: '<yyyymmdd>_<site>_<optional free text; no space, no special chars>_<sensor>'. "
                "Please specify a valid --mission-id."
            )
        args.mission_id = mission_id

    # Extract year from the mission_id (first 4 characters)
    mission_year = args.mission_id[:4]
    # Assign default paths if not provided
    if args.project_path is None:
        args.project_path = f"/mnt/nfs/conrad/labolaliberte_metashape_projects/{mission_year}/{args.mission_id}/"
    if args.output_path is None:
        args.output_path = f"/mnt/nfs/conrad/labolaliberte_upload/_data/metashape/{mission_year}/{args.mission_id}/"

    return args

args = parse_args()

# Check if required parameters are provided or appropriate config file is used
required_params = {
    "images_path": "Error: No images path provided. Please specify --images-path or use an appropriate config file.",
    "mission_id": "Error: No run name provided. Please specify --mission-id or use an appropriate config file.",
    "project_crs": "Error: No project CRS provided. Please specify --project-crs or use an appropriate config file."
}

if args.config_file == default_config_file:
    for param, error_message in required_params.items():
        if getattr(args, param) is None:
            raise ValueError(error_message)

# Initialize the workflow instance with the configuration file and the dictionary representation of CLI overrides
meta = MetashapeWorkflowLefolab(config_file=args.config_file, override_dict=args.__dict__)

# Run the Metashape workflow
meta.run()
