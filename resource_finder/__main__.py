# resource_finder/__main__.py
from .gui_app import main
import pandas as pd
from sqlalchemy import create_engine
import urllib.parse as _u

# --- SQL connection ---
server   = "dblistener1"
database = "information_centre"
driver   = _u.quote_plus("ODBC Driver 17 for SQL Server")  # encode spaces
conn_str = f"mssql+pyodbc://{server}/{database}?driver={driver}"

query = """
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
    engine = create_engine(conn_str)
    with engine.connect() as con:
        df = pd.read_sql(query, con)
    return df

if __name__ == "__main__":
    df = load_fieldteams()
    print(f"Loaded {len(df)} teams from SQL.")
    main(df)  # launches the Tk GUI with real data
