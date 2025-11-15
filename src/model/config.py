"""
Configuration model for Metashape workflow using Pydantic for validation.
"""
from typing import Optional, Union, List, Any
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum
import re


class MetashapeFiltering(str, Enum):
    """Filtering modes for depth maps"""
    NoFiltering = "Metashape.NoFiltering"
    MildFiltering = "Metashape.MildFiltering"
    ModerateFiltering = "Metashape.ModerateFiltering"
    AggressiveFiltering = "Metashape.AggressiveFiltering"


class MetashapeBlending(str, Enum):
    """Blending modes for orthomosaic"""
    AverageBlending = "Metashape.AverageBlending"
    MosaicBlending = "Metashape.MosaicBlending"
    MinBlending = "Metashape.MinBlending"
    MaxBlending = "Metashape.MaxBlending"
    DisabledBlending = "Metashape.DisabledBlending"


class MetashapeReferencePreselectionMode(str, Enum):
    """Reference preselection modes"""
    Source = "Metashape.ReferencePreselectionSource"
    Estimated = "Metashape.ReferencePreselectionEstimated"
    Sequential = "Metashape.ReferencePreselectionSequential"


class MetashapeCalibrationFormat(str, Enum):
    """Camera calibration formats"""
    XML = "Metashape.CalibrationFormatXML"
    Australis = "Metashape.CalibrationFormatAustralis"
    AustralisV7 = "Metashape.CalibrationFormatAustralisV7"
    PhotoModeler = "Metashape.CalibrationFormatPhotoModeler"
    CalibCam = "Metashape.CalibrationFormatCalibCam"
    CalCam = "Metashape.CalibrationFormatCalCam"
    Inpho = "Metashape.CalibrationFormatInpho"
    USGS = "Metashape.CalibrationFormatUSGS"
    Pix4D = "Metashape.CalibrationFormatPix4D"
    OpenCV = "Metashape.CalibrationFormatOpenCV"
    Photomod = "Metashape.CalibrationFormatPhotomod"
    Grid = "Metashape.CalibrationFormatGrid"
    STMap = "Metashape.CalibrationFormatSTMap"


class MetashapePointClass(str, Enum):
    """Point classes for point cloud classification"""
    Created = "Metashape.PointClass.Created"
    Unclassified = "Metashape.PointClass.Unclassified"
    Ground = "Metashape.PointClass.Ground"
    LowVegetation = "Metashape.PointClass.LowVegetation"
    MediumVegetation = "Metashape.PointClass.MediumVegetation"
    HighVegetation = "Metashape.PointClass.HighVegetation"
    Building = "Metashape.PointClass.Building"
    LowPoint = "Metashape.PointClass.LowPoint"
    ModelKeyPoint = "Metashape.PointClass.ModelKeyPoint"
    Water = "Metashape.PointClass.Water"
    Rail = "Metashape.PointClass.Rail"
    RoadSurface = "Metashape.PointClass.RoadSurface"
    OverlapPoints = "Metashape.PointClass.OverlapPoints"
    WireGuard = "Metashape.PointClass.WireGuard"
    WireConductor = "Metashape.PointClass.WireConductor"
    TransmissionTower = "Metashape.PointClass.TransmissionTower"
    WireConnector = "Metashape.PointClass.WireConnector"
    BridgeDeck = "Metashape.PointClass.BridgeDeck"
    HighNoise = "Metashape.PointClass.HighNoise"
    Car = "Metashape.PointClass.Car"
    Manmade = "Metashape.PointClass.Manmade"


class AddPhotosConfig(BaseModel):
    """Configuration for adding photos"""
    enabled: bool = True
    multispectral: bool = False
    use_xmp_accuracy: bool = True
    photos_accuracy: float = Field(default=5.0, gt=0)
    load_reference: bool = True
    load_xmp_calibration: bool = True
    load_xmp_orientation: bool = True
    load_xmp_accuracy: bool = True
    load_xmp_antenna: bool = True


class CameraCalibrationConfig(BaseModel):
    """Configuration for camera calibration"""
    format: MetashapeCalibrationFormat = MetashapeCalibrationFormat.XML
    fixed_parameters: Union[str, List[str]] = ""

    @field_validator('fixed_parameters')
    @classmethod
    def validate_fixed_parameters(cls, v):
        if isinstance(v, str) and v == "":
            return []
        if isinstance(v, list):
            valid_params = ["F", "Cx", "Cy", "K1", "K2", "K3", "K4", "P1", "P2", "B1", "B2"]
            for param in v:
                if param not in valid_params:
                    raise ValueError(f"Invalid fixed parameter: {param}. Must be one of {valid_params}")
        return v


