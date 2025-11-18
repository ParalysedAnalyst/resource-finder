import pandas as pd
import sqlalchemy as sa
from urllib.parse import quote_plus

from resource_finder.gui_app import main

# SQL connection details (Windows auth/trusted connection)
server = "dblistener1"
database = "information_centre"
driver = "ODBC Driver 17 for SQL Server"  # must be installed on this machine

# URL-encode the driver (spaces!)
driver_enc = quote_plus(driver)
connection_string = f"mssql+pyodbc://@{server}/{database}?driver={driver_enc}&trusted_connection=yes"

engine = sa.create_engine(connection_string, fast_executemany=True)

# The SQL query to load field team contractors
QUERY = """
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
"""

def load_fieldteams() -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(QUERY, conn)


    df.columns = [c.strip() for c in df.columns]
    required = {
        "intContractorID","Contractor","BusinessUnit","Postcode",
        "Latitude","Longitude","InternalContractor"
    }
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"SQL result missing columns: {missing}")

    # Optional: coerce numeric lat/lon
    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")

    if len(df) == 0:
        raise SystemExit("SQL returned 0 rows; cannot start GUI without data.")

    return df

if __name__ == "__main__":
    print("Connecting to SQL and loading field teams …")
    fieldteams = load_fieldteams()
    print(f"Loaded {len(fieldteams):,} rows.")
    main(fieldteams)