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
