import exifread
import os
import statistics

def calculate_utm_epsg(latitude, longitude):
    """Calculate the EPSG code for the UTM zone based on latitude and longitude."""
    zone = int((longitude + 180) / 6) + 1
    hemisphere = '6' if latitude >= 0 else '7'
    return f"EPSG:32{hemisphere}{zone:02d}"

def extract_coordinates_from_image(image_path):
    """Extract latitude and longitude from the image metadata."""
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
                        latitude, longitude = extract_coordinates_from_image(image_path)
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
