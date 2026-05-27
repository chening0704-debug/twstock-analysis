# main.py — GitHub Actions 主入口（完整版含深度分析）
import os
import sys
import logging
import datetime
import pandas as pd
from pathlib import Path

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
    logging.info("台股智能分析系統 v4.0 啟動")

    # Step 1：初始化 SQLite
    from db import init_db
    init_db()
    logging.info("SQLite 初始化完成")

    # Step 2：台灣時區開市判斷
    tw_tz    = datetime.timezone(datetime.timedelta(hours=8))
    now_tw   = datetime.datetime.now(tw_tz)
    today_tw = now_tw.date()
    weekday  = today_tw.weekday()
    wd_name  = ["一","二","三","四","五","六","日"][weekday]

    logging.info(
        f"台灣現在時間：{now_tw.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    logging.info(f"今天星期{wd_name}")

    if weekday >= 5:
        logging.info(f"今日週{wd_name}，系統不執行")
        Path("reports/skip.txt").write_text(
            f"{today_tw} 週末休市"
        )
        sys.exit(0)

    from market_calendar import MarketCalendarGuard
    guard = MarketCalendarGuard()
    if not guard.is_trading_day(today_tw):
        logging.info(f"今日 {today_tw} 國定假日，系統不執行")
        Path("reports/skip.txt").write_text(
            f"{today_tw} 國定假日休市"
        )
        sys.exit(0)

    logging.info(f"今日 {today_tw} 台股開市，開始執行")

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

    # Step 5：確認 price_volume 有資料
    if counts.get("price_volume", 0) == 0:
        from db import query
        check = query(
            "SELECT COUNT(*) as cnt "
            "FROM daily_price WHERE volume>0"
        )
        total = int(check["cnt"].iloc[0]) \
                if not check.empty else 0
        if total == 0:
            logging.error(
                "DB 完全無資料，"
                "TWSE 資料可能尚未更新，中止分析"
            )
            sys.exit(1)
        logging.warning(
            f"今日資料未更新，"
            f"使用 DB 現有 {total} 筆資料繼續"
        )

    # Step 6：五維 + RF 分析引擎
    from engine.scorer import run_analysis_engine
    results = run_analysis_engine()

    mode = results.get("mode", "")
    days = results.get("days", 0)

    # Step 7：深度分析（第6天起對十大推薦執行）
    deep_results = []
    if mode == "full" and not results["top10"].empty:
        logging.info("開始執行十大推薦深度分析（8大模組）...")
        try:
            from engine.deep_analysis import (
                run_deep_analysis_top10
            )
            deep_results = run_deep_analysis_top10(
                results["top10"]
            )
            logging.info(
                f"深度分析完成：{len(deep_results)} 支"
            )
        except Exception as e:
            logging.error(f"深度分析失敗：{e}")

    # Step 8：產出完整報告 HTML
    from engine.report_builder import (
        build_deep_report_html,
        save_report,
    )
    html = build_deep_report_html(
        top10            = results.get("top10", pd.DataFrame()),
        deep_results     = deep_results,
        portfolio_advice = results.get("portfolio", []),
        macro_score      = results.get("macro_score", 50),
        market_state     = results.get("market_state", "—"),
        mode             = mode,
        days             = days,
    )
    save_report(html)
    logging.info("HTML 報告已產出")

    # Step 9：累積期發通知信
    if mode == "accumulating":
        logging.info(f"資料累積期（第 {days} 天），發進度通知")
        _send_accumulating_email(days)
        sys.exit(0)

    # Step 10：回寫 Excel 庫存
    write_results_to_excel(results["portfolio"])

    # Step 11：推送完整報告
    from notifier import send_report
    send_report(results, html)

    logging.info("全部完成！")
    logging.info("=" * 50)


def _send_accumulating_email(days: int):
    import os, smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    eu = os.environ.get("EMAIL_USER",   "")
    ep = os.environ.get("EMAIL_PASS",   "")
    et = os.environ.get("EMAIL_TARGET", "")
    if not eu or not ep or not et:
        return

    pct   = min(int(days / 5 * 100), 100)
    today = datetime.date.today().strftime("%Y/%m/%d")

    html = f"""
<div style="font-family:Arial;max-width:500px;
            margin:0 auto;padding:24px;background:#f5f7fa">
  <div style="background:#1F3864;color:#fff;padding:20px;
              border-radius:10px 10px 0 0;text-align:center">
    <h2 style="margin:0">📊 台股分析系統｜資料累積中</h2>
    <p style="margin:6px 0 0;opacity:.8">{today}</p>
  </div>
  <div style="background:#fff;padding:24px;
              border-radius:0 0 10px 10px;text-align:center">
    <p style="color:#555;font-size:15px">
      系統正在累積歷史資料，進度如下：
    </p>
    <div style="font-size:48px;font-weight:700;
                color:#1A5276;margin:16px 0">
      第 {days} 天 / 5 天
    </div>
    <div style="background:#eee;border-radius:8px;
                height:14px;margin:0 20px 16px">
      <div style="background:#2E86C1;height:14px;
                  border-radius:8px;width:{pct}%"></div>
    </div>
    <p style="color:#888;font-size:13px">
      資料完整度 {pct}%<br>
      累積滿 5 個交易日後自動開始產出十大推薦<br>
      明日繼續累積，請耐心等待 🙏
    </p>
  </div>
</div>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"📊 台股系統累積進度 "
            f"第{days}天/5天 {today}"
        )
        msg["From"] = eu
        msg["To"]   = et
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(eu, ep)
            s.send_message(msg)
        logging.info("[accumulating] 進度通知信已發送")
    except Exception as e:
        logging.warning(f"[accumulating] 通知信失敗：{e}")


if __name__ == "__main__":
    main()
