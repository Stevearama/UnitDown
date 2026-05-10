import pandas as pd

from constants import PADD_RENAME, RENAME_UNIT_TYPE

KEEP_COLS = [
    "UNIT_ID", "OWNER_NAME", "PLANT_ID", "PLANT_NAME", "P_COUNTRY",
    "MARKET_REG", "WORLD_REG", "U_STATUS", "U_CAPACITY", "CAP_UOM",
    "STARTUP", "SHUTDOWN", "UNIT_TYPE", "PAD_DIST",
    "LATITUDE", "LONGITUDE",
]

EXCLUDE_ALWAYS      = {"Cancelled", "On Hold"}
REQUIRE_STARTUP     = {"Under Construction", "Planned", "Engineered"}
REQUIRE_EITHER_DATE = {"Closed", "Mothballed", "Removed", "Shuttered"}

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
    """Parse 2-digit year dates, correcting implausible far-future dates back 100 years.

    Years within 20 years of today are kept as-is (legitimate planned-unit horizons).
    Years beyond that are assumed to be century-rollover artefacts (e.g. '47' parsed
    as 2047 when the source meant 1947).
    """
    parsed = pd.to_datetime(series, format="%d-%b-%y", errors="coerce")
    cutoff_year = pd.Timestamp.today().year + 20
    def _fix(dt):
        if pd.isna(dt):
            return dt
        return dt.replace(year=dt.year - 100) if dt.year > cutoff_year else dt
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
    bbl_mask = df["CAP_UOM"] == "BBL/d"
    tyr_mask = df["CAP_UOM"] == "Metric T/yr"

    df.loc[bbl_mask, "U_CAPACITY"] /= 1000
    df.loc[bbl_mask, "CAP_UOM"]    = "kbd"

    df.loc[tyr_mask, "U_CAPACITY"] = df.loc[tyr_mask, "U_CAPACITY"] * 7 / (1000 * 365)
    df.loc[tyr_mask, "CAP_UOM"]    = "kbd"

    # Strip UOMs that cannot be meaningfully converted to kbd.
    _STRIP = {"Gallons/yr", "k cubic ft/day", "M Lbs/yr", "MMSCFD"}
    df = df[~df["CAP_UOM"].isin(_STRIP)]
    return df
