# -*- coding: utf-8 -*-
# File for running a metashape workflow

# Derek Young and Alex Mandel
# University of California, Davis
# 2021
# Adapted by Antoine Caron-Guay, for Lefolab, 2025

import argparse
import os

# ---- If this is a first run from the standalone python module, need to copy the license file from the full metashape install: from python import metashape_license_setup

# Define where to get the config file
script_dir = os.path.dirname(os.path.abspath(__file__))
default_config_file = os.path.join(script_dir, "config", "config_lefolab_default.yml")

from python.metashape_workflow_functions_lefolab import MetashapeWorkflowLefolab

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
        help="Path to save Metashape project file (.psx). Will be created if does not exist.",
    )
    parser.add_argument(
        "-o",
        "--output-path",
        help="Path for exports (e.g., cloudpoint, DSM, orthomosaic) "
        + "Will be created if does not exist.",
    )
    parser.add_argument(
        "-run",
        "--run-name",
        help="The identifier for the run. Will be used in naming output files.",
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
        "--highdis-disabled",
        action="store_true",
        help="Disable High quality and No filering (HighDis) processing. Enabled by default.",
    )
    parser.add_argument(
        "--keep-project",
        action="store_true",
        help="Keep project file after processing. Deleted by default.",
    )

    args = parser.parse_args()
    return args


args = parse_args()


# Check if required parameters are provided or appropriate config file is used
required_params = {
    "images_path": "Error: No images path provided. Please specify --images-path or use an appropriate config file.",
    "output_path": "Error: No output path provided. Please specify --output-path or use an appropriate config file.",
    "run_name": "Error: No run name provided. Please specify --run-name or use an appropriate config file.",
    "project_crs": "Error: No project CRS provided. Please specify --project-crs or use an appropriate config file."
}

if args.config_file == default_config_file:
    for param, error_message in required_params.items():
        if getattr(args, param) is None:
            raise ValueError(error_message)

# Check if --keep-project is True and either --project-path or --config-file is missing
if (args.keep_project and (args.config_file != default_config_file or args.project_path is not None)):
    pass
elif not args.keep_project:
    pass
else:
    raise ValueError("Error: --keep-project is set, but no project path or config file was provided.")

# Initialize the workflow instance with the configuration file and the dictionary representation of CLI overrides
meta = MetashapeWorkflowLefolab(config_file=args.config_file, override_dict=args.__dict__)

# Run the Metashape workflow
meta.run()
