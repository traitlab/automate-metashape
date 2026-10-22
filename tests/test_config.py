"""Tests for the config model and load_config (no Metashape needed)."""

from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from src.model.config import MetashapeConfig, load_config

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
DEFAULT_CONFIG = CONFIG_DIR / "config_lefolab_default.yml"
CONFIG_FILES = sorted(CONFIG_DIR.glob("*.yml"))

MISSION_ID = "20261006_zf2amzface_m3e"


def unknown_keys(model, values, prefix=""):
    """Keys of a config dict that the model doesn't define (Pydantic would silently drop them)."""
    unknown = []
    for key, value in values.items():
        if key not in model.model_fields:
            unknown.append(prefix + key)
            continue
        annotation = model.model_fields[key].annotation
        if (
            isinstance(value, dict)
            and isinstance(annotation, type)
            and issubclass(annotation, BaseModel)
        ):
            unknown += unknown_keys(annotation, value, f"{prefix}{key}.")
    return unknown


def load(images_path, **overrides):
    """load_config on the default config, with a project_crs so no photo is read."""
    return load_config(
        str(DEFAULT_CONFIG),
        {"images_path": str(images_path), "project_crs": "EPSG::32618", **overrides},
    )


@pytest.fixture
def mission_dir(tmp_path):
    path = tmp_path / MISSION_ID
    path.mkdir()
    return path


@pytest.mark.parametrize("config_file", CONFIG_FILES, ids=lambda p: p.name)
def test_config_keys_match_model(config_file):
    values = yaml.safe_load(config_file.read_text())
    assert unknown_keys(MetashapeConfig, values) == []


def test_default_config_validates(mission_dir):
    _, cfg = load(mission_dir)
    assert cfg["mission_id"] == MISSION_ID
    assert cfg["buildDepthMaps"]["filter_mode"] == "Metashape.AggressiveFiltering"
    assert cfg["config_file"] == str(DEFAULT_CONFIG)


def test_mission_id_from_images_path(mission_dir):
    _, cfg = load(mission_dir)
    assert cfg["mission_id"] == MISSION_ID


def test_mission_id_from_first_of_several_images_paths(tmp_path, mission_dir):
    other = tmp_path / "other"
    other.mkdir()
    _, cfg = load_config(
        str(DEFAULT_CONFIG),
        {"images_path": [str(mission_dir), str(other)], "project_crs": "EPSG::32618"},
    )
    assert cfg["mission_id"] == MISSION_ID


def test_invalid_folder_name_without_mission_id_fails(tmp_path):
    folder = tmp_path / "not a mission"
    folder.mkdir()
    with pytest.raises(ValueError, match="Could not extract valid mission_id"):
        load(folder)


@pytest.mark.parametrize(
    "mission_id",
    [
        "20261006_zf2amzface_m3e",
        "20261006_site_free01_m3e",
    ],
)
def test_valid_mission_ids(tmp_path, mission_id):
    _, cfg = load(tmp_path, mission_id=mission_id)
    assert cfg["mission_id"] == mission_id


@pytest.mark.parametrize(
    "mission_id",
    [
        "2026106_site_m3e",  # 7-digit date
        "20261006_Site_m3e",  # uppercase
        "20261006_site",  # no sensor
        "20261006_site_a_b_m3e",  # two optional parts
        "_20261006_site_m3e",  # leading underscore
    ],
)
def test_invalid_mission_ids(tmp_path, mission_id):
    with pytest.raises(ValidationError, match="mission_id"):
        load(tmp_path, mission_id=mission_id)


def test_default_paths(mission_dir):
    _, cfg = load(mission_dir)
    project = f"/mnt/nfs/conrad/labolaliberte_metashape_projects/2026/{MISSION_ID}"
    assert cfg["project_path"] == project
    assert cfg["output_path"] == f"{project}/metashape/"


def test_project_path_from_load_project(mission_dir):
    _, cfg = load(mission_dir, load_project="/data/projects/existing.psx")
    assert cfg["project_path"] == "/data/projects"


def test_none_overrides_are_ignored(mission_dir):
    # argparse leaves unset options as None: they must not replace config values
    _, cfg = load(mission_dir, input_crs=None, quick_process=None)
    assert cfg["input_crs"] == "EPSG::4326"
    assert cfg["quick_process"] is False


@pytest.mark.parametrize("field", ["input_crs", "project_crs"])
def test_invalid_crs(mission_dir, field):
    with pytest.raises(ValidationError, match=field):
        load(mission_dir, **{field: "32618"})


def base_config(mission_dir, **values):
    return MetashapeConfig(images_path=str(mission_dir), mission_id=MISSION_ID, **values)


@pytest.mark.parametrize(
    "values",
    [
        {"alignPhotos": {"downscale": 3}},
        {"buildDepthMaps": {"downscale": 3}},
        {"buildDepthMaps": {"filter_mode": "Metashape.NotAFilter"}},
        {"buildOrthomosaic": {"blending": "MosaicBlending"}},  # missing "Metashape." prefix
        {"cameracalibration": {"fixed_parameters": ["F", "K9"]}},
        {"buildPointCloud": {"classes": "Ground"}},
        {"thermal_parameters": {"mission_start": "2026-10-06"}},
    ],
    ids=lambda values: next(iter(values)),
)
def test_invalid_step_values(mission_dir, values):
    with pytest.raises(ValidationError):
        base_config(mission_dir, **values)


def test_images_path_required_when_adding_photos():
    with pytest.raises(ValidationError, match="images_path"):
        MetashapeConfig(mission_id=MISSION_ID)
    MetashapeConfig(mission_id=MISSION_ID, addPhotos={"enabled": False})
