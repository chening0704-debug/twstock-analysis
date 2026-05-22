# portfolio_excel.py — Excel 庫存讀取與結果回寫
import pandas as pd
import logging
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from db import upsert, get_conn, query

EXCEL_PATH  = Path("portfolio.xlsx")
SHEET_INPUT = "庫存輸入"
DATA_START  = 5


def load_portfolio_from_excel() -> int:
    """讀取 Excel 庫存表，驗證後寫入 my_portfolio"""
    if not EXCEL_PATH.exists():
        logging.warning(f"[Portfolio] 找不到 {EXCEL_PATH}，跳過")
        return 0
    try:
        wb = load_workbook(EXCEL_PATH, data_only=True)
        if SHEET_INPUT not in wb.sheetnames:
            logging.error(f"[Portfolio] 找不到工作表「{SHEET_INPUT}」")
            return 0
        ws = wb[SHEET_INPUT]
    except Exception as e:
        logging.error(f"[Portfolio] 開啟 Excel 失敗：{e}")
        return 0

    records, errors = [], []

    for row in ws.iter_rows(min_row=DATA_START, values_only=True):
        stock_id, stock_name, cost_price, shares, buy_date, market = (
            row[i] if i < len(row) else None for i in range(6)
        )

        if stock_id is None or str(stock_id).strip() == "":
            continue

        stock_id = str(stock_id).strip().zfill(4)

        if not stock_id.isdigit() or not (4 <= len(stock_id) <= 5):
            errors.append(f"代號格式錯誤：{stock_id}")
            continue

        try:
            cost_price = float(cost_price)
            if cost_price <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{stock_id} 成本錯誤：{cost_price}")
            continue

        try:
            shares = int(shares)
            if shares <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{stock_id} 張數錯誤：{shares}")
            continue

        if buy_date is not None:
            try:
                buy_date = pd.Timestamp(buy_date).strftime("%Y-%m-%d")
            except Exception:
                buy_date = None

        if market:
            market = str(market).split("（")[0].strip()

        records.append({
            "stock_id":   stock_id,
            "stock_name": str(stock_name).strip() if stock_name else stock_id,
            "cost_price": cost_price,
            "shares":     shares,
            "buy_date":   buy_date,
            "market":     market or "TSE",
            "note":       None,
        })

    if errors:
        for e in errors:
            logging.warning(f"  [Portfolio] 略過：{e}")

    if not records:
        logging.warning("[Portfolio] Excel 無有效庫存資料")
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM my_portfolio")

    upsert("my_portfolio", pd.DataFrame(records), pk=["stock_id"])
    logging.info(
        f"[Portfolio] 載入 {len(records)} 支持倉"
        + (f"，略過 {len(errors)} 筆" if errors else "")
    )
    return len(records)


def write_results_to_excel(portfolio_advice: list) -> None:
    """將分析結果回寫到 Excel G~J 欄"""
    if not EXCEL_PATH.exists() or not portfolio_advice:
        return
    try:
        wb = load_workbook(EXCEL_PATH)
        ws = wb[SHEET_INPUT]
    except Exception as e:
        logging.error(f"[Portfolio] 回寫開啟失敗：{e}")
        return

    advice_map = {a["stock_id"]: a for a in portfolio_advice}

    signal_colors = {
        "加碼": ("E8F8F5", "196F3D"),
        "持有": ("EBF5FB", "1A5276"),
        "觀察": ("F2F3F4", "555555"),
        "減碼": ("FEF9E7", "7D6608"),
        "出清": ("FEF0E7", "784212"),
        "停損": ("FDEDEC", "922B21"),
    }
    signal_label = {
        "加碼": "🟢 加碼",
        "持有": "🔵 持有",
        "觀察": "⚪ 觀察",
        "減碼": "🟡 減碼",
        "出清": "🟠 出清",
        "停損": "🔴 停損",
    }

    def hfill(c):
        return PatternFill("solid", fgColor=c)

    for row in ws.iter_rows(min_row=DATA_START):
        cell_a = row[0]
        if cell_a.value is None:
            continue
        sid = str(cell_a.value).strip().zfill(4)
        if sid not in advice_map:
            continue

        adv    = advice_map[sid]
        sig    = adv.get("signal", "觀察")
        bg, fg = signal_colors.get(sig, ("F2F3F4", "555555"))
        rn     = cell_a.row

        # G：現價
        g = ws[f"G{rn}"]
        g.value          = adv.get("current", "")
        g.number_format  = "#,##0.00"
        g.font           = Font(size=11, name="Arial")
        g.fill           = hfill("EAFAF1")
        g.alignment      = Alignment(
            horizontal="center", vertical="center"
        )

        # H：損益
        h   = ws[f"H{rn}"]
        pnl = adv.get("pnl_pct", 0) / 100
        h.value         = pnl
        h.number_format = "0.00%"
        h.font          = Font(
            bold=True, size=11, name="Arial",
            color="196F3D" if pnl >= 0 else "922B21"
        )
        h.fill      = hfill("EAFAF1" if pnl >= 0 else "FDEDEC")
        h.alignment = Alignment(
            horizontal="center", vertical="center"
        )

        # I：評分
        i_c             = ws[f"I{rn}"]
        i_c.value       = round(adv.get("score", 0), 1)
        i_c.font        = Font(bold=True, size=11, name="Arial")
        i_c.fill        = hfill("EBF5FB")
        i_c.alignment   = Alignment(
            horizontal="center", vertical="center"
        )

        # J：操作建議
        j           = ws[f"J{rn}"]
        j.value     = signal_label.get(sig, sig)
        j.font      = Font(
            bold=True, size=10, name="Arial", color=fg
        )
        j.fill      = hfill(bg)
        j.alignment = Alignment(
            horizontal="center", vertical="center"
        )

    last = DATA_START + 32
    ws[f"A{last}"] = "最後更新"
    ws[f"B{last}"] = pd.Timestamp.today().strftime("%Y-%m-%d %H:%M")
    for cell in [ws[f"A{last}"], ws[f"B{last}"]]:
        cell.font = Font(
            italic=True, size=9, color="888888", name="Arial"
        )

    try:
        wb.save(EXCEL_PATH)
        logging.info(f"[Portfolio] 結果回寫完成")
    except Exception as e:
        logging.error(f"[Portfolio] 回寫失敗：{e}")
