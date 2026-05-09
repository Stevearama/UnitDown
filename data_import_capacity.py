import pandas as pd

KEEP_COLS = [
    "UNIT_ID", "OWNER_NAME", "PLANT_ID", "PLANT_NAME", "P_COUNTRY",
    "MARKET_REG", "WORLD_REG", "U_STATUS", "U_CAPACITY", "CAP_UOM",
    "STARTUP", "SHUTDOWN", "UNIT_TYPE", "PAD_DIST",
    "LATITUDE", "LONGITUDE",
]

EXCLUDE_ALWAYS    = {"Cancelled"}
REQUIRE_STARTUP   = {"On Hold", "Under Construction", "Planned", "Engineered"}
REQUIRE_EITHER_DATE = {"Closed", "Mothballed", "Removed", "Shuttered"}

# Intentionally duplicated from data_import.py — pipelines are kept independent
RENAME_UNIT_TYPE = {
    "Distillate Hydrotreater":                  "DHTU",
    "Reformer Feed Hydrotreater":               "REMOVE",
    "Vacuum Distillation":                      "VDU",
    "Sulfuric Alkylation":                      "Alky",
    "Atmospheric Distillation":                 "CDU",
    "Aromatics":                                "Aroms",
    "BTX (Benzene-Toluene-Xylene)":             "Aroms",
    "Amine Treatment":                          "REMOVE",
    "Olefin/Aromatics Hydrotreater":            "REMOVE",
    "Asphalt":                                  "REMOVE",
    "Residual Hydrotreater":                    "REMOVE",
    "Condensate Splitter":                      "CDU",
    "Isomerization":                            "Isom",
    "Benzene":                                  "Aroms",
    "CCR (Continuous Catalytic Reformer)":      "Reformer",
    "FCCU (Fluid Catalytic Cracker)":           "FCCU",
    "FCCU Feed Hydrotreater":                   "REMOVE",
    "Mid Distillate Hydrotreater":              "DHTU",
    "FCCU Gasoline Hydrotreater":               "REMOVE",
    "Refinery Gas/Lights Ends":                 "REMOVE",
    "Sulfur Recovery (SRU)":                    "REMOVE",
    "Semiregen/Cyclic Reformer":                "Reformer",
    "Petroleum Coke Calciner":                  "REMOVE",
    "HGO (Heavy Gas Oils) Hydrotreater":        "REMOVE",
    "Light Naphtha Hydrotreater":               "REMOVE",
    "Solvent Extraction":                       "REMOVE",
    "Delayed Coker":                            "Coker / Visbreaker",
    "Distillate Hydrocracker":                  "Hydrocracker",
    "Diesel Hydrotreater":                      "DHTU",
    "Diluent Recovery Unit (DRU)":              "REMOVE",
    "Naphtha Splitter":                         "REMOVE",
    "Lube Oil Dewaxing":                        "REMOVE",
    "VRU (Vapor Recovery Unit)":                "REMOVE",
    "Fluidized-Bed Coker":                      "Coker / Visbreaker",
    "Lube Oil Finishing":                       "REMOVE",
    "Sour Water Stripper":                      "REMOVE",
    "Hydrogen (H2) Production":                 "REMOVE",
    "Hydrodealkylation":                        "Alky",
    "Lube Oil Hydrotreater":                    "REMOVE",
    "Hydrofluoric Alkylation":                  "Alky",
    "Hydrogen (H2) Recovery":                   "REMOVE",
    "SR (Straight-Run) Hydrotreater":           "DHTU",
    "Residual Hydrocracker":                    "Hydrocracker",
    "Ionic Salt (Liquid) Alkylation":           "Alky",
    "Mercaptan-Extraction":                     "REMOVE",
    "Lube Oil Hydrocracker":                    "REMOVE",
    "MTBE (Methyl tert Butyl Ether)":           "REMOVE",
    "Tail Gas Treater":                         "REMOVE",
    "Propylene Splitter":                       "REMOVE",
    "Paraxylene":                               "Aroms",
    "RFCCU (Residue Fluid Catalytic Cracker)":  "FCCU",
    "Reformate Splitter":                       "REMOVE",
    "TAME (Tertiary Amyl Methyl Ether)":        "REMOVE",
    "Visbreaker":                               "Coker / Visbreaker",
    "Crude Stabilization":                      "REMOVE",
    "Linear Alkyl Benzene (LAB)":               "REMOVE",
    "Toluene":                                  "Aroms",
    "Vacuum (No Atmospheric)":                  "VDU",
    "Xylene":                                   "Aroms",
}

PADD_RENAME = {
    "I":   "PADD 1",
    "II":  "PADD 2",
    "III": "PADD 3",
    "IV":  "PADD 4",
    "V":   "PADD 5",
}

COLUMN_RENAME = {
    "P_COUNTRY": "COUNTRY",
    "UNIT_TYPE": "UTYPE_DESC",
    "PAD_DIST":  "PADD_REG",
    "STARTUP":   "START_DATE",
    "SHUTDOWN":  "END_DATE",
}


def _apply_status_filter(df: pd.DataFrame) -> pd.DataFrame:
    df = df[~df["U_STATUS"].isin(EXCLUDE_ALWAYS)]
    needs_startup = df["U_STATUS"].isin(REQUIRE_STARTUP)
    df = df[~needs_startup | df["STARTUP"].notna()]
    has_period = df["U_STATUS"].isin(REQUIRE_EITHER_DATE)
    both_null = df["STARTUP"].isna() & df["SHUTDOWN"].isna()
    df = df[~(has_period & both_null)]
    return df


def _parse_dates(series: pd.Series) -> pd.Series:
    """Parse 2-digit year dates (e.g. '1-Jan-51'), correcting future dates back 100 years."""
    parsed = pd.to_datetime(series, format="%d-%b-%y", errors="coerce")
    today_year = pd.Timestamp.today().year
    def _fix(dt):
        if pd.isna(dt):
            return dt
        return dt.replace(year=dt.year - 100) if dt.year > today_year else dt
    return parsed.apply(_fix)


def load_units(filepath: str = "units.csv") -> pd.DataFrame:
    df = pd.read_csv(filepath, usecols=KEEP_COLS, low_memory=False)
    df = df.dropna(subset=["U_CAPACITY"])
    df = df[df["U_CAPACITY"] > 0]
    df["STARTUP"] = _parse_dates(df["STARTUP"])
    df["SHUTDOWN"] = _parse_dates(df["SHUTDOWN"])
    df = _apply_status_filter(df)
    df = df[df["SHUTDOWN"].isna() | (df["SHUTDOWN"] >= "2020-01-01")]
    df = df.rename(columns=COLUMN_RENAME)
    df["UTYPE_DESC"] = df["UTYPE_DESC"].replace(RENAME_UNIT_TYPE)
    df = df[df["UTYPE_DESC"] != "REMOVE"]
    df["PADD_REG"] = df["PADD_REG"].replace(PADD_RENAME)
    df.loc[df["CAP_UOM"] == "BBL/d", "U_CAPACITY"] /= 1000
    df["CAP_UOM"] = df["CAP_UOM"].replace("BBL/d", "kbd")
    return df
