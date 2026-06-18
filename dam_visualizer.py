import base64
import streamlit as st
from streamlit_option_menu import option_menu
import os
from datetime import datetime
import geemap.foliumap as geemap
import ee
import pandas as pd
import json
import io
import time
from pathlib import Path
from glob import glob as gb
import matplotlib.pyplot as plt
import joblib
import imageio
from PIL import Image, ImageDraw, ImageFont
from selenium import webdriver 
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from webdriver_manager.firefox import GeckoDriverManager
from time import sleep
import re 
from IPython.display import display
import zipfile
import xml.etree.ElementTree as ET
import tempfile
import numpy as np
import pyodbc  
from dotenv import load_dotenv as ld 
from urllib.parse import quote_plus  
import math


from IPython.core.interactiveshell import InteractiveShell
InteractiveShell.ast_node_interactivity = "all"

# Load environment variables from .env file
ld()

# Initialize Earth Engine

project_id = 'ee-replace' 
try:
    ee.Initialize(project=project_id)
except Exception as e:
    ee.Authenticate()
    ee.Initialize(project=project_id)
# try:
#     ee.Initialize()
# except:
#     ee.Authenticate()
#     ee.Initialize()

# Configuration and global Variable
GIF_PATH = "kyle_dam_changes.gif"
directory = r'C:\Users\python files'
DEFAULT_STUDY_AREA = {
    "type": "Polygon",
    "coordinates": [[
        [30.860057848885614, -20.278826349806817],
        [31.14776231665905, -20.278826349806817],
        [31.14776231665905, -20.10482605907246],
        [30.860057848885614, -20.10482605907246],
        [30.860057848885614, -20.278826349806817]
    ]]
}

# Database setup for SQL Server 

ld()  # Load .env file

# Database setup for SQL Server
def get_db_connection():
    """Create and return a SQL Server connection using environment variables."""
    try:
        server = os.getenv('SQL_SERVER')
        database = os.getenv('SQL_DATABASE')
        username = os.getenv('SQL_USERNAME')
        password = os.getenv('SQL_PASSWORD')



        if not server or not database:
            raise ValueError("Missing SQL_SERVER or SQL_DATABASE in .env file")

        # Use Windows Authentication if username/password not set
        if username and password:
            connection_string = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"UID={username};"
                f"PWD={password}"
            )
        else:
            connection_string = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database};"
                f"Trusted_Connection=yes;"
            )

        conn = pyodbc.connect(connection_string)
        return conn

    except Exception as e:
        raise ConnectionError(f"Error connecting to SQL Server: {e}")


        # Alternative approach if the above doesn't work
        try:
            conn = pyodbc.connect(connection_string)
            return conn
        except pyodbc.Error as e:
            st.error(f"First connection attempt failed: {str(e)}. Trying alternative method...")

            # Try with quoted password
            connection_string = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={server};"
                f"DATABASE={database}}}"
            )
            conn = pyodbc.connect(connection_string)
            return conn

    except Exception as e:
        st.error(f"Error connecting to SQL Server: {str(e)}")

        # Provide detailed troubleshooting information
        st.markdown("""
        ### Connection Troubleshooting Guide:
        1. Verify your SQL Server credentials in the .env file
        2. Ensure the SQL Server is running and accessible
        3. Check if the user 'myAdmin' has proper permissions
        4. Try wrapping special characters in your password with curly braces
        5. Verify the ODBC Driver 17 for SQL Server is installed
        """)

        return None

def init_db():
    """Initialize database tables if they don't exist."""
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()

        # Create tables if they don't exist
        cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='water_stats' AND xtype='U')
        CREATE TABLE water_stats (
            date NVARCHAR(50) PRIMARY KEY,
            water_area FLOAT,
            water_percentage FLOAT,
            non_water_area FLOAT,
            non_water_percentage FLOAT,
            total_area FLOAT
        )
        ''')

        cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='accuracy_metrics' AND xtype='U')
        CREATE TABLE accuracy_metrics (
            date NVARCHAR(50) PRIMARY KEY,
            overall_accuracy FLOAT,
            kappa FLOAT,
            producer_accuracy NVARCHAR(MAX),
            user_accuracy NVARCHAR(MAX),
            confusion_matrix NVARCHAR(MAX)
        )
        ''')

        cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='feature_importance' AND xtype='U')
        CREATE TABLE feature_importance (
            date NVARCHAR(50),
            feature NVARCHAR(255),
            importance FLOAT,
            PRIMARY KEY (date, feature)
        )
        ''')

        cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='classification_results' AND xtype='U')
        CREATE TABLE classification_results (
            date NVARCHAR(50) PRIMARY KEY,
            map_path NVARCHAR(MAX),
            pie_chart_path NVARCHAR(MAX),
            year INT
        )
        ''')

        cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='image_stats' AND xtype='U')
        CREATE TABLE image_stats (
            date NVARCHAR(50) PRIMARY KEY,
            total_pixels INT,
            total_area FLOAT,
            num_bands INT,
            missing_pixels INT,
            missing_area FLOAT,
            cloud_cover FLOAT
        )
        ''')

        cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='band_stats' AND xtype='U')
        CREATE TABLE band_stats (
            date NVARCHAR(50),
            band NVARCHAR(50),
            min_value FLOAT,
            max_value FLOAT,
            mean_value FLOAT,
            std_dev FLOAT,
            PRIMARY KEY (date, band)
        )
        ''')

        cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='class_stats' AND xtype='U')
        CREATE TABLE class_stats (
            date NVARCHAR(50),
            class_name NVARCHAR(255),
            class_value INT,
            pixels INT,
            area FLOAT,
            percentage FLOAT,
            PRIMARY KEY (date, class_value)
        )
        ''')

        conn.commit()
    except Exception as e:
        st.error(f"Error initializing database: {str(e)}")
    finally:
        conn.close()

# Initialize database on startup
init_db()

# Database operations
def save_water_stats(date, stats):
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        cursor.execute('''
        MERGE INTO water_stats AS target
        USING (VALUES (?, ?, ?, ?, ?, ?)) AS source (date, water_area, water_percentage, non_water_area, non_water_percentage, total_area)
        ON target.date = source.date
        WHEN MATCHED THEN
            UPDATE SET water_area = source.water_area, 
                       water_percentage = source.water_percentage,
                       non_water_area = source.non_water_area,
                       non_water_percentage = source.non_water_percentage,
                       total_area = source.total_area
        WHEN NOT MATCHED THEN
            INSERT (date, water_area, water_percentage, non_water_area, non_water_percentage, total_area)
            VALUES (source.date, source.water_area, source.water_percentage, source.non_water_area, source.non_water_percentage, source.total_area);
        ''', (date, stats['water_area_sq_m'], stats['water_percentage'],
             stats['non_water_area_sq_m'], stats['non_water_percentage'],
             stats['total_area_sq_m']))
        conn.commit()
    except Exception as e:
        st.error(f"Error saving water stats: {str(e)}")
    finally:
        conn.close()

def save_accuracy_metrics(date, metrics):
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        cursor.execute('''
        MERGE INTO accuracy_metrics AS target
        USING (VALUES (?, ?, ?, ?, ?, ?)) AS source (date, overall_accuracy, kappa, producer_accuracy, user_accuracy, confusion_matrix)
        ON target.date = source.date
        WHEN MATCHED THEN
            UPDATE SET overall_accuracy = source.overall_accuracy, 
                       kappa = source.kappa,
                       producer_accuracy = source.producer_accuracy,
                       user_accuracy = source.user_accuracy,
                       confusion_matrix = source.confusion_matrix
        WHEN NOT MATCHED THEN
            INSERT (date, overall_accuracy, kappa, producer_accuracy, user_accuracy, confusion_matrix)
            VALUES (source.date, source.overall_accuracy, source.kappa, source.producer_accuracy, source.user_accuracy, source.confusion_matrix);
        ''', (date, metrics['overall_accuracy'], metrics['kappa'],
             json.dumps(metrics['producer_accuracy']),
             json.dumps(metrics['user_accuracy']),
             json.dumps(metrics['confusion_matrix'])))
        conn.commit()
    except Exception as e:
        st.error(f"Error saving accuracy metrics: {str(e)}")
    finally:
        conn.close()

def save_feature_importance(date, features):
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        # Delete old entries for this date
        cursor.execute('DELETE FROM feature_importance WHERE date = ?', (date,))
        # Insert new ones
        for feature, importance in features:
            cursor.execute('''
            INSERT INTO feature_importance (date, feature, importance)
            VALUES (?, ?, ?)
            ''', (date, feature, importance))
        conn.commit()
    except Exception as e:
        st.error(f"Error saving feature importance: {str(e)}")
    finally:
        conn.close()

def save_classification_results(date, results, year):
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        cursor.execute('''
        MERGE INTO classification_results AS target
        USING (VALUES (?, ?, ?, ?)) AS source (date, map_path, pie_chart_path, year)
        ON target.date = source.date
        WHEN MATCHED THEN
            UPDATE SET map_path = source.map_path, 
                       pie_chart_path = source.pie_chart_path,
                       year = source.year
        WHEN NOT MATCHED THEN
            INSERT (date, map_path, pie_chart_path, year)
            VALUES (source.date, source.map_path, source.pie_chart_path, source.year);
        ''', (date, results['map_path'], results['pie_chart_path'], year))
        conn.commit()
    except Exception as e:
        st.error(f"Error saving classification results: {str(e)}")
    finally:
        conn.close()

def save_image_stats(date, stats):
    conn = get_db_connection()
    if not conn:
        return

    try:
        # Validate and clean numeric values
        def clean_value(val):
            if val is None:
                return None
            try:
                val = float(val)
                if not math.isfinite(val):  # Check for NaN or infinity
                    return None
                return round(val, 6)  # Round to 6 decimal places
            except (TypeError, ValueError):
                return None

        cleaned_stats = {
            'total_pixels': clean_value(stats.get('total_pixels')),
            'total_area_sq_m': clean_value(stats.get('total_area_sq_m')),
            'num_bands': clean_value(stats.get('num_bands')),
            'missing_pixels': clean_value(stats.get('missing_pixels')),
            'missing_pixel_area': clean_value(stats.get('missing_pixel_area')),
            'cloud_cover': clean_value(stats.get('cloud_cover'))
        }

        cursor = conn.cursor()
        cursor.execute('''
        MERGE INTO image_stats AS target
        USING (VALUES (?, ?, ?, ?, ?, ?, ?)) AS source (date, total_pixels, total_area, num_bands, missing_pixels, missing_area, cloud_cover)
        ON target.date = source.date
        WHEN MATCHED THEN
            UPDATE SET total_pixels = source.total_pixels, 
                       total_area = source.total_area,
                       num_bands = source.num_bands,
                       missing_pixels = source.missing_pixels,
                       missing_area = source.missing_area,
                       cloud_cover = source.cloud_cover
        WHEN NOT MATCHED THEN
            INSERT (date, total_pixels, total_area, num_bands, missing_pixels, missing_area, cloud_cover)
            VALUES (source.date, source.total_pixels, source.total_area, source.num_bands, source.missing_pixels, source.missing_area, source.cloud_cover);
        ''', (
            date,
            cleaned_stats['total_pixels'],
            cleaned_stats['total_area_sq_m'],
            cleaned_stats['num_bands'],
            cleaned_stats['missing_pixels'],
            cleaned_stats['missing_pixel_area'],
            cleaned_stats['cloud_cover']
        ))
        conn.commit()
    except Exception as e:
        st.error(f"Error saving image stats: {str(e)}")
        # Log the problematic values for debugging
        st.error(f"Problematic values: {stats}")
    finally:
        conn.close()

def save_band_stats(date, band_stats):
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        # Delete old entries for this date
        cursor.execute('DELETE FROM band_stats WHERE date = ?', (date,))
        # Insert new ones
        for band, stats in band_stats.items():
            cursor.execute('''
            INSERT INTO band_stats (date, band, min_value, max_value, mean_value, std_dev)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (date, band, stats['min'], stats['max'], 
                 stats['mean'], stats['std_dev']))
        conn.commit()
    except Exception as e:
        st.error(f"Error saving band stats: {str(e)}")
    finally:
        conn.close()

