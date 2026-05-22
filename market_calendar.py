# market_calendar.py — 開市判斷守衛（三層驗證）
import requests
import pandas as pd
import logging
from datetime import date, timedelta

TWSE = "https://openapi.twse.com.tw/v1"


class MarketCalendarGuard:

    @staticmethod
    def _is_weekend(d: date) -> bool:
        return d.weekday() >= 5

    def _fetch_official_holidays(self, year: int) -> set:
        try:
            r = requests.get(
                f"{TWSE}/holidaySchedule/holidaySchedule",
                timeout=10
            )
            r.raise_for_status()
            holidays = set()
            for item in r.json():
                raw = item.get("Date", "")
                if len(raw) == 7:
                    ad_y = int(raw[:3]) + 1911
                    holidays.add(f"{ad_y}-{raw[3:5]}-{raw[5:7]}")
            logging.info(f"[MarketCalendar] 取得 {len(holidays)} 個休市日")
            return holidays
        except Exception as e:
            logging.warning(f"[MarketCalendar] 官方行事曆失敗：{e}")
            return set()

    def _confirm_by_volume(self, target_date: date):
        try:
            date_str = target_date.strftime("%Y%m%d")
            r = requests.get(
                f"{TWSE}/exchangeReport/FMTQIK?date={date_str}",
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                return isinstance(data, list) and len(data) > 0
            elif r.status_code == 404:
                return False
            return None
        except Exception as e:
            logging.warning(f"[MarketCalendar] 成交量確認失敗：{e}")
            return None

    def is_trading_day(self, target_date: date = None) -> bool:
        if target_date is None:
            target_date = date.today()

        # Layer A：週末
        if self._is_weekend(target_date):
            logging.info(f"[MarketCalendar] {target_date} 週末，休市")
            return False

        # Layer B：官方行事曆
        holidays = self._fetch_official_holidays(target_date.year)
        if holidays:
            date_str = target_date.strftime("%Y-%m-%d")
            if date_str in holidays:
                logging.info(f"[MarketCalendar] {target_date} 官方假日，休市")
                return False
            confirmed = self._confirm_by_volume(target_date)
            if confirmed is False:
                logging.warning(
                    f"[MarketCalendar] {target_date} 無成交資料，休市"
                )
                return False
            return True

        # Layer C：純靠成交量判斷
        confirmed = self._confirm_by_volume(target_date)
        if confirmed is True:
            return True
        if confirmed is False:
            logging.info(f"[MarketCalendar] {target_date} 無成交資料，休市")
            return False
        logging.warning(f"[MarketCalendar] {target_date} 無法確認，保守判定交易日")
        return True

    def get_last_trading_day(self, from_date: date = None) -> date:
        if from_date is None:
            from_date = date.today()
        for i in range(1, 11):
            candidate = from_date - timedelta(days=i)
            if self.is_trading_day(candidate):
                return candidate
        raise RuntimeError("無法找到最近交易日（已回溯 10 天）")

    def get_trading_days_count_in_db() -> int:
        """查詢 DB 中已累積的交易日數量"""
        try:
            from db import query
            df = query("""
                SELECT COUNT(DISTINCT date) as cnt
                FROM daily_price
                WHERE volume > 0
            """)
            return int(df["cnt"].iloc[0]) if not df.empty else 0
        except Exception:
            return 0
