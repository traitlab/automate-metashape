<h1 align="center">automate-metashape (LEFO)</h1>

<p align="center">
<img src="https://img.shields.io/badge/python-3.11-blue" alt="Python 3.11">
<img src="https://img.shields.io/badge/Metashape-2.2-orange" alt="Metashape 2.2">
<img src="https://img.shields.io/badge/license-GPLv3-green" alt="License: GPLv3">
<img src="https://img.shields.io/badge/platform-Linux-lightgrey" alt="Platform: Linux">
</p>

<p align="center">
Command-line pipeline to process drone imagery with the <a href="https://www.agisoft.com/">Agisoft Metashape</a> Python API, from raw photos to orthomosaic, DSM and point cloud. LEFO fork of <a href="https://github.com/open-forest-observatory/automate-metashape">open-forest-observatory/automate-metashape</a>.
</p>

## ✨ Features

- **Full pipeline in one command**: add photos → align → depth maps → point cloud → DSM → orthomosaic → report, driven by a validated YAML config.
- **High-detail pass (HighDis)**: second point cloud and DSM at High quality with no depth filtering. Skip it with `--quick-process`.
- **RGB, multispectral and thermal** (DJI M3T, converted with R) imagery.
- **Manual GCPs**: pause after alignment, add GCPs in the GUI, then resume.
- **Reproducible runs**: a processing log with timings, system info and the full config is written next to the project. A lock prevents two runs of the same mission at once.
- **Step-by-step processing** of existing projects with `scripts/run_task.py`, including aligning and merging chunks.

## 🔧 Setup

```bash
git clone https://github.com/traitlab/automate-metashape.git
cd automate-metashape

conda create -n metashape python=3.11
conda activate metashape
pip install https://download.agisoft.com/Metashape-2.2.2-cp37.cp38.cp39.cp310.cp311-abi3-linux_x86_64.whl
pip install -r requirements.txt
```

You also need a Metashape Professional license. Set `agisoft_LICENSE` to the folder containing `metashape.lic` (node-locked license) or `AGISOFT_FLS` to `<ip>:<port>` (floating license).

Thermal processing also requires R with the packages `hexView`, `raster`, `ijtiff`, `exifr`, `foreach` and `doParallel`.

## 🚀 Usage

Run from the repository root with the `metashape` environment activated.

```bash
# Default config; mission_id is read from the photo folder name
python main.py -i /path/to/photos/20261006_site_m3e

# Custom config (CLI arguments override its values)
python main.py -c config/my_mission.yml

# Skip the HighDis pass
python main.py -i /path/to/photos/20261006_site_m3e --quick-process
```

**GCPs**: run with `--gcps`. Processing stops after alignment and prints the command to resume. Add the GCPs in the Metashape GUI, then rerun that command (`--gcps --load-project <project.psx>`).

### Command-line arguments

| Argument | Description |
|---|---|
| `-i`, `--images-path` | Folder of photos (required with the default config) |
| `-c`, `--config-file` | YAML config (default: `config/config_lefolab_default.yml`) |
| `-p`, `--project-path` | Folder for the `.psx` project and log |
| `-o`, `--output-path` | Folder for exports (default: `<project_path>/metashape/`) |
| `--mission-id` | `<yyyymmdd>_<site>_<optional>_<sensor>`; default: photo folder name |
| `--input-crs` | CRS of the photo coordinates (default: `EPSG::4326`) |
| `--project-crs` | Output CRS, e.g. `EPSG::32618` (default: UTM zone from the photos) |
| `--camera-calibration-path` | Camera calibration `.xml` (examples in `calibration/`) |
| `-l`, `--load-project` | Existing `.psx` to continue from |
| `-g`, `--gcps` | Pause after alignment to add GCPs in the GUI |
| `-q`, `--quick-process` | Skip the HighDis pass |
| `-t`, `--thermal` | Process thermal images |
| `--delete-project` | Delete the project after processing (outputs are kept) |

## ⚙️ Configuration

Copy [`config/config_lefolab_default.yml`](config/config_lefolab_default.yml) and edit the copy. Every parameter is documented there. The config is validated against [`src/model/config.py`](src/model/config.py) before processing starts, and Metashape constants are written as strings (e.g. `Metashape.MosaicBlending`).

## 📊 Outputs

Written to the output path:

| File | Content |
|---|---|
| `<mission_id>_rgb.tif` | Orthomosaic (`_ms.tif` reflectance for multispectral, `_tir.tif` for thermal) |
| `<mission_id>_dsm.tif` | Digital surface model |
| `<mission_id>_pg.copc.laz` | Point cloud (COPC) |
| `<mission_id>_report.pdf` | Metashape processing report |

The project (`<mission_id>_<timestamp>.psx`) and its processing log (`_log.txt`) are written to the project path. With the default lab paths, outputs are moved to `labolaliberte_upload/_data/metashape/<yyyy>/<mission_id>/` when the run finishes.

## 🧩 Scripts

- [`scripts/run_task.py`](scripts/run_task.py): run individual steps on an existing project and chunk, e.g. re-export in another CRS, rebuild a DEM, calibrate reflectance, or align, merge and deduplicate chunks. See the docstring for examples.
- [`scripts/make_overlap_chunks.sh`](scripts/make_overlap_chunks.sh): build symlinked photo folders so adjacent chunks share their boundary flight lines, so the chunks can be aligned on common cameras before merging.

## 📄 License

GPLv3, see [`LICENSE`](LICENSE). Based on code by UC Davis / Open Forest Observatory originally released under BSD 3-Clause, see [`NOTICE`](NOTICE).
