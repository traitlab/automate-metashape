"""Processing steps: GPU setup, add photos, alignment through orthomosaic/DEM build.

Every parameter comes from the workflow YAML config via src/ms_lib/defaults.py,
so these reproduce the lab's tuned settings without restating them. Pass a
keyword argument to override one for a single call; leave it out (None) to take
the configured value.

The ``section`` argument on the build steps selects which config block to read,
which is how you reach the second, high-detail pass:

    build_depth_maps(chunk)                                  # buildDepthMaps
    build_depth_maps(chunk, section="buildDepthMapsHighDis")  # the HighDis block
"""

import glob
import os
import re

import Metashape

from src.model.config import (
    AddPhotosConfig,
    AlignPhotosConfig,
    BuildDemConfig,
    BuildDepthMapsConfig,
    BuildOrthomosaicConfig,
    BuildPointCloudConfig,
)
from src.ms_lib.defaults import global_param, step_params


def enable_gpu(use_cuda=None, gpu_multiplier=None, config_file=None):
    """Enable the first available GPU and configure it for GPU-heavy steps.

    Mirrors the pipeline's enable_and_log_gpu step (minus the logging): turn on
    the first GPU if one exists but none is active, disable the CPU during GPU
    steps, optionally switch off CUDA (falling back to OpenCL), and set the
    depth_max_gpu_multiplier tweak.
    """
    if use_cuda is None:
        use_cuda = global_param("use_cuda", True, config_file)
    if gpu_multiplier is None:
        gpu_multiplier = global_param("gpu_multiplier", 2, config_file)

    gpu_mask = Metashape.app.gpu_mask
    gpu_count = len(Metashape.app.enumGPUDevices())

    if gpu_count > 0 and gpu_mask == 0:
        Metashape.app.gpu_mask = 1

    # Standard wisdom: don't also use the CPU during GPU steps.
    Metashape.app.cpu_enable = False

    if not use_cuda:
        Metashape.app.settings.setValue("main/gpu_enable_cuda", "0")

    Metashape.app.settings.setValue("main/depth_max_gpu_multiplier", gpu_multiplier)

    return gpu_count


def add_photos(
    chunk,
    images_path,
    multispectral=None,
    load_reference=None,
    load_xmp_calibration=None,
    load_xmp_orientation=None,
    load_xmp_accuracy=None,
    load_xmp_antenna=None,
    use_xmp_accuracy=None,
    photos_accuracy=None,
    pattern=r"\.jpg$",
    config_file=None,
):
    """Add photos from one or more directories and label cameras by full path.

    Debug helper: main.py's add_photos is the real one (secondary photo sets,
    camera calibration import, PPK reference import). This covers the simple
    case so a chunk can be populated without a full mission run.

    ``images_path`` may be a single directory or a list of directories; each is
    added as its own camera group. ``pattern`` is a case-insensitive regex used
    to select files (default matches ``.jpg``; use ``r"\\.tif$"`` for thermal
    TIFFs). When the config's ``use_xmp_accuracy`` is False, every camera's
    reference accuracy is set to ``photos_accuracy`` (in CRS units).
    """
    p = step_params(
        "addPhotos",
        AddPhotosConfig,
        config_file=config_file,
        multispectral=multispectral,
        load_reference=load_reference,
        load_xmp_calibration=load_xmp_calibration,
        load_xmp_orientation=load_xmp_orientation,
        load_xmp_accuracy=load_xmp_accuracy,
        load_xmp_antenna=load_xmp_antenna,
        use_xmp_accuracy=use_xmp_accuracy,
        photos_accuracy=photos_accuracy,
    )

    if isinstance(images_path, str):
        images_path = [images_path]

    for path in images_path:
        group = chunk.addCameraGroup()
        candidates = glob.iglob(os.path.join(path, "**", "*.*"), recursive=True)
        photo_files = [f for f in candidates if re.search(pattern, f, re.IGNORECASE)]

        if p["multispectral"]:
            chunk.addPhotos(photo_files, layout=Metashape.MultiplaneLayout, group=group)
        else:
            chunk.addPhotos(
                photo_files,
                group=group,
                load_reference=p["load_reference"],
                load_xmp_calibration=p["load_xmp_calibration"],
                load_xmp_orientation=p["load_xmp_orientation"],
                load_xmp_accuracy=p["load_xmp_accuracy"],
                load_xmp_antenna=p["load_xmp_antenna"],
            )

    # Change the label of cameras to show the full path. The pipeline does the
    # same, and scripts/make_overlap_chunks.sh depends on it for merging by
    # camera label -- don't drop this.
    for camera in chunk.cameras:
        camera.label = camera.photo.path

    if not p["use_xmp_accuracy"]:
        accuracy = Metashape.Vector([p["photos_accuracy"]] * 3)
        for camera in chunk.cameras:
            camera.reference.location_accuracy = accuracy
            camera.reference.accuracy = accuracy