class AlignPhotosConfig(BaseModel):
    """Configuration for photo alignment"""
    enabled: bool = True
    downscale: int = Field(default=1, ge=0, le=8)
    adaptive_fitting: bool = False
    keep_keypoints: bool = True
    reset_alignment: bool = False
    generic_preselection: bool = True
    reference_preselection: bool = True
    reference_preselection_mode: MetashapeReferencePreselectionMode = MetashapeReferencePreselectionMode.Source
    filter_stationary_points: bool = False
    keypoint_limit: int = Field(default=60000, ge=0)
    keypoint_limit_per_mpx: int = Field(default=1000, ge=0)
    tiepoint_limit: int = Field(default=0, ge=0)

    @field_validator('downscale')
    @classmethod
    def validate_downscale(cls, v):
        valid_values = [0, 1, 2, 4, 8]
        if v not in valid_values:
            raise ValueError(f"downscale must be one of {valid_values}")
        return v


class BuildDepthMapsConfig(BaseModel):
    """Configuration for building depth maps"""
    enabled: bool = True
    downscale: int = Field(default=4, ge=1, le=16)
    filter_mode: MetashapeFiltering = MetashapeFiltering.AggressiveFiltering
    reuse_depth: bool = False
    max_neighbors: int = Field(default=16, ge=1, le=100)

    @field_validator('downscale')
    @classmethod
    def validate_downscale(cls, v):
        valid_values = [1, 2, 4, 8, 16]
        if v not in valid_values:
            raise ValueError(f"downscale must be one of {valid_values}")
        return v


class BuildPointCloudConfig(BaseModel):
    """Configuration for building point cloud"""
    enabled: bool = True
    keep_depth: bool = True
    max_neighbors: int = Field(default=100, ge=1)
    classify_ground_points: bool = False
    export: bool = True
    classes: Union[str, MetashapePointClass, List[Union[str, MetashapePointClass]]] = "ALL"
    remove_after_export: bool = False
    
    @field_validator('classes')
    @classmethod
    def validate_classes(cls, v):
        if isinstance(v, str):
            if v == "ALL":
                return v
            valid_values = [e.value for e in MetashapePointClass]
            if v not in valid_values:
                raise ValueError(f"classes must be 'ALL', a MetashapePointClass value, or a list of values. Got: {v}")
            return v
        if isinstance(v, list):
            valid_values = [e.value for e in MetashapePointClass]
            for class_val in v:
                class_str = class_val if isinstance(class_val, str) else class_val.value
                if class_str not in valid_values:
                    raise ValueError(f"Invalid point class: {class_str}. Must be one of {valid_values}")
        return v


class BuildDemConfig(BaseModel):
    """Configuration for building DEM"""
    enabled: bool = True
    classify_ground_points: bool = False
    resolution: float = Field(default=0.0, ge=0)
    export: bool = True
    tiff_big: bool = True
    tiff_tiled: bool = True
    nodata: int = -32767
    tiff_overviews: bool = True


class BuildOrthomosaicConfig(BaseModel):
    """Configuration for building orthomosaic"""
    enabled: bool = True
    blending: MetashapeBlending = MetashapeBlending.MosaicBlending
    fill_holes: bool = True
    refine_seamlines: bool = False
    export: bool = True
    tiff_big: bool = True
    tiff_tiled: bool = True
    nodata: int = -32767
    tiff_overviews: bool = True
    remove_after_export: bool = False


