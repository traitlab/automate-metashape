import exifread
import glob
import os
import pandas as pd
import statistics
from datetime import datetime, timedelta

def calculate_utm_epsg(latitude, longitude):
    """Calculate the EPSG code for the UTM zone based on latitude and longitude."""
    zone = int((longitude + 180) / 6) + 1
    hemisphere = '6' if latitude >= 0 else '7'
    return f"EPSG::32{hemisphere}{zone:02d}"

def get_coordinates_from_image(image_path):
    """Get latitude and longitude from the image metadata."""
    with open(image_path, 'rb') as f:
        tags = exifread.process_file(f)
        latitude = tags.get('GPS GPSLatitude')
        latitude_ref = tags.get('GPS GPSLatitudeRef')
        longitude = tags.get('GPS GPSLongitude')
        longitude_ref = tags.get('GPS GPSLongitudeRef')
        # Convert to decimal degrees
        latitude = convert_to_decimal_degrees(latitude, latitude_ref)
        longitude = convert_to_decimal_degrees(longitude, longitude_ref)
    return latitude, longitude

def convert_to_decimal_degrees(value, ref):
    """Convert GPS coordinates to decimal degrees."""
    d, m, s = [float(x.num) / float(x.den) for x in value.values]
    decimal_degrees = d + (m / 60) + (s / 3600)
    if ref.values[0] in ['S', 'W']:
        decimal_degrees = -decimal_degrees
    return decimal_degrees

def calculate_median_coordinates(images_path):
    """Calculate the median latitude and longitude from a folder containing image files or subfolders."""
    latitudes = []
    longitudes = []

    def process_folder(folder_path):
        nonlocal latitudes, longitudes
        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff')):
                    image_path = os.path.join(root, file)
                    try:
                        latitude, longitude = get_coordinates_from_image(image_path)
                        latitudes.append(latitude)
                        longitudes.append(longitude)
                    except Exception as e:
                        print(f"Error processing {image_path}: {e}")

    if os.path.isdir(images_path):
        process_folder(images_path)
    else:
        raise ValueError(f"{images_path} is not a valid directory.")

    if not latitudes or not longitudes:
        raise ValueError("No valid coordinates found in the provided images.")

    median_latitude = statistics.median(latitudes)
    median_longitude = statistics.median(longitudes)

    return median_latitude, median_longitude

def gps2utc(gps_week, gps_seconds):
    # GPS Epoch: January 6, 1980
    gps_epoch = datetime(1980, 1, 6, 0, 0, 0)

    # Compute GPS time
    gps_time = gps_epoch + timedelta(weeks=gps_week, seconds=gps_seconds)

    # Convert to UTC by subtracting leap seconds
    leap_seconds = 18  # As of 2024; check if updated in future
    utc_time = gps_time - timedelta(seconds=leap_seconds)

    return utc_time

def get_start_end_datetime_timestamp(directory_path):
    """
    Process all Timestamp files in a directory, convert GPS time to UTC time,
    filter out invalid timestamps (-259200.000000), and return begin and end UTC times.
    """
    # Find all .MRK files in the directory recursively
    mrk_files = glob.glob(os.path.join(directory_path, "**/*.MRK"), recursive=True)
    
    if not mrk_files:
        raise ValueError(f"No .MRK files found in {directory_path}")
    
    all_utc_times = []
    
    for mrk_file in mrk_files:
        with open(mrk_file, 'r') as f:
            for line in f:
                # Skip empty lines or header lines
                line = line.strip()
                if not line or not line[0].isdigit():
                    continue
                
                # Split the line by tabs or spaces
                parts = line.split()
                
                if len(parts) < 3:
                    continue
                
                try:
                    # Extract GPS seconds of week (second field) and GPS week (third field)
                    gps_ms_str = parts[1]
                    gps_week_str = parts[2].strip('[]')  # Remove brackets if present
                    
                    gps_ms = float(gps_ms_str)
                    gps_week = int(gps_week_str)
                    
                    # Filter out invalid GPS time (-259200.000000)
                    if gps_ms == -259200.000000 or gps_ms < 0:
                        continue
                    
                    # Convert to UTC
                    utc_time = gps2utc(gps_week, gps_ms)
                    all_utc_times.append(utc_time)
                    
                except (ValueError, IndexError) as e:
                    # Skip lines that can't be parsed
                    continue
    
    if not all_utc_times:
        raise ValueError(f"No valid GPS times found in .MRK files in {directory_path}")
    
    # Sort times to get begin and end
    all_utc_times.sort()
    
    return [all_utc_times[0], all_utc_times[-1]]

