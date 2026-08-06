"""Open/create/save Metashape documents, select chunks, and derive a project CRS."""

import statistics

import Metashape

from src.utilis import calculate_utm_epsg


def open_document(project_path, read_only=False, ignore_lock=False):
    """Open an existing .psx project.

    A locked project doesn't raise: Metashape opens it read-only and only fails
    at save time, after the processing. Catch that here instead.
    """
    doc = Metashape.Document()
    doc.open(project_path, read_only=read_only, ignore_lock=ignore_lock)

    if not read_only and doc.read_only:
        raise RuntimeError(
            f"{project_path} is locked and opened read-only; results would be lost at "
            "save. Another run or the GUI has it open. If the lock is stale, use "
            "--ignore-lock to override."
        )

    return doc


def new_document(project_path, label=None, crs="EPSG::4326"):
    """Create a new project with a single chunk and save it to ``project_path``.

    Debug helper only. Real missions go through main.py, which additionally
    enforces the mission_id naming convention, takes the mission lock, derives
    project_crs from the photos, and writes the reproducibility log.
    """
    Metashape.app.settings.project_absolute_paths = True

    doc = Metashape.Document()
    chunk = doc.addChunk()
    if label:
        chunk.label = label
    chunk.crs = Metashape.CoordinateSystem(crs)

    doc.save(project_path)
    return doc


def get_chunk(doc, name=None, index=0):
    """Return a chunk by label, or by position if no label is given.

    Selecting by label is the main reason this exists: the pipeline class only
    ever works on doc.chunk and refuses multi-chunk projects outright, which
    leaves no way to touch a project produced by a GUI "Merge by camera labels".
    """
    if name:
        for chunk in doc.chunks:
            if chunk.label == name:
                return chunk
        available = ", ".join(repr(c.label) for c in doc.chunks) or "none"
        raise ValueError(f"No chunk named '{name}' in {doc.path} (available: {available})")
    return doc.chunks[index]


def derive_project_crs(chunk):
    """Guess a projected (UTM) CRS from the chunk's camera reference coordinates.

    Same rule main.py uses for a fresh mission (median position -> UTM zone), but
    read from the coordinates already stored in the chunk instead of re-walking
    the photos' EXIF. Returns an "EPSG::<code>" string.

    This matters because chunk.crs is never the right answer for outputs: the
    workflow leaves it at input_crs (EPSG::4326) for the life of the project and
    passes project_crs explicitly to every build and export. Defaulting to
    chunk.crs would silently produce rasters in degrees.
    """
    latitudes = []
    longitudes = []

    for camera in chunk.cameras:
        location = camera.reference.location
        if location is None:
            continue
        # Only trust these as lon/lat if they are in a geographic range; a chunk
        # whose coordinates are already projected would give metres here and a
        # nonsense UTM zone.
        if abs(location.x) > 180 or abs(location.y) > 90:
            raise ValueError(
                f"Chunk '{chunk.label}' has non-geographic camera coordinates, so a UTM "
                "zone cannot be derived from them. Pass --crs explicitly."
            )
        longitudes.append(location.x)
        latitudes.append(location.y)

    if not latitudes:
        raise ValueError(
            f"Chunk '{chunk.label}' has no camera reference coordinates to derive a CRS "
            "from. Pass --crs explicitly (the mission's processing log records the "
            "project_crs used originally)."
        )

    return calculate_utm_epsg(statistics.median(latitudes), statistics.median(longitudes))


def save(doc, project_path=None):
    if project_path:
        doc.save(project_path)
    else:
        doc.save()
