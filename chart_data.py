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


def build_seasonality_data(df: pd.DataFrame) -> pd.DataFrame:
    """Full pipeline: event rows -> daily expanded rows -> summed totals -> fill zeros -> seasonality columns."""
    selected_years = set(df["START_DATE"].dropna().dt.year.unique()) | set(df["END_DATE"].dropna().dt.year.unique())
    selected_years = {y for y in selected_years if y >= MIN_CHART_DATE.year}
    daily = expand_events_to_daily(df)
    daily = daily[daily["date"] >= MIN_CHART_DATE]
    daily = daily[daily["date"].dt.year.isin(selected_years)]
    totals = compute_daily_totals(daily)
    totals = fill_missing_days(totals)
    return add_seasonality_columns(totals)
