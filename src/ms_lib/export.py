"""Export helpers for common Metashape output products.

Raster exports use Deflate-compressed, tiled, overview-carrying (Big)TIFFs and an
explicit projection; point clouds are exported as COPC LAZ. The nodata value and
the TIFF flags come from the same config block as the corresponding build step
("buildDem" for the DEM, "buildOrthomosaic" for the ortho), which is how the
pipeline pairs them too.
"""

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET

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
        image_compression=_image_compression(p["tiff_big"], p["tiff_tiled"], p["tiff_overviews"]),
    )


def is_multi_camera(chunk):
    """True when the chunk is a multi-camera rig (several sensor layers, e.g. the M3M RGB + MS bands)."""
    return len({sensor.layer_index for sensor in chunk.sensors}) > 1


def _multi_camera_bands(chunk):
    """(1-based orthomosaic band index, band name) of the RGB sensor and of the single-band (multispectral) sensors.

    Orthomosaic bands follow the sensors in layer order, e.g. M3M: Red, Green, Blue, Green, Red, RedEdge, NIR.
    """
    rgb_bands, ms_bands = [], []
    band_index = 1
    for sensor in sorted(chunk.sensors, key=lambda s: s.layer_index):
        bands = list(enumerate(sensor.bands, start=band_index))
        (rgb_bands if len(sensor.bands) == 3 else ms_bands).extend(bands)
        band_index += len(sensor.bands)
    return rgb_bands, ms_bands


def _gdal(*args):
    """Run a GDAL command-line tool, showing its output only if it fails."""
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{args[0]} failed:\n{result.stdout}{result.stderr}")


def _gdal_finalize(src, dst, names, to_8bit, tiff_big, tiff_tiled, tiff_overviews):
    """Rewrite a float32 raster-transform export ``src`` as ``dst`` with named bands, then delete ``src``.

    Metashape writes a raster-transform export without band names, always as float32. A VRT wrapping
    ``src`` carries the names (and, for the RGB, the red/green/blue color interpretation), and
    gdal_translate stores them in ``dst`` itself. ``to_8bit`` converts the 0-255 RGB to uint8 with an
    alpha band built from the nodata pixels, the layout of a plain RGB orthomosaic.
    """
    vrt = dst + ".tmp.vrt"
    _gdal("gdal_translate", "-q", "-of", "VRT", src, vrt)
    tree = ET.parse(vrt)
    for band, name in zip(tree.getroot().iter("VRTRasterBand"), names):
        ET.SubElement(band, "Description").text = name
    tree.write(vrt)

    creation = ["-co", "COMPRESS=DEFLATE", "-co", f"BIGTIFF={'YES' if tiff_big else 'IF_NEEDED'}"]
    if tiff_tiled:
        creation += ["-co", "TILED=YES"]
    if to_8bit:
        # -b mask turns the nodata pixels into the alpha band; uint8 can't hold the -32767 nodata value
        bands = [
            "-ot",
            "Byte",
            "-b",
            "1",
            "-b",
            "2",
            "-b",
            "3",
            "-b",
            "mask",
            "-colorinterp",
            "red,green,blue,alpha",
            "-a_nodata",
            "none",
        ]
        creation += ["-co", "PREDICTOR=2", "-co", "ALPHA=YES"]
    else:
        bands = []
        creation += ["-co", "PREDICTOR=3"]
    _gdal("gdal_translate", "-q", *bands, *creation, vrt, dst)

    if tiff_overviews:
        _gdal("gdaladdo", "-q", "-r", "average", "--config", "COMPRESS_OVERVIEW", "DEFLATE", dst)

    os.remove(vrt)
    os.remove(src)


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
    """Split a multi-camera orthomosaic into two GeoTIFFs with named bands, through a raster transform.

    - ``ms_path``: the single-band multispectral sensors as float32 reflectance (0-1). Metashape
      stores calibrated reflectance in uint16 with 1.0 = 32768, so run calibrate_reflectance before
      building the orthomosaic.
    - ``rgb_path``: the RGB sensor (8-bit .JPG, stored in the uint16 orthomosaic as 0-65535) as
      uint8 with an alpha band. It is display color, not reflectance, so it is only rescaled.

    Metashape can only write these as unnamed float32, so the GDAL command-line tools (gdal_translate,
    gdaladdo) name the bands and convert the RGB. Without GDAL on PATH, both stay unnamed float32
    (RGB as 0-255) and a warning is printed. Either path may be None to skip that product.
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

    use_gdal = shutil.which("gdal_translate") is not None and shutil.which("gdaladdo") is not None
    if not use_gdal:
        print("[export] GDAL command-line tools not found: exporting unnamed float32 bands")

    rgb_bands, ms_bands = _multi_camera_bands(chunk)
    exports = [
        (ms_path, ms_bands, "32768", False),
        (rgb_path, rgb_bands, "257", True),
    ]

    raster_transform = chunk.raster_transform
    raster_transform.enabled = True
    for path, bands, scale, to_8bit in exports:
        if path is None or not bands:
            continue
        raster_transform.formula = [f"B{i}/{scale}" for i, _ in bands]
        # With GDAL, Metashape writes a temporary file that GDAL rewrites (and adds overviews to)
        export_path = path + ".tmp.tif" if use_gdal else path
        chunk.exportRaster(
            path=export_path,
            projection=_projection(crs),
            nodata_value=p["nodata"],
            source_data=Metashape.OrthomosaicData,
            raster_transform=Metashape.RasterTransformValue,
            # The alpha band would be float32 too, holding 1 for opaque, which GIS
            # software reads on the 0-255 scale (nearly transparent). nodata_value
            # marks the pixels outside the orthomosaic instead.
            save_alpha=False,
            image_compression=_image_compression(
                p["tiff_big"], p["tiff_tiled"], p["tiff_overviews"] and not use_gdal
            ),
        )
        if use_gdal:
            _gdal_finalize(
                export_path,
                path,
                [name for _, name in bands],
                to_8bit,
                p["tiff_big"],
                p["tiff_tiled"],
                p["tiff_overviews"],
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
        image_compression=_image_compression(p["tiff_big"], p["tiff_tiled"], p["tiff_overviews"]),
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
