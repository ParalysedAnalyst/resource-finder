# Field Team Resource Finder

A Python-based desktop application for finding and ranking field teams/contractors based on their travel time to a site location. The application uses geospatial analysis to help identify the most suitable teams within specified travel time bands, calculate accurate driving routes, and estimate CO₂ emissions.

## Features

- **Postcode Geocoding**: Convert UK postcodes to geographic coordinates using the postcodes.io API
- **Isochrone Analysis**: Visualize travel time bands (15, 30, 45, and 60 minutes) from a site location
- **Interactive Map**: View teams, isochrones, and routes on an interactive map with OpenStreetMap basemap
- **Team Filtering**: Filter teams by:
  - Business unit
  - Contractor type (Direct/Internal or External Contractor)
  - Travel time bands
- **Route Calculation**: Calculate precise driving routes with:
  - Driving time (minutes)
  - Distance (kilometers)
  - CO₂ emissions (kg)
- **SQL Server Integration**: Load contractor and team data from Microsoft SQL Server database
- **Visual Design**: Custom-styled GUI using Ground Control color palette

## Prerequisites

- Python 3.8 or higher
- Access to a Microsoft SQL Server database with contractor information
- Internet connection for geocoding, isochrones, and routing APIs

## Dependencies

The application requires the following Python packages:

### Core Dependencies
- `pandas` - Data manipulation and analysis
- `geopandas` - Geospatial data operations
- `shapely` - Geometric operations
- `sqlalchemy` - SQL database connectivity
- `pyodbc` - ODBC database driver for SQL Server

### Mapping and Visualization
- `matplotlib` - Plotting and visualization
- `contextily` - Basemap tiles from OpenStreetMap

### API Communication
- `requests` - HTTP requests to external APIs
- `urllib3` - HTTP client library

### GUI
- `tkinter` - Built-in Python GUI framework (usually pre-installed)

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-organization/resource-finder.git
   cd resource-finder
   ```
   
   > **Note**: Replace `your-organization` with the actual GitHub organization or username.

2. **Install dependencies**:
   ```bash
   pip install pandas geopandas shapely sqlalchemy pyodbc matplotlib contextily requests urllib3
   ```

3. **Configure SQL Server connection** (edit `resource_finder/__main__.py`):
   ```python
   server   = "your_server_name"      # Default: "dblistener1"
   database = "your_database_name"    # Default: "information_centre"
   driver   = urllib.parse.quote_plus("ODBC Driver 17 for SQL Server")
   ```
   
   > **Note**: Replace with your specific SQL Server instance and database names. The default values shown are examples from the original configuration.

4. **Configure environment variables** (optional):
   ```bash
   # Mapbox API token (default token provided, but you can use your own)
   export MAPBOX_TOKEN="your_mapbox_token"
   
   # OSRM routing server (defaults to public server)
   export OSRM_BASE="https://router.project-osrm.org"
   
   # CO2 emissions factor (kg per km)
   export CO2_PER_KM_KG="0.171"
   
   # TLS/SSL verification settings
   export VERIFY_DEFAULT="false"
   export SUPPRESS_TLS_WARNINGS="true"
   
   # Proxy settings (if needed)
   export HTTP_PROXY="http://proxy.example.com:8080"
   export HTTPS_PROXY="https://proxy.example.com:8080"
   ```

## Usage

### Running the Application

Launch the application from the command line:

```bash
python -m resource_finder
```

The application will:
1. Connect to the SQL Server database
2. Load contractor/team data
3. Launch the GUI

### Using the Application

1. **Enter a Postcode** (Step 1):
   - Type a UK postcode in the "Postcode" field
   - Press Enter to geocode and load isochrones
   - The map will show the site location and available teams within 60 minutes

2. **Select Business Unit** (Step 2):
   - Choose a specific business unit from the dropdown, or leave as "(Any)"

3. **Select Contractor Type**:
   - Choose "Either" for all teams
   - Choose "Direct" for internal/direct teams only
   - Choose "Contractor" for external contractors only

4. **Select Travel Time Band**:
   - Choose from 15, 30, 45, or 60 minutes
   - The isochrone (colored area) shows the area reachable within the selected time

5. **Apply Filters** (Step 3):
   - Click "Apply filters" to filter teams based on your selections
   - The table and map will update to show matching teams

6. **Calculate Drive Times** (Step 4):
   - Click "Calculate drive times" to get precise routing information
   - The application calculates:
     - Exact driving time
     - Distance
     - CO₂ emissions
   - Teams are automatically ranked by fastest travel time
   - Click on any row in the table to see its route on the map

## Project Structure

```
resource-finder/
├── resource_finder/          # Main application package
│   ├── __init__.py          # Package initialization
│   ├── __main__.py          # Application entry point and SQL connection
│   ├── gui_app.py           # Main GUI application and user interface
│   ├── api_config.py        # External API integrations (postcodes.io, Mapbox, OSRM)
│   ├── geo_config.py        # Geospatial operations and filtering
│   ├── routing_config.py    # Route calculation and ranking
│   ├── run_gui_sql.py       # Alternative entry point
│   └── Natural Earth/       # Geographic data files
├── tests/                    # Unit tests
│   ├── test_api_config.py   # API integration tests
│   ├── test_geo_config.py   # Geospatial function tests
│   └── test_routing.py      # Routing function tests
└── notebooks/                # Jupyter notebooks for development/analysis
    ├── 010 Resource Finder.ipynb
    └── GUI Resource Finder.ipynb
