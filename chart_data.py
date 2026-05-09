import pandas as pd


def expand_events_to_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Expand each event into one row per calendar day it spans."""
    valid = df.dropna(subset=["START_DATE", "END_DATE"]).copy()
    valid["date"] = valid.apply(
        lambda r: pd.date_range(r["START_DATE"], r["END_DATE"], freq="D"),
        axis=1,
    )
    return valid[["CAP_OFFLINE", "date"]].explode("date")


def compute_daily_totals(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Sum CAP_OFFLINE across all units for each calendar date."""
    return (
        daily_df.groupby("date", as_index=False)["CAP_OFFLINE"]
        .sum()
        .sort_values("date")
    )


def fill_missing_days(daily_totals: pd.DataFrame) -> pd.DataFrame:
    """Insert zero-value rows for every calendar day that has no recorded outages."""
    if daily_totals.empty:
        return daily_totals
    years = daily_totals["date"].dt.year.unique()
    full_range = pd.DatetimeIndex(
        pd.concat([pd.Series(pd.date_range(f"{y}-01-01", f"{y}-12-31", freq="D")) for y in years])
    )
    return (
        daily_totals
        .set_index("date")
        .reindex(full_range, fill_value=0)
        .rename_axis("date")
        .reset_index()
    )


def add_seasonality_columns(daily_totals: pd.DataFrame) -> pd.DataFrame:
    """Add year and a normalised plot_date (pinned to year 2000) for the seasonality x-axis.

    Year 2000 is chosen because it is a leap year, so Feb 29 dates never raise an error.
    """
    df = daily_totals.copy()
    df["year"] = df["date"].dt.year
    df["plot_date"] = df["date"].apply(lambda d: d.replace(year=2000))
    return df


MIN_CHART_DATE = pd.Timestamp("2021-01-01")


def build_timeline_data(df: pd.DataFrame, years: list = None) -> pd.DataFrame:
    """Build daily offline capacity by unit type for a timeline (actual-date) chart."""
    if years:
        selected_years = {y for y in years if y >= MIN_CHART_DATE.year}
    else:
        selected_years = {y for y in df["START_DATE"].dropna().dt.year.unique() if y >= MIN_CHART_DATE.year}

    if not selected_years:
        return pd.DataFrame(columns=["date", "UTYPE_DESC", "CAP_OFFLINE"])

    date_start = pd.Timestamp(f"{min(selected_years)}-01-01")
    date_end   = pd.Timestamp(f"{max(selected_years)}-12-31")
    full_range = pd.date_range(date_start, date_end, freq="D")

    valid = df.dropna(subset=["START_DATE", "END_DATE"]).copy()
    valid["date"] = valid.apply(
        lambda r: pd.date_range(r["START_DATE"], r["END_DATE"], freq="D"), axis=1
    )
    daily = valid[["CAP_OFFLINE", "UTYPE_DESC", "date"]].explode("date")
    daily = daily[(daily["date"] >= date_start) & (daily["date"] <= date_end)]

    totals = daily.groupby(["date", "UTYPE_DESC"], as_index=False)["CAP_OFFLINE"].sum()

    utypes = totals["UTYPE_DESC"].unique()
    full_index = pd.MultiIndex.from_product([full_range, utypes], names=["date", "UTYPE_DESC"])
    totals = (
        totals.set_index(["date", "UTYPE_DESC"])
        .reindex(full_index, fill_value=0)
        .reset_index()
    )
    return totals


def build_seasonality_data(df: pd.DataFrame, years: list = None) -> pd.DataFrame:
    """Full pipeline: event rows -> daily expanded rows -> summed totals -> fill zeros -> seasonality columns."""
    if years:
        selected_years = {y for y in years if y >= MIN_CHART_DATE.year}
    else:
        selected_years = {y for y in df["START_DATE"].dropna().dt.year.unique() if y >= MIN_CHART_DATE.year}
    daily = expand_events_to_daily(df)
    daily = daily[daily["date"] >= MIN_CHART_DATE]
    daily = daily[daily["date"].dt.year.isin(selected_years)]
    totals = compute_daily_totals(daily)
    totals = fill_missing_days(totals)
    return add_seasonality_columns(totals)
