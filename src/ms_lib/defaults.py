"""Resolve step parameters from the workflow YAML config.

Single source of truth: the same config file and the same pydantic models that
main.py validates are used here, so changing a value in
config/config_lefolab_default.yml moves the full pipeline and the standalone task
runner together. Nothing in src/ms_lib/ should hardcode a processing parameter.

Resolution order, last one wins:

    pydantic field default  ->  YAML value  ->  caller keyword argument

Callers pass their keyword arguments straight through; a value of None means
"not specified", so a plain ``build_depth_maps(chunk)`` gets the YAML settings
and ``build_depth_maps(chunk, downscale=2)`` overrides just that one.

Note this reads only the step sections. It deliberately does not go through
load_config(), which does mission-level work a step runner has no business
triggering: it requires a mission_id, invents project/output paths, and walks
every photo's EXIF to derive project_crs.
"""

import os

import yaml

from src.metashape_workflow_functions_lefolab import convert_objects

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CONFIG = os.path.join(REPO_ROOT, "config", "config_lefolab_default.yml")

_raw_cache = {}


def load_raw(config_file=None):
    """Parsed YAML for ``config_file`` (default: the lefolab default config)."""
    path = config_file or DEFAULT_CONFIG
    if path not in _raw_cache:
        with open(path, "r") as f:
            _raw_cache[path] = yaml.safe_load(f) or {}
    return _raw_cache[path]


def step_params(section, model, config_file=None, **overrides):
    """Validated parameters for one config section, with caller overrides applied.

    ``section`` is a top-level key of the config ("buildDepthMaps", ...) and
    ``model`` the matching pydantic model from src/model/config.py. Overrides
    whose value is None are ignored. Strings naming Metashape objects (e.g.
    "Metashape.AggressiveFiltering") are resolved into the objects themselves.

    Keys the model does not declare are dropped by pydantic, and orchestration
    flags it does declare ("enabled", "export") are returned but unused here:
    which steps run is decided by the caller, not the config.
    """
    raw = load_raw(config_file).get(section) or {}
    params = model(**raw).model_dump(mode="json")
    params.update({k: v for k, v in overrides.items() if v is not None})
    convert_objects(params)
    return params


def global_param(key, default=None, config_file=None):
    """A top-level config value that is not step-specific (subdivide_task, ...)."""
    value = load_raw(config_file).get(key)
    return default if value is None else value