def save_class_stats(date, class_stats):
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        # Delete old entries for this date
        cursor.execute('DELETE FROM class_stats WHERE date = ?', (date,))
        # Insert new ones
        for class_value, stats in class_stats.items():
            cursor.execute('''
            INSERT INTO class_stats (date, class_name, class_value, pixels, area, percentage)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (date, stats['name'], class_value, 
                 stats['pixels'], stats['area'], stats['percentage']))
        conn.commit()
    except Exception as e:
        st.error(f"Error saving class stats: {str(e)}")
    finally:
        conn.close()

def get_all_results():
    """Retrieve all results with column validation."""
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        # Modified query to ensure all expected columns
        cursor.execute('''
        SELECT 
            cr.date, 
            cr.year, 
            COALESCE(ws.water_area, 0) as water_area,
            COALESCE(ws.water_percentage, 0) as water_percentage,
            COALESCE(am.overall_accuracy, 0) as accuracy,
            COALESCE(am.kappa, 0) as kappa,
            cr.map_path
        FROM classification_results cr
        LEFT JOIN water_stats ws ON cr.date = ws.date
        LEFT JOIN accuracy_metrics am ON cr.date = am.date
        ORDER BY cr.date
        ''')

        results = cursor.fetchall()

        # Convert to list of dictionaries with proper column names
        all_results = []
        for row in results:
            all_results.append({
                'date': row[0],
                'year': row[1],
                'water_area': row[2],
                'water_percentage': row[3],
                'accuracy': row[4],
                'kappa': row[5],
                'map_path': row[6]
            })

        return all_results
    except Exception as e:
        st.error(f"Error retrieving results: {str(e)}")
        return []
    finally:
        conn.close()

def get_result_by_date(date):
    """Retrieve detailed results for a specific date."""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()

        # Get water stats
        cursor.execute('SELECT * FROM water_stats WHERE date = ?', (date,))
        water_stats = cursor.fetchone()

        # Get accuracy metrics
        cursor.execute('SELECT * FROM accuracy_metrics WHERE date = ?', (date,))
        accuracy_metrics = cursor.fetchone()

        # Get feature importance
        cursor.execute('''
        SELECT feature, importance 
        FROM feature_importance 
        WHERE date = ? 
        ORDER BY importance DESC
        ''', (date,))
        feature_importance = cursor.fetchall()

        # Get classification results
        cursor.execute('SELECT * FROM classification_results WHERE date = ?', (date,))
        classification_results = cursor.fetchone()

        # Get image stats
        cursor.execute('SELECT * FROM image_stats WHERE date = ?', (date,))
        image_stats = cursor.fetchone()

        # Get band stats
        cursor.execute('SELECT * FROM band_stats WHERE date = ?', (date,))
        band_stats = cursor.fetchall()

        # Get class stats
        cursor.execute('SELECT * FROM class_stats WHERE date = ?', (date,))
        class_stats = cursor.fetchall()

        if not water_stats or not accuracy_metrics or not classification_results:
            return None

        # Format the results
        result = {
            'date': date,
            'water_stats': {
                'water_area_sq_m': water_stats[1],
                'water_percentage': water_stats[2],
                'non_water_area_sq_m': water_stats[3],
                'non_water_percentage': water_stats[4],
                'total_area_sq_m': water_stats[5]
            },
            'accuracy_stats': {
                'overall_accuracy': accuracy_metrics[1],
                'kappa': accuracy_metrics[2],
                'producer_accuracy': json.loads(accuracy_metrics[3]),
                'user_accuracy': json.loads(accuracy_metrics[4]),
                'confusion_matrix': json.loads(accuracy_metrics[5])
            },
            'feature_importance': feature_importance,
            'map_path': classification_results[1],
            'pie_chart_path': classification_results[2],
            'year': classification_results[3]
        }

        if image_stats:
            result['image_stats'] = {
                'total_pixels': image_stats[1],
                'total_area_sq_m': image_stats[2],
                'num_bands': image_stats[3],
                'missing_pixels': image_stats[4],
                'missing_pixel_area': image_stats[5],
                'cloud_cover': image_stats[6]
            }

        if band_stats:
            result['band_stats'] = {}
            for band in band_stats:
                result['band_stats'][band[1]] = {
                    'min': band[2],
                    'max': band[3],
                    'mean': band[4],
                    'std_dev': band[5]
                }

        if class_stats:
            result['class_stats'] = {}
            for cls in class_stats:
                result['class_stats'][cls[2]] = {
                    'name': cls[1],
                    'pixels': cls[3],
                    'area': cls[4],
                    'percentage': cls[5]
                }

        return result
    except Exception as e:
        st.error(f"Error retrieving result for date {date}: {str(e)}")
        return None
    finally:
        conn.close()

def date_exists_in_db(date):
    """Check if a date already exists in the database."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM water_stats WHERE date = ?', (date,))
        return cursor.fetchone() is not None
    except Exception as e:
        st.error(f"Error checking date existence: {str(e)}")
        return False
    finally:
        conn.close()

# Authentication functions
def authenticate(username, password):
    # In a real app, use proper authentication with hashed passwords
    return username == "admin" and password == "password"

def login_page():
    # Page styling
    st.markdown("""
    <style>
        .centered {
            text-align: center;
            margin: auto;
            max-width: 900px;
        }

        .main-title {
            color: #001f54;
            font-size: 42px;
            font-weight: bold;
            margin-bottom: 25px;
        }

        .login-instruction {
            margin: 25px 0;
        }

        .landing-title {
            color: #001f54;
            font-size: 40px;
            font-weight: bold;
            margin-top: 30px;
            margin-bottom: 10px;
        }

        .landing-subtitle {
            color: #4b5563;
            font-size: 22px;
            margin-bottom: 30px;
        }

        .overview-box {
            background-color: #eef7ff;
            padding: 30px;
            border-radius: 12px;
            margin: 30px auto;
            max-width: 900px;
        }

        .overview-box h3 {
            color: #001f54;
            font-size: 28px;
        }

        .overview-box p,
        .overview-box li {
            color: #001f54;
            font-size: 18px;
            line-height: 1.8;
        }
    </style>
    """, unsafe_allow_html=True)

    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False

    if 'show_landing' not in st.session_state:
        st.session_state['show_landing'] = False

    # If not authenticated, show login page
    if not st.session_state['authenticated']:

        st.markdown("""
        <div class='centered'>
            <div class='main-title'>
                AI-Powered Dam Capacity<br>
                Monitoring And Forecasting System
            </div>
        </div>
        """, unsafe_allow_html=True)

        emptyCol, imageCol, emptyCol2 = st.columns([1, 4, 1])

        with imageCol:
            try:
                st.image(
                    r'C:\Users\Kyle20031231.jpg',
                    width=700,
                    caption='',
                    use_container_width=False
                )
            except FileNotFoundError:
                st.warning("Dam image not found at specified path")

        st.title("Dam Analysis Platform - Login")

        st.markdown("""
        <div class='centered login-instruction'>
            <h3>🔒 Please log in below to access resources</h3>
        </div>
        """, unsafe_allow_html=True)

        with st.container():
            col1, col2, col3 = st.columns([1, 3, 1])

            with col2:
                with st.form("login_form"):
                    username = st.text_input("Username")
                    password = st.text_input("Password", type="password")
                    submitted = st.form_submit_button("Login")

                    if submitted:
                        if authenticate(username, password):
                            st.session_state['authenticated'] = True
                            st.session_state['show_landing'] = True
                            st.rerun()
                        else:
                            st.error("Invalid username or password")

    elif st.session_state['show_landing']:
        display_landing_page()

    else:
        main_app()


def display_landing_page():
    """Display landing page with proceed button"""

    st.markdown("""
    <div class='centered'>
        <div class='landing-title'>Welcome to the Dam Analysis Platform</div>
        <div class='landing-subtitle'>AI-Powered Dam Capacity Monitoring And Forecasting System</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("""
    <div class='overview-box'>
        <h3>Overview</h3>
        <p>This platform provides tools for:</p>
        <ul>
            <li>Dam capacity monitoring</li>
            <li>Water surface area analysis</li>
            <li>Historical trend analysis</li>
            <li>Capacity forecasting</li>
            <li>Interactive visualisations and reporting</li>
        </ul>
        <p>Please click the button below to continue.</p>
    </div>
    """, unsafe_allow_html=True)

    if st.button("Proceed to Analysis Platform", key="proceed_button", use_container_width=True):
        st.session_state['show_landing'] = False
        st.rerun()

def kml_to_geojson(kml_string):
    """Convert KML string to GeoJSON format."""
    try:
        root = ET.fromstring(kml_string)
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}

        # Find all Polygon elements in the KML
        polygons = root.findall('.//kml:Polygon', ns)
        if not polygons:
            return None

        coordinates = []
        for polygon in polygons:
            # Get coordinates from KML
            coord_elem = polygon.find('.//kml:coordinates', ns)
            if coord_elem is not None:
                coord_text = coord_elem.text.strip()
                # Parse coordinates
                coord_pairs = [c.split(',')[:2] for c in coord_text.split()]
                coordinates.append([[float(x), float(y)] for x, y in coord_pairs])

        if not coordinates:
            return None

        return {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": coordinates
                }
            }]
        }
    except Exception as e:
        st.error(f"Error parsing KML: {str(e)}")
        return None

def kmz_to_geojson(kmz_file):
    """Convert KMZ file to GeoJSON format."""
    try:
        with zipfile.ZipFile(kmz_file, 'r') as kmz:
            # Find the first KML file in the KMZ
            kml_files = [f for f in kmz.namelist() if f.endswith('.kml')]
            if not kml_files:
                return None

            with kmz.open(kml_files[0]) as kml_file:
                kml_content = kml_file.read().decode('utf-8')
                return kml_to_geojson(kml_content)
    except Exception as e:
        st.error(f"Error processing KMZ file: {str(e)}")
        return None

def validate_geojson(geojson_data):
    """Validate GeoJSON structure and convert to proper format if needed."""
    if isinstance(geojson_data, dict):
        if geojson_data.get("type") == "FeatureCollection":
            # Ensure it has features array with at least one feature
            if "features" in geojson_data and len(geojson_data["features"]) > 0:
                return geojson_data
            else:
                # Create a feature collection with empty properties if features array is missing
                return {
                    "type": "FeatureCollection",
                    "features": [{
                        "type": "Feature",
                        "properties": {},
                        "geometry": geojson_data
                    }]
                }
        elif geojson_data.get("type") in ["Polygon", "MultiPolygon"]:
            # Convert geometry directly to FeatureCollection
            return {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "properties": {},
                    "geometry": geojson_data
                }]
            }
    return None

def dms_to_dd(coord_str):
    """
    Convert a coordinate string in either DMS or decimal degrees format to decimal degrees.
    Handles formats like:
    - DMS: "30°51'36.208\"N" or "20°16'43.775\"W"
    - Decimal degrees: "30.860057848885614" or "-20.278826349806817"
    """
    coord_str = coord_str.strip()
    coord_str = coord_str.replace("° ", "°")
    coord_str = ''.join([''.join([''.join([''.join([coord_str.split(".")[0], ''.join(["'",coord_str.split(".")[1][:-4]])]),''.join(['.',coord_str.split(".")[1][-4:-2]])]), '"']), coord_str.split(".")[1][-1]])
    coord_str = coord_str.replace("° ", "°")

    # Try to parse as decimal degrees first
    try:
        return float(coord_str)
    except ValueError:
        pass

    # If not decimal degrees, try to parse as DMS
    match = re.match(r"(\d+)[°](\d+)'(\d+(\.\d+)?)\"([NSEW])", coord_str)
    if not match:
        raise ValueError(f"Invalid coordinate format: {coord_str}")

    degrees, minutes, seconds, _, direction = match.groups()
    dd = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    if direction in 'SW':
        dd *= -1
    return dd

def read_coordinates(file_path):
    """
    Read coordinates from a .txt file and convert them to a DataFrame with decimal degrees.
    """
    data = []
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
        for line in lines:
            if (len(line) > 0) & (line.strip() != ""):
                lon_dms, lat_dms = line.strip().strip(",").split(',')
                lat_dd = dms_to_dd(lat_dms.strip())
                lon_dd = dms_to_dd(lon_dms.strip())
                data.append({'Longitude': lon_dd, 'Latitude': lat_dd})

    df = pd.DataFrame(data)
    return df

def training_samples(file_path):
    coords = []
    df = read_coordinates(file_path)
    for i in range(0,len(df)):
        coords.append([df['Longitude'][i],df['Latitude'][i]])
    return coords

def get_study_area_geometry(study_area):
    """Convert study area to ee.Geometry."""
    if isinstance(study_area, dict):
        if study_area.get("type") == "FeatureCollection":
            geometry = study_area["features"][0]["geometry"]
        else:
            geometry = study_area
        return ee.Geometry(geometry)
    return None

def display_gif(gif_path, speed=1.0, auto_play=True):
    try:
        with open(gif_path, "rb") as f:
            contents = f.read()

        data_url = base64.b64encode(contents).decode("utf-8")

        html = f"""
        <div style="text-align: center;">
            <img src="data:image/gif;base64,{data_url}" 
                 alt="dam changes gif" 
                 style="max-width: 100%; height: auto;"
                 {'autoplay' if auto_play else ''}
                 {'loop' if auto_play else ''}>
        </div>
        """
        st.components.v1.html(html, height=500)
    except FileNotFoundError:
        st.error("GIF file not found. Please ensure the animation has been generated.")

class LandCoverAnalysis:
    def __init__(self, year, monthMin, monthMax, cloud_cover, scale, coordinates_list_dict, study_area, directory=directory):
        self.year = year
        self.monthMin = monthMin
        self.monthMax = monthMax
        self.cloud_cover = cloud_cover
        self.scale = scale
        self.coordinates_list_dict = coordinates_list_dict
        self.study_area = study_area
        self.directory = Path(directory)
        self.Map = geemap.Map()
        self.training_data = None
        self.classified = None
        self.classifier = None
        self.vis_params = {
            'bands': ['SR_B3', 'SR_B2', 'SR_B1'],
            'min': 0,
            'max': 3000,
            'gamma': 1.2
        }
        self.classVisParams = {
            'min': 0,
            'max': 1,
            'palette': ['#25523B', 'blue']  # ['Non Water', 'Water']
        }
        self.legend_colors = [(37, 82, 59), (0, 0, 255)]
        self.legend_labels = ['Non Water', 'Water']
        self.bands = ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'ST_B6', 'SR_B7', 'NDWI']

    def add_ndwi(self, image):
        """Calculate NDWI based on Landsat sensor type."""
        if self.year < 1999:  # Landsat 5 (TM): Green = SR_B2, NIR = SR_B4
            ndwi = image.normalizedDifference(['SR_B2', 'SR_B4']).rename('NDWI')
        else:  # Landsat 7 (ETM+): Green = SR_B3, NIR = SR_B4
            ndwi = image.normalizedDifference(['SR_B3', 'SR_B4']).rename('NDWI')
        return image.addBands(ndwi)

    def calculate_dynamic_threshold(self, ndwi_band):
        """Calculate dynamic threshold based on NDWI statistics with enhanced logic."""
        # Get comprehensive statistics including mean and std dev
        stats = ndwi_band.reduceRegion(
            reducer=ee.Reducer.minMax().combine(
                reducer2=ee.Reducer.mean(),
                sharedInputs=True
            ).combine(
                reducer2=ee.Reducer.stdDev(),
                sharedInputs=True
            ),
            geometry=self.study_area,
            scale=self.scale,
            maxPixels=1e9
        ).getInfo()

        min_val = stats.get('NDWI_min', -1)
        max_val = stats.get('NDWI_max', 1)
        mean_val = stats.get('NDWI_mean', 0)
        std_dev = stats.get('NDWI_stdDev', 0.1)

        st.write(f"\nNDWI Statistics:")
        st.write(f"Min: {min_val:.4f}, Max: {max_val:.4f}")
        st.write(f"Mean: {mean_val:.4f}, Std Dev: {std_dev:.4f}")

        # Enhanced threshold calculation logic
        if max_val < 0:
            # Case 1: All values negative (no visible water)
            threshold = max_val * 0.5  # Conservative threshold
            st.write("Case 1: All values negative")
        elif min_val > 0:
            # Case 2: All values positive (likely all water)
            threshold = min_val * 0.8  # More conservative than 1.5x to catch edges
            st.write("Case 2: All values positive")
        else:
            # Case 3: Mixed values (normal case)
            # Base threshold considers mean and standard deviation
            base_threshold = mean_val + (1.25 * std_dev)

            # Adjust based on distribution characteristics
            if mean_val < -0.2:
                # Very dry conditions - be more conservative
                threshold = min(base_threshold, -0.05)
                st.write("Case 3a: Very dry conditions")
            elif mean_val < -0.1:
                # Moderately dry conditions
                threshold = min(base_threshold, 0.0)
                st.write("Case 3b: Moderately dry conditions")
            else:
                # Normal or wet conditions
                threshold = max(min(base_threshold, 0.1), 0.0)
                st.write("Case 3c: Normal/wet conditions")

            # Ensure threshold stays within reasonable bounds
            threshold = max(min(threshold, max_val * 0.8), min_val * 1.2)

        # Final sanity checks
        if threshold > 0.3:
            threshold = 0.2  # Prevent unrealistically high thresholds
        elif threshold < -0.3:
            threshold = -0.1  # Prevent unrealistically low thresholds

        st.write(f"Calculated threshold: {threshold:.4f}")
        return threshold

    def add_water_mapping(self, image):
        """Map water areas using NDWI with dynamic threshold, clipped to study_area."""
        ndwi = image.select('NDWI').clip(self.study_area)  # Clip NDWI to study area

        # Calculate dynamic threshold
        threshold = self.calculate_dynamic_threshold(ndwi)
        st.write(f"Using NDWI threshold: {threshold}")

        # Classify water using threshold and clip to study area
        water_ndwi = ndwi.gt(threshold).selfMask().rename('water_ndwi').clip(self.study_area)

        # Add layer to the map
        self.Map.addLayer(water_ndwi, {'palette': 'blue'}, 'Water (NDWI)')

        return image.addBands(water_ndwi)

    def create_feature_collection(self, coordinates_list, name, k):
        features = []
        for coordinates in coordinates_list:
            point = ee.Geometry.Point(coordinates)
            feature = ee.Feature(point, {'class': k})
            features.append(feature)
        feature_collection = ee.FeatureCollection(features)
        self.Map.addLayer(feature_collection, {}, f'{name} Points')
        return feature_collection

    def prepare_training_data(self):
        feature_collections = {}
        for class_name, coordinates_list in self.coordinates_list_dict.items():
            feature_collections[class_name] = self.create_feature_collection(
                coordinates_list, f'{class_name}{self.year}', len(feature_collections))

        self.training_data = feature_collections[list(feature_collections.keys())[0]]
        for key in list(feature_collections.keys())[1:]:
            self.training_data = self.training_data.merge(feature_collections[key])

        self.Map.centerObject(self.study_area, 11)  # Zoom level adjusted for lake

    def preprocess_image(self, image):
        # Add NDWI band
        image = self.add_ndwi(image)
        image = self.add_water_mapping(image)

        # Create the composite and preprocess the image
        composite_image = image.clip(self.study_area)
        filled_image = composite_image.focal_mean(1, 'square', 'pixels', 8)
        blended_image = filled_image.blend(composite_image)

        # Extract metadata for the image
        props = image.getInfo()['properties']
        self.image_date = props.get('DATE_ACQUIRED', datetime.now().strftime('%Y-%m-%d'))

        table_data = [{
            "Satellite": props.get('SPACECRAFT_ID'),
            "Sensor": props.get('SENSOR_ID', 'ETM+'),
            "Path/Row": f"{props.get('WRS_PATH')}/{props.get('WRS_ROW')}",
            "Spatial Resolution": "30m",
            "Date of Acquisition": self.image_date,
            "Sources": "USGS Earth Explorer"
        }]

        # Convert table_data to a DataFrame for visualization
        df = pd.DataFrame(table_data)
        st.write(df)

        return blended_image, composite_image

    def get_all_images_for_year(self):
        """Get all images for the year with improved error handling."""
        try:
            if self.year < 1999:
                collection = ee.ImageCollection('LANDSAT/LT05/C02/T1_L2') \
                    .filterDate(f"{self.year}-{self.monthMin}-01", f"{self.year}-{self.monthMax}-31") \
                    .filterBounds(self.study_area) \
                    .filter(ee.Filter.lte("CLOUD_COVER", self.cloud_cover)) \
                    .select(self.bands[:-1])
            else:
                collection = ee.ImageCollection('LANDSAT/LE07/C02/T1_L2') \
                    .filterDate(f"{self.year}-{self.monthMin}-01", f"{self.year}-{self.monthMax}-31") \
                    .filterBounds(self.study_area) \
                    .filter(ee.Filter.lte("CLOUD_COVER", self.cloud_cover)) \
                    .select(self.bands[:-1])

            # Check if collection is empty
            count = collection.size().getInfo()
            if count == 0:
                st.warning(f"No images found for year {self.year} with current filters (Cloud cover ≤ {self.cloud_cover}%)")
                return None  # Return None instead of empty collection

            return collection.sort('DATE_ACQUIRED', False)
        except Exception as e:
            st.error(f"Error getting images for year {self.year}: {str(e)}")
            return None

    def apply_scale_factors(self, image):
        optical_bands = image.select("SR_B.").multiply(0.0000275).add(-0.2)
        thermal_bands = image.select("ST_B.*").multiply(0.00341802).add(149.0)
        ndwi_band = image.select('NDWI')  # Keep NDWI as is (already normalized)
        return image.addBands(optical_bands, None, True) \
                   .addBands(thermal_bands, None, True) \
                   .addBands(ndwi_band, None, True)

    def extract_training_data(self, image):
        return image.sampleRegions(
            collection=self.training_data,
            properties=['class'],
            scale=self.scale
        )

    def train_classifier(self, training):
        classifier = ee.Classifier.smileRandomForest(numberOfTrees=5, seed=42).train(
            features=training,
            classProperty='class',
            inputProperties=self.bands
        )
        joblib.dump(classifier, f'classifier_{self.year}.pkl')
        self.classifier = classifier
        return classifier

    def get_feature_importance(self, classifier):
        importance = classifier.explain().get('importance')
        importance_dict = importance.getInfo()
        sorted_importance = sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)
        st.write(sorted_importance)
        return sorted_importance

    def classify_image(self, image, rawImage, classifier):
        """Classify image and ensure results are clipped to study_area."""
        self.classified = image.classify(classifier).clip(self.study_area)
        self.rawClassified = rawImage.classify(classifier).clip(self.study_area)


    def save_classified_map(self, image_date):
        """Save the classified map with a filename based on image date using Firefox."""
        date_str = datetime.strptime(image_date, '%Y-%m-%d').strftime('%y%m%d')
        filename = f"lakeMutirikwi_{date_str}"

        # Save as HTML
        html_file = self.directory / f"{filename}.html"
        self.Map.save(str(html_file))

        # Set up Firefox options
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--window-size=1920,1080')

        # Launch Firefox browser with GeckoDriver
        driver = webdriver.Firefox(service=Service(GeckoDriverManager().install()), options=options)

        try:
            driver.get(f'file://{html_file.absolute()}')
            sleep(5)  # Wait for rendering
            png_file = self.directory / f"{filename}.png"
            driver.save_screenshot(str(png_file))
        finally:
            driver.quit()

        return str(png_file)


    def create_and_display_water_pie_chart(self, water_stats, image_date):
        """Create and display water/non-water pie chart, then save it."""
        labels = ['Non Water', 'Water']
        sizes = [
            water_stats['total_pixels'] - water_stats['water_pixels'], 
            water_stats['water_pixels']
        ]
        colors = ['#25523B', 'blue']

        fig, ax = plt.subplots(figsize=(8, 6))
        ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
        ax.axis('equal')
        plt.title(f'Water Coverage - {image_date}')

        # Save the pie chart with date-based filename
        date_str = datetime.strptime(image_date, '%Y-%m-%d').strftime('%y%m%d')
        filename = f"waterPie_{date_str}.png"
        png_file = self.directory / filename
        plt.savefig(str(png_file))
        plt.close()

        # Display in Streamlit using st.pyplot()
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
        ax.axis('equal')
        plt.title(f'Water Coverage - {image_date}')
        st.pyplot(fig)
        plt.close()

        return str(png_file)

    def plot_band_distributions(self, image):
        """Plot histograms and box plots for each band."""
        for band in image.bandNames().getInfo():
            # Get pixel values for the band
            band_values = image.select(band).reduceRegion(
                reducer=ee.Reducer.toList(),
                geometry=self.study_area,
                scale=self.scale,
                maxPixels=1e6
            ).get(band).getInfo()

            if not band_values:
                st.write(f"No data available for band {band}")
                continue

            # Create figure with two subplots
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
            fig.suptitle(f'Band {band} Distribution - {self.year}')

            # Plot histogram
            ax1.hist(band_values, bins=50, color='blue', alpha=0.7)
            ax1.set_title('Histogram')
            ax1.set_xlabel('Pixel Value')
            ax1.set_ylabel('Frequency')

            # Plot boxplot
            ax2.boxplot(band_values, vert=True, patch_artist=True)
            ax2.set_title('Boxplot')
            ax2.set_ylabel('Pixel Value')

            plt.tight_layout()
            st.pyplot(fig)
            plt.close()

    def calculate_class_statistics(self, image):
        # Total pixel calculation and class statistics
        class_stats = self.classified.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=self.study_area,
            scale=self.scale,
            maxPixels=1e9
        ).getInfo()

        rawclass_stats = self.rawClassified.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=self.study_area,
            scale=self.scale,
            maxPixels=1e9
        ).getInfo()

        # Collect image band statistics
        band_stats = image.reduceRegion(
            reducer=ee.Reducer.minMax().combine(
                reducer2=ee.Reducer.mean(),
                sharedInputs=True
            ).combine(
                reducer2=ee.Reducer.stdDev(),
                sharedInputs=True
            ).combine(
                reducer2=ee.Reducer.count(),
                sharedInputs=True
            ),
            geometry=self.study_area,
            scale=self.scale,
            maxPixels=1e9
        ).getInfo()

        # Clean and validate numeric values
        def clean_value(val):
            if val is None:
                return 0
            try:
                val = float(val)
                return val if math.isfinite(val) else 0
            except (TypeError, ValueError):
                return 0

        total_pixels = clean_value(sum(class_stats.get('classification', {}).values()))
        missing_pixels = clean_value(total_pixels - sum(rawclass_stats.get('classification', {}).values()))
        pixel_area = self.scale * self.scale
        total_area = clean_value(total_pixels * pixel_area)
        missing_pixel_area = clean_value(missing_pixels * pixel_area)
        num_bands = clean_value(len(image.bandNames().getInfo()))

        if "CLOUD_COVER" in band_stats:
            cloud_cover = clean_value(band_stats.get("CLOUD_COVER", 0))
        else:
            cloud_cover = np.nan

        # Save image stats to database
        save_image_stats(self.image_date, {
            'total_pixels': total_pixels,
            'total_area_sq_m': total_area,
            'num_bands': num_bands,
            'missing_pixels': missing_pixels,
            'missing_pixel_area': missing_pixel_area,
            'cloud_cover': cloud_cover
        })

        # Process band stats
        band_stats_dict = {}
        for band in image.bandNames().getInfo():
            band_stats_dict[band] = {
                'min': clean_value(band_stats.get(f"{band}_min")),
                'max': clean_value(band_stats.get(f"{band}_max")),
                'mean': clean_value(band_stats.get(f"{band}_mean")),
                'std_dev': clean_value(band_stats.get(f"{band}_stdDev"))
            }

        # Save band stats to database
        save_band_stats(self.image_date, band_stats_dict)

        # Process class stats
        class_stats_dict = {}
        for class_value, pixel_count in class_stats.get('classification', {}).items():
            pixel_count = clean_value(pixel_count)
            area_sq_m = clean_value(pixel_count * pixel_area)
            percentage = clean_value((pixel_count / total_pixels) * 100) if total_pixels else 0

            class_stats_dict[class_value] = {
                'name': self.legend_labels[int(class_value)],
                'pixels': pixel_count,
                'area': area_sq_m,
                'percentage': percentage
            }

        # Save class stats to database
        save_class_stats(self.image_date, class_stats_dict)

        return {
            'total_pixels': total_pixels,
            'total_area_sq_m': total_area,
            'num_bands': num_bands,
            'missing_pixels': missing_pixels,
            'missing_pixel_area': missing_pixel_area,
            'cloud_cover': cloud_cover,
            'band_stats': band_stats_dict,
            'class_stats': class_stats_dict
        }

    def calculate_water_stats(self, image):
        """Calculate water area coverage using NDWI, strictly within study_area."""
        try:
            water_ndwi = image.select('water_ndwi').clip(self.study_area)  # Ensure clipping

            # Pixel counts for water (strictly within study_area)
            stats_ndwi = water_ndwi.reduceRegion(
                ee.Reducer.sum(),
                geometry=self.study_area,
                scale=self.scale,
                maxPixels=1e9
            ).getInfo()

            # Calculate total pixels strictly within study_area
            total_area_image = ee.Image.pixelArea() \
                .clip(self.study_area) \
                .divide(self.scale * self.scale) \
                .reduceRegion(
                    ee.Reducer.sum(),
                    geometry=self.study_area,
                    scale=self.scale,
                    maxPixels=1e9
                )

            total_pixels = total_area_image.getInfo().get('area', 0)
            pixel_area = self.scale * self.scale
            total_area = total_pixels * pixel_area

            # Get water pixels (default to 0 if None)
            ndwi_pixels = stats_ndwi.get('water_ndwi', 0) or 0
            ndwi_area = ndwi_pixels * pixel_area
            non_water_pixels = total_pixels - ndwi_pixels
            non_water_area = non_water_pixels * pixel_area

            # Calculate percentages
            ndwi_percent = (ndwi_pixels / total_pixels) * 100 if total_pixels else 0
            non_water_percent = 100 - ndwi_percent

            st.write("\nWater Coverage Statistics (Study Area Only):")
            st.write(f"Water Pixels: {ndwi_pixels}")
            st.write(f"Water Area: {ndwi_area} sq m")
            st.write(f"Water Percentage: {ndwi_percent:.2f}%")
            st.write(f"Non-Water Pixels: {non_water_pixels}")
            st.write(f"Non-Water Area: {non_water_area} sq m")
            st.write(f"Non-Water Percentage: {non_water_percent:.2f}%")
            st.write(f"Total Study Area: {total_area} sq m")

            # Create and save water pie chart
            pie_chart_path = self.create_and_display_water_pie_chart({
                'water_pixels': ndwi_pixels,
                'total_pixels': total_pixels
            }, self.image_date)
            st.write(f"Saved water pie chart to: {pie_chart_path}")

            # Save water stats to database
            water_stats = {
                'water_area_sq_m': ndwi_area,
                'water_percentage': ndwi_percent,
                'non_water_area_sq_m': non_water_area,
                'non_water_percentage': non_water_percent,
                'total_area_sq_m': total_area
            }
            save_water_stats(self.image_date, water_stats)

            return {
                'water_pixels': ndwi_pixels,
                'water_area_sq_m': ndwi_area,
                'water_percentage': ndwi_percent,
                'non_water_pixels': non_water_pixels,
                'non_water_area_sq_m': non_water_area,
                'non_water_percentage': non_water_percent,
                'total_pixels': total_pixels,
                'total_area_sq_m': total_area,
                'pie_chart_path': pie_chart_path
            }

        except Exception as e:
            st.error(f"Error calculating water stats: {e}")
            return {
                'water_pixels': 0,
                'water_area_sq_m': 0,
                'water_percentage': 0,
                'non_water_pixels': 0,
                'non_water_area_sq_m': 0,
                'non_water_percentage': 0,
                'total_pixels': 0,
                'total_area_sq_m': 0,
                'pie_chart_path': None
            }

    def perform_accuracy_assessment(self, image, classifier):
        validation = image.sampleRegions(
            collection=self.training_data,
            properties=['class'],
            scale=self.scale,
            geometries=True
        )
        validated = validation.classify(classifier)
        errorMatrix = validated.errorMatrix('class', 'classification')

        accuracy = errorMatrix.accuracy().getInfo()
        producer_acc = errorMatrix.producersAccuracy().getInfo()
        user_acc = errorMatrix.consumersAccuracy().getInfo()
        kappa = errorMatrix.kappa().getInfo()
        confusion_matrix = errorMatrix.array().getInfo()

        st.write('\nAccuracy Assessment:')
        st.write(f'Overall Accuracy: {accuracy:.2%}')
        st.write(f'Kappa Coefficient: {kappa:.2f}')

        # Fixed the producer/user accuracy printing
        st.write('Producer Accuracy (User Accuracy): ', producer_acc)
        st.write('Consumer Accuracy (Producer Accuracy): ', user_acc)

        st.write('\nConfusion Matrix:')
        st.write("Rows = Reference, Columns = Classified")
        st.write(pd.DataFrame(confusion_matrix, 
                          index=self.legend_labels, 
                          columns=self.legend_labels))

        accuracy_stats = {
            'overall_accuracy': accuracy,
            'producer_accuracy': dict(zip(self.legend_labels, producer_acc)),
            'user_accuracy': dict(zip(self.legend_labels, user_acc)),
            'kappa': kappa,
            'confusion_matrix': confusion_matrix
        }

        # Save accuracy metrics to database
        save_accuracy_metrics(self.image_date, accuracy_stats)

        return accuracy_stats

    def run(self, force_reprocess=False):
        try:
            # Prepare training data (once for all images)
            self.Map = geemap.Map()
            self.Map.centerObject(self.study_area, 11)
            self.prepare_training_data()

            # Get all images for the year
            image_collection = self.get_all_images_for_year()

            # Skip year if no images found
            if image_collection is None:
                return []  # Return empty list for this year

            image_list = image_collection.toList(image_collection.size())
            num_images = image_list.size().getInfo()

            # Check if collection is empty
            if num_images == 0:
                st.warning(f"No images found for year {self.year} with the current filters")
                return []

            all_results = []

            for i in range(num_images):
                try:
                    # Get the image and its date first
                    image = ee.Image(image_list.get(i))
                    props = image.getInfo()['properties']
                    image_date = props.get('DATE_ACQUIRED', datetime.now().strftime('%Y-%m-%d'))

                    # Skip if this date already exists in the database and we're not forcing reprocess
                    if not force_reprocess and date_exists_in_db(image_date):
                        st.write(f"Skipping image {i+1} of {num_images} for {self.year} (date {image_date} already processed)")
                        continue

                    st.write(f"\nProcessing image {i+1} of {num_images} for {self.year} (date {image_date})")
                    if force_reprocess and date_exists_in_db(image_date):
                        st.warning("Force reprocessing - overwriting existing data for this date")

                    # Create new map for each image
                    current_map = geemap.Map()
                    current_map.centerObject(self.study_area, 11)
                    self.Map = current_map  # Set as instance map

                    # Preprocess the image
                    blended_image, composite_image = self.preprocess_image(image)

                    # Apply scale factors
                    scaled_image = self.apply_scale_factors(blended_image)
                    scaled_raw_image = self.apply_scale_factors(composite_image)

                    # Extract training data
                    training = self.extract_training_data(scaled_image)

                    # Train classifier
                    classifier = self.train_classifier(training)

                    # Get feature importance
                    feature_importance = self.get_feature_importance(classifier)
                    save_feature_importance(image_date, feature_importance)

                    # Classify image
                    self.classify_image(scaled_image, scaled_raw_image, classifier)

                    # Calculate statistics
                    image_stats_summary = self.calculate_class_statistics(blended_image)

                    # Calculate water statistics
                    water_stats = self.calculate_water_stats(scaled_image)

                    # Perform accuracy assessment
                    accuracy_stats = self.perform_accuracy_assessment(scaled_image, classifier)

                    # Display the current map with only the two layers we want
                    display(current_map)

                    # Save the classified map with date-based filename
                    map_path = self.save_classified_map(image_date)
                    st.write(f"Saved classified map to: {map_path}")

                    # Save classification results to database
                    save_classification_results(
                        image_date, 
                        {
                            'map_path': map_path,
                            'pie_chart_path': water_stats['pie_chart_path']
                        },
                        self.year
                    )

                    # Collect results
                    all_results.append({
                        'image_date': image_date,
                        'year': self.year,
                        'water_stats': water_stats,
                        'accuracy_stats': accuracy_stats,
                        'feature_importance': feature_importance,
                        'map_path': map_path
                    })

                except Exception as e:
                    st.error(f"Error processing image {i+1}: {str(e)}")
                    continue

            return all_results

        except Exception as e:
            st.error(f"Fatal error in run(): {str(e)}")
            return []

# Main app function
def main_app():
    # Initialize session state variables if they don't exist
    if 'current_config' not in st.session_state:
        st.session_state.current_config = None

    if 'classification_results' not in st.session_state:
        st.session_state.classification_results = None

    if 'last_run_time' not in st.session_state:
        st.session_state.last_run_time = None

    # When storing results:
    st.session_state.last_run_time = datetime.now()

    # When displaying:
    if st.session_state.last_run_time:
        st.caption(f"Last run: {st.session_state.last_run_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Sidebar settings
    with st.sidebar:
        st.title("Settings")

        # Add the force reprocess checkbox
        force_reprocess = st.checkbox("Force Reprocess All Images", False,
                                    help="Check this to reprocess all images, even if they've been processed before")

        # Study area selection
        study_area_option = st.radio(
            "Select Study Area",
            ["Use Default", "Draw on Map", "Upload GeoJSON/KML/KMZ"]
        )

        study_area = None

        if study_area_option == "Use Default":
            study_area = DEFAULT_STUDY_AREA
            st.info("Using default Kyle Dam study area")
        elif study_area_option == "Upload GeoJSON/KML/KMZ":
            uploaded_file = st.file_uploader("Upload GeoJSON/KML/KMZ", type=['geojson', 'json', 'kml', 'kmz'])
            if uploaded_file:
                try:
                    file_ext = uploaded_file.name.split('.')[-1].lower()
                    if file_ext in ['kml', 'kmz']:
                        if file_ext == 'kml':
                            kml_content = uploaded_file.read().decode('utf-8')
                            study_area = kml_to_geojson(kml_content)
                        else:  # KMZ
                            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                                tmp.write(uploaded_file.read())
                                tmp_path = tmp.name
                            study_area = kmz_to_geojson(tmp_path)
                            os.unlink(tmp_path)
                    else:  # GeoJSON
                        study_area = json.load(uploaded_file)

                    validated = validate_geojson(study_area)
                    if validated:
                        study_area = validated
                        st.success("File successfully loaded!")
                    else:
                        st.error("Invalid file format")
                        study_area = None
                except Exception as e:
                    st.error(f"Error loading file: {str(e)}")
                    study_area = None

        # Year selection
        year_options = list(range(1984, 2024))
        selected_years = st.multiselect(
            "Select Years for Classification",
            year_options,
            default=[2020]
        )

        # Cloud cover threshold
        cloud_cover = st.slider(
            "Max Cloud Cover Percentage",
            0, 100, 10
        )

        # Run button
        run_classification = st.button("Run Classification")

    # Main content
    st.title("Dam Surface Area Analysis Platform")

    # Tab navigation
    tabs = option_menu(
        None, ["Visualization", "Water Classification"],
        icons=['image', 'gear'],
        menu_icon="cast", default_index=0, orientation="horizontal"
    )

    if tabs == "Visualization":
        visualization_tab()
    else:
        classification_tab(study_area, selected_years, cloud_cover, run_classification, study_area_option, force_reprocess)

def visualization_tab():
    st.header("Historical Dam Surface Area Changes")

    # GIF display with controls
    st.markdown("""
    ### Animation of Dam Changes (1984-2023)
    The animation shows yearly changes in the dam's surface area.
    """)

    # Playback controls
    col1, col2 = st.columns(2)
    with col1:
        playback_speed = st.slider("Playback Speed", 0.5, 2.0, 1.0, 0.1)
    with col2:
        auto_play = st.checkbox("Auto-play", value=True)

    # Display the GIF
    display_gif(GIF_PATH, speed=playback_speed, auto_play=auto_play)

    # Statistics section
    st.subheader("Dam Statistics")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Years Covered", "40 years (1984-2023)")
    with col2:
        st.metric("Images Processed", "40 high-res images")

def classification_tab(study_area, selected_years, cloud_cover, run_classification, study_area_option, force_reprocess):
    st.header("Water Body Classification")

    # Initialize map
    m = geemap.Map()

    # Get results from database at the start
    db_results = get_all_results()

    # Handle study area display
    if study_area_option == "Draw on Map":
        st.info("Draw your study area on the map below")
        # Add drawing tools using the newer method
        try:
            # Try the most common method first
            m.add_layer_control()
        except AttributeError:
            try:
                # Fallback to older method
                m.add_draw_control()
            except AttributeError:
                st.warning("Drawing tools not available in this geemap version")

        # Check for drawn features
        if hasattr(m, 'draw_features') and m.draw_features:
            st.session_state.last_active_drawing = m.draw_features[-1]
            if st.session_state.last_active_drawing:
                # Ensure drawn feature has properties
                if 'properties' not in st.session_state.last_active_drawing:
                    st.session_state.last_active_drawing['properties'] = {}
                study_area = {
                    "type": "FeatureCollection",
                    "features": [st.session_state.last_active_drawing]
                }
                try:
                    m.add_geojson(study_area, layer_name="Drawn Study Area")
                except Exception as e:
                    st.error(f"Error adding drawn study area: {str(e)}")
    elif study_area:
        # Validate and normalize the study area GeoJSON
        validated_study_area = validate_geojson(study_area)
        if validated_study_area:
            try:
                # Add predefined study area to map
                m.add_geojson(validated_study_area, layer_name="Study Area")
                # Center map on study area
                study_geom = get_study_area_geometry(validated_study_area)
                if study_geom:
                    m.centerObject(study_geom, 11)
            except Exception as e:
                st.error(f"Error adding study area to map: {str(e)}")
        else:
            st.warning("Invalid study area format")

    # Display map
    m.to_streamlit(height=500)

    # Check if we need to run classification
    current_config = {
        'study_area': study_area,
        'selected_years': selected_years,
        'cloud_cover': cloud_cover,
        'study_area_option': study_area_option
    }

    config_changed = (
        st.session_state.current_config is None or
        current_config != st.session_state.current_config
    )

    # If not forcing reprocess and we have results, show them
    if not force_reprocess and db_results and not config_changed:
        st.info("Showing previously calculated results from database. Check 'Force Reprocess' to re-run analysis.")
        display_summary_results(db_results)

        # Create tabs for each year's detailed results
        year_tabs = st.tabs([f"Year {res['year']}" for res in db_results])

        for i, result in enumerate(db_results):
            with year_tabs[i]:
                detailed_result = get_result_by_date(result['date'])
                if detailed_result:
                    display_detailed_results(detailed_result)

        if st.button("Clear Results and Re-run"):
            st.session_state.classification_results = None
            st.session_state.current_config = None
            st.rerun()
        return

    # Rest of the function remains the same...
    # Run classification if needed
    if run_classification or (config_changed and (force_reprocess or not db_results)):
        # Update the current config
        st.session_state.current_config = current_config

        if not study_area and study_area_option != "Draw on Map":
            st.warning("Please select or draw a study area first")
            return

        if not selected_years:
            st.warning("Please select at least one year")
            return

        # Get the final study area geometry
        if study_area_option == "Draw on Map" and 'last_active_drawing' in st.session_state:
            study_geom = ee.Geometry(st.session_state.last_active_drawing['geometry'])
        elif study_area:
            study_geom = get_study_area_geometry(study_area)
        else:
            study_geom = ee.Geometry(DEFAULT_STUDY_AREA)

        if not study_geom:
            st.error("Invalid study area geometry")
            return

        st.info(f"Running water classification for years: {', '.join(map(str, selected_years))}")

        # Initialize progress
        progress_bar = st.progress(0)
        status_text = st.empty()

        # Process each year
        all_results = []
        for i, year in enumerate(selected_years):
            status_text.text(f"Processing year {year} ({i+1}/{len(selected_years)})")
            progress_bar.progress((i + 1) / len(selected_years))

            try:
                # Load training data
                fileList = []
                fList = gb(r'C:\Users\training\training_data\*.txt')
                for file in fList:
                    fileList.append(file)

                for file_path in fileList:
                    coords = []
                    file_year = file_path.split('List')[0][-4:]
                    if file_path.split('\\')[-1][:5] == 'Water':
                        className = 'Water'
                        globals()[f'{className}{file_year}List'] = training_samples(file_path)
                    else:
                        className = 'NonWater'
                        globals()[f'{className}{file_year}List'] = training_samples(file_path)

                # Create dictionary of coordinates for current year
                coordinates_dict = {
                    f'NonWater{year}': globals()[f'NonWater{year}List'],
                    f'Water{year}': globals()[f'Water{year}List']
                }

                # Initialize and run analysis
                analysis = LandCoverAnalysis(
                    year=year,
                    monthMin=1,
                    monthMax=12,
                    cloud_cover=cloud_cover,
                    scale=30,
                    coordinates_list_dict=coordinates_dict,
                    study_area=study_geom
                )

                results = analysis.run(force_reprocess=force_reprocess)

                if results:
                    # Get the first result (most recent image for the year)
                    first_result = results[0]

                    # Add to all results for summary
                    all_results.append({
                        'year': year,
                        'date': first_result['image_date'],
                        'water_area': first_result['water_stats']['water_area_sq_m'],
                        'water_percentage': first_result['water_stats']['water_percentage'],
                        'accuracy': first_result['accuracy_stats']['overall_accuracy'],
                        'kappa': first_result['accuracy_stats']['kappa'],
                        'map_path': first_result['map_path']
                    })
                else:
                    st.warning(f"No valid images processed for year {year}")

            except Exception as e:
                st.error(f"Error processing year {year}: {str(e)}")
                continue

        # Store results in session state
        st.session_state.classification_results = all_results

        # Display results
        if st.session_state.classification_results:
            st.success("Classification completed!")

            # Get all results from database for display
            db_results = get_all_results()

            # Summary section
            st.header("Summary Across All Years")
            display_summary_results(db_results)

            # Create tabs for each year's detailed results
            year_tabs = st.tabs([f"Year {res['year']}" for res in db_results])

            for i, result in enumerate(db_results):
                with year_tabs[i]:
                    detailed_result = get_result_by_date(result['date'])
                    if detailed_result:
                        display_detailed_results(detailed_result)

            if st.button("Clear Results"):
                st.session_state.classification_results = None
                st.session_state.current_config = None
                st.rerun()

def display_accuracy_metrics(accuracy_stats):
    """Display accuracy metrics in a formatted way with robust data handling."""
    if not accuracy_stats:
        st.warning("No accuracy metrics available")
        return

    st.subheader("Classification Accuracy Metrics")

    # Main metrics in columns
    col1, col2 = st.columns(2)

    # Handle overall accuracy
    if 'overall_accuracy' in accuracy_stats:
        col1.metric("Overall Accuracy", f"{accuracy_stats['overall_accuracy']:.2%}")
    else:
        col1.warning("Overall Accuracy not available")

    # Handle kappa coefficient
    if 'kappa' in accuracy_stats:
        col2.metric("Kappa Coefficient", f"{accuracy_stats['kappa']:.2f}")
    else:
        col2.warning("Kappa Coefficient not available")

    # Producer and User accuracy tables
    st.write("#### Class-wise Accuracy")

    # Initialize empty DataFrames as fallback
    producer_df = pd.DataFrame(columns=['Producer Accuracy'])
    user_df = pd.DataFrame(columns=['User Accuracy'])

    # Safely create producer accuracy DataFrame
    if 'producer_accuracy' in accuracy_stats and accuracy_stats['producer_accuracy']:
        try:
            producer_data = accuracy_stats['producer_accuracy']
            if isinstance(producer_data, dict):
                producer_df = pd.DataFrame.from_dict(
                    producer_data,
                    orient='index',
                    columns=['Producer Accuracy']
                )
                # Convert to percentage values (0-1 to 0-100)
                producer_df = producer_df.apply(lambda x: x * 100)
        except Exception as e:
            st.error(f"Error creating producer accuracy table: {str(e)}")

    # Safely create user accuracy DataFrame
    if 'user_accuracy' in accuracy_stats and accuracy_stats['user_accuracy']:
        try:
            user_data = accuracy_stats['user_accuracy']

            # Initialize empty DataFrame
            user_df = pd.DataFrame(columns=['User Accuracy'])

            if isinstance(user_data, dict):
                # Special case: "Non Water" key contains both accuracies
                if "Non Water" in user_data and isinstance(user_data["Non Water"], list) and len(user_data["Non Water"]) == 2:
                    # Create DataFrame with both classes
                    user_df = pd.DataFrame({
                        'User Accuracy': [
                            user_data["Non Water"][0] * 100,  # Non Water accuracy
                            user_data["Non Water"][1] * 100   # Water accuracy
                        ]
                    }, index=['Non Water', 'Water'])

                # Handle the case where values are lists [producer_acc, user_acc] for each class
                elif all(isinstance(v, list) and len(v) == 2 for v in user_data.values()):
                    # Extract just the user accuracy (second value in each list)
                    user_acc_dict = {k: v[1] for k, v in user_data.items()}
                    user_df = pd.DataFrame.from_dict(
                        user_acc_dict,
                        orient='index',
                        columns=['User Accuracy']
                    )
                    # Convert to percentage values (0-1 to 0-100)
                    user_df = user_df.apply(lambda x: x * 100)

                # Original handling for simple dict format
                else:
                    user_df = pd.DataFrame.from_dict(
                        user_data,
                        orient='index',
                        columns=['User Accuracy']
                    )
                    # Convert to percentage values (0-1 to 0-100)
                    user_df = user_df.apply(lambda x: x * 100)

            elif isinstance(user_data, list):
                user_df = pd.DataFrame(
                    user_data,
                    columns=['Class', 'User Accuracy']
                ).set_index('Class')
                user_df['User Accuracy'] = user_df['User Accuracy'] * 100

        except Exception as e:
            st.error(f"Error creating user accuracy table: {str(e)}")
            st.error(f"Problematic data structure: {type(user_data)}")
            if isinstance(user_data, dict):
                st.error(f"Sample items: {list(user_data.items())[:2]}")

    # Display in columns
    acc_col1, acc_col2 = st.columns(2)
    with acc_col1:
        st.write("**Producer Accuracy**")
        if not producer_df.empty:
            st.dataframe(producer_df.style.format("{:.2f}%"))
        else:
            st.warning("Producer accuracy data not available")

    with acc_col2:
        st.write("**User Accuracy**")
        if not user_df.empty:
            st.dataframe(user_df.style.format("{:.2f}%"))
        else:
            st.warning("User accuracy data not available")

    # Confusion matrix
    st.write("#### Confusion Matrix")
    if 'confusion_matrix' in accuracy_stats and accuracy_stats['confusion_matrix']:
        try:
            cm = pd.DataFrame(
                accuracy_stats['confusion_matrix'],
                index=['Non Water', 'Water'],
                columns=['Non Water', 'Water']
            )
            cm_style = cm.style.background_gradient(cmap='Blues')
            st.write("Rows = Reference, Columns = Classified")
            st.write(cm_style)
        except Exception as e:
            st.error(f"Error displaying confusion matrix: {str(e)}")
    else:
        st.warning("Confusion matrix not available")

    # Interpretation expander
    with st.expander("How to interpret these metrics"):
        st.markdown("""
        - **Overall Accuracy**: Percentage of correctly classified pixels
        - **Kappa Coefficient**: Agreement between classification and reference data (1 = perfect agreement)
        - **Producer Accuracy**: Percentage of reference pixels correctly classified (omission errors)
        - **User Accuracy**: Percentage of classified pixels that match reference (commission errors)
        - **Confusion Matrix**: Shows correct classifications (diagonal) and errors (off-diagonal)
        """)

def display_feature_importance(feature_importance):
    """Display feature importance with proper data structure handling."""
    if not feature_importance:
        st.warning("No feature importance data available")
        return

    try:
        # Convert input to consistent format
        if isinstance(feature_importance, dict):
            # Convert dict to list of tuples
            features_list = list(feature_importance.items())
        elif isinstance(feature_importance, list):
            if all(isinstance(x, (list, tuple)) and len(x) == 2 for x in feature_importance):
                # Already in correct format [(feature, importance), ...]
                features_list = feature_importance
            else:
                # Handle case where it might be a list of dicts or other format
                features_list = []
                for item in feature_importance:
                    if isinstance(item, dict):
                        features_list.extend(item.items())
                    else:
                        st.warning(f"Unexpected item format in feature importance: {type(item)}")
                        return
        else:
            raise ValueError(f"Unsupported feature importance format: {type(feature_importance)}")

        # Create DataFrame with explicit column names
        features_df = pd.DataFrame(
            features_list,
            columns=['Feature', 'Importance']
        ).sort_values('Importance', ascending=False)

        # Display results
        st.dataframe(
            features_df.style.format({
                'Importance': '{:.4f}'
            })
        )

        # Visualization
        if not features_df.empty:
            fig, ax = plt.subplots(figsize=(10, 6))
            features_df.plot.barh(
                x='Feature',
                y='Importance',
                ax=ax,
                color='skyblue',
                legend=False
            )
            ax.set_title('Feature Importance')
            ax.set_xlabel('Relative Importance')
            st.pyplot(fig)
            plt.close()

        # Interpretation
        with st.expander("About Feature Importance"):
            st.markdown("""
            Feature importance shows which input bands contributed most to the classification:
            - Higher values indicate more important features
            - NDWI (Normalized Difference Water Index) is often the most important for water detection
            - Thermal bands can help distinguish water from other dark surfaces
            """)

    except Exception as e:
        st.error(f"Error processing feature importance: {str(e)}")
        st.error(f"Data format received: {type(feature_importance)}")
        if isinstance(feature_importance, (list, dict)):
            sample = feature_importance[:3] if isinstance(feature_importance, list) else list(feature_importance.items())[:3]
            st.error(f"Data sample: {sample}")

def display_detailed_results(result):
    """Display detailed results for a single analysis."""
    st.subheader(f"Detailed Analysis Results - {result['date']}")

    tabs = st.tabs(["Water Coverage", "Accuracy Metrics", "Feature Importance", "Classified Map"])

    with tabs[0]:
        # Water coverage statistics
        st.subheader("Water Coverage Statistics")

        # Metrics in columns
        col1, col2, col3 = st.columns(3)
        col1.metric("Water Area", f"{result['water_stats']['water_area_sq_m']:,.2f} sq m")
        col2.metric("Water Percentage", f"{result['water_stats']['water_percentage']:.2f}%")
        col3.metric("Total Area", f"{result['water_stats']['total_area_sq_m']:,.2f} sq m")

        # Visualizations
        col_viz1, col_viz2 = st.columns(2)

        with col_viz1:
            # Display pie chart if available
            if result.get('pie_chart_path'):
                st.image(result['pie_chart_path'], 
                         caption="Water Coverage Distribution",
                         use_container_width=True)

        with col_viz2:
            # Create a bar chart of water vs non-water
            data = {
                'Category': ['Water', 'Non-Water'],
                'Area (sq m)': [
                    result['water_stats']['water_area_sq_m'], 
                    result['water_stats']['non_water_area_sq_m']
                ]
            }
            df = pd.DataFrame(data)
            st.bar_chart(df.set_index('Category'))

        # Detailed statistics
        with st.expander("Detailed Water Statistics"):
            st.write(f"**Water Area:** {result['water_stats']['water_area_sq_m']:,.2f} sq m")
            st.write(f"**Water Percentage:** {result['water_stats']['water_percentage']:.2f}%")
            st.write(f"**Non-Water Area:** {result['water_stats']['non_water_area_sq_m']:,.2f} sq m")
            st.write(f"**Non-Water Percentage:** {result['water_stats']['non_water_percentage']:.2f}%")
            st.write(f"**Total Area:** {result['water_stats']['total_area_sq_m']:,.2f} sq m")

    with tabs[1]:
        # Accuracy metrics
        if 'accuracy_stats' in result:
            display_accuracy_metrics(result['accuracy_stats'])
        else:
            st.warning("Accuracy metrics not available")

    with tabs[2]:
        # Feature importance
        if 'feature_importance' in result:
            display_feature_importance(result['feature_importance'])
        else:
            st.warning("Feature importance data not available")

    with tabs[3]:
        # Classified map
        st.subheader("Classified Land Cover Map")

        if result.get('map_path'):
            # Display the map image
            st.image(result['map_path'], use_container_width=True)

            # Map legend
            st.markdown("""
            **Map Legend:**
            - <span style="color:blue">**Blue**</span>: Water
            - <span style="color:#25523B">**Green**</span>: Non-Water
            """, unsafe_allow_html=True)

            # Download option
            with open(result['map_path'], "rb") as file:
                st.download_button(
                    label="Download Classified Map",
                    data=file,
                    file_name=os.path.basename(result['map_path']),
                    mime="image/png"
                )
        else:
            st.warning("Classified map not available")

def display_summary_results(all_results):
    """Display summary of results with proper column handling."""
    if not all_results:
        st.warning("No results available to display")
        return

    # Convert to DataFrame
    summary_df = pd.DataFrame(all_results)

    # Ensure date is datetime type
    if 'date' in summary_df.columns:
        summary_df['date'] = pd.to_datetime(summary_df['date'])
        # Extract temporal components
        summary_df['year'] = summary_df['date'].dt.year
        summary_df['month'] = summary_df['date'].dt.month
        summary_df['day'] = summary_df['date'].dt.day
        summary_df['year-month'] = summary_df['date'].dt.to_period('M').astype(str)

    # Metrics columns
    col1, col2, col3 = st.columns(3)
    col1.metric("Years Processed", len(summary_df['year'].unique()) if 'year' in summary_df.columns else 0)

    if 'water_percentage' in summary_df.columns:
        col2.metric("Average Water %", f"{summary_df['water_percentage'].mean():.2f}%")
    else:
        col2.metric("Average Water %", "N/A")

    if 'accuracy' in summary_df.columns:
        col3.metric("Average Accuracy", f"{summary_df['accuracy'].mean():.2%}")
    else:
        col3.metric("Average Accuracy", "N/A")

    # Drill-down selector
    drill_level = st.radio(
        "Select Time Aggregation Level",
        ["Years", "Months", "Days"],
        horizontal=True
    )

    # Prepare data based on drill level
    if drill_level == "Years" and 'year' in summary_df.columns:
        grouped_df = summary_df.groupby('year').mean(numeric_only=True).reset_index()
        x_col = 'year'
        x_title = 'Year'
    elif drill_level == "Months" and 'year-month' in summary_df.columns:
        grouped_df = summary_df.groupby('year-month').mean(numeric_only=True).reset_index()
        x_col = 'year-month'
        x_title = 'Month'
    elif drill_level == "Days" and 'date' in summary_df.columns:
        grouped_df = summary_df.copy()
        x_col = 'date'
        x_title = 'Date'
    else:
        st.warning(f"Cannot group by {drill_level} - missing required columns")
        return

    # Create tabs for different visualizations
    viz_tabs = st.tabs(["Water Area", "Water Percentage", "Accuracy Metrics"])

    with viz_tabs[0]:
        if 'water_area' in grouped_df.columns:
            st.subheader(f"Water Area Over Time ({drill_level})")
            st.line_chart(
                data=grouped_df,
                x=x_col,
                y='water_area',
                use_container_width=True
            )
        else:
            st.warning("Water area data not available")

    with viz_tabs[1]:
        if 'water_percentage' in grouped_df.columns:
            st.subheader(f"Water Percentage Over Time ({drill_level})")
            st.line_chart(
                data=grouped_df,
                x=x_col,
                y='water_percentage',
                use_container_width=True
            )
        else:
            st.warning("Water percentage data not available")

    with viz_tabs[2]:
        col_acc1, col_acc2 = st.columns(2)
        with col_acc1:
            if 'accuracy' in grouped_df.columns:
                st.line_chart(
                    data=grouped_df,
                    x=x_col,
                    y='accuracy',
                    use_container_width=True
                )
                st.write("**Overall Accuracy**")
            else:
                st.warning("Accuracy data not available")

        with col_acc2:
            if 'kappa' in grouped_df.columns:
                st.line_chart(
                    data=grouped_df,
                    x=x_col,
                    y='kappa',
                    use_container_width=True
                )
                st.write("**Kappa Coefficient**")
            else:
                st.warning("Kappa coefficient data not available")

    # Download button (only if we have data)
    if not grouped_df.empty:
        csv = grouped_df.to_csv(index=False)
        st.download_button(
            label="Download Data",
            data=csv,
            file_name=f"water_data_{drill_level.lower()}.csv",
            mime="text/csv"
        )

# App routing
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

if not st.session_state['authenticated']:
    login_page()
else:
    main_app()