class MetashapeConfig(BaseModel):
    """Main configuration model for Metashape workflow"""
    
    # Project parameters
    images_path: Union[str, List[str]] = ""
    output_path: str = ""
    project_path: str = ""
    delete_project: bool = False
    mission_id: str = ""
    input_crs: str = "EPSG::4326"
    project_crs: str = ""
    load_project: str = ""
    subdivide_task: bool = True
    use_cuda: bool = True
    gpu_multiplier: int = Field(default=2, ge=1)
    
    # Camera calibration
    camera_calibration_path: str = ""
    cameracalibration: CameraCalibrationConfig = Field(default_factory=CameraCalibrationConfig)
    
    # Processing steps
    addPhotos: AddPhotosConfig = Field(default_factory=AddPhotosConfig)
    alignPhotos: AlignPhotosConfig = Field(default_factory=AlignPhotosConfig)
    buildDepthMaps: BuildDepthMapsConfig = Field(default_factory=BuildDepthMapsConfig)
    buildPointCloud: BuildPointCloudConfig = Field(default_factory=BuildPointCloudConfig)
    buildDem: BuildDemConfig = Field(default_factory=BuildDemConfig)
    buildOrthomosaic: BuildOrthomosaicConfig = Field(default_factory=BuildOrthomosaicConfig)
    
    # High quality / Disable filtering mode
    quick_process: bool = False
    buildDepthMapsHighDis: BuildDepthMapsConfig = Field(default_factory=BuildDepthMapsConfig)
    buildPointCloudHighDis: BuildPointCloudConfig = Field(default_factory=BuildPointCloudConfig)
    buildDemHighDis: BuildDemConfig = Field(default_factory=BuildDemConfig)
    
    # GCP workflow flags
    add_gcps: bool = False
    after_gcps: bool = False

    
    @field_validator('mission_id')
    @classmethod
    def validate_mission_id(cls, v):
        if v and not re.match(r'^(?!_)\d{8}_[0-9a-z]{2,16}(?:_[0-9a-z]{2,16}){0,1}_[0-9a-z]{2,16}$', v):
            raise ValueError(
                "mission_id must be in format '<yyyymmdd>_<site>_<optional>_<sensor>'"
            )
        return v
    
    @field_validator('input_crs')
    @classmethod
    def validate_input_crs(cls, v):
        if not re.match(r'^EPSG::\d+$', v):
            raise ValueError("input_crs must be in format 'EPSG::<code>'")
        return v

    @field_validator('project_crs')
    @classmethod
    def validate_project_crs(cls, v):
        if v and not re.match(r'^EPSG::\d+$', v):
            raise ValueError("project_crs must be in format 'EPSG::<code>'")
        return v
    
    @field_validator('images_path')
    @classmethod
    def validate_images_path(cls, v):
        if isinstance(v, list):
            for path in v:
                if not isinstance(path, str):
                    raise ValueError("All photo paths must be strings")
        return v
    
    @model_validator(mode='after')
    def validate_paths(self):
        """Validate that required paths are set when enabled"""
        if self.addPhotos.enabled and not self.images_path:
            raise ValueError("images_path must be set when addPhotos is enabled")
        return self
    
    class Config:
        # Use enum values instead of names
        use_enum_values = True


def load_config(config_file: str, override_dict: Optional[dict] = None) -> tuple[MetashapeConfig, dict]:
    """
    Load and validate configuration from YAML file with optional overrides
    
    Args:
        config_file: Path to YAML configuration file
        override_dict: Dictionary of values to override from CLI arguments
        
    Returns:
        Tuple of (validated MetashapeConfig object, original config dict)
        The dict is suitable for passing to workflow functions
    """
    import yaml
    import os
    from src.utilis import calculate_median_coordinates, calculate_utm_epsg
    
    # Load YAML file
    with open(config_file, 'r') as f:
        config_dict = yaml.safe_load(f)
    
    # Apply overrides from CLI
    if override_dict:
        for key, value in override_dict.items():
            if value is not None:
                config_dict[key] = value
    
    # Extract mission_id from images_path if not provided
    if not config_dict.get('mission_id') and config_dict.get('images_path'):
        images_path = config_dict['images_path']
        # Handle list - use first path
        if isinstance(images_path, list):
            images_path = images_path[0]
        
        mission_id = os.path.basename(os.path.normpath(images_path))
        # Validate format
        mission_id_pattern = r'^(?!_)\d{8}_[0-9a-z]{2,16}(?:_[0-9a-z]{2,16}){0,1}_[0-9a-z]{2,16}$'
        if re.match(mission_id_pattern, mission_id):
            config_dict['mission_id'] = mission_id
        else:
            raise ValueError(
                f"Could not extract valid mission_id from images path: '{mission_id}'."
                "mission_id should be in the format: '<yyyymmdd>_<site>_<optional>_<sensor>'."
            )
    
    # Raise error if mission_id is still not set
    if not config_dict.get('mission_id'):
        raise ValueError(
            "mission_id is required but not provided. "
            "Please specify mission_id in your config file or use --mission-id CLI argument."
        )
    
    # Generate default paths if not provided
    mission_id = config_dict['mission_id']
    mission_year = mission_id[:4]
    
    if not config_dict.get('project_path'):
        config_dict['project_path'] = f"/mnt/nfs/conrad/labolaliberte_metashape_projects/{mission_year}/{mission_id}"
    
    if not config_dict.get('output_path'):
        config_dict['output_path'] = f"{config_dict['project_path']}/metashape/"
    
    # Calculate project_crs from photos if not provided
    if not config_dict.get('project_crs') and config_dict.get('images_path'):
        images_path = config_dict['images_path']
        
        # Handle list of paths - concatenate all paths
        if isinstance(images_path, list):
            all_images = []
            for path in images_path:
                all_images.append(path)
            images_path = all_images
        
        try:
            median_latitude, median_longitude = calculate_median_coordinates(images_path)
            config_dict['project_crs'] = calculate_utm_epsg(median_latitude, median_longitude)
        except Exception as e:
            raise ValueError(
                f"Failed to calculate project_crs from photos: {e}\n"
                "Please specify project_crs manually in the config file or as a CLI argument."
            )
    
    # Validate and return both the Pydantic model and the dict
    validated_config = MetashapeConfig(**config_dict)
    return validated_config, config_dict
