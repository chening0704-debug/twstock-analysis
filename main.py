# main.py — GitHub Actions 主入口
import os
import sys
import logging
from datetime import date
from pathlib import Path

# 建立必要目錄
Path("logs").mkdir(exist_ok=True)
Path("data").mkdir(exist_ok=True)
Path("models").mkdir(exist_ok=True)
Path("reports").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("logs/analysis.log"),
        logging.StreamHandler(sys.stdout),
    ]
)


def main():
    logging.info("=" * 50)
    logging.info("台股智能分析系統 v3.0 啟動")

    # Step 1：初始化 SQLite
    from db import init_db
    init_db()
    logging.info("SQLite 初始化完成")

    # Step 2：開市判斷（三層驗證）
    from market_calendar import MarketCalendarGuard
    guard = MarketCalendarGuard()
    if not guard.is_trading_day():
        logging.info("今日台股休市，系統結束")
        Path("reports/skip.txt").write_text(
            f"{date.today()} 休市，系統不執行"
        )
        sys.exit(0)

    logging.info("今日開市，開始執行")

    # Step 3：讀取 Excel 庫存
    from portfolio_excel import (
        load_portfolio_from_excel,
        write_results_to_excel,
    )
    n = load_portfolio_from_excel()
    logging.info(f"庫存載入：{n} 支持倉")

    # Step 4：七路並行資料擷取
    from concurrent.futures import ThreadPoolExecutor
    from collectors import (
        collect_price_volume,
        collect_institutional,
        collect_margin,
        collect_chip_broker,
        collect_financials,
        collect_macro,
        collect_announcements,
    )

    with ThreadPoolExecutor(max_workers=4) as ex:
        tasks = {
            "price_volume":  ex.submit(collect_price_volume),
            "institutional": ex.submit(collect_institutional),
            "margin":        ex.submit(collect_margin),
            "chip_broker":   ex.submit(collect_chip_broker),
            "financials":    ex.submit(collect_financials),
            "macro":         ex.submit(collect_macro),
            "announcements": ex.submit(collect_announcements),
        }
        counts = {}
        for name, f in tasks.items():
            try:
                counts[name] = f.result()
                logging.info(f"  [{name}] 完成 {counts[name]} 筆")
            except Exception as e:
                logging.error(f"  [{name}] 失敗：{e}")
                counts[name] = 0

    # Step 5：守衛確認 price_volume 有資料
    if counts.get("price_volume", 0) == 0:
        logging.error("price_volume=0 筆，可能未開市，中止分析")
        sys.exit(1)

    # Step 6：五維 + RF 分析引擎
    from engine.scorer import run_analysis_engine
    results = run_analysis_engine()

    mode = results.get("mode", "")
    days = results.get("days", 0)

    if mode == "accumulating":
        logging.info(
            f"資料累積期（第 {days} 天），"
            f"不輸出推薦，明日繼續累積"
        )
        Path("reports/index.html").write_text(
            build_accumulating_page(days),
            encoding="utf-8"
        )
        sys.exit(0)

    # Step 7：回寫 Excel
    write_results_to_excel(results["portfolio"])

    # Step 8：推送報告
    from notifier import send_report
    send_report(results)

    logging.info("全部完成！")
    logging.info("=" * 50)


def build_accumulating_page(days: int) -> str:
    """資料累積期的佔位網頁"""
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3600">
<title>台股分析系統｜初始化中</title>
<style>
  body{{font-family:Arial,sans-serif;display:flex;
        align-items:center;justify-content:center;
        min-height:100vh;margin:0;background:#f5f7fa}}
  .card{{background:#fff;border-radius:16px;
         padding:48px 40px;text-align:center;
         box-shadow:0 4px 20px rgba(0,0,0,.08);
         max-width:480px}}
  h1{{color:#1F3864;font-size:22px;margin-bottom:12px}}
  .progress-wrap{{background:#eee;border-radius:8px;
                  height:12px;margin:24px 0}}
  .progress-bar{{background:#2E86C1;height:12px;
                 border-radius:8px;
                 width:{min(days/5*100, 100):.0f}%}}
  p{{color:#666;font-size:14px;line-height:1.6}}
  .day-badge{{display:inline-block;background:#EBF5FB;
              color:#1A5276;font-size:28px;font-weight:700;
              padding:12px 24px;border-radius:12px;
              margin:16px 0}}
</style>
</head>
<body>
<div class="card">
  <h1>📊 台股智能分析系統</h1>
  <p>系統正在累積歷史資料<br>累積滿 5 個交易日後自動開始分析</p>
  <div class="day-badge">第 {days} 天 / 5 天</div>
  <div class="progress-wrap">
    <div class="progress-bar"></div>
  </div>
  <p style="color:#999;font-size:12px">
    每日 23:30 自動執行，資料持續累積中<br>
    此頁面每小時自動重新整理
  </p>
</div>
</body>
</html>"""


if __name__ == "__main__":
    main()
