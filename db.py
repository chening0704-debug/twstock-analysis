# db.py — SQLite 版本（GitHub Actions 雲端用）
import sqlite3
import pandas as pd
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path("data/twstock.db")

@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def query(sql: str) -> pd.DataFrame:
    with get_conn() as conn:
        try:
            return pd.read_sql_query(sql, conn)
        except Exception:
            return pd.DataFrame()

def upsert(table: str, df: pd.DataFrame, pk: list):
    if df.empty:
        return
    with get_conn() as conn:
        df.to_sql(f"_tmp_{table}", conn, if_exists="replace", index=False)
        cols = ", ".join(df.columns)
        conn.execute(f"""
            INSERT OR REPLACE INTO {table} ({cols})
            SELECT {cols} FROM _tmp_{table}
        """)
        conn.execute(f"DROP TABLE IF EXISTS _tmp_{table}")

def init_db():
    """建立所有資料表"""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS stock_universe (
            stock_id TEXT NOT NULL,
            stock_name TEXT,
            market TEXT NOT NULL,
            update_date TEXT NOT NULL,
            PRIMARY KEY (stock_id)
        );
        CREATE TABLE IF NOT EXISTS daily_price (
            stock_id TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume INTEGER,
            turnover_rate REAL,
            market TEXT,
            PRIMARY KEY (stock_id, date)
        );
        CREATE INDEX IF NOT EXISTS idx_price_date
            ON daily_price(date);
        CREATE TABLE IF NOT EXISTS institutional_netbuy (
            stock_id TEXT NOT NULL,
            date TEXT NOT NULL,
            foreign_net INTEGER,
            trust_net INTEGER,
            dealer_net INTEGER,
            total_net INTEGER,
            PRIMARY KEY (stock_id, date)
        );
        CREATE TABLE IF NOT EXISTS margin_balance (
            stock_id TEXT NOT NULL,
            date TEXT NOT NULL,
            margin_buy INTEGER,
            margin_sell INTEGER,
            margin_balance INTEGER,
            short_balance INTEGER,
            short_sell_borrow INTEGER,
            PRIMARY KEY (stock_id, date)
        );
        CREATE TABLE IF NOT EXISTS monthly_revenue (
            stock_id TEXT NOT NULL,
            year_month TEXT NOT NULL,
            revenue INTEGER,
            yoy REAL,
            mom REAL,
            PRIMARY KEY (stock_id, year_month)
        );
        CREATE TABLE IF NOT EXISTS quarterly_financial (
            stock_id TEXT NOT NULL,
            year_quarter TEXT NOT NULL,
            eps REAL, gross_margin REAL,
            op_margin REAL, net_margin REAL,
            roe REAL, roa REAL,
            debt_ratio REAL, fcf INTEGER,
            per REAL, pbr REAL,
            PRIMARY KEY (stock_id, year_quarter)
        );
        CREATE TABLE IF NOT EXISTS macro_daily (
            date TEXT PRIMARY KEY,
            vix REAL,
            usd_twd REAL,
            sox_chg_pct REAL,
            nvda_chg_pct REAL
        );
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id TEXT,
            stock_name TEXT,
            title TEXT,
            announce_time TEXT,
            date TEXT
        );
        CREATE TABLE IF NOT EXISTS daily_score (
            stock_id TEXT NOT NULL,
            date TEXT NOT NULL,
            score_fundamental REAL,
            score_technical REAL,
            score_chip REAL,
            score_macro REAL,
            score_news REAL,
            score_rule REAL,
            rf_prob_up REAL,
            rf_confidence REAL,
            score_total REAL,
            signal TEXT,
            target_price REAL,
            stop_loss REAL,
            optimal_weight REAL,
            PRIMARY KEY (stock_id, date)
        );
        CREATE INDEX IF NOT EXISTS idx_score_rank
            ON daily_score(date, score_total DESC);
        CREATE TABLE IF NOT EXISTS my_portfolio (
            stock_id TEXT PRIMARY KEY,
            stock_name TEXT,
            cost_price REAL NOT NULL,
            shares INTEGER NOT NULL,
            buy_date TEXT,
            market TEXT,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS rf_model_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            train_date TEXT,
            n_samples INTEGER,
            n_features INTEGER,
            accuracy REAL,
            precision_buy REAL,
            recall_buy REAL,
            f1_buy REAL,
            model_path TEXT
        );
        """)
