# collectors.py — 七路資料擷取（含開市守衛）
import os
import requests
import pandas as pd
import time
import logging
from db import upsert, query

TWSE          = "https://openapi.twse.com.tw/v1"
FINMIND       = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")


def _parse_roc_date(s: str) -> str:
    """民國年 '1130520' → '2024-05-20'"""
    s = str(s).strip().replace("/", "")
    if len(s) == 7 and s.isdigit():
        return f"{int(s[:3])+1911}-{s[3:5]}-{s[5:7]}"
    return s


def _get_active_ids(date_str: str) -> set:
    try:
        df = query(
            f"SELECT stock_id FROM daily_price "
            f"WHERE date='{date_str}' AND volume>0"
        )
        return set(df["stock_id"].tolist())
    except Exception:
        return set()


def collect_price_volume() -> int:
    logging.info("擷取：當日股價量")
    try:
        r = requests.get(
            f"{TWSE}/exchangeReport/STOCK_DAY_ALL",
            timeout=30
        )
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        logging.error(f"[price_volume] 失敗：{e}")
        return 0

    if not raw or len(raw) == 0:
        logging.warning("[price_volume] TWSE 回傳空資料，今日未開市")
        return 0

    df = pd.DataFrame(raw)
    col_map = {
        "Code":          "stock_id",
        "Name":          "stock_name",
        "Date":          "date",
        "OpeningPrice":  "open",
        "HighestPrice":  "high",
        "LowestPrice":   "low",
        "ClosingPrice":  "close",
        "TradeVolume":   "volume",
        "TurnoverRatio": "turnover_rate",
    }
    df = df.rename(columns={
        k: v for k, v in col_map.items() if k in df.columns
    })

    for col in ["open","high","low","close","volume","turnover_rate"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("--", "0", regex=False)
                .pipe(pd.to_numeric, errors="coerce")
                .fillna(0)
            )

    from stock_universe import StockUniverseManager
    mgr  = StockUniverseManager()
    mask = (
        df.apply(lambda r: mgr._is_valid_stock(
            r.get("stock_id",""), r.get("stock_name","")), axis=1)
        & (df["volume"] > 0)
    )
    df = df[mask].copy()
    df["market"] = "TSE"

    if "date" in df.columns:
        df["date"] = df["date"].apply(_parse_roc_date)
    else:
        df["date"] = pd.Timestamp.today().strftime("%Y-%m-%d")

    keep = ["stock_id","stock_name","date","open","high",
            "low","close","volume","turnover_rate","market"]
    df = df[[c for c in keep if c in df.columns]]
    upsert("daily_price", df, pk=["stock_id","date"])

    u = df[["stock_id","stock_name"]].copy()
    u["market"]      = "TSE"
    u["update_date"] = pd.Timestamp.today().strftime("%Y-%m-%d")
    upsert("stock_universe", u, pk=["stock_id"])

    logging.info(f"[price_volume] 寫入 {len(df)} 筆")
    return len(df)


def collect_institutional() -> int:
    logging.info("擷取：三大法人")
    try:
        r = requests.get(f"{TWSE}/fund/T86", timeout=30)
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        logging.error(f"[institutional] 失敗：{e}")
        return 0
    if not raw:
        logging.warning("[institutional] 無資料，跳過")
        return 0

    df = pd.DataFrame(raw)
    col_map = {
        "Code":                            "stock_id",
        "Date":                            "date",
        "Foreign_Investor_Net_Buy_or_Sell":"foreign_net",
        "Investment_Trust_Net_Buy_or_Sell":"trust_net",
        "Dealer_Net_Buy_or_Sell":          "dealer_net",
        "Total_Net_Buy_or_Sell":           "total_net",
    }
    df = df.rename(columns={
        k: v for k, v in col_map.items() if k in df.columns
    })
    for col in ["foreign_net","trust_net","dealer_net","total_net"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(",","",regex=False)
                .pipe(pd.to_numeric, errors="coerce")
                .fillna(0).astype(int)
            )

    today  = pd.Timestamp.today().strftime("%Y-%m-%d")
    active = _get_active_ids(today)
    if active:
        df = df[df["stock_id"].isin(active)]
    if "date" in df.columns:
        df["date"] = df["date"].apply(_parse_roc_date)
    else:
        df["date"] = today

    upsert("institutional_netbuy", df, pk=["stock_id","date"])
    logging.info(f"[institutional] 寫入 {len(df)} 筆")
    return len(df)


