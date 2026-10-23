#!/bin/bash

source /opt/miniconda3/bin/activate
conda activate metashape

# List of images_paths
IMAGES_PATHS=(
"" # Add path
"" # Add path
# Add more paths here
)

# Loop through each project
for IMAGES_PATH in "${IMAGES_PATHS[@]}"; do

    echo "Processing project: $IMAGES_PATH"
    python /app/automate-metashape/main.py -i $IMAGES_PATH
done
