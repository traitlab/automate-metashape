"""Export helpers for common Metashape output products.

Raster exports use Deflate-compressed, tiled, overview-carrying (Big)TIFFs and an
explicit projection; point clouds are exported as COPC LAZ. The nodata value and
the TIFF flags come from the same config block as the corresponding build step
("buildDem" for the DEM, "buildOrthomosaic" for the ortho), which is how the
pipeline pairs them too.
"""

import Metashape

from src.model.config import (
    BuildDemConfig,
    BuildOrthomosaicConfig,
    BuildPointCloudConfig,
)
from src.ms_lib.defaults import global_param, step_params


def _image_compression(tiff_big, tiff_tiled, tiff_overviews):
    """Build the standard TIFF compression settings (Deflate)."""
    compression = Metashape.ImageCompression()
    compression.tiff_big = tiff_big
    compression.tiff_tiled = tiff_tiled
    compression.tiff_overviews = tiff_overviews
    compression.tiff_compression = Metashape.ImageCompression.TiffCompressionDeflate
    return compression


def _projection(crs):
    projection = Metashape.OrthoProjection()
    projection.crs = Metashape.CoordinateSystem(crs)
    return projection


def export_orthomosaic(
    chunk,
    output_path,
    crs,
    nodata=None,
    tiff_big=None,
    tiff_tiled=None,
    tiff_overviews=None,
    section="buildOrthomosaic",
    config_file=None,
):
    """Export the orthomosaic as a GeoTIFF in ``crs`` (a required "EPSG::<code>")."""
    p = step_params(
        section,
        BuildOrthomosaicConfig,
        config_file=config_file,
        nodata=nodata,
        tiff_big=tiff_big,
        tiff_tiled=tiff_tiled,
        tiff_overviews=tiff_overviews,
    )

    chunk.exportRaster(
        path=output_path,
        projection=_projection(crs),
        nodata_value=p["nodata"],
        source_data=Metashape.OrthomosaicData,
        image_compression=_image_compression(
            p["tiff_big"], p["tiff_tiled"], p["tiff_overviews"]
        ),
    )


def is_multi_camera(chunk):
    """True when the chunk is a multi-camera rig (several sensor layers, e.g. the M3M RGB + MS bands)."""
    return len({sensor.layer_index for sensor in chunk.sensors}) > 1


def _multi_camera_bands(chunk):
    """1-based orthomosaic band indices of the RGB sensor and of the single-band (multispectral) sensors.

    Orthomosaic bands follow the sensors in layer order, e.g. M3M: Red, Green, Blue, Green, Red, RedEdge, NIR.
    """
    rgb_bands, ms_bands = [], []
    band_index = 1
    for sensor in sorted(chunk.sensors, key=lambda s: s.layer_index):
        indices = list(range(band_index, band_index + len(sensor.bands)))
        (rgb_bands if len(sensor.bands) == 3 else ms_bands).extend(indices)
        band_index += len(sensor.bands)
    return rgb_bands, ms_bands


def export_multispectral_orthomosaic(
    chunk,
    ms_path,
    rgb_path,
    crs,
    nodata=None,
    tiff_big=None,
    tiff_tiled=None,
    tiff_overviews=None,
    section="buildOrthomosaic",
    config_file=None,
):
    """Split a multi-camera orthomosaic into two float32 GeoTIFFs through a raster transform.

    - ``ms_path``: the single-band multispectral sensors as reflectance (0-1). Metashape stores
      calibrated reflectance in uint16 with 1.0 = 32768, so run calibrate_reflectance before
      building the orthomosaic.
    - ``rgb_path``: the RGB sensor (8-bit .JPG, stored in the uint16 orthomosaic as 0-65535)
      brought back to 0-255. It is display color, not reflectance, so it is only rescaled.

    Either path may be None to skip that product.
    """
    p = step_params(
        section,
        BuildOrthomosaicConfig,
        config_file=config_file,
        nodata=nodata,
        tiff_big=tiff_big,
        tiff_tiled=tiff_tiled,
        tiff_overviews=tiff_overviews,
    )

    rgb_bands, ms_bands = _multi_camera_bands(chunk)
    exports = [
        (ms_path, [f"B{i}/32768" for i in ms_bands]),
        (rgb_path, [f"B{i}/257" for i in rgb_bands]),
    ]

    raster_transform = chunk.raster_transform
    raster_transform.enabled = True
    for path, formula in exports:
        if path is None or not formula:
            continue
        raster_transform.formula = formula
        chunk.exportRaster(
            path=path,
            projection=_projection(crs),
            nodata_value=p["nodata"],
            source_data=Metashape.OrthomosaicData,
            raster_transform=Metashape.RasterTransformValue,
            image_compression=_image_compression(
                p["tiff_big"], p["tiff_tiled"], p["tiff_overviews"]
            ),
        )


def export_dem(
    chunk,
    output_path,
    crs,
    nodata=None,
    tiff_big=None,
    tiff_tiled=None,
    tiff_overviews=None,
    section="buildDem",
    config_file=None,
):
    """Export the active elevation as a GeoTIFF in ``crs`` (a required "EPSG::<code>")."""
    p = step_params(
        section,
        BuildDemConfig,
        config_file=config_file,
        nodata=nodata,
        tiff_big=tiff_big,
        tiff_tiled=tiff_tiled,
        tiff_overviews=tiff_overviews,
    )

    chunk.exportRaster(
        path=output_path,
        projection=_projection(crs),
        nodata_value=p["nodata"],
        source_data=Metashape.ElevationData,
        image_compression=_image_compression(
            p["tiff_big"], p["tiff_tiled"], p["tiff_overviews"]
        ),
    )


def export_point_cloud(
    chunk,
    output_path,
    crs,
    classes=None,
    source_data=Metashape.PointCloudData,
    subdivide_task=None,
    section="buildPointCloud",
    config_file=None,
):
    """Export the point cloud as COPC LAZ (name the file ``*.copc.laz``).

    ``classes`` is either the string "ALL" (export every class) or a list of
    Metashape.PointClass values; omitting it takes the configured value.
    """
    p = step_params(section, BuildPointCloudConfig, config_file=config_file, classes=classes)
    if subdivide_task is None:
        subdivide_task = global_param("subdivide_task", True, config_file)

    kwargs = dict(
        path=output_path,
        source_data=source_data,
        format=Metashape.PointCloudFormatCOPC,
        crs=Metashape.CoordinateSystem(crs),
        subdivide_task=subdivide_task,
    )
    # Omitting the argument entirely is what makes Metashape export all classes.
    if p["classes"] != "ALL":
        kwargs["classes"] = p["classes"]

    chunk.exportPointCloud(**kwargs)


def export_report(chunk, output_path):
    chunk.exportReport(path=output_path)
