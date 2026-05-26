# main.py — GitHub Actions 主入口（完整修正版）
import os
import sys
import logging
import datetime
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

    # Step 2：台灣時區開市判斷
    tw_tz    = datetime.timezone(datetime.timedelta(hours=8))
    now_tw   = datetime.datetime.now(tw_tz)
    today_tw = now_tw.date()
    weekday  = today_tw.weekday()
    weekday_name = ["一","二","三","四","五","六","日"][weekday]

    logging.info(
        f"台灣現在時間：{now_tw.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    logging.info(f"今天星期{weekday_name}")

    # 週六日直接跳過
    if weekday >= 5:
        logging.info(f"今日為週{weekday_name}，系統不執行")
        Path("reports/skip.txt").write_text(
            f"{today_tw} 週末休市"
        )
        sys.exit(0)

    # 平日確認 TWSE 開市
    from market_calendar import MarketCalendarGuard
    guard = MarketCalendarGuard()
    if not guard.is_trading_day(today_tw):
        logging.info(f"今日 {today_tw} 為國定假日，系統不執行")
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
                logging.info(
                    f"  [{name}] 完成 {counts[name]} 筆"
                )
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
                "TWSE 資料可能尚未更新（請等下午4點後執行），"
                "中止分析"
            )
            sys.exit(1)
        logging.warning(
            f"今日資料未更新，"
            f"使用 DB 現有 {total} 筆資料繼續分析"
        )

    # Step 6：五維 + RF 分析引擎
    from engine.scorer import run_analysis_engine
    results = run_analysis_engine()

    mode = results.get("mode", "")
    days = results.get("days", 0)

    if mode == "accumulating":
        logging.info(
            f"資料累積期（第 {days} 天），"
            f"不輸出推薦"
        )
        Path("reports/index.html").write_text(
            build_accumulating_page(days),
            encoding="utf-8"
        )
        # 累積期也寄通知信
        send_accumulating_email(days)
        sys.exit(0)

    # Step 7：回寫 Excel
    write_results_to_excel(results["portfolio"])

    # Step 8：推送報告
    from notifier import send_report
    send_report(results)

    logging.info("全部完成！")
    logging.info("=" * 50)


def build_accumulating_page(days: int) -> str:
    pct = min(int(days / 5 * 100), 100)
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
         max-width:480px;width:90%}}
  h1{{color:#1F3864;font-size:22px;margin-bottom:8px}}
  p{{color:#666;font-size:14px;line-height:1.6;margin:8px 0}}
  .progress-wrap{{background:#eee;border-radius:8px;
                  height:14px;margin:20px 0}}
  .progress-bar{{background:#2E86C1;height:14px;
                 border-radius:8px;width:{pct}%;
                 transition:width 0.5s}}
  .day-badge{{display:inline-block;background:#EBF5FB;
              color:#1A5276;font-size:32px;font-weight:700;
              padding:14px 28px;border-radius:12px;margin:16px 0}}
  .note{{color:#999;font-size:12px;margin-top:20px}}
</style>
</head>
<body>
<div class="card">
  <h1>📊 台股智能分析系統</h1>
  <p>系統正在累積歷史資料<br>累積滿 5 個交易日後自動開始推薦</p>
  <div class="day-badge">第 {days} 天 / 5 天</div>
  <div class="progress-wrap">
    <div class="progress-bar"></div>
  </div>
  <p>資料完整度 {pct}%</p>
  <p class="note">每日 23:30 自動執行<br>此頁面每小時自動更新</p>
</div>
</body>
</html>"""


def send_accumulating_email(days: int):
    """資料累積期發送進度通知信"""
    import os, smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    email_user   = os.environ.get("EMAIL_USER","")
    email_pass   = os.environ.get("EMAIL_PASS","")
    email_target = os.environ.get("EMAIL_TARGET","")

    if not email_user or not email_pass or not email_target:
        return

    pct  = min(int(days/5*100), 100)
    today = datetime.date.today().strftime("%Y/%m/%d")

    html = f"""
    <div style="font-family:Arial;max-width:500px;margin:0 auto;
                padding:24px;background:#f5f7fa">
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
          累積滿 5 個交易日後自動開始產出十大推薦<br>
          明日繼續累積，請耐心等待 🙏
        </p>
      </div>
    </div>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📊 台股系統累積進度 第{days}天/5天 {today}"
        msg["From"]    = email_user
        msg["To"]      = email_target
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(email_user, email_pass)
            s.send_message(msg)
        logging.info("[accumulating] 進度通知信已發送")
    except Exception as e:
        logging.warning(f"[accumulating] 通知信發送失敗：{e}")


if __name__ == "__main__":
    main()
