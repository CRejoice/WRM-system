# WRM system

## Overview

This project is an AI-powered dam monitoring and forecasting system developed for Lake Mutirikwi, Zimbabwe. The system integrates satellite imagery, machine learning, remote sensing and interactive visualisation tools to monitor water surface area changes and support dam management decision-making.

The application automatically processes Landsat satellite imagery, classifies water and non-water areas, calculates dam surface area statistics, evaluates classification accuracy, stores results in a SQL Server database, and provides an interactive Streamlit dashboard for analysis and reporting.

---

## Features

* Water and non-water classification using satellite imagery
* Automated NDWI (Normalized Difference Water Index) calculation
* Dynamic water detection thresholding
* Landsat image preprocessing and cloud filtering
* Surface water area calculation
* Historical dam monitoring and trend analysis
* Classification accuracy assessment
* Feature importance analysis using Random Forest
* Interactive Streamlit dashboard
* SQL Server database integration
* GeoJSON, KML and KMZ study area support
* Automated map generation and reporting
* Historical dam change visualisation

---

## Technologies Used

### Programming Languages

* Python

### Geospatial and Remote Sensing

* Google Earth Engine
* Geemap
* Landsat Satellite Imagery

### Machine Learning

* Scikit-Learn
* Random Forest Classifier
* Joblib

### Data Processing

* Pandas
* NumPy

### Visualisation

* Streamlit
* Matplotlib

### Database

* Microsoft SQL Server
* PyODBC

### Other Libraries

* Pillow
* ImageIO
* Selenium
* XML Processing
* Dotenv

---

## Project Structure

```text
Project/
│
├── dam_visualizer.py
├── Lake Kyle Streamlit App.ipynb
├── Kyle LULC Change Analysis.ipynb
├── training_data/
│   ├── WaterYYYYList.txt
│   ├── NonWaterYYYYList.txt
│   └── ...
│
├── classifier_models/
├── outputs/
├── maps/
├── reports/
│
├── requirements.txt
├── .env
└── README.md
```

---

## Methodology

The workflow consists of:

1. Satellite image acquisition from Google Earth Engine
2. Cloud filtering and image preprocessing
3. NDWI calculation
4. Training data extraction
5. Random Forest model training
6. Water and non-water classification
7. Surface area calculation
8. Accuracy assessment
9. Database storage
10. Interactive dashboard visualisation

---

## Study Area

**Lake Mutirikwi (Kyle Dam)**

Location: Masvingo Province, Zimbabwe

The system is designed to monitor historical and current water surface changes within the dam using Landsat imagery and machine learning techniques.

---

## Google Earth Engine Setup

Authenticate Google Earth Engine:

```python
import ee

ee.Authenticate()
ee.Initialize()
```

Replace the project ID in the script with your own Earth Engine project.

---



## Author

Rejoice Chivasa

Data Scientist 


## License

This project is licensed under the MIT License.
