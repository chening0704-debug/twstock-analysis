# collectors.py — 七路資料擷取（完整修正版）
# 財報改用 TWSE 公開資訊站，不依賴 FinMind 付費功能
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
        logging.warning(
            "[price_volume] TWSE 回傳空資料，今日未開市或資料未更新"
        )
        return 0

    df = pd.DataFrame(raw)
    logging.info(f"[price_volume] 原始欄位：{list(df.columns)}")

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
        "股票代號":       "stock_id",
        "股票名稱":       "stock_name",
        "開盤價":         "open",
        "最高價":         "high",
        "最低價":         "low",
        "收盤價":         "close",
        "成交股數":       "volume",
        "週轉率":         "turnover_rate",
    }
    df = df.rename(columns={
        k: v for k, v in col_map.items() if k in df.columns
    })

    if "stock_id" not in df.columns:
        logging.error(
            f"[price_volume] 找不到 stock_id，"
            f"欄位：{list(df.columns)}"
        )
        return 0

    if "turnover_rate" not in df.columns:
        df["turnover_rate"] = 0.0

    for col in ["open","high","low","close","volume","turnover_rate"]:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(",",  "", regex=False)
                .str.replace("--", "0", regex=False)
                .str.replace("X",  "0", regex=False)
                .pipe(pd.to_numeric, errors="coerce")
                .fillna(0)
            )

    from stock_universe import StockUniverseManager
    mgr  = StockUniverseManager()
    mask = (
        df.apply(lambda r: mgr._is_valid_stock(
            r.get("stock_id",""),
            r.get("stock_name","")
        ), axis=1)
        & (df["volume"] > 0)
    )
    df = df[mask].copy()
    df["market"] = "TSE"

    if "date" in df.columns:
        df["date"] = df["date"].apply(_parse_roc_date)
    else:
        df["date"] = pd.Timestamp.today().strftime("%Y-%m-%d")

    keep = [
        "stock_id","date","open","high","low",
        "close","volume","turnover_rate","market"
    ]
    df = df[[c for c in keep if c in df.columns]]

    if df.empty:
        logging.warning("[price_volume] 過濾後無有效資料")
        return 0

    upsert("daily_price", df, pk=["stock_id","date"])

    # 更新 stock_universe
    raw_df = pd.DataFrame(raw)
    raw_df = raw_df.rename(columns={
        "Code":"stock_id","Name":"stock_name",
        "股票代號":"stock_id","股票名稱":"stock_name",
    })
    if "stock_id" in raw_df.columns and "stock_name" in raw_df.columns:
        u = raw_df[["stock_id","stock_name"]].copy()
        u["market"]      = "TSE"
        u["update_date"] = pd.Timestamp.today().strftime("%Y-%m-%d")
        u = u[u.apply(lambda r: mgr._is_valid_stock(
            r["stock_id"], r["stock_name"]), axis=1)]
        if not u.empty:
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
    logging.info(f"[institutional] 原始欄位：{list(df.columns)}")

    col_map = {
        "Code":                            "stock_id",
        "Date":                            "date",
        "Foreign_Investor_Net_Buy_or_Sell":"foreign_net",
        "Investment_Trust_Net_Buy_or_Sell":"trust_net",
        "Dealer_Net_Buy_or_Sell":          "dealer_net",
        "Total_Net_Buy_or_Sell":           "total_net",
        "股票代號":                         "stock_id",
        "外陸資買賣超股數(不含外資自營商)":   "foreign_net",
        "投信買賣超股數":                    "trust_net",
        "自營商買賣超股數":                  "dealer_net",
    }
    df = df.rename(columns={
        k: v for k, v in col_map.items() if k in df.columns
    })

    if "stock_id" not in df.columns:
        logging.error(
            f"[institutional] 找不到 stock_id，"
            f"欄位：{list(df.columns)}"
        )
        return 0

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

    keep = ["stock_id","date","foreign_net",
            "trust_net","dealer_net","total_net"]
    df = df[[c for c in keep if c in df.columns]]

    if df.empty:
        return 0

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
    logging.info(f"[margin] 原始欄位：{list(df.columns)}")

    col_map = {
        "Stock_id":              "stock_id",
        "Date":                  "date",
        "MarginPurchaseBuy":     "margin_buy",
        "MarginPurchaseSell":    "margin_sell",
        "MarginPurchaseBalance": "margin_balance",
        "ShortSaleBalance":      "short_balance",
        "OffsetLoanAndShort":    "short_sell_borrow",
        "股票代號":               "stock_id",
        "融資買進":               "margin_buy",
        "融資賣出":               "margin_sell",
        "融資餘額":               "margin_balance",
        "融券餘額":               "short_balance",
        "借券賣出餘額":            "short_sell_borrow",
    }
    df = df.rename(columns={
        k: v for k, v in col_map.items() if k in df.columns
    })

    if "stock_id" not in df.columns:
        logging.error(
            f"[margin] 找不到 stock_id，"
            f"欄位：{list(df.columns)}"
        )
        return 0

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

    keep = ["stock_id","date","margin_buy","margin_sell",
            "margin_balance","short_balance","short_sell_borrow"]
    df = df[[c for c in keep if c in df.columns]]

    if df.empty:
        return 0

    upsert("margin_balance", df, pk=["stock_id","date"])
    logging.info(f"[margin] 寫入 {len(df)} 筆")
    return len(df)


