import copy
import datetime
import glob
import os
import platform
import re
import shutil
import sys
import time
import yaml

import Metashape


def resolve_metashape_object(name):
    """
    Resolve a dotted Metashape object name (e.g., "Metashape.MosaicBlending") 
    into the actual Metashape object.
    """
    if not name.startswith("Metashape."):
        raise ValueError(f"Invalid Metashape object name: {name}")
    
    parts = name.split(".")[1:]
    obj = Metashape
    for part in parts:
        obj = getattr(obj, part)
    return obj

def convert_objects(a_dict):
    """
    Convert strings that refer to metashape objects (e.g. "Metashape.MosaicBlending") 
    into metashape objects.
    """
    for k, v in a_dict.items():
        if not isinstance(v, dict):
            if isinstance(v, str):
                # Allow "path", "project", and "name" keys to include "Metashape" in their values
                if v and "Metashape" in v and not any(x in k for x in ("path", "project", "name")):
                    a_dict[k] = resolve_metashape_object(v)
            elif isinstance(v, list):
                # Convert list items that contain "Metashape"
                if any("Metashape" in item for item in v if isinstance(item, str)):
                    a_dict[k] = [resolve_metashape_object(item) for item in v if isinstance(item, str) and "Metashape" in item]
        else:
            convert_objects(v)

def stamp_time():
    """
    Format the timestamps as needed
    """
    stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H%M")
    return stamp

def diff_time(t2, t1):
    """
    Give a end and start time, subtract, and format.
    """
    total_seconds = int(t2 - t1)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    # Format based on value
    if hours > 0:
        return f"{hours}h{minutes:02d}m{seconds:02d}s"
    elif minutes > 0:
        return f"{minutes}m{seconds:02d}s"
    else:
        return f"{seconds}s"