```

## Technical Details

### External APIs

1. **Postcodes.io** (`https://api.postcodes.io`):
   - Free UK postcode geocoding
   - No API key required
   - Converts postcodes to latitude/longitude coordinates

2. **Mapbox Isochrone API** (`https://api.mapbox.com/isochrone/v1`):
   - Generates travel time polygons
   - Requires API token (default provided)
   - Profile: `driving-traffic` for realistic travel times
   - Returns 15, 30, 45, and 60-minute contours in a single call

3. **OSRM Routing API** (`https://router.project-osrm.org`):
   - Open-source routing engine
   - Calculates precise driving routes
   - No API key required
   - Returns distance, duration, and route geometry

### Database Schema

The application expects the following SQL Server query structure:

```sql
SELECT
    a.intContractorID,
    a.strName AS Contractor,
    a.strMobileTel AS MobileTel,
    a.strWebsite AS Email,
    e.BusinessUnitID,
    e.Name AS BusinessUnit,
    UPPER(a.strPostcode) AS Postcode,
    g.Latitude,
    g.Longitude,
    a.InternalContractor
FROM
    tblContractor a
    LEFT JOIN Contractor_Business_Unit d
        ON a.intContractorID = d.ContractorID
    LEFT JOIN Business_Unit e
        ON d.BusinessUnitID = e.BusinessUnitID
    LEFT JOIN Business_Unit_Master_Status f
        ON d.StatusID = f.StatusID
    LEFT JOIN dbs_PostCode.dbo.tblPostcodes_New g
        ON REPLACE(a.strPostcode, ' ', '') = g.PostcodeNoSpaces COLLATE Latin1_General_CI_AS
WHERE
    ISNULL(a.bDisabled, 0) = 0
    AND f.StatusID IN (60, 70, 80)
    AND ISNULL(a.IsTest, 0) = 0
    AND e.BusinessUnitID != 37;
```

**Key Requirements**:
- Contractor table with postcode information
- Business unit associations
- Postcode geocoding table with latitude/longitude
- Status filtering to exclude disabled and test contractors

### Coordinate Reference Systems

- **EPSG:4326** (WGS84): Used for latitude/longitude coordinates and API communication
- **EPSG:3857** (Web Mercator): Used for map visualization and basemap overlay

### CO₂ Emissions Calculation

The application estimates CO₂ emissions using:
- Default factor: **0.171 kg CO₂ per km**
- Configurable via `CO2_PER_KM_KG` environment variable
- Based on average car emissions

## Testing

The project includes unit tests for core functionality:

```bash
# Install pytest (if not already installed)
pip install pytest

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_geo_config.py
```

### Test Coverage

- **API Configuration** (`test_api_config.py`):
  - Postcode geocoding with 404 handling
  - OSRM route calculation

- **Geospatial Operations** (`test_geo_config.py`):
  - Isochrone conversion to GeoDataFrame
  - Team filtering by travel time
  - Business unit and contractor type filtering

- **Routing** (`test_routing.py`):
  - Air distance pre-selection
  - Route ranking

## Troubleshooting

### Map Background Not Loading
- **Issue**: "Unable to load the detailed map background"
- **Cause**: No internet connection or contextily not installed
- **Solution**: The app will continue to work without the basemap. Install contextily if needed: `pip install contextily`

### SQL Connection Error
- **Issue**: "Unable to connect to SQL Server"
- **Solution**: 
  - Verify SQL Server is accessible
  - Check `ODBC Driver 17 for SQL Server` is installed
  - Verify database credentials in `__main__.py`

### Postcode Not Found
- **Issue**: "Postcode not found" error
- **Solution**: 
  - Verify the postcode is valid UK format
  - Check internet connection to postcodes.io

### API Rate Limits
- **Mapbox**: Free tier allows 100,000 requests/month
- **OSRM**: Public server has rate limits; consider self-hosting for production use

## Color Palette

The application uses the Ground Control brand colors:

- **GC Dark Green**: `#294238` - Headers and text
- **GC Light Green**: `#b2d235` - Isochrone overlay and hover states
- **GC Mid Green**: `#50b748` - Team markers and buttons
- **GC Orange**: `#f57821` - Site marker and primary action button
- **GC Light Grey**: `#e6ebe3` - Background

## Contributing

When contributing to this project:

1. Write unit tests for new functionality
2. Follow existing code style and conventions
3. Update documentation as needed
4. Ensure all tests pass before submitting

## License

Please check with the repository owner for licensing information.

## Acknowledgments

- **Natural Earth**: Country boundary data
- **OpenStreetMap**: Map tiles via contextily
- **Mapbox**: Isochrone API
- **OSRM Project**: Open-source routing engine
- **postcodes.io**: Free UK postcode API

## Support

For issues, questions, or contributions, please open an issue on the GitHub repository.