def get_start_end_datetime_filename(directory_path):
    """
    Extract start and end datetime from image filenames in a directory
    using DJI filename format: DJI_YYYYMMDDHHMMSS_*_T.JPG.
    """
    import re
    
    # Find all thermal JPG files in the directory recursively
    jpg_files = glob.glob(os.path.join(directory_path, "**/*_T.JPG"), recursive=True)
    
    if not jpg_files:
        raise ValueError(f"No thermal image files (*_T.JPG) found in {directory_path}")
    
    all_datetimes = []
    
    # Pattern to match DJI_YYYYMMDDHHMMSS
    pattern = re.compile(r'DJI_(\d{14})')
    
    for jpg_file in jpg_files:
        filename = os.path.basename(jpg_file)
        match = pattern.search(filename)
        
        if match:
            datetime_str = match.group(1)
            try:
                # Parse datetime from filename (YYYYMMDDHHMMSS) as local time
                dt = datetime.strptime(datetime_str, '%Y%m%d%H%M%S')
                all_datetimes.append(dt)
            except ValueError:
                # Skip files with invalid datetime format
                continue
    
    if not all_datetimes:
        raise ValueError(f"No valid datetime found in filenames in {directory_path}")
    
    # Sort datetimes to get begin and end
    all_datetimes.sort()
    
    return [all_datetimes[0], all_datetimes[-1]]

def load_weather_data(file_path):
    # Read .dat file, skipping first metadata line, using second line as column names
    weather = pd.read_csv(file_path, skiprows=[0], sep=',', decimal='.')
    
    # Delete rows 0 and 1 (units / non-data rows)
    weather = weather.iloc[2:].reset_index(drop=True)
    
    # Convert all columns to numeric except TIMESTAMP and MetSENS_Status
    exclude_cols = ['TIMESTAMP', 'MetSENS_Status']
    for col in weather.columns:
        if col not in exclude_cols:
            weather[col] = pd.to_numeric(weather[col], errors='coerce')
    
    # Rename TIMESTAMP column
    weather = weather.rename(columns={'TIMESTAMP': 'TIMESTAMP_LOCAL'})
    
    # Convert timestamp to datetime with specified timezone
    weather['TIMESTAMP_LOCAL'] = pd.to_datetime(
        weather['TIMESTAMP_LOCAL'],
        format='%Y-%m-%d %H:%M:%S'
    )
      
    # Remove rows with NA values
    weather = weather.dropna()
    
    return weather

def extract_weather_mean(weather_data, start_datetime, end_datetime):
    """
    Extract mean weather values for a given time window.
    """
    # Validate inputs are datetime objects
    if not isinstance(start_datetime, datetime):
        raise TypeError(f"start_datetime must be a datetime object, got {type(start_datetime)}")
    if not isinstance(end_datetime, datetime):
        raise TypeError(f"end_datetime must be a datetime object, got {type(end_datetime)}")
    
    # Filter data for the time window using local timestamps
    filtered = weather_data[
        (weather_data['TIMESTAMP_LOCAL'] >= start_datetime) &
        (weather_data['TIMESTAMP_LOCAL'] <= end_datetime)
    ]
    
    if filtered.empty:
        raise ValueError(f"No data found in the specified time window: {start_datetime} to {end_datetime} (local time)")
    
    # Calculate means for numeric columns
    numeric_cols = filtered.select_dtypes(include=['number']).columns
    
    # Exclude RECORD and BattV_Avg if they exist
    exclude_cols = ['RECORD', 'BattV_Avg']
    numeric_cols = [col for col in numeric_cols if col not in exclude_cols]
    
    means = filtered[numeric_cols].mean()
    
    # Create result dictionary
    result = {
        'start_LOCAL': filtered['TIMESTAMP_LOCAL'].min(),
        'end_LOCAL': filtered['TIMESTAMP_LOCAL'].max(),
    }
    
    # Add mean values
    result.update(means.to_dict())
    
    return result
