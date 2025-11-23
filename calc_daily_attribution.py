import os
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd
import pyodbc
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
EXCEL_PATH = BASE_DIR / "ModelPort - demo allocation.xlsx"
ENV_PATH = BASE_DIR / ".env"
OUTPUT_PATH = BASE_DIR / "analysis/mp_model_daily_attribution.csv"
ODBC_DRIVER = "/Users/ducle/Coding-Chat/libmsodbcsql.18.dylib"
ODBCINST_PATH = "/Users/ducle/Coding-Chat/odbcinst.ini"


def ensure_env() -> None:
    if "SQL_SERVER" not in os.environ:
        load_dotenv(ENV_PATH)
    os.environ.setdefault("ODBCINSTINI", ODBCINST_PATH)


def get_connection() -> pyodbc.Connection:
    ensure_env()
    conn_str = (
        f"DRIVER={ODBC_DRIVER};"
        f"SERVER={os.environ['SQL_SERVER']};"
        f"DATABASE={os.environ['SQL_DATABASE']};"
        f"UID={os.environ['SQL_USERNAME']};"
        f"PWD={os.environ['SQL_PASSWORD']};"
        "Encrypt=yes;TrustServerCertificate=no;"
    )
    return pyodbc.connect(conn_str)


def parse_rebalance_label(label) -> pd.Timestamp:
    if isinstance(label, pd.Timestamp):
        return label.normalize()
    return pd.to_datetime(str(label), dayfirst=True).normalize()


def load_rebalance_weights() -> Tuple[pd.DataFrame, List[str]]:
    df = pd.read_excel(EXCEL_PATH)
    if "Ticker" not in df.columns:
        raise ValueError("Excel file must contain 'Ticker' column.")
    df = df[~df["Ticker"].astype(str).str.contains("total", case=False, na=False)]
    value_cols = [c for c in df.columns if c != "Ticker"]
    date_map = {col: parse_rebalance_label(col) for col in value_cols}

    melted = df.melt(
        id_vars="Ticker",
        value_vars=value_cols,
        var_name="RebalanceRaw",
        value_name="Weight",
    )
    melted["RebalanceDate"] = melted["RebalanceRaw"].map(date_map)
    melted["Ticker"] = melted["Ticker"].astype(str)
    ticker_mask = melted["Ticker"].str.fullmatch(r"[A-Z]{3}", na=False)
    melted.loc[ticker_mask, "Ticker"] = melted.loc[ticker_mask, "Ticker"].str.upper()
    cash_mask = melted["Ticker"].str.contains("cash", case=False, na=False)

    ticker_weights = (
        melted[ticker_mask]
        .pivot_table(
            index="RebalanceDate",
            columns="Ticker",
            values="Weight",
            aggfunc="first",
        )
        .fillna(0.0)
    )
    cash_weights = (
        melted[cash_mask]
        .groupby("RebalanceDate")["Weight"]
        .sum()
        .rename("CASH")
    )
    weights = ticker_weights.copy()
    weights["CASH"] = cash_weights
    weights = weights.fillna(0.0).sort_index()
    weights.index = pd.to_datetime(weights.index)
    weights = weights[weights.index.notnull()]
    weights = weights.div(weights.sum(axis=1), axis=0)
    active_tickers = [c for c in weights.columns if c != "CASH"]
    return weights, active_tickers


def chunked(iterable: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


def fetch_vni_components(conn: pyodbc.Connection) -> List[str]:
    query = "SELECT DISTINCT Ticker FROM dbo.Sector_Map WHERE VNI = 'Y'"
    df = pd.read_sql(query, conn)
    return sorted(df["Ticker"].dropna().astype(str).str.upper().unique())


def fetch_price_history(
    conn: pyodbc.Connection, tickers: Sequence[str], start_date: pd.Timestamp
) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()

    # SQL Server allows up to 2100 parameters per statement; chunk to be safe
    frames = []
    for subset in chunked(list(tickers), 200):
        placeholders = ",".join("?" for _ in subset)
        query = f"""
            SELECT TICKER, TRADE_DATE, PX_LAST
            FROM dbo.Market_Data
            WHERE TICKER IN ({placeholders})
              AND TRADE_DATE >= ?
        """
        params = list(subset) + [start_date.date()]
        frames.append(
            pd.read_sql(query, conn, params=params, parse_dates=["TRADE_DATE"])
        )
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    pivot = (
        df.pivot_table(index="TRADE_DATE", columns="TICKER", values="PX_LAST")
        .sort_index()
        .ffill()
    )
    return pivot


def fetch_benchmark_caps(
    conn: pyodbc.Connection, tickers: Sequence[str], start_date: pd.Timestamp
) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    frames = []
    for subset in chunked(list(tickers), 200):
        placeholders = ",".join("?" for _ in subset)
        query = f"""
            SELECT
                TICKER,
                CAST(TRADE_DATE AS DATE) AS TRADE_DATE,
                MKT_CAP
            FROM dbo.Market_Data
            WHERE TICKER IN ({placeholders})
              AND TRADE_DATE >= ?
        """
        params = list(subset) + [start_date.date()]
        frames.append(
            pd.read_sql(query, conn, params=params, parse_dates=["TRADE_DATE"])
        )
    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["MKT_CAP"])
    pivot = (
        df.pivot_table(
            index="TRADE_DATE", columns="TICKER", values="MKT_CAP", aggfunc="last"
        )
        .sort_index()
        .ffill()
    )
    return pivot


