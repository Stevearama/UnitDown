import pandas as pd

from constants import PADD_RENAME, RENAME_UNIT_TYPE

KEEP_COLS = [
    "UNIT_ID", "OWNER_NAME", "PLANT_ID", "PLANT_NAME", "COUNTRY",
    "MARKET_REG", "WORLD_REG", "U_STATUS", "U_CAPACITY", "CAP_OFFLINE",
    "CAP_UOM", "DERATE", "START_DATE", "END_DATE", "EVENT_TYPE",
    "E_CAUSE", "E_STATUS_RESEARCH", "UTYPE_DESC", "PADD_REG",
    "LATITUDE", "LONGITUDE",
]

DATE_COLS = ["START_DATE", "END_DATE"]


def apply_unit_type_mapping(df: pd.DataFrame) -> pd.DataFrame:
    """Rename UTYPE_DESC to display names and drop rows tagged REMOVE."""
    df = df.copy()
    df["UTYPE_DESC"] = df["UTYPE_DESC"].replace(RENAME_UNIT_TYPE)
    return df[df["UTYPE_DESC"] != "REMOVE"]


def rename_padd_regions(df: pd.DataFrame) -> pd.DataFrame:
    """Replace Roman-numeral PADD codes with 'PADD N' labels; leave non-US regions unchanged."""
    df = df.copy()
    df["PADD_REG"] = df["PADD_REG"].replace(PADD_RENAME)
    return df


def load_offline_events(filepath: str = "Offline Event.csv") -> pd.DataFrame:
    """Read the offline events CSV, keep relevant columns, clean unit types, and parse dates."""
    df = pd.read_csv(filepath, usecols=KEEP_COLS, low_memory=False)
    for col in DATE_COLS:
        df[col] = pd.to_datetime(df[col], format="%d-%b-%Y", errors="coerce")
    df = apply_unit_type_mapping(df)
    df = rename_padd_regions(df)
    bbl_mask = (df["CAP_UOM"] == "BBL/d") | df["CAP_UOM"].isna()
    td_mask  = df["CAP_UOM"] == "T/d"
    tyr_mask = df["CAP_UOM"] == "Metric T/yr"

    df.loc[bbl_mask, "CAP_OFFLINE"] /= 1000
    df.loc[bbl_mask, "U_CAPACITY"]  /= 1000
    df.loc[bbl_mask, "CAP_UOM"]     = "kbd"

    df.loc[td_mask, "CAP_OFFLINE"] = df.loc[td_mask, "CAP_OFFLINE"] * 7 / 1000
    df.loc[td_mask, "U_CAPACITY"]  = df.loc[td_mask, "U_CAPACITY"]  * 7 / 1000
    df.loc[td_mask, "CAP_UOM"]     = "kbd"

    df.loc[tyr_mask, "CAP_OFFLINE"] = df.loc[tyr_mask, "CAP_OFFLINE"] * 7 / (1000 * 365)
    df.loc[tyr_mask, "U_CAPACITY"]  = df.loc[tyr_mask, "U_CAPACITY"]  * 7 / (1000 * 365)
    df.loc[tyr_mask, "CAP_UOM"]     = "kbd"

    # Keep only rows successfully converted to kbd; strip everything else.
    df = df[df["CAP_UOM"] == "kbd"]
    return df