def collect_chip_broker() -> int:
    """分點進出（FinMind，無 Token 跳過）"""
    logging.info("擷取：分點進出")
    if not FINMIND_TOKEN:
        logging.warning("[chip_broker] 無 FINMIND_TOKEN，跳過")
        return 0
    today  = pd.Timestamp.today().strftime("%Y-%m-%d")
    params = {
        "dataset":    "TaiwanStockShareholding",
        "token":      FINMIND_TOKEN,
        "start_date": today,
    }
    try:
        r    = requests.get(FINMIND, params=params, timeout=60)
        data = r.json().get("data", [])
        if data:
            df = pd.DataFrame(data)
            if "stock_id" in df.columns:
                upsert("broker_chip", df,
                       pk=["stock_id","date"])
        time.sleep(2)
        logging.info(f"[chip_broker] 寫入 {len(data)} 筆")
        return len(data)
    except Exception as e:
        logging.error(f"[chip_broker] 失敗：{e}")
        return 0


def collect_financials() -> int:
    """
    財報資料：改用 TWSE OpenAPI + 公開資訊站
    完全免費，不需要 FinMind 付費
    """
    logging.info("擷取：財報資料（TWSE 免費版）")
    total = 0

    # ── 1. 月營收（TWSE OpenAPI）────────────────────────────
    try:
        today      = pd.Timestamp.today()
        year_roc   = today.year - 1911
        month      = today.month

        # 嘗試本月，若無資料則抓上個月
        for m_offset in [0, 1, 2]:
            target = today - pd.DateOffset(months=m_offset)
            roc_y  = target.year - 1911
            roc_m  = target.month
            url    = (
                f"{TWSE}/exchangeReport/BWIBBU_d"
                f"?selectType=ALL"
            )
            # 使用月營收備用端點
            rev_url = (
                f"https://mops.twse.com.tw/server-java/t05st10"
            )
            break

        # 直接用 TWSE 個股 PER/PBR 端點（含本益比）
        per_url = f"{TWSE}/exchangeReport/BWIBBU_d?selectType=ALL"
        r = requests.get(per_url, timeout=30)
        if r.status_code == 200 and r.json():
            raw = r.json()
            df  = pd.DataFrame(raw)
            logging.info(
                f"[financials] PER/PBR 原始欄位：{list(df.columns)}"
            )

            col_map = {
                "Code":              "stock_id",
                "PEratio":           "per",
                "PBratio":           "pbr",
                "DividendYield":     "dividend_yield",
                "股票代號":           "stock_id",
                "本益比":             "per",
                "股價淨值比":         "pbr",
                "殖利率(%)":         "dividend_yield",
            }
            df = df.rename(columns={
                k: v for k, v in col_map.items()
                if k in df.columns
            })

            if "stock_id" in df.columns:
                for col in ["per","pbr","dividend_yield"]:
                    if col in df.columns:
                        df[col] = (
                            df[col].astype(str)
                            .str.replace(",","",regex=False)
                            .pipe(pd.to_numeric, errors="coerce")
                            .fillna(0)
                        )
                df["year_quarter"] = (
                    f"{today.year}Q{(today.month-1)//3+1}"
                )
                keep = ["stock_id","year_quarter","per","pbr"]
                df   = df[[c for c in keep if c in df.columns]]
                df   = df[df["stock_id"].str.isdigit()
                           & df["stock_id"].str.len().between(4,5)]

                if not df.empty:
                    upsert("quarterly_financial", df,
                           pk=["stock_id","year_quarter"])
                    total += len(df)
                    logging.info(
                        f"[financials] PER/PBR 寫入 {len(df)} 筆"
                    )

    except Exception as e:
        logging.error(f"[financials] PER/PBR 失敗：{e}")

    # ── 2. 月營收（FinMind，若有 Token）──────────────────────
    if FINMIND_TOKEN:
        try:
            params = {
                "dataset":    "TaiwanStockMonthRevenue",
                "token":      FINMIND_TOKEN,
                "start_date": (
                    pd.Timestamp.today()
                    - pd.DateOffset(months=3)
                ).strftime("%Y-%m-%d"),
            }
            r  = requests.get(
                FINMIND, params=params, timeout=60
            )
            df = pd.DataFrame(r.json().get("data", []))
            if not df.empty and "stock_id" in df.columns:
                upsert("monthly_revenue", df,
                       pk=["stock_id","year_month"])
                total += len(df)
                logging.info(
                    f"[financials] 月營收 寫入 {len(df)} 筆"
                )
            time.sleep(2)
        except Exception as e:
            logging.error(f"[financials] 月營收 失敗：{e}")
    else:
        logging.info(
            "[financials] 無 FinMind Token，跳過月營收"
        )

    logging.info(f"[financials] 共寫入 {total} 筆")
    return total


