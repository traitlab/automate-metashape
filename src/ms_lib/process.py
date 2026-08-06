"""Processing steps: GPU setup, add photos, alignment through orthomosaic/DEM build.

Most steps take the chunk they act on. The two multi-chunk steps -- align_chunks
and merge_chunks -- take the *document* and a list of chunks instead, because
Metashape puts them on Document rather than Chunk.

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
    AlignChunksConfig,
    AlignPhotosConfig,
    BuildDemConfig,
    BuildDepthMapsConfig,
    BuildOrthomosaicConfig,
    BuildPointCloudConfig,
    MergeChunksConfig,
)
from src.ms_lib.defaults import global_param, step_params

# Document.alignChunks takes the method as a bare int. Map the readable config
# names onto it rather than putting magic numbers in the YAML.
ALIGN_CHUNKS_METHODS = {"points": 0, "markers": 1, "cameras": 2}


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


def _chunk_keys(chunks):
    """Chunk objects -> the integer keys Document.alignChunks/mergeChunks take.

    Both APIs are documented as list[int]: they identify chunks by key, not by
    object. io.resolve_chunks turns labels into the objects passed in here.
    """
    return [chunk.key for chunk in chunks]


def align_chunks(
    doc,
    chunks,
    reference=None,
    method=None,
    fit_scale=None,
    downscale=None,
    generic_preselection=None,
    filter_mask=None,
    mask_tiepoints=None,
    keypoint_limit=None,
    markers=None,
    section="alignChunks",
    config_file=None,
):
    """Bring a set of chunks into a common coordinate frame.

    Document-level, unlike the other steps here: ``doc`` is the document and
    ``chunks`` the list of Chunk objects to align (see io.resolve_chunks).
    ``reference`` is the chunk the others are moved onto; it defaults to the
    first of ``chunks`` and must be one of them.

    The method comes from the config: "cameras" aligns off the cameras the
    chunks have in common (matched by label), "points" matches image features,
    "markers" uses markers. Only "points" reads downscale, generic_preselection
    and keypoint_limit.

    ``markers`` (a list of marker keys) is only used by the "markers" method and
    is project-specific, so it is a plain argument rather than a config value.
    """
    p = step_params(
        section,
        AlignChunksConfig,
        config_file=config_file,
        method=method,
        fit_scale=fit_scale,
        downscale=downscale,
        generic_preselection=generic_preselection,
        filter_mask=filter_mask,
        mask_tiepoints=mask_tiepoints,
        keypoint_limit=keypoint_limit,
    )

    if len(chunks) < 2:
        raise ValueError(
            f"align_chunks needs at least two chunks, got {len(chunks)}. Name them with "
            "--chunks, or leave it out to align every chunk in the project."
        )

    if reference is None:
        reference = chunks[0]
    elif reference.key not in _chunk_keys(chunks):
        raise ValueError(
            f"Reference chunk '{reference.label}' is not one of the chunks being aligned."
        )

    # Config values arrive as the readable names; an int passes straight through
    # so a caller can give Metashape's own code.
    align_method = p["method"]
    if not isinstance(align_method, int):
        if align_method not in ALIGN_CHUNKS_METHODS:
            raise ValueError(
                f"Unknown chunk alignment method '{align_method}'; expected one of "
                f"{sorted(ALIGN_CHUNKS_METHODS)}."
            )
        align_method = ALIGN_CHUNKS_METHODS[align_method]

    kwargs = dict(
        chunks=_chunk_keys(chunks),
        reference=reference.key,
        method=align_method,
        fit_scale=p["fit_scale"],
        downscale=p["downscale"],
        generic_preselection=p["generic_preselection"],
        filter_mask=p["filter_mask"],
        mask_tiepoints=p["mask_tiepoints"],
        keypoint_limit=p["keypoint_limit"],
    )
    if markers:
        kwargs["markers"] = markers

    doc.alignChunks(**kwargs)


def merge_chunks(
    doc,
    chunks,
    label=None,
    merge_assets=None,
    merge_markers=None,
    merge_tiepoints=None,
    copy_laser_scans=None,
    copy_masks=None,
    copy_depth_maps=None,
    copy_point_clouds=None,
    copy_models=None,
    copy_tiled_models=None,
    copy_elevations=None,
    copy_orthomosaics=None,
    section="mergeChunks",
    config_file=None,
):
    """Merge a set of chunks into one new chunk, and return that chunk.

    Document-level, like align_chunks: ``chunks`` is a list of Chunk objects
    (see io.resolve_chunks). The source chunks are left untouched and the result
    is appended to the document. Metashape returns nothing, so the new chunk is
    found by diffing the document's chunk keys; pass ``label`` to name it
    something better than "Merged Chunk".

    A photo held by two of the merged chunks stays as two cameras in the result:
    each was aligned from its own chunk's tie points, and those tie points do
    not exist in the other copy, so the merge keeps both. Run
    deduplicate_cameras on the merged chunk to leave one camera per photo.

    The copy_* flags decide which built products are carried into the merged
    chunk.
    """
    p = step_params(
        section,
        MergeChunksConfig,
        config_file=config_file,
        merge_assets=merge_assets,
        merge_markers=merge_markers,
        merge_tiepoints=merge_tiepoints,
        copy_laser_scans=copy_laser_scans,
        copy_masks=copy_masks,
        copy_depth_maps=copy_depth_maps,
        copy_point_clouds=copy_point_clouds,
        copy_models=copy_models,
        copy_tiled_models=copy_tiled_models,
        copy_elevations=copy_elevations,
        copy_orthomosaics=copy_orthomosaics,
    )

    if len(chunks) < 2:
        raise ValueError(
            f"merge_chunks needs at least two chunks, got {len(chunks)}. Name them with "
            "--chunks, or leave it out to merge every chunk in the project."
        )

    keys_before = {chunk.key for chunk in doc.chunks}

    doc.mergeChunks(
        chunks=_chunk_keys(chunks),
        merge_assets=p["merge_assets"],
        merge_markers=p["merge_markers"],
        merge_tiepoints=p["merge_tiepoints"],
        copy_laser_scans=p["copy_laser_scans"],
        copy_masks=p["copy_masks"],
        copy_depth_maps=p["copy_depth_maps"],
        copy_point_clouds=p["copy_point_clouds"],
        copy_models=p["copy_models"],
        copy_tiled_models=p["copy_tiled_models"],
        copy_elevations=p["copy_elevations"],
        copy_orthomosaics=p["copy_orthomosaics"],
    )

    merged = [chunk for chunk in doc.chunks if chunk.key not in keys_before]
    if not merged:
        raise RuntimeError(
            "mergeChunks produced no new chunk. Nothing was merged; check that the "
            "named chunks exist and hold cameras."
        )

    merged_chunk = merged[-1]
    if label:
        merged_chunk.label = label

    return merged_chunk


def deduplicate_cameras(chunk, remove=False):
    """Disable the cameras that repeat a photo already present in the chunk.

    Chunks that overlap on purpose -- so that align_chunks has cameras in common
    to work from -- leave the merged chunk holding the shared photos twice, once
    per source chunk (see merge_chunks). Left alone, those photos contribute
    twice to everything built next.

    Duplicates are found by photo path, keeping the first camera that holds each
    path in chunk order. Already-disabled cameras are skipped, so running this
    twice changes nothing the second time. This follows the script Agisoft give
    for it: https://www.agisoft.com/forum/index.php?topic=8587.0

    Disabling rather than deleting is the default because a camera carries the
    tie points it was aligned from, and the duplicate that survives does not
    have them. Pass ``remove=True`` to delete the duplicates outright.

    Returns the number of cameras disabled (or removed).
    """
    seen = set()
    duplicates = []

    for camera in chunk.cameras:
        if not camera.enabled or camera.photo is None:
            continue
        path = camera.photo.path
        if path in seen:
            duplicates.append(camera)
        else:
            seen.add(path)

    if remove:
        chunk.remove(duplicates)
    else:
        for camera in duplicates:
            camera.enabled = False

    return len(duplicates)


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
