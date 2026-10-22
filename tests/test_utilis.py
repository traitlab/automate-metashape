"""Tests for the pure-Python helpers in src/utilis.py."""

from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest
from exifread.utils import Ratio

from src.utilis import (
    calculate_utm_epsg,
    convert_to_decimal_degrees,
    extract_weather_mean,
    gps2utc,
    load_weather_data,
)


@pytest.mark.parametrize(
    ("latitude", "longitude", "epsg"),
    [
        (45.56, -73.56, "EPSG::32618"),  # Montréal
        (-2.6, -60.2, "EPSG::32720"),  # Manaus area, southern hemisphere
        (9.15, -79.85, "EPSG::32617"),  # Barro Colorado Island
        (0.0, 0.0, "EPSG::32631"),  # equator counts as north
        (51.5, -180.0, "EPSG::32601"),  # first zone
    ],
)
def test_calculate_utm_epsg(latitude, longitude, epsg):
    assert calculate_utm_epsg(latitude, longitude) == epsg


def exif_tag(*values):
    """Stand-in for an exifread tag: .values holds Ratio objects or strings."""
    return SimpleNamespace(values=list(values))


def test_convert_to_decimal_degrees_north():
    value = exif_tag(Ratio(45), Ratio(33), Ratio(36))
    assert convert_to_decimal_degrees(value, exif_tag("N")) == pytest.approx(45.56)


@pytest.mark.parametrize("ref", ["S", "W"])
def test_convert_to_decimal_degrees_negative(ref):
    value = exif_tag(Ratio(73), Ratio(30), Ratio(1512, 100))
    assert convert_to_decimal_degrees(value, exif_tag(ref)) == pytest.approx(-73.5042)


def test_gps2utc():
    # GPS week 0, second 0 is the GPS epoch, minus the 18 leap seconds
    assert gps2utc(0, 0) == datetime(1980, 1, 5, 23, 59, 42)
    assert gps2utc(2400, 3600) == datetime(2026, 1, 4, 0, 59, 42)


WEATHER_FILE = """\
"TOA5","CR1000","CR1000","1234","CR1000.Std.32","CPU:prog.CR1","1234","OneMin"
"TIMESTAMP","RECORD","BattV_Avg","AirTC_Avg","RH","MetSENS_Status"
"TS","RN","Volts","Deg C","%",""
"","","Avg","Avg","Smp","Smp"
"2026-10-06 10:00:00",1,12.5,20,60,"OK"
"2026-10-06 10:01:00",2,12.5,22,70,"OK"
"2026-10-06 10:02:00",3,12.5,24,80,"OK"
"2026-10-06 10:03:00",4,12.5,NAN,90,"OK"
"""


@pytest.fixture
def weather(tmp_path):
    path = tmp_path / "CR1000_OneMin.dat"
    path.write_text(WEATHER_FILE)
    return load_weather_data(str(path))


def test_load_weather_data(weather):
    # header kept, units and aggregation rows dropped, NAN row removed
    assert len(weather) == 3
    assert pd.api.types.is_datetime64_any_dtype(weather["TIMESTAMP_LOCAL"])
    assert weather["AirTC_Avg"].tolist() == [20, 22, 24]


def test_extract_weather_mean(weather):
    means = extract_weather_mean(
        weather, datetime(2026, 10, 6, 10, 1), datetime(2026, 10, 6, 10, 2)
    )
    assert means["AirTC_Avg"] == pytest.approx(23)
    assert means["RH"] == pytest.approx(75)
    assert "RECORD" not in means
    assert "BattV_Avg" not in means
    assert means["start_LOCAL"] == pd.Timestamp("2026-10-06 10:01:00")
    assert means["end_LOCAL"] == pd.Timestamp("2026-10-06 10:02:00")


def test_extract_weather_mean_empty_window(weather):
    with pytest.raises(ValueError, match="No data found"):
        extract_weather_mean(weather, datetime(2026, 10, 7), datetime(2026, 10, 8))


def test_extract_weather_mean_requires_datetimes(weather):
    with pytest.raises(TypeError):
        extract_weather_mean(weather, "2026-10-06 10:00:00", datetime(2026, 10, 6, 11))