def fetch_vnindex(conn: pyodbc.Connection, start_date: pd.Timestamp) -> pd.DataFrame:
    query = """
        SELECT TRADINGDATE, INDEXVALUE
        FROM dbo.MarketIndex
        WHERE COMGROUPCODE = 'VNINDEX'
          AND TRADINGDATE >= ?
        ORDER BY TRADINGDATE ASC
    """
    df = pd.read_sql(
        query, conn, params=[start_date.date()], parse_dates=["TRADINGDATE"]
    )
    df = df.rename(columns={"TRADINGDATE": "TRADE_DATE"}).set_index("TRADE_DATE")
    return df.sort_index()


def simulate_portfolio(
    weights: pd.DataFrame, price_history: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    portfolio_cols = [c for c in weights.columns if c != "CASH"]
    common_cols = [c for c in portfolio_cols if c in price_history.columns]
    if not common_cols:
        raise ValueError("No overlapping tickers between weights and price history.")
    prices = price_history[common_cols].loc[price_history.index >= weights.index.min()]

    units = pd.Series(0.0, index=common_cols)
    cash_balance = 0.0
    rebalance_dates = list(weights.index)
    rebalance_idx = 0
    records = []
    weight_records = []

    for date, px in prices.iterrows():
        while rebalance_idx < len(rebalance_dates) and date >= rebalance_dates[rebalance_idx]:
            target_date = rebalance_dates[rebalance_idx]
            portfolio_value = float((units * px).sum() + cash_balance)
            if rebalance_idx == 0:
                portfolio_value = 100.0
            target_weights = weights.loc[target_date]
            cash_balance = portfolio_value * target_weights.get("CASH", 0.0)
            for ticker in common_cols:
                weight = target_weights.get(ticker, 0.0)
                allocation = portfolio_value * weight
                price = px[ticker]
                units[ticker] = allocation / price if price and not np.isnan(price) else 0.0
            rebalance_idx += 1
        portfolio_value = float((units * px).sum() + cash_balance)
        weights_today = (units * px) / portfolio_value
        weights_today = weights_today.reindex(common_cols, fill_value=0.0)
        records.append((date, portfolio_value, cash_balance))
        weight_records.append(weights_today)

    portfolio = pd.DataFrame(
        records, columns=["TRADE_DATE", "PortfolioValue", "CashBalance"]
    ).set_index("TRADE_DATE")
    portfolio["PortfolioIndex"] = (
        portfolio["PortfolioValue"] / portfolio["PortfolioValue"].iloc[0] * 100
    )
    weight_df = pd.DataFrame(weight_records, index=portfolio.index, columns=common_cols)
    return portfolio, weight_df


def simulate_static_portfolio(
    weights: pd.DataFrame, price_history: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Simulate the initial portfolio without any subsequent rebalancing."""
    if weights.empty:
        raise ValueError("Weights dataframe is empty.")
    initial_weights = weights.iloc[0]
    start_date = weights.index.min()
    tickers = [c for c in initial_weights.index if c != "CASH"]
    common_cols = [t for t in tickers if t in price_history.columns]
    if not common_cols:
        raise ValueError("No overlapping tickers for static portfolio simulation.")
    prices = price_history[common_cols].loc[price_history.index >= start_date]
    if start_date not in prices.index:
        raise ValueError("Price history missing the initial rebalance date.")

    start_prices = prices.loc[start_date]
    portfolio_value = 100.0
    cash_balance = portfolio_value * initial_weights.get("CASH", 0.0)
    units = pd.Series(0.0, index=common_cols)
    for ticker in common_cols:
        weight = initial_weights.get(ticker, 0.0)
        allocation = portfolio_value * weight
        price = start_prices[ticker]
        units[ticker] = allocation / price if price and not np.isnan(price) else 0.0

    records = []
    weight_records = []
    for date, px in prices.iterrows():
        portfolio_value = float((units * px).sum() + cash_balance)
        weights_today = (units * px) / portfolio_value
        weights_today = weights_today.reindex(common_cols, fill_value=0.0)
        records.append((date, portfolio_value, cash_balance))
        weight_records.append(weights_today)

    portfolio = pd.DataFrame(
        records, columns=["TRADE_DATE", "PortfolioValue", "CashBalance"]
    ).set_index("TRADE_DATE")
    portfolio["PortfolioIndex"] = (
        portfolio["PortfolioValue"] / portfolio["PortfolioValue"].iloc[0] * 100
    )
    weight_df = pd.DataFrame(weight_records, index=portfolio.index, columns=common_cols)
    return portfolio, weight_df


def main() -> None:
    weights, portfolio_tickers = load_rebalance_weights()
    start_date = weights.index.min()
    ensure_env()
    with get_connection() as conn:
        vni_tickers = fetch_vni_components(conn)
        all_tickers = sorted(set(portfolio_tickers) | set(vni_tickers))
        price_history = fetch_price_history(conn, all_tickers, start_date)
        vnindex = fetch_vnindex(conn, start_date)
        market_caps = fetch_benchmark_caps(conn, vni_tickers, start_date)

    portfolio, daily_weights = simulate_portfolio(weights, price_history)
    baseline_portfolio, baseline_weights = simulate_static_portfolio(weights, price_history)

    aligned_prices = price_history.reindex(portfolio.index).ffill()
    ticker_returns = aligned_prices.pct_change()

    portfolio_weights = daily_weights.reindex(columns=all_tickers, fill_value=0.0)
    avg_port_weights = portfolio_weights.expanding(min_periods=1).mean()

    benchmark_weights = (
        market_caps.reindex(portfolio.index).ffill().fillna(0.0)
    )
    benchmark_weights = benchmark_weights.div(
        benchmark_weights.sum(axis=1), axis=0
    ).fillna(0.0)
    benchmark_weights = benchmark_weights.reindex(columns=all_tickers, fill_value=0.0)
    avg_bench_weights = benchmark_weights.expanding(min_periods=1).mean()

    avg_active_weights = avg_port_weights - avg_bench_weights

    baseline_weights = baseline_weights.reindex(columns=all_tickers, fill_value=0.0)
    baseline_weights = baseline_weights.reindex(portfolio.index).ffill()
    avg_baseline_weights = baseline_weights.expanding(min_periods=1).mean()
    avg_active_weights_base = avg_port_weights - avg_baseline_weights

    vnindex = vnindex.reindex(portfolio.index).ffill()
    benchmark_returns = vnindex["INDEXVALUE"].pct_change().rename("BenchmarkReturn")
    active_returns = ticker_returns.sub(benchmark_returns, axis=0)
    baseline_returns = (
        baseline_portfolio.reindex(portfolio.index)["PortfolioValue"]
        .pct_change()
        .rename("BaselineReturn")
    )
    active_returns_base = ticker_returns.sub(baseline_returns, axis=0)

    attribution = avg_active_weights * active_returns
    attribution_base = avg_active_weights_base * active_returns_base

    def stack_df(df: pd.DataFrame, name: str) -> pd.Series:
        return df.stack(dropna=False).rename(name)

    result = pd.concat(
        [
            stack_df(avg_port_weights, "AvgPortfolioWeightYTD"),
            stack_df(avg_bench_weights, "AvgBenchmarkWeightYTD"),
            stack_df(avg_active_weights, "ActiveWeightYTD"),
            stack_df(ticker_returns, "TickerReturn"),
            stack_df(active_returns, "ActiveReturn"),
            stack_df(attribution, "Attribution"),
            stack_df(avg_baseline_weights, "AvgBaselineWeightYTD"),
            stack_df(avg_active_weights_base, "ActiveWeightVsOriginal"),
            stack_df(active_returns_base, "ActiveReturnVsOriginal"),
            stack_df(attribution_base, "AttributionVsOriginal"),
        ],
        axis=1,
    ).reset_index().rename(columns={"level_0": "TRADE_DATE", "level_1": "Ticker"})

    result["BenchmarkReturn"] = benchmark_returns.reindex(result["TRADE_DATE"]).values
    result["BaselineReturn"] = baseline_returns.reindex(result["TRADE_DATE"]).values
    result = result.dropna(subset=["Attribution"])

    analysis_dir = OUTPUT_PATH.parent
    analysis_dir.mkdir(exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)
    print(f"Saved daily attribution to {OUTPUT_PATH}")
    print(result.head())
    print(result.tail())


if __name__ == "__main__":
    main()
