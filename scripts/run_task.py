#!/usr/bin/env python3
"""
Run individual Metashape steps against a project that already exists.

main.py runs a whole mission: one document lifecycle, the active chunk only, a
mission lock, and a reproducibility log. It refuses projects with more than one
chunk. This runs one step at a time on a chunk you name, which is what you need
for surgery -- re-export a product in a different CRS, rebuild a DEM at a
different resolution, or process the chunk left behind by a GUI
"Merge by camera labels" after scripts/make_overlap_chunks.sh.

Use main.py for real missions. Nothing here writes a processing log, so a
product built with this script has no provenance record of its own.

Run from the repository root with the Metashape environment activated:

    source /opt/miniconda3/bin/activate metashape
    python scripts/run_task.py \
        --project path/to/project.psx \
        --chunk "Chunk 1" \
        --task export_ortho \
        --output out/ortho.tif

Repeat --task to chain steps in one document open/save cycle:

    python scripts/run_task.py \
        --project path/to/project.psx \
        --task build_dem --task build_orthomosaic \
        --task export_ortho --output out/ortho.tif

The project is saved after each step that changes it, as the pipeline does, so a
failure late in a chain doesn't discard the work before it. Pass --no-save for a
throwaway run.

Processing parameters are read from config/config_lefolab_default.yml (override
with --config-file), so they always match what main.py would have used. Add new
steps to TASKS below instead of writing a new script.
"""

import argparse
import os
import sys

# Allow "import src.*" when invoked as scripts/run_task.py: Python puts this
# file's directory on sys.path, not the repository root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ms_lib import export, process  # noqa: E402
from src.ms_lib.io import (  # noqa: E402
    derive_project_crs,
    get_chunk,
    new_document,
    open_document,
    save,
)


def task_add_photos(chunk, args):
    require(args, "images")
    process.add_photos(chunk, args.images, multispectral=args.multispectral or None,
                       config_file=args.config_file)


def task_align(chunk, args):
    process.align_photos(chunk, config_file=args.config_file)


def task_reset_region(chunk, args):
    process.reset_region(chunk)


def task_build_depth_maps(chunk, args):
    process.build_depth_maps(chunk, config_file=args.config_file)


def task_build_depth_maps_highdis(chunk, args):
    process.build_depth_maps(chunk, section="buildDepthMapsHighDis",
                             config_file=args.config_file)


def task_build_point_cloud(chunk, args):
    process.build_point_cloud(chunk, config_file=args.config_file)


def task_build_point_cloud_highdis(chunk, args):
    process.build_point_cloud(chunk, section="buildPointCloudHighDis",
                              config_file=args.config_file)


def task_build_model(chunk, args):
    process.build_model(chunk)


def task_build_dem(chunk, args):
    process.build_dem(chunk, args.crs, resolution=args.resolution,
                      config_file=args.config_file)


def task_build_dem_highdis(chunk, args):
    process.build_dem(chunk, args.crs, resolution=args.resolution,
                      section="buildDemHighDis", config_file=args.config_file)


def task_build_orthomosaic(chunk, args):
    process.build_orthomosaic(chunk, args.crs, config_file=args.config_file)


def task_export_ortho(chunk, args):
    require(args, "output")
    export.export_orthomosaic(chunk, args.output, args.crs, config_file=args.config_file)


def task_export_dem(chunk, args):
    require(args, "output")
    export.export_dem(chunk, args.output, args.crs, config_file=args.config_file)


def task_export_point_cloud(chunk, args):
    require(args, "output")
    export.export_point_cloud(chunk, args.output, args.crs, config_file=args.config_file)


def task_export_model(chunk, args):
    require(args, "output")
    export.export_model(chunk, args.output)


def task_export_report(chunk, args):
    require(args, "output")
    export.export_report(chunk, args.output)


TASKS = {
    "add_photos": task_add_photos,
    "align": task_align,
    "reset_region": task_reset_region,
    "build_depth_maps": task_build_depth_maps,
    "build_depth_maps_highdis": task_build_depth_maps_highdis,
    "build_point_cloud": task_build_point_cloud,
    "build_point_cloud_highdis": task_build_point_cloud_highdis,
    "build_model": task_build_model,
    "build_dem": task_build_dem,
    "build_dem_highdis": task_build_dem_highdis,
    "build_orthomosaic": task_build_orthomosaic,
    "export_ortho": task_export_ortho,
    "export_dem": task_export_dem,
    "export_point_cloud": task_export_point_cloud,
    "export_model": task_export_model,
    "export_report": task_export_report,
}

