"""Standalone Metashape step helpers used by scripts/run_task.py.

Unlike src/metashape_workflow_functions_lefolab.py -- which runs a whole mission
in one document lifecycle, on the active chunk, with a mission lock and a log
file -- these helpers act on a chunk you hand them, one step at a time. They are
for surgery on projects that already exist (re-export a product, rebuild a DEM,
process a chunk produced by a GUI merge), not for running missions.

Processing parameters are not defined here: they are read from the workflow YAML
config through src/ms_lib/defaults.py, so the pipeline and the task runner stay
in step. See that module for the resolution order.
"""