def collect_margin() -> int:
    logging.info("擷取：融資融券")
    try:
        r = requests.get(
            f"{TWSE}/exchangeReport/MI_MARGN",
            timeout=30
        )
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        logging.error(f"[margin] 失敗：{e}")
        return 0
    if not raw:
        logging.warning("[margin] 無資料，跳過")
        return 0

    df = pd.DataFrame(raw)
    col_map = {
        "Stock_id":              "stock_id",
        "Date":                  "date",
        "MarginPurchaseBuy":     "margin_buy",
        "MarginPurchaseSell":    "margin_sell",
        "MarginPurchaseBalance": "margin_balance",
        "ShortSaleBalance":      "short_balance",
        "OffsetLoanAndShort":    "short_sell_borrow",
    }
    df = df.rename(columns={
        k: v for k, v in col_map.items() if k in df.columns
    })
    for col in ["margin_buy","margin_sell","margin_balance",
                "short_balance","short_sell_borrow"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(",","",regex=False)
                .pipe(pd.to_numeric, errors="coerce")
                .fillna(0).astype(int)
            )

    today  = pd.Timestamp.today().strftime("%Y-%m-%d")
    active = _get_active_ids(today)
    if active:
        df = df[df["stock_id"].isin(active)]
    if "date" in df.columns:
        df["date"] = df["date"].apply(_parse_roc_date)
    else:
        df["date"] = today

    upsert("margin_balance", df, pk=["stock_id","date"])
    logging.info(f"[margin] 寫入 {len(df)} 筆")
    return len(df)


def collect_chip_broker() -> int:
    logging.info("擷取：分點進出")
    if not FINMIND_TOKEN:
        logging.warning("[chip_broker] 無 FINMIND_TOKEN，跳過")
        return 0
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    params = {
        "dataset":    "TaiwanStockShareholding",
        "token":      FINMIND_TOKEN,
        "start_date": today,
    }
    try:
        r    = requests.get(FINMIND, params=params, timeout=60)
        data = r.json().get("data", [])
        if data:
            upsert("broker_chip", pd.DataFrame(data),
                   pk=["stock_id","date","broker_id"])
        time.sleep(2)
        logging.info(f"[chip_broker] 寫入 {len(data)} 筆")
        return len(data)
    except Exception as e:
        logging.error(f"[chip_broker] 失敗：{e}")
        return 0


def collect_financials() -> int:
    logging.info("擷取：月營收 / 財報")
    if not FINMIND_TOKEN:
        logging.warning("[financials] 無 FINMIND_TOKEN，跳過")
        return 0
    total = 0
    tasks = [
        ("TaiwanStockMonthRevenue",
         "monthly_revenue",
         ["stock_id","year_month"]),
        ("TaiwanStockFinancialStatements",
         "quarterly_financial",
         ["stock_id","year_quarter"]),
    ]
    for dataset, table, pk in tasks:
        params = {
            "dataset":    dataset,
            "token":      FINMIND_TOKEN,
            "start_date": "2022-01-01",
        }
        try:
            r  = requests.get(FINMIND, params=params, timeout=60)
            df = pd.DataFrame(r.json().get("data", []))
            if not df.empty:
                upsert(table, df, pk=pk)
                total += len(df)
            time.sleep(2)
        except Exception as e:
            logging.error(f"[financials] {dataset} 失敗：{e}")
    logging.info(f"[financials] 共寫入 {total} 筆")
    return total


def collect_macro() -> int:
    logging.info("擷取：總經指標")
    import yfinance as yf

    def safe_last(ticker):
        try:
            df = yf.download(ticker, period="5d", progress=False)
            return float(df["Close"].dropna().iloc[-1]) if not df.empty else None
        except Exception:
            return None

    def safe_pct(ticker):
        try:
            df = yf.download(ticker, period="5d", progress=False)
            c  = df["Close"].dropna()
            return float((c.iloc[-1]/c.iloc[-2]-1)*100) if len(c)>=2 else 0.0
        except Exception:
            return 0.0

    vix      = safe_last("^VIX")
    usd_twd  = safe_last("USDTWD=X")
    sox_chg  = safe_pct("^SOX")
    nvda_chg = safe_pct("NVDA")

    if vix is None and usd_twd is None:
        logging.warning("[macro] 總經資料不可用，跳過")
        return 0

    row = {
        "date":         pd.Timestamp.today().strftime("%Y-%m-%d"),
        "vix":          round(vix or 20.0, 2),
        "usd_twd":      round(usd_twd or 32.0, 4),
        "sox_chg_pct":  round(sox_chg, 2),
        "nvda_chg_pct": round(nvda_chg, 2),
    }
    upsert("macro_daily", pd.DataFrame([row]), pk=["date"])
    logging.info(
        f"[macro] VIX={row['vix']} USD/TWD={row['usd_twd']}"
    )
    return 1


def collect_announcements() -> int:
    logging.info("擷取：重大訊息")
    from bs4 import BeautifulSoup
    try:
        r = requests.post(
            "https://mops.twse.com.tw/mops/web/t05sr01",
            data={"step":"1","firstin":"1","off":"1"},
            timeout=30
        )
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select("table.hasBorder tr")[1:]
        data = []
        for row in rows:
            cols = row.select("td")
            if len(cols) >= 4:
                data.append({
                    "stock_id":      cols[0].text.strip(),
                    "stock_name":    cols[1].text.strip(),
                    "title":         cols[2].text.strip(),
                    "announce_time": cols[3].text.strip(),
                    "date":          pd.Timestamp.today().strftime("%Y-%m-%d"),
                })
        if data:
            upsert("announcements", pd.DataFrame(data),
                   pk=["stock_id","announce_time"])
        logging.info(f"[announcements] 寫入 {len(data)} 筆")
        return len(data)
    except Exception as e:
        logging.error(f"[announcements] 失敗：{e}")
        return 0
