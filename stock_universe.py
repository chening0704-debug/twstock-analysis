# stock_universe.py — 全市場股票清單管理（TSE + OTC）
import requests
import pandas as pd
import re
import logging
from db import query, upsert

TWSE = "https://openapi.twse.com.tw/v1"
TPEX = "https://www.tpex.org.tw/openapi/v1"

ETF_KEYWORDS = [
    "ETF", "期貨", "反1", "槓桿", "債券",
    "基金", "外幣", "黃金", "石油", "指數",
]
EXCLUDE_PATTERNS = [
    r'^Y',
    r'^9',
    r'^\d{6}',
    r'[A-Z]$',
    r'^\d{4}[A-Z]',
]


class StockUniverseManager:

    def _is_valid_stock(self, code: str, name: str) -> bool:
        code = str(code).strip()
        name = str(name).strip()
        if not code.isdigit() or not (4 <= len(code) <= 5):
            return False
        if any(kw in name for kw in ETF_KEYWORDS):
            return False
        for pattern in EXCLUDE_PATTERNS:
            if re.search(pattern, code):
                return False
        code_int = int(code)
        if 6000 <= code_int <= 6999:
            return False
        return True

    def fetch_tse_stocks(self) -> pd.DataFrame:
        try:
            r = requests.get(
                f"{TWSE}/exchangeReport/STOCK_DAY_ALL",
                timeout=30
            )
            r.raise_for_status()
            df = pd.DataFrame(r.json())
            df = df.rename(columns={
                "Code": "stock_id",
                "Name": "stock_name",
            })
            df = df[["stock_id", "stock_name"]].copy()
            df["stock_id"] = df["stock_id"].str.strip()
            df["market"] = "TSE"
            mask = df.apply(
                lambda r: self._is_valid_stock(
                    r["stock_id"], r["stock_name"]
                ), axis=1
            )
            df = df[mask].reset_index(drop=True)
            logging.info(f"[Universe] TSE 有效普通股：{len(df)} 支")
            return df
        except Exception as e:
            logging.error(f"[Universe] TSE 清單失敗：{e}")
            return pd.DataFrame(
                columns=["stock_id", "stock_name", "market"]
            )

    def fetch_otc_stocks(self) -> pd.DataFrame:
        try:
            r = requests.get(
                f"{TPEX}/mopsfin/listOtcStockInfo",
                timeout=30
            )
            r.raise_for_status()
            records = []
            for item in r.json():
                code = str(
                    item.get("SecuritiesCompanyCode", "")
                ).strip()
                name = str(item.get("Company", "")).strip()
                if self._is_valid_stock(code, name):
                    records.append({
                        "stock_id":   code,
                        "stock_name": name,
                        "market":     "OTC",
                    })
            df = pd.DataFrame(records)
            logging.info(f"[Universe] OTC 有效普通股：{len(df)} 支")
            return df
        except Exception as e:
            logging.warning(f"[Universe] OTC 清單失敗：{e}，使用 DB 備援")
            return query(
                "SELECT DISTINCT stock_id, stock_name, market "
                "FROM stock_universe WHERE market='OTC'"
            )

    def get_full_universe(self, force_refresh: bool = False) -> pd.DataFrame:
        today = pd.Timestamp.today().strftime("%Y-%m-%d")
        if not force_refresh:
            cached = query(f"""
                SELECT stock_id, stock_name, market
                FROM stock_universe
                WHERE update_date = '{today}'
                ORDER BY stock_id
            """)
            if not cached.empty:
                logging.info(f"[Universe] 快取：{len(cached)} 支")
                return cached

        tse = self.fetch_tse_stocks()
        otc = self.fetch_otc_stocks()
        universe = pd.concat([tse, otc], ignore_index=True)
        universe = universe.drop_duplicates(subset=["stock_id"])
        universe["update_date"] = today
        upsert("stock_universe", universe, pk=["stock_id"])
        logging.info(
            f"[Universe] 完整清單：{len(universe)} 支"
            f"（TSE={len(tse)} OTC={len(otc)}）"
        )
        return universe

    def get_active_stocks_today(self) -> list:
        try:
            r = requests.get(
                f"{TWSE}/exchangeReport/STOCK_DAY_ALL",
                timeout=30
            )
            r.raise_for_status()
            df = pd.DataFrame(r.json())
            active = []
            for _, row in df.iterrows():
                code = str(row.get("Code", "")).strip()
                name = str(row.get("Name", "")).strip()
                vol  = str(
                    row.get("TradeVolume", "0")
                ).replace(",", "")
                try:
                    vol_int = int(vol)
                except Exception:
                    vol_int = 0
                if self._is_valid_stock(code, name) and vol_int > 0:
                    active.append(code)
            logging.info(f"[Universe] 今日有效成交：{len(active)} 支")
            return active
        except Exception as e:
            logging.error(f"[Universe] 今日有效個股查詢失敗：{e}")
            df = query("""
                SELECT DISTINCT stock_id FROM daily_price
                WHERE date = (SELECT MAX(date) FROM daily_price)
                AND volume > 0
            """)
            return df["stock_id"].tolist()