class MetashapeWorkflowLefolab:
    sep = ": "

    def __init__(
        self,
        config_file,
    ):
        """
        Initializes an instance of the MetashapeWorkflowLefolab class based on the config file given
        """       
        self.config_file = copy.deepcopy(config_file) # Store config for logging (before conversion to Metashape objects)
        self.cfg = config_file
        self.doc = None
        self.log_file = None
        self.run_id = None
        convert_objects(self.cfg)

    #### Functions for each major step in Metashape

    def run(self):
        """
        Execute metashape workflow steps based on config file
        """
        self.processing_start_time = time.time()
        
        self.project_setup()

        self.enable_and_log_gpu()

        # Skip add_photos and align_photos if resuming after GCPs
        if not self.cfg.get("after_gcps"):
            # Add photos
            if (self.cfg["images_path"] != "") and (self.cfg["addPhotos"]["enabled"]):
                self.add_photos()

            # Align photos
            if self.cfg["alignPhotos"]["enabled"]:
                self.align_photos()
                self.reset_region()

        # Add GCPs manually via GUI if specified
        if self.cfg.get("add_gcps"):
            self.add_gcps()
            return

        if self.cfg.get("after_gcps"):
            self.after_gcps()

        if self.cfg["buildDepthMaps"]["enabled"]:
            self.build_depth_maps()

        if self.cfg["buildPointCloud"]["enabled"]:
            self.build_point_cloud()

        # For this step, the check for whether it is enabled in the config happens inside the function, because there are two steps (DEM and ortho), each of which can be enabled independently
        self.build_dem_orthomosaic()

        if not self.cfg["quick_process"]:
            self.build_depth_maps_highdis()
            self.build_point_cloud_highdis()
            self.build_dem_highdis()

        self.export_report()

        self.finish_run()

    def project_setup(self):
        """
        Create output and project paths, if they don't exist
        Define a project ID based on specified project name and timestamp
        Define a project filename and a log filename
        Create the project
        Start a log file
        """
        # Ensure output path exists
        os.makedirs(self.cfg["output_path"], exist_ok=True)

        # Ensure project path exists
        os.makedirs(self.cfg["project_path"], exist_ok=True)

        mission_id = self.cfg["mission_id"]

        ## Project file example: "missionID_YYYY-MM-DDtHHMM.psx"
        timestamp = stamp_time()
        self.run_id = mission_id
        self.run_id_with_time = "_".join([mission_id, timestamp])

        project_file = os.path.join(
            self.cfg["project_path"], ".".join([self.run_id_with_time, "psx"])
        )
        self.log_file = os.path.join(
            self.cfg["project_path"], ".".join([self.run_id_with_time + "_log", "txt"])
        )

        """
        Create a doc and a chunk
        """
        # create a handle to the Metashape object
        self.doc = (Metashape.Document())  # When running via Metashape, can use: doc = Metashape.app.document

        # If specified, open existing project
        if self.cfg["load_project"] != "":
            self.doc.open(self.cfg["load_project"])
        else:
            # Initialize a chunk, set its CRS as specified
            chunk = self.doc.addChunk()
            chunk.label = mission_id
            chunk.crs = Metashape.CoordinateSystem(self.cfg["input_crs"])
            # chunk.marker_crs = Metashape.CoordinateSystem(
            #     self.cfg["addGCPs"]["gcp_crs"]
            # )

        # Save doc as new project (even if we opened an existing project, save as a separate one so the existing project remains accessible in its original state)
        self.doc.save(project_file)

        """
        Log specs except for GPU
        """
        with open(self.log_file, "a") as file:

            file.write(MetashapeWorkflowLefolab.sep.join(["Project", self.run_id]) + "\n")
            file.write(MetashapeWorkflowLefolab.sep.join(["Agisoft Metashape Professional Version", Metashape.app.version]) + "\n")
            file.write(MetashapeWorkflowLefolab.sep.join(["Processing started", stamp_time()]) + "\n")
            file.write(MetashapeWorkflowLefolab.sep.join(["Node", platform.node()]) + "\n")
            try:
                with open('/proc/cpuinfo', 'r') as cpuinfo:
                    for line in cpuinfo:
                        if 'model name' in line:
                            cpu_model = line.split(':')[1].strip()
                            file.write(MetashapeWorkflowLefolab.sep.join(["CPU Model", cpu_model]) + "\n")
                            break
            except:
                file.write(MetashapeWorkflowLefolab.sep.join(["CPU Model", platform.processor()]) + "\n")
            file.write(MetashapeWorkflowLefolab.sep.join(["CPU Cores", str(os.cpu_count())]) + "\n")
            try:
                with open('/proc/meminfo', 'r') as meminfo:
                    for line in meminfo:
                        if line.startswith('MemTotal'):
                            ram_kb = int(line.split()[1])
                            ram_gb = round(ram_kb / (1024**2), 2)
                            file.write(MetashapeWorkflowLefolab.sep.join(["Total RAM (GB)", str(ram_gb)]) + "\n")
                            break
            except:
                file.write(MetashapeWorkflowLefolab.sep.join(["Total RAM", "Unable to determine"]) + "\n")
            file.write(MetashapeWorkflowLefolab.sep.join(["Operating System", platform.system() + " " + platform.release()]) + "\n")
            try:
                with open('/etc/os-release', 'r') as os_release:
                    for line in os_release:
                        if line.startswith('PRETTY_NAME'):
                            os_name = line.split('=')[1].strip().strip('"')
                            file.write(MetashapeWorkflowLefolab.sep.join(["OS Distribution", os_name]) + "\n")
                            break
            except:
                pass
            file.write(MetashapeWorkflowLefolab.sep.join(["Python Version", platform.python_version()]) + "\n")

    def enable_and_log_gpu(self):
        """
        Enables GPU and logs GPU specs
        """
        gpustringraw = str(Metashape.app.enumGPUDevices())
        gpucount = gpustringraw.count("name': '")
        gpustring = ""
        currentgpu = 1
        while gpucount >= currentgpu:
            if gpustring != "":
                gpustring = gpustring + ", "
            gpustring = (
                gpustring + gpustringraw.split("name': '")[currentgpu].split("',")[0]
            )
            currentgpu = currentgpu + 1
        # gpustring = gpustringraw.split("name': '")[1].split("',")[0]
        gpu_mask = Metashape.app.gpu_mask

        with open(self.log_file, "a") as file:
            file.write(MetashapeWorkflowLefolab.sep.join(["Number of GPUs Found", str(gpucount)]) + "\n")
            file.write(MetashapeWorkflowLefolab.sep.join(["GPU Model", gpustring]) + "\n")
            # file.write(MetashapeWorkflowLefolab.sep.join(["GPU Mask", str(gpu_mask)]) + "\n")

            # If a GPU exists but is not enabled, enable the 1st one
            if (gpucount > 0) and (gpu_mask == 0):
                Metashape.app.gpu_mask = 1
                gpu_mask = Metashape.app.gpu_mask
                file.write(
                    MetashapeWorkflowLefolab.sep.join(["GPU Mask Enabled", str(gpu_mask)])
                    + "\n"
                )

            # This writes down all the GPU devices available
            # file.write('GPU(s): '+str(Metashape.app.enumGPUDevices())+'\n')

        # set Metashape to *not* use the CPU during GPU steps (appears to be standard wisdom)
        Metashape.app.cpu_enable = False

        # Disable CUDA if specified
        if not self.cfg["use_cuda"]:
            Metashape.app.settings.setValue("main/gpu_enable_cuda", "0")

        # Set GPU multiplier to value specified (2 is default)
        Metashape.app.settings.setValue(
            "main/depth_max_gpu_multiplier", self.cfg["gpu_multiplier"]
        )

        return True

    def add_photos(self, secondary=False):
        """
        Add photos to project and change their labels to include their containing folder. Secondary: if
        True, this is a secondary set of photos to be aligned only, after all photogrammetry products
        have been produced from the primary set of photos.
        """
        images_paths = self.cfg["images_path"]

        # If it's a single string (i.e. one directory), make it a list of one string so we can iterate
        # over it the same as if it were a list of strings
        if isinstance(images_paths, str):
            images_paths = [images_paths]

        for images_path in images_paths:

            grp = self.doc.chunk.addCameraGroup()

            ## Get paths to all the project photos
            a = glob.iglob(
                os.path.join(images_path, "**", "*.*"), recursive=True
            )  # (([jJ][pP][gG])|([tT][iI][fF]))
            b = [path for path in a]
            photo_files = [
                x
                for x in b
                if (
                    re.search("(.tif$)|(.jpg$)|(.TIF$)|(.JPG$)", x)
                    and (not re.search("dem_usgs.tif", x))
                )
            ]

            ## Add them
            if self.cfg["addPhotos"]["multispectral"]:
                self.doc.chunk.addPhotos(
                    photo_files, layout=Metashape.MultiplaneLayout, group=grp
                )
            else:
                self.doc.chunk.addPhotos(photo_files, group=grp,
                                         load_reference=self.cfg["addPhotos"]["load_reference"],
                                         load_xmp_calibration=self.cfg["addPhotos"]["load_xmp_calibration"],
                                         load_xmp_orientation=self.cfg["addPhotos"]["load_xmp_orientation"],
                                         load_xmp_accuracy=self.cfg["addPhotos"]["load_xmp_accuracy"],
                                         load_xmp_antenna=self.cfg["addPhotos"]["load_xmp_antenna"],
                                         )

        ## Need to change the label on each camera so that it includes the containing folder(s)
        for camera in self.doc.chunk.cameras:
            path = camera.photo.path
            camera.label = path

        # If specified, change the accuracy of the cameras for custom value
        if self.cfg["addPhotos"]["use_xmp_accuracy"] == False:
            for cam in self.doc.chunk.cameras:
                cam.reference.location_accuracy = Metashape.Vector(
                    [
                        self.cfg["addPhotos"]["photos_accuracy"],
                        self.cfg["addPhotos"]["photos_accuracy"],
                        self.cfg["addPhotos"]["photos_accuracy"],
                    ]
                )
                cam.reference.accuracy = Metashape.Vector(
                    [
                        self.cfg["addPhotos"]["photos_accuracy"],
                        self.cfg["addPhotos"]["photos_accuracy"],
                        self.cfg["addPhotos"]["photos_accuracy"],
                    ]
                )

        if self.cfg["camera_calibration_path"] != "":
            sensor = self.doc.chunk.sensors[0]
            calib = Metashape.Calibration()

            calib.load(self.cfg["camera_calibration_path"],
                       format=self.cfg["cameracalibration"]["format"])
            sensor.user_calib = calib
            
            sensor.fixed_params=self.cfg["cameracalibration"]["fixed_parameters"]

        self.doc.save()

        return True

    def align_photos(self):
        """
        Match photos, align cameras, optimize cameras
        """

        #### Align photos

        # get a beginning time stamp
        timer1a = time.time()

        # Align cameras
        self.doc.chunk.matchPhotos(
            downscale=self.cfg["alignPhotos"]["downscale"],
            subdivide_task=self.cfg["subdivide_task"],
            keep_keypoints=self.cfg["alignPhotos"]["keep_keypoints"],
            generic_preselection=self.cfg["alignPhotos"]["generic_preselection"],
            reference_preselection=self.cfg["alignPhotos"]["reference_preselection"],
            reference_preselection_mode=self.cfg["alignPhotos"]["reference_preselection_mode"],            
            filter_stationary_points=self.cfg["alignPhotos"]["filter_stationary_points"],
            keypoint_limit=self.cfg["alignPhotos"]["keypoint_limit"],
            keypoint_limit_per_mpx=self.cfg["alignPhotos"]["keypoint_limit_per_mpx"],
            tiepoint_limit=self.cfg["alignPhotos"]["tiepoint_limit"],
        )
        self.doc.chunk.alignCameras(
            adaptive_fitting=self.cfg["alignPhotos"]["adaptive_fitting"],
            subdivide_task=self.cfg["subdivide_task"],
            reset_alignment=self.cfg["alignPhotos"]["reset_alignment"],
        )
        self.doc.save()

        # get an ending time stamp
        timer1b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time1 = diff_time(timer1b, timer1a)

        # record processing time to file
        with open(self.log_file, "a") as file:
            file.write(MetashapeWorkflowLefolab.sep.join(["Align Photos", time1]) + "\n")

        return True

    def reset_region(self):
        """
        Reset the region and make it much larger than the points; necessary because if points go outside the region, they get clipped when saving
        """

        self.doc.chunk.resetRegion()
        region_dims = self.doc.chunk.region.size
        region_dims[2] *= 3
        self.doc.chunk.region.size = region_dims

        return True

    def add_gcps(self):
        """
        Pause processing and continue with GUI to add GCPs manually
        """
        chunk = self.doc.chunk
        
        for camera in chunk.cameras:
            if not camera.photo:
                continue
            old_path = camera.photo.path
            
            if old_path.startswith("/mnt/nfs/lefodata/"):
                new_path = old_path.replace("/mnt/nfs/lefodata/", "//lefodata/")
                camera.photo.path = new_path
            elif old_path.startswith("/mnt/nfs/conrad/"):
                new_path = old_path.replace("/mnt/nfs/conrad/", "//conrad-irbv.irbv.umontreal.ca/")
                camera.photo.path = new_path
            # Not working on Windows paths currently

        self.doc.save()
        print("\n[INFO] Photos alignment completed. Please add GCPs using the Metashape GUI, then rerun with --after-gcps to resume processing.")
        gui_path = self.doc.path.replace('/mnt/nfs/conrad/', '//conrad-irbv.irbv.umontreal.ca/').replace('/', '\\')
        print(f"[INFO] Command to rerun: {' '.join(sys.argv).replace(' -gcps', '').replace(' -add-gcps', '')} -load {self.doc.path} --after-gcps")
        print(f"[INFO] Open project on GUI server at: {gui_path}")
        return

    def after_gcps(self):
        """
        Resume processing after GCPs have been added manually via GUI
        """
        chunk = self.doc.chunk

        for camera in chunk.cameras:
            if not camera.photo:
                continue
            camera.photo.path = camera.label

        self.doc.save()

    def build_depth_maps(self):
        ### Build depth maps

        # get a beginning time stamp for the next step
        timer2a = time.time()

        # build depth maps only instead of also building the point cloud ##?? what does
        self.doc.chunk.buildDepthMaps(
            downscale=self.cfg["buildDepthMaps"]["downscale"],
            filter_mode=self.cfg["buildDepthMaps"]["filter_mode"],
            reuse_depth=self.cfg["buildDepthMaps"]["reuse_depth"],
            max_neighbors=self.cfg["buildDepthMaps"]["max_neighbors"],
            subdivide_task=self.cfg["subdivide_task"],
        )

        # get an ending time stamp for the previous step
        timer2b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time2 = diff_time(timer2b, timer2a)

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(MetashapeWorkflowLefolab.sep.join(["Build Depth Maps", time2]) + "\n")

        self.doc.save()

    def build_point_cloud(self):
        """
        Build point cloud
        """
        ### Build point cloud

        # get a beginning time stamp for the next step
        timer3a = time.time()

        # build point cloud
        self.doc.chunk.buildPointCloud(
            max_neighbors=self.cfg["buildPointCloud"]["max_neighbors"],
            keep_depth=self.cfg["buildPointCloud"]["keep_depth"],
            subdivide_task=self.cfg["subdivide_task"],
            point_colors=True,
            replace_asset=True,
        )

        # get an ending time stamp for the previous step
        timer3b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time3 = diff_time(timer3b, timer3a)

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(MetashapeWorkflowLefolab.sep.join(["Build Point Cloud", time3]) + "\n")

        self.doc.save()

        # # classify ground points if specified
        # if self.cfg["buildPointCloud"]["classify_ground_points"]:
        #     self.classify_ground_points()

        ### Export points

        if self.cfg["buildPointCloud"]["export"] and self.cfg["quick_process"]:

            output_file = os.path.join(
                self.cfg["output_path"], self.run_id + "_pg.copc.laz"
            )

            if self.cfg["buildPointCloud"]["classes"] == "ALL":
                # call without classes argument (Metashape then defaults to all classes)
                self.doc.chunk.exportPointCloud(
                    path=output_file,
                    source_data=Metashape.PointCloudData,
                    format=Metashape.PointCloudFormatCOPC,
                    crs=Metashape.CoordinateSystem(self.cfg["project_crs"]),
                    subdivide_task=self.cfg["subdivide_task"],
                )
            else:
                # call with classes argument
                self.doc.chunk.exportPointCloud(
                    path=output_file,
                    source_data=Metashape.PointCloudData,
                    format=Metashape.PointCloudFormatCOPC,
                    crs=Metashape.CoordinateSystem(self.cfg["project_crs"]),
                    clases=self.cfg["buildPointCloud"]["classes"],
                    subdivide_task=self.cfg["subdivide_task"],
                )

        return True

    # def build_model(self):
    #     """
    #     Build and export the model
    #     """

    #     start_time = time.time()
    #     # Build the mesh
    #     self.doc.chunk.buildModel(
    #         surface_type=Metashape.Arbitrary,
    #         interpolation=Metashape.EnabledInterpolation,
    #         face_count=self.cfg["buildModel"]["face_count"],
    #         face_count_custom=self.cfg["buildModel"][
    #             "face_count_custom"
    #         ],  # Only used if face_count is custom
    #         source_data=Metashape.DepthMapsData,
    #     )

    #     time_taken = diff_time(time.time(), start_time)

    #     # record results to file
    #     with open(self.log_file, "a") as file:
    #         file.write(MetashapeWorkflow.sep.join(["Build Model", time_taken]) + "\n")

    #     # Save the model
    #     self.doc.save()

    #     if self.cfg["buildModel"]["export_georeferenced"]:
    #         output_file = os.path.join(
    #             self.cfg["output_path"],
    #             self.run_id
    #             + "_model_georeferenced."
    #             + self.cfg["buildModel"]["export_extension"],
    #         )
    #         self.doc.chunk.exportModel(path=output_file)

    #     if self.cfg["buildModel"]["export_local"]:
    #         # Wipe the CRS and transform so it aligns with the cameras
    #         # The approach was recommended here: https://www.agisoft.com/forum/index.php?topic=8210.0
    #         old_crs = self.doc.chunk.crs
    #         old_transform_matrix = self.doc.chunk.transform.matrix
    #         # Wipe the transform
    #         self.doc.chunk.crs = None
    #         self.doc.chunk.transform.matrix = None

    #         # Export the transform
    #         if self.cfg["buildModel"]["export_transform"]:
    #             output_file = os.path.join(
    #                 self.cfg["output_path"],
    #                 self.run_id + "_local_model_transform.csv",
    #             )

    #             with open(output_file, "w") as fileh:
    #                 # This is a row-major representation
    #                 transform_tuple = tuple(old_transform_matrix)
    #                 # Write each row in the the transform
    #                 for i in range(4):
    #                     fileh.write(
    #                         ", ".join(str(transform_tuple[i * 4 : (i + 1) * 4]))
    #                     )

    #         # Export the model
    #         output_file = os.path.join(
    #             self.cfg["output_path"],
    #             self.run_id
    #             + "_model_local."
    #             + self.cfg["buildModel"]["export_extension"],
    #         )
    #         self.doc.chunk.exportModel(path=output_file)

    #         # Reset CRS and transform
    #         self.doc.chunk.crs = old_crs
    #         self.doc.chunk.transform.matrix = old_transform_matrix

    #         self.doc.open(self.doc.path)

    #     return True

    def build_dem_orthomosaic(self):
        """
        Build end export DEM
        """

        # # classify ground points if specified
        # if self.cfg["buildDem"]["classify_ground_points"]:
        #     self.classify_ground_points()

        if self.cfg["buildDem"]["enabled"]:
            # prepping params for buildDem
            projection = Metashape.OrthoProjection()
            projection.crs = Metashape.CoordinateSystem(self.cfg["project_crs"])

            # prepping params for export
            compression = Metashape.ImageCompression()
            compression.tiff_big = self.cfg["buildDem"]["tiff_big"]
            compression.tiff_tiled = self.cfg["buildDem"]["tiff_tiled"]
            compression.tiff_overviews = self.cfg["buildDem"]["tiff_overviews"]
            compression.tiff_compression = Metashape.ImageCompression.TiffCompressionDeflate

            start_time = time.time()

            # call without point classes argument (Metashape then defaults to all classes)
            self.doc.chunk.buildDem(
                source_data=Metashape.PointCloudData,
                subdivide_task=self.cfg["subdivide_task"],
                projection=projection,
                resolution=self.cfg["buildDem"]["resolution"],
                replace_asset=True,
            )

            time_taken = diff_time(time.time(), start_time)

            self.doc.chunk.elevation.label = "DSM"

            # record results to file
            with open(self.log_file, "a") as file:
                file.write(
                    MetashapeWorkflowLefolab.sep.join(["Build DSM", time_taken])
                    + "\n"
                )

            output_file = os.path.join(
                self.cfg["output_path"], self.run_id + "_dsm.tif"
            )
            if self.cfg["buildDem"]["export"] and self.cfg["quick_process"]:
                self.doc.chunk.exportRaster(
                    path=output_file,
                    projection=projection,
                    nodata_value=self.cfg["buildDem"]["nodata"],
                    source_data=Metashape.ElevationData,
                    image_compression=compression,
                )

            # if "DTM-ptcloud" in self.cfg["buildDem"]["surface"]:

            #     start_time = time.time()

            #     # call with point classes argument to specify ground points only
            #     self.doc.chunk.buildDem(
            #         source_data=Metashape.PointCloudData,
            #         classes=Metashape.PointClass.Ground,
            #         subdivide_task=self.cfg["subdivide_task"],
            #         projection=projection,
            #         resolution=self.cfg["buildDem"]["resolution"],
            #     )

            #     time_taken = diff_time(time.time(), start_time)

            #     self.doc.chunk.elevation.label = "DTM-ptcloud"

            #     # record results to file
            #     with open(self.log_file, "a") as file:
            #         file.write(
            #             MetashapeWorkflowLefolab.sep.join(["Build DTM-ptcloud", time_taken])
            #             + "\n"
            #         )

            #     output_file = os.path.join(
            #         self.cfg["output_path"], self.run_id + "_dtm-ptcloud.tif"
            #     )
            #     if self.cfg["buildDem"]["export"]:
            #         self.doc.chunk.exportRaster(
            #             path=output_file,
            #             projection=projection,
            #             nodata_value=self.cfg["buildDem"]["nodata"],
            #             source_data=Metashape.ElevationData,
            #             image_compression=compression,
            #         )

            # if "DSM-mesh" in self.cfg["buildDem"]["surface"]:

            #     start_time = time.time()

            #     self.doc.chunk.buildDem(
            #         source_data=Metashape.ModelData,
            #         subdivide_task=self.cfg["subdivide_task"],
            #         projection=projection,
            #         resolution=self.cfg["buildDem"]["resolution"],
            #     )

            #     time_taken = diff_time(time.time(), start_time)

            #     self.doc.chunk.elevation.label = "DSM-mesh"

            #     # record results to file
            #     with open(self.log_file, "a") as file:
            #         file.write(
            #             MetashapeWorkflowLefolab.sep.join(["Build DSM-mesh", time_taken])
            #             + "\n"
            #         )

            #     output_file = os.path.join(
            #         self.cfg["output_path"], self.run_id + "_dsm-mesh.tif"
            #     )
            #     if self.cfg["buildDem"]["export"]:
            #         self.doc.chunk.exportRaster(
            #             path=output_file,
            #             projection=projection,
            #             nodata_value=self.cfg["buildDem"]["nodata"],
            #             source_data=Metashape.ElevationData,
            #             image_compression=compression,
            #         )

        # Each DEM has a label associated with it which is used to identify and activate the correct DEM for orthomosaic generation
        if self.cfg["buildOrthomosaic"]["enabled"]:
            # We need to activate the appropriate DEM based on the DEM labels assigned when the DEMs were generated
            dem_found = False
            # Iterate through all the available DEMs
            for elevation in self.doc.chunk.elevations:
                if elevation.label == "DSM":
                    self.doc.chunk.elevation = elevation
                    dem_found = True
                    break

            if not dem_found:
                raise ValueError(
                    f"Error: DSM is not available.\n"
                    "Ensure the DSM has been generated because it is needed for orthomosaic generation."
                )

            self.build_export_orthomosaic()

        if self.cfg["buildPointCloud"]["remove_after_export"]:
            self.doc.chunk.remove(self.doc.chunk.point_clouds)

        self.doc.save()

        return True

    def build_export_orthomosaic(self):
        """
        Helper function called by build_dem_orthomosaic. build_export_orthomosaic builds and exports an ortho based on the current elevation data.
        build_dem_orthomosaic sets the current elevation data and calls build_export_orthomosaic (one or more times depending on how many orthomosaics requested)

        Note that we have tried using the 'resolution' parameter of buildOrthomosaic, but it does not have any effect. An orthomosaic built onto a DSM always has a reslution of 1/4 the DSM, and one built onto the mesh has a resolution of ~the GSD.
        """

        # get a beginning time stamp for the next step
        timer6a = time.time()

        # prepping params for buildDem
        projection = Metashape.OrthoProjection()
        projection.crs = Metashape.CoordinateSystem(self.cfg["project_crs"])

        self.doc.chunk.buildOrthomosaic(
            surface_data=Metashape.ElevationData,
            blending_mode=self.cfg["buildOrthomosaic"]["blending"],
            fill_holes=self.cfg["buildOrthomosaic"]["fill_holes"],
            refine_seamlines=self.cfg["buildOrthomosaic"]["refine_seamlines"],
            subdivide_task=self.cfg["subdivide_task"],
            projection=projection,
            replace_asset=True,
        )

        # get an ending time stamp for the previous step
        timer6b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time6 = diff_time(timer6b, timer6a)

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(MetashapeWorkflowLefolab.sep.join(["Build Orthomosaic", time6]) + "\n")

        self.doc.save()

        ## Export orthomosaic
        if self.cfg["buildOrthomosaic"]["export"]:
            output_file = os.path.join(
                self.cfg["output_path"], self.run_id + "_rgb" + ".tif"
            )

            compression = Metashape.ImageCompression()
            compression.tiff_big = self.cfg["buildOrthomosaic"]["tiff_big"]
            compression.tiff_tiled = self.cfg["buildOrthomosaic"]["tiff_tiled"]
            compression.tiff_overviews = self.cfg["buildOrthomosaic"]["tiff_overviews"]
            compression.tiff_compression = Metashape.ImageCompression.TiffCompressionDeflate

            projection = Metashape.OrthoProjection()
            projection.crs = Metashape.CoordinateSystem(self.cfg["project_crs"])

            self.doc.chunk.exportRaster(
                path=output_file,
                projection=projection,
                nodata_value=self.cfg["buildOrthomosaic"]["nodata"],
                source_data=Metashape.OrthomosaicData,
                image_compression=compression,
            )

        if self.cfg["buildOrthomosaic"]["remove_after_export"]:
            self.doc.chunk.remove(self.doc.chunk.orthomosaics)

        return True

    def build_depth_maps_highdis(self):
        ### Build depth maps

        # get a beginning time stamp for the next step
        timer2a = time.time()

        # build depth maps only instead of also building the point cloud ##?? what does
        self.doc.chunk.buildDepthMaps(
            downscale=self.cfg["buildDepthMapsHighDis"]["downscale"],
            filter_mode=self.cfg["buildDepthMapsHighDis"]["filter_mode"],
            reuse_depth=self.cfg["buildDepthMapsHighDis"]["reuse_depth"],
            max_neighbors=self.cfg["buildDepthMapsHighDis"]["max_neighbors"],
            subdivide_task=self.cfg["subdivide_task"],
        )

        # get an ending time stamp for the previous step
        timer2b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time2 = diff_time(timer2b, timer2a)

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(MetashapeWorkflowLefolab.sep.join(["Build Depth Maps", time2]) + "\n")

        self.doc.save()

    def build_point_cloud_highdis(self):
        """
        Build point cloud
        """

        ### Build point cloud

        # get a beginning time stamp for the next step
        timer3a = time.time()

        # build point cloud
        self.doc.chunk.buildPointCloud(
            max_neighbors=self.cfg["buildPointCloudHighDis"]["max_neighbors"],
            keep_depth=self.cfg["buildPointCloudHighDis"]["keep_depth"],
            subdivide_task=self.cfg["subdivide_task"],
            point_colors=True,
            replace_asset=True,
        )

        # get an ending time stamp for the previous step
        timer3b = time.time()

        # calculate difference between end and start time to 1 decimal place
        time3 = diff_time(timer3b, timer3a)

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(MetashapeWorkflowLefolab.sep.join(["Build Point Cloud", time3]) + "\n")

        self.doc.save()

        # # classify ground points if specified
        # if self.cfg["buildPointCloudHighDis"]["classify_ground_points"]:
        #     self.classify_ground_points()

        ### Export points

        if self.cfg["buildPointCloudHighDis"]["export"]:

            output_file = os.path.join(
                self.cfg["output_path"], self.run_id + "_pg.copc.laz"
            )

            if self.cfg["buildPointCloudHighDis"]["classes"] == "ALL":
                # call without classes argument (Metashape then defaults to all classes)
                self.doc.chunk.exportPointCloud(
                    path=output_file,
                    source_data=Metashape.PointCloudData,
                    format=Metashape.PointCloudFormatCOPC,
                    crs=Metashape.CoordinateSystem(self.cfg["project_crs"]),
                    subdivide_task=self.cfg["subdivide_task"],
                )
            else:
                # call with classes argument
                self.doc.chunk.exportPointCloud(
                    path=output_file,
                    source_data=Metashape.PointCloudData,
                    format=Metashape.PointCloudFormatCOPC,
                    crs=Metashape.CoordinateSystem(self.cfg["project_crs"]),
                    clases=self.cfg["buildPointCloudHighDis"]["classes"],
                    subdivide_task=self.cfg["subdivide_task"],
                )

        return True
    
    def build_dem_highdis(self):
        """
        Build end export DEM
        """

        # prepping params for buildDem
        projection = Metashape.OrthoProjection()
        projection.crs = Metashape.CoordinateSystem(self.cfg["project_crs"])

        # prepping params for export
        compression = Metashape.ImageCompression()
        compression.tiff_big = self.cfg["buildDemHighDis"]["tiff_big"]
        compression.tiff_tiled = self.cfg["buildDemHighDis"]["tiff_tiled"]
        compression.tiff_overviews = self.cfg["buildDemHighDis"]["tiff_overviews"]
        compression.tiff_compression = Metashape.ImageCompression.TiffCompressionDeflate

        start_time = time.time()

        # call without point classes argument (Metashape then defaults to all classes)
        self.doc.chunk.buildDem(
            source_data=Metashape.PointCloudData,
            subdivide_task=self.cfg["subdivide_task"],
            projection=projection,
            resolution=self.cfg["buildDemHighDis"]["resolution"],
            replace_asset=True,
        )

        time_taken = diff_time(time.time(), start_time)

        self.doc.chunk.elevation.label = "DSM-highdis"

        # record results to file
        with open(self.log_file, "a") as file:
            file.write(
                MetashapeWorkflowLefolab.sep.join(["Build DSM - HighDis", time_taken])
                + "\n"
            )

        output_file = os.path.join(
            self.cfg["output_path"], self.run_id + "_dsm.tif"
        )
        if self.cfg["buildDemHighDis"]["export"]:
            self.doc.chunk.exportRaster(
                path=output_file,
                projection=projection,
                nodata_value=self.cfg["buildDemHighDis"]["nodata"],
                source_data=Metashape.ElevationData,
                image_compression=compression,
            )

            # if "DTM-ptcloud" in self.cfg["buildDemHighDis"]["surface"]:

            #     start_time = time.time()

            #     # call with point classes argument to specify ground points only
            #     self.doc.chunk.buildDem(
            #         source_data=Metashape.PointCloudData,
            #         classes=Metashape.PointClass.Ground,
            #         subdivide_task=self.cfg["subdivide_task"],
            #         projection=projection,
            #         resolution=self.cfg["buildDem"]["resolution"],
            #     )

            #     time_taken = diff_time(time.time(), start_time)

            #     self.doc.chunk.elevation.label = "DTM-ptcloud"

            #     # record results to file
            #     with open(self.log_file, "a") as file:
            #         file.write(
            #             MetashapeWorkflowLefolab.sep.join(["Build DTM-ptcloud", time_taken])
            #             + "\n"
            #         )

            #     output_file = os.path.join(
            #         self.cfg["output_path"], self.run_id + "_dtm-ptcloud.tif"
            #     )
            #     if self.cfg["buildDem"]["export"]:
            #         self.doc.chunk.exportRaster(
            #             path=output_file,
            #             projection=projection,
            #             nodata_value=self.cfg["buildDem"]["nodata"],
            #             source_data=Metashape.ElevationData,
            #             image_compression=compression,
            #         )

            # if "DSM-mesh" in self.cfg["buildDem"]["surface"]:

            #     start_time = time.time()

            #     self.doc.chunk.buildDem(
            #         source_data=Metashape.ModelData,
            #         subdivide_task=self.cfg["subdivide_task"],
            #         projection=projection,
            #         resolution=self.cfg["buildDem"]["resolution"],
            #     )

            #     time_taken = diff_time(time.time(), start_time)

            #     self.doc.chunk.elevation.label = "DSM-mesh"

            #     # record results to file
            #     with open(self.log_file, "a") as file:
            #         file.write(
            #             MetashapeWorkflowLefolab.sep.join(["Build DSM-mesh", time_taken])
            #             + "\n"
            #         )

            #     output_file = os.path.join(
            #         self.cfg["output_path"], self.run_id + "_dsm-mesh.tif"
            #     )
            #     if self.cfg["buildDem"]["export"]:
            #         self.doc.chunk.exportRaster(
            #             path=output_file,
            #             projection=projection,
            #             nodata_value=self.cfg["buildDem"]["nodata"],
            #             source_data=Metashape.ElevationData,
            #             image_compression=compression,
            #         )

        # # Each DEM has a label associated with it which is used to identify and activate the correct DEM for orthomosaic generation
        # if self.cfg["buildOrthomosaicHighDis"]["enabled"]:
        #     # Iterate through each specified surface in the configuration
        #     for surface in self.cfg["buildOrthomosaicHighDis"]["surface"]:
        #         if surface == "Mesh":
        #             # If the surface type is "Mesh", we do not need to activate an elevation model so we can go straight to building the orthomosaic
        #             self.build_export_orthomosaic_higdis(from_mesh=True, file_ending="mesh")
        #         else:
        #             # Otherwise, we need to activate the appropriate DEM based on the DEM labels assigned when the DEMs were generated
        #             dem_found = False
        #             # Iterate through all the available DEMs
        #             for elevation in self.doc.chunk.elevations:
        #                 if elevation.label == surface:
        #                     # If the DEM label matches the surface, activate the appropriate DEM
        #                     self.doc.chunk.elevation = elevation
        #                     dem_found = True
        #                     break

        #             if not dem_found:
        #                 raise ValueError(
        #                     f"Error: DEM for {surface} is not available.\n"
        #                     "Ensure the DEM for the specified surface has been generated because it is needed for orthomosaic generation."
        #                 )

        #             self.build_export_orthomosaic_higdis(file_ending=surface.lower())

        if self.cfg["buildPointCloudHighDis"]["remove_after_export"]:
            self.doc.chunk.remove(self.doc.chunk.point_clouds)

        self.doc.save()

        return True

    def export_report(self):
        """
        Export report
        """

        output_file = os.path.join(self.cfg["output_path"], self.run_id + "_report.pdf")

        self.doc.chunk.exportReport(path=output_file)

        return True

    def finish_run(self):
        """
        Finish run (i.e., write completed time to log)
        """

        # finish local results log and close it for the last time
        with open(self.log_file, "a") as file:
            file.write(
                MetashapeWorkflowLefolab.sep.join(["Run Completed", stamp_time()]) + "\n"
            )
            
            if hasattr(self, 'processing_start_time'):
                processing_end_time = time.time()
                total_time = diff_time(processing_end_time, self.processing_start_time)
                file.write(
                    MetashapeWorkflowLefolab.sep.join(["Total Processing Time", total_time]) + "\n"
                )

        # Write the run configuration to the log file
        with open(self.log_file, "a") as file:
            file.write("\n\n### CONFIGURATION ###\n")
            yaml.dump(self.config_file, file, default_flow_style=False, sort_keys=False)
            file.write("### END CONFIGURATION ###\n")

        # Cleanup project files if specified
        if self.cfg.get("delete_project") == True:
            project_file = os.path.join(self.cfg["project_path"], ".".join([self.run_id_with_time, "psx"]))
            project_files_dir = os.path.join(self.cfg["project_path"], ".".join([self.run_id_with_time, "files"]))
            
            del self.doc  # Close the Metashape project and remove the lock file
            
            if os.path.exists(project_file):
                os.remove(project_file)
                print(f"Deleted project file: {project_file}")
            
            # Delete the .files directory if it exists
            if os.path.exists(project_files_dir):
                shutil.rmtree(project_files_dir)
                print(f"Deleted project files directory: {project_files_dir}")
            
            # Delete the log file
            if os.path.exists(self.log_file):
                os.remove(self.log_file)
                print(f"Deleted log file: {self.log_file}")
            
            print("Project files deleted (output files preserved).")

        return True