# Tasks that project into an output CRS. For these, --crs is resolved up front
# (from the chunk's camera coordinates if not given) rather than silently
# falling back to chunk.crs, which the workflow leaves at EPSG::4326 forever.
CRS_TASKS = {
    "build_dem",
    "build_dem_highdis",
    "build_orthomosaic",
    "export_ortho",
    "export_dem",
    "export_point_cloud",
}

# Tasks that change the project and so need --save to persist.
MUTATING_TASKS = set(TASKS) - {
    "export_ortho",
    "export_dem",
    "export_point_cloud",
    "export_model",
    "export_report",
}


def require(args, *names):
    missing = [n for n in names if getattr(args, n, None) is None]
    if missing:
        raise SystemExit(f"--{missing[0]} is required for this task")


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    project = parser.add_mutually_exclusive_group(required=True)
    project.add_argument("--project", help="Path to an existing .psx project to open")
    project.add_argument(
        "--create",
        help="Path at which to create a new .psx project. Debug only -- real missions "
        "go through main.py, which enforces the mission_id convention, takes the "
        "mission lock, and writes the processing log.",
    )
    parser.add_argument("--chunk", help="Chunk label (defaults to the first chunk)")
    parser.add_argument(
        "--input-crs", default="EPSG::4326", help="Input CRS for a newly created chunk"
    )
    parser.add_argument(
        "--task",
        required=True,
        choices=sorted(TASKS),
        action="append",
        help="Task to run; repeat --task to chain multiple steps",
    )
    parser.add_argument(
        "--config-file",
        help="Path to the yaml config supplying processing parameters.\n"
        "Defaults to config/config_lefolab_default.yml.",
    )
    parser.add_argument(
        "--images", action="append", help="Photo directory for add_photos; repeat for multiple"
    )
    parser.add_argument(
        "--multispectral", action="store_true", help="Treat photos as a multispectral set"
    )
    parser.add_argument("--output", help="Output path (required by export_* tasks)")
    parser.add_argument(
        "-crs",
        "--crs",
        help="Projected CRS ('EPSG::<code>') for DEM/ortho/point-cloud build & export.\n"
        "If omitted, derived as the UTM zone of the median camera position, the same\n"
        "rule main.py applies to a fresh mission.",
    )
    parser.add_argument(
        "--resolution", type=float, default=None, help="DEM build resolution in meters/pixel"
    )
    parser.add_argument(
        "--no-cuda", action="store_true", help="Use OpenCL instead of CUDA for GPU steps"
    )
    parser.add_argument(
        "--gpu-multiplier", type=int, default=None,
        help="Metashape depth_max_gpu_multiplier tweak",
    )
    parser.add_argument(
        "--ignore-lock",
        action="store_true",
        help="Open the project even if it is locked. Only for clearing a stale lock left\n"
        "by a crashed run -- a lock usually means main.py or the GUI has it open.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Discard results instead of saving after each step that changes the project.",
    )
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)

    if args.create:
        doc = new_document(args.create, label=args.chunk, crs=args.input_crs)
        chunk = get_chunk(doc)
    else:
        doc = open_document(args.project, ignore_lock=args.ignore_lock)
        chunk = get_chunk(doc, name=args.chunk)

    if args.no_save and MUTATING_TASKS.intersection(args.task):
        print("[run_task] --no-save: results of processing steps will be discarded")

    if args.crs is None and CRS_TASKS.intersection(args.task):
        args.crs = derive_project_crs(chunk)
        print(f"[run_task] using {args.crs} as project CRS (median camera position)")

    # Enable GPU acceleration for the processing steps (harmless if no GPU).
    process.enable_gpu(
        use_cuda=False if args.no_cuda else None,
        gpu_multiplier=args.gpu_multiplier,
        config_file=args.config_file,
    )

    for task_name in args.task:
        print(f"[run_task] {task_name} on chunk '{chunk.label}'")
        TASKS[task_name](chunk, args)

        # Save per step, like the pipeline does, so a failure late in a chain
        # doesn't throw away the hours of work before it.
        if task_name in MUTATING_TASKS and not args.no_save:
            save(doc)

    print("[run_task] done")


if __name__ == "__main__":
    main(sys.argv[1:])