def align_photos(
    chunk,
    downscale=None,
    generic_preselection=None,
    reference_preselection=None,
    reference_preselection_mode=None,
    keep_keypoints=None,
    filter_stationary_points=None,
    keypoint_limit=None,
    keypoint_limit_per_mpx=None,
    tiepoint_limit=None,
    adaptive_fitting=None,
    reset_alignment=None,
    subdivide_task=None,
    config_file=None,
):
    """Match photos and align cameras."""
    p = step_params(
        "alignPhotos",
        AlignPhotosConfig,
        config_file=config_file,
        downscale=downscale,
        generic_preselection=generic_preselection,
        reference_preselection=reference_preselection,
        reference_preselection_mode=reference_preselection_mode,
        keep_keypoints=keep_keypoints,
        filter_stationary_points=filter_stationary_points,
        keypoint_limit=keypoint_limit,
        keypoint_limit_per_mpx=keypoint_limit_per_mpx,
        tiepoint_limit=tiepoint_limit,
        adaptive_fitting=adaptive_fitting,
        reset_alignment=reset_alignment,
    )
    if subdivide_task is None:
        subdivide_task = global_param("subdivide_task", True, config_file)

    chunk.matchPhotos(
        downscale=p["downscale"],
        subdivide_task=subdivide_task,
        keep_keypoints=p["keep_keypoints"],
        generic_preselection=p["generic_preselection"],
        reference_preselection=p["reference_preselection"],
        reference_preselection_mode=p["reference_preselection_mode"],
        filter_stationary_points=p["filter_stationary_points"],
        keypoint_limit=p["keypoint_limit"],
        keypoint_limit_per_mpx=p["keypoint_limit_per_mpx"],
        tiepoint_limit=p["tiepoint_limit"],
    )
    chunk.alignCameras(
        adaptive_fitting=p["adaptive_fitting"],
        subdivide_task=subdivide_task,
        reset_alignment=p["reset_alignment"],
    )


def reset_region(chunk):
    """Reset the region and triple its Z extent.

    Necessary because points outside the region get clipped when saving; the
    pipeline runs this right after alignment.
    """
    chunk.resetRegion()
    region_size = chunk.region.size
    region_size[2] *= 3
    chunk.region.size = region_size


def build_depth_maps(
    chunk,
    downscale=None,
    filter_mode=None,
    reuse_depth=None,
    max_neighbors=None,
    subdivide_task=None,
    section="buildDepthMaps",
    config_file=None,
):
    """Build depth maps. Use ``section="buildDepthMapsHighDis"`` for the second pass."""
    p = step_params(
        section,
        BuildDepthMapsConfig,
        config_file=config_file,
        downscale=downscale,
        filter_mode=filter_mode,
        reuse_depth=reuse_depth,
        max_neighbors=max_neighbors,
    )
    if subdivide_task is None:
        subdivide_task = global_param("subdivide_task", True, config_file)

    chunk.buildDepthMaps(
        downscale=p["downscale"],
        filter_mode=p["filter_mode"],
        reuse_depth=p["reuse_depth"],
        max_neighbors=p["max_neighbors"],
        subdivide_task=subdivide_task,
    )


def build_point_cloud(
    chunk,
    max_neighbors=None,
    keep_depth=None,
    point_colors=True,
    subdivide_task=None,
    section="buildPointCloud",
    config_file=None,
):
    """Build a colored point cloud, replacing any existing one.

    ``point_colors`` is not a config parameter; the pipeline hardcodes it True.
    """
    p = step_params(
        section,
        BuildPointCloudConfig,
        config_file=config_file,
        max_neighbors=max_neighbors,
        keep_depth=keep_depth,
    )
    if subdivide_task is None:
        subdivide_task = global_param("subdivide_task", True, config_file)

    chunk.buildPointCloud(
        max_neighbors=p["max_neighbors"],
        keep_depth=p["keep_depth"],
        point_colors=point_colors,
        subdivide_task=subdivide_task,
        replace_asset=True,
    )


def build_model(chunk, source_data=Metashape.DepthMapsData, surface_type=Metashape.Arbitrary):
    """Build a mesh model.

    Not part of the raster pipeline and not represented in the config, so the
    parameters stay as plain arguments. Kept for projects that need a mesh.
    """
    chunk.buildModel(source_data=source_data, surface_type=surface_type)


def build_dem(
    chunk,
    crs,
    resolution=None,
    source_data=Metashape.PointCloudData,
    subdivide_task=None,
    label="DSM",
    section="buildDem",
    config_file=None,
):
    """Build a DEM from the point cloud, projected into ``crs``.

    ``crs`` is a required "EPSG::<code>" string -- see io.derive_project_crs for
    why falling back to chunk.crs would be wrong. The resulting elevation is
    tagged with ``label`` (default "DSM") so build_orthomosaic can find it.
    """
    p = step_params(section, BuildDemConfig, config_file=config_file, resolution=resolution)
    if subdivide_task is None:
        subdivide_task = global_param("subdivide_task", True, config_file)

    projection = Metashape.OrthoProjection()
    projection.crs = Metashape.CoordinateSystem(crs)

    chunk.buildDem(
        source_data=source_data,
        subdivide_task=subdivide_task,
        projection=projection,
        resolution=p["resolution"],
        replace_asset=True,
    )

    if label:
        chunk.elevation.label = label


def build_orthomosaic(
    chunk,
    crs,
    blending=None,
    fill_holes=None,
    refine_seamlines=None,
    surface_data=Metashape.ElevationData,
    subdivide_task=None,
    section="buildOrthomosaic",
    config_file=None,
):
    """Build an orthomosaic over the active elevation, projected into ``crs``.

    ``crs`` is a required "EPSG::<code>" string. Requires an active DEM (see
    build_dem).
    """
    p = step_params(
        section,
        BuildOrthomosaicConfig,
        config_file=config_file,
        blending=blending,
        fill_holes=fill_holes,
        refine_seamlines=refine_seamlines,
    )
    if subdivide_task is None:
        subdivide_task = global_param("subdivide_task", True, config_file)

    projection = Metashape.OrthoProjection()
    projection.crs = Metashape.CoordinateSystem(crs)

    chunk.buildOrthomosaic(
        surface_data=surface_data,
        blending_mode=p["blending"],
        fill_holes=p["fill_holes"],
        refine_seamlines=p["refine_seamlines"],
        subdivide_task=subdivide_task,
        projection=projection,
        replace_asset=True,
    )