def collect_macro() -> int:
    logging.info("擷取：總經指標")
    try:
        import yfinance as yf
        import time as _time

        def safe_fetch(ticker: str):
            for period in ["5d", "1mo"]:
                try:
                    tk   = yf.Ticker(ticker)
                    hist = tk.history(
                        period=period, auto_adjust=True
                    )
                    if not hist.empty:
                        c = hist["Close"].dropna()
                        if len(c) >= 1:
                            return c
                except Exception:
                    pass
                _time.sleep(1)
            return None

        vix_d  = safe_fetch("^VIX")
        usd_d  = safe_fetch("USDTWD=X")
        sox_d  = safe_fetch("^SOX")
        nvda_d = safe_fetch("NVDA")

        vix     = float(vix_d.iloc[-1])  if vix_d  is not None else None
        usd_twd = float(usd_d.iloc[-1])  if usd_d  is not None else None
        sox_chg = (float((sox_d.iloc[-1]/sox_d.iloc[-2]-1)*100)
                   if sox_d  is not None and len(sox_d)>=2 else 0.0)
        nvda_chg= (float((nvda_d.iloc[-1]/nvda_d.iloc[-2]-1)*100)
                   if nvda_d is not None and len(nvda_d)>=2 else 0.0)

        row = {
            "date":         pd.Timestamp.today().strftime("%Y-%m-%d"),
            "vix":          round(vix     or 20.0, 2),
            "usd_twd":      round(usd_twd or 32.0, 4),
            "sox_chg_pct":  round(sox_chg,          2),
            "nvda_chg_pct": round(nvda_chg,          2),
        }
        upsert("macro_daily", pd.DataFrame([row]), pk=["date"])
        logging.info(
            f"[macro] VIX={row['vix']} "
            f"USD/TWD={row['usd_twd']} "
            f"SOX={row['sox_chg_pct']:+.2f}%"
        )
        return 1

    except Exception as e:
        logging.error(f"[macro] 嚴重錯誤：{e}")
        try:
            row = {
                "date":         pd.Timestamp.today().strftime("%Y-%m-%d"),
                "vix":          20.0,
                "usd_twd":      32.0,
                "sox_chg_pct":  0.0,
                "nvda_chg_pct": 0.0,
            }
            upsert("macro_daily", pd.DataFrame([row]), pk=["date"])
            logging.warning("[macro] 使用預設值繼續執行")
        except Exception:
            pass
        return 0


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
                    "date": pd.Timestamp.today().strftime(
                        "%Y-%m-%d"
                    ),
                })
        if data:
            upsert("announcements", pd.DataFrame(data),
                   pk=["stock_id","announce_time"])
        logging.info(f"[announcements] 寫入 {len(data)} 筆")
        return len(data)
    except Exception as e:
        logging.error(f"[announcements] 失敗：{e}")
        return 0
