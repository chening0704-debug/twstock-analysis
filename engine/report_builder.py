# engine/report_builder.py — 每日報告產生器 v6
import pandas as pd
from pathlib import Path
from engine.flying_stock_report import (
    build_flying_stock_html,
    build_flying_stock_email_section,
)


def _build_diagnosis_html(learning: dict) -> str:
    """產出自我學習診斷區塊"""
    if not learning:
        return ""

    bt      = learning.get("backtest", {})
    weights = learning.get("weights", {})
    diag    = learning.get("diagnosis", {})

    win_rate = bt.get("win_rate", None)
    total    = bt.get("total", 0)
    hits     = bt.get("hits", 0)

    # 權重視覺化
    weight_bars = ""
    colors = {
        "fundamental": "#2E86C1",
        "technical":   "#1D9E75",
        "chip":        "#BA7517",
        "macro":       "#7F77DD",
        "news":        "#D85A30",
        "flying":      "#085041",
        "advanced":    "#1A5276",
    }
    labels = {
        "fundamental": "基本面",
        "technical":   "技術面",
        "chip":        "籌碼面",
        "macro":       "總經面",
        "news":        "消息面",
        "flying":      "飆股基因",
        "advanced":    "進階技術",
    }
    for key, val in weights.items():
        color = colors.get(key, "#888")
        label = labels.get(key, key)
        pct   = round(val * 100, 1)
        weight_bars += f"""
        <div style="display:flex;align-items:center;
                    gap:8px;margin-bottom:5px;font-size:12px">
          <span style="width:70px;color:#666">{label}</span>
          <div style="flex:1;height:8px;background:#EEE;
                      border-radius:4px;overflow:hidden">
            <div style="width:{pct*2}%;height:8px;
                        background:{color};border-radius:4px">
            </div>
          </div>
          <span style="width:36px;text-align:right;
                       font-weight:500;color:#444">
            {pct}%
          </span>
        </div>"""

    # 回測結果
    bt_html = ""
    if win_rate is not None:
        color = "#196F3D" if win_rate >= 0.5 else "#922B21"
        bt_html = f"""
        <div style="display:flex;gap:16px;flex-wrap:wrap;
                    margin-bottom:14px">
          <div style="background:#F0F4F8;border-radius:8px;
                      padding:10px 14px;text-align:center">
            <div style="font-size:11px;color:#888;
                        margin-bottom:4px">昨日推薦勝率</div>
            <div style="font-size:22px;font-weight:500;
                        color:{color}">
              {win_rate:.0%}
            </div>
            <div style="font-size:11px;color:#888">
              {hits}/{total} 筆命中
            </div>
          </div>
          <div style="flex:1;background:#F0F4F8;
                      border-radius:8px;padding:10px 14px">
            <div style="font-size:11px;color:#888;
                        margin-bottom:6px">回測詳情</div>
            {''.join([
                f'<div style="font-size:12px;color:#444;'
                f'margin-bottom:2px">'
                f'{d["stock_id"]} '
                f'<span style="color:{"#196F3D" if d["hit"] else "#922B21"}">'
                f'{"✅" if d["hit"] else "❌"} '
                f'{d["actual_chg"]:+.1f}%</span></div>'
                for d in bt.get("details", [])
            ])}
          </div>
        </div>"""

    # 診斷建議
    suggestions_html = ""
    if diag.get("suggestions"):
        items = "".join([
            f'<div style="font-size:12px;color:#444;'
            f'padding:3px 0;border-bottom:0.5px solid #EEE">'
            f'💡 {s}</div>'
            for s in diag["suggestions"]
        ])
        suggestions_html = f"""
        <div style="margin-top:12px">
          <div style="font-size:13px;font-weight:500;
                      color:#1F3864;margin-bottom:8px">
            系統診斷建議
          </div>
          {items}
        </div>"""

    return f"""
    <div style="background:#fff;border-radius:16px;
                padding:20px 24px;margin-bottom:28px;
                box-shadow:0 2px 8px rgba(0,0,0,.07)">
      <div style="font-size:16px;font-weight:600;
                  color:#1F3864;margin-bottom:16px;
                  border-left:4px solid #2E86C1;
                  padding-left:10px">
        🧠 自我學習引擎｜昨日驗證 + 今日權重
      </div>
      {bt_html}
      <div style="font-size:13px;font-weight:500;
                  color:#1F3864;margin-bottom:10px">
        當前自適應權重（系統自動調整中）
      </div>
      {weight_bars}
      {suggestions_html}
    </div>"""


def build_deep_report_html(
    top10:            pd.DataFrame,
    deep_results:     list,
    portfolio_advice: list,
    macro_score:      float,
    market_state:     str,
    mode:             str = "full",
    days:             int = 0,
    top_flying:       list = None,
    flying_scan:      list = None,
    learning:         dict = None,
    intl_linkage:     dict = None,
    adapt_weights:    dict = None,
) -> str:

    today       = pd.Timestamp.today().strftime("%Y/%m/%d")
    top_flying  = top_flying  or []
    flying_scan = flying_scan or []
    learning    = learning    or {}
    intl_linkage= intl_linkage or {}

    css = """
    <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:Arial,sans-serif;background:#F0F4F8;
         color:#2D3748;line-height:1.6}
    .container{max-width:1100px;margin:0 auto;padding:20px}
    .header{background:linear-gradient(135deg,#1F3864,#2E86C1);
            color:#fff;padding:28px 32px;border-radius:16px;
            margin-bottom:24px}
    .header h1{font-size:24px;margin-bottom:6px}
    .header .meta{font-size:13px;opacity:.8}
    .header .stats{display:flex;gap:12px;
                   margin-top:14px;flex-wrap:wrap}
    .stat{background:rgba(255,255,255,.15);
          padding:8px 14px;border-radius:8px;
          font-size:13px;text-align:center;min-width:80px}
    .stat b{font-size:18px;display:block;margin-bottom:2px}
    .sec-title{font-size:18px;font-weight:600;color:#1F3864;
               border-left:4px solid #2E86C1;
               padding-left:12px;margin:28px 0 16px}
    .top10-grid{display:grid;
                grid-template-columns:repeat(auto-fill,
                  minmax(320px,1fr));
                gap:16px;margin-bottom:24px}
    .scard{background:#fff;border-radius:12px;
           padding:16px 18px;
           box-shadow:0 2px 8px rgba(0,0,0,.07);
           border-top:4px solid #2E86C1}
    .scard.flying{border-top:4px solid #1D9E75}
    .scard .rank{font-size:12px;color:#888;margin-bottom:4px}
    .scard .sname{font-size:17px;font-weight:600;
                  color:#1F3864;margin-bottom:10px}
    .srow{display:flex;align-items:center;gap:8px;
          margin-bottom:5px;font-size:12px}
    .slbl{width:30px;color:#888}
    .strk{flex:1;height:6px;background:#EEE;
          border-radius:3px;overflow:hidden}
    .sfil{height:6px;border-radius:3px}
    .snum{width:28px;text-align:right;
          font-weight:600;color:#444}
    .cfoot{display:flex;gap:5px;flex-wrap:wrap;
           margin-top:10px;font-size:11px}
    .tag{padding:2px 7px;border-radius:10px;font-weight:500}
    .tg{background:#E8F8F5;color:#196F3D}
    .tb{background:#EBF5FB;color:#1A5276}
    .tr{background:#FDEDEC;color:#922B21}
    .ty{background:#FEF9E7;color:#7D6608}
    .tfly{background:#E1F5EE;color:#085041}
    .tchain{background:#EEEDFE;color:#3C3489}
    .deep-sec{background:#fff;border-radius:16px;
              padding:24px 28px;margin-bottom:28px;
              box-shadow:0 2px 12px rgba(0,0,0,.07)}
    .dhead{display:flex;align-items:center;gap:12px;
           margin-bottom:20px;padding-bottom:14px;
           border-bottom:1px solid #EEE;flex-wrap:wrap}
    .dbadge{background:#1F3864;color:#fff;
            padding:6px 14px;border-radius:8px;
            font-size:15px;font-weight:600}
    .dinfo h2{font-size:18px;color:#1F3864}
    .dinfo p{font-size:13px;color:#888;margin-top:2px}
    .dgrid{display:grid;
           grid-template-columns:repeat(auto-fill,
             minmax(120px,1fr));
           gap:8px;margin-top:14px}
    .ditem{background:#F0F4F8;border-radius:8px;
           padding:8px;text-align:center}
    .dlbl{font-size:10px;color:#888;margin-bottom:3px}
    .dval{font-size:14px;font-weight:600;color:#1F3864}
    .mgrid{display:grid;
           grid-template-columns:repeat(auto-fill,
             minmax(440px,1fr));
           gap:14px;margin-top:16px}
    .mcard{background:#F8FAFE;border:1px solid #E8EDF5;
           border-radius:10px;padding:14px}
    .mtitle{font-size:13px;font-weight:600;
            color:#2E86C1;margin-bottom:8px}
    .mcontent{font-size:12px;color:#444;
              line-height:1.7;white-space:pre-line}
    .ptable{width:100%;border-collapse:collapse;
            background:#fff;border-radius:12px;
            overflow:hidden;
            box-shadow:0 2px 8px rgba(0,0,0,.07)}
    .ptable th{background:#1F3864;color:#fff;
               padding:10px 12px;text-align:left;
               font-size:12px}
    .ptable td{padding:10px 12px;
               border-bottom:1px solid #F0F4F8;
               font-size:12px}
    .ptable tr:hover{background:#F8FAFE}
    .pp{color:#196F3D;font-weight:600}
    .pn{color:#922B21;font-weight:600}
    .accumulate{background:#fff;border-radius:16px;
                padding:48px 40px;text-align:center;
                box-shadow:0 4px 20px rgba(0,0,0,.08);
                max-width:480px;margin:40px auto}
    .footer{text-align:center;color:#AAA;font-size:12px;
            margin-top:32px;padding-bottom:20px}
    @media(max-width:600px){
      .mgrid{grid-template-columns:1fr}
      .top10-grid{grid-template-columns:1fr}
    }
    </style>"""

    if mode == "accumulating":
        pct = min(int(days / 5 * 100), 100)
        return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3600">
<title>台股分析系統｜初始化中</title>
{css}
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📊 台股智能分析系統 v6</h1>
    <div class="meta">{today}</div>
  </div>
  <div class="accumulate">
    <h2>系統正在累積歷史資料</h2>
    <p style="color:#555;margin-bottom:8px">
      累積滿 5 個交易日後自動開始推薦
    </p>
    <div style="font-size:40px;font-weight:700;
                color:#1A5276;margin:16px 0">
      第 {days} 天 / 5 天
    </div>
    <div style="background:#eee;border-radius:8px;
                height:12px;margin:16px 20px">
      <div style="background:#2E86C1;height:12px;
                  border-radius:8px;width:{pct}%"></div>
    </div>
    <p style="color:#888;font-size:13px">
      資料完整度 {pct}%<br>
      每日 23:30 自動執行，此頁面每小時更新
    </p>
  </div>
</div>
</body>
</html>"""

    sig_tag = {
        "BUY":  ("tg","✅ BUY"),
        "BUY*": ("tb","🟩 BUY*"),
        "HOLD": ("tb","💙 HOLD"),
        "SELL": ("ty","⚠️ SELL"),
        "CUT":  ("tr","🚨 CUT"),
    }

    flying_ids  = {r["stock_id"] for r in top_flying}

    # 十大推薦卡片
    top10_cards = ""
    if not top10.empty:
        for i, (_, row) in enumerate(top10.iterrows()):
            sc, sl   = sig_tag.get(
                row.get("signal","HOLD"), ("tb","💙 HOLD")
            )
            is_flying = row["stock_id"] in flying_ids
            bars = ""
            for lbl, key, color in [
                ("基","score_fundamental","#2E86C1"),
                ("技","score_technical",  "#1D9E75"),
                ("籌","score_chip",       "#BA7517"),
            ]:
                val = float(row.get(key, 0) or 0)
                bars += f"""
                <div class="srow">
                  <span class="slbl">{lbl}</span>
                  <div class="strk">
                    <div class="sfil"
                      style="width:{val}%;background:{color}">
                    </div>
                  </div>
                  <span class="snum">{val:.0f}</span>
                </div>"""

            total  = float(row.get("score_total",   0) or 0)
            rf     = float(row.get("rf_prob_up",    0) or 0)*100
            tgt    = float(row.get("target_price",  0) or 0)
            sl_p   = float(row.get("stop_loss",     0) or 0)
            fly_s  = float(row.get("flying_score",  0) or 0)
            adv_s  = float(row.get("advanced_score",0) or 0)
            ind    = str(row.get("industry",        ""))
            themes = str(row.get("themes",          ""))

            fly_tag = ""
            if fly_s >= 75:
                fly_tag = (
                    f'<span class="tag tfly">'
                    f'🧬 飆股{fly_s:.0f}</span>'
                )
            elif fly_s >= 60:
                fly_tag = (
                    f'<span class="tag tg">'
                    f'🧬{fly_s:.0f}</span>'
                )

            ind_tag = (
                f'<span class="tag tchain">{ind}</span>'
                if ind and ind != "其他" else ""
            )

            theme_tags = "".join([
                f'<span class="tag tchain">{t}</span>'
                for t in themes.split(",")[:2] if t
            ])

            card_class = (
                "scard flying" if is_flying else "scard"
            )

            top10_cards += f"""
            <div class="{card_class}">
              <div class="rank">
                #{i+1}
                {' 🧬飆股訊號' if is_flying else ''}
              </div>
              <div class="sname">
                {row['stock_id']}
                <span style="font-size:12px;color:#888;
                             font-weight:400">
                  &nbsp;{total:.1f}分
                </span>
              </div>
              <div>{bars}</div>
              <div class="cfoot">
                <span class="tag {sc}">{sl}</span>
                <span class="tag tb">RF {rf:.0f}%</span>
                <span class="tag tg">▲{tgt:.0f}</span>
                <span class="tag tr">▼{sl_p:.0f}</span>
                {fly_tag}{ind_tag}{theme_tags}
              </div>
            </div>"""

    # 深度分析區塊
    deep_html = ""
    for result in deep_results:
        sid   = result["stock_id"]
        sname = result["stock_name"]
        data  = result.get("data", {})
        mods  = result.get("modules", {})

        fields = [
            ("現價",    f"{data.get('current_price','N/A')}"),
            ("PER",     str(data.get("per","N/A"))),
            ("ROE",     f"{data.get('roe','N/A')}%"),
            ("毛利率",  f"{data.get('gross_margin','N/A')}%"),
            ("負債率",  f"{data.get('debt_ratio','N/A')}%"),
            ("YoY",     f"{data.get('revenue_yoy','N/A')}%"),
            ("EPS",     str(data.get("eps","N/A"))),
            ("目標",    f"{data.get('target_price','N/A')}"),
        ]
        data_items = "".join([
            f'<div class="ditem">'
            f'<div class="dlbl">{l}</div>'
            f'<div class="dval">{v}</div>'
            f'</div>'
            for l, v in fields
        ])
        module_cards = "".join([
            f'<div class="mcard">'
            f'<div class="mtitle">{m.get("label","")}</div>'
            f'<div class="mcontent">'
            f'{m.get("content","").strip()}'
            f'</div></div>'
            for m in mods.values()
        ])
        score = float(data.get("score_total", 0) or 0)
        rf    = float(data.get("rf_prob_up",  0) or 0)*100
        sig   = str(data.get("signal","HOLD"))
        sc2, sl2 = sig_tag.get(sig, ("tb","💙 HOLD"))

        deep_html += f"""
        <div class="deep-sec">
          <div class="dhead">
            <div class="dbadge">{sid}</div>
            <div class="dinfo">
              <h2>{sname}</h2>
              <p>綜合評分 {score:.1f}/100
                 RF漲機率 {rf:.0f}%</p>
            </div>
            <span class="tag {sc2}"
                  style="font-size:13px">{sl2}</span>
          </div>
          <div class="dgrid">{data_items}</div>
          <div class="mgrid">{module_cards}</div>
        </div>"""

    # 庫存建議
    sig_emoji = {
        "加碼":"🟢","持有":"🔵","觀察":"⚪",
        "減碼":"🟡","出清":"🟠","停損":"🔴",
    }
    port_rows = ""
    total_val = 0
    for p in portfolio_advice:
        pnl = float(p.get("pnl_pct",     0) or 0)
        pc  = "pp" if pnl >= 0 else "pn"
        em  = sig_emoji.get(p.get("signal",""), "▪")
        mv  = int(p.get("market_val",    0) or 0)
        fs  = float(p.get("flying_score",0) or 0)
        fg  = p.get("flying_grade","")
        total_val += mv

        fly_cell = (
            f'<br><span style="font-size:11px;color:#085041">'
            f'🧬 飆股{fs:.0f} {fg}</span>'
            if fs >= 60 else ""
        )

        port_rows += f"""
        <tr>
          <td style="padding:10px 12px">
            <b>{p['stock_id']}</b>&nbsp;{p.get('name','')}
            {fly_cell}
          </td>
          <td style="padding:10px 12px">
            {float(p.get('cost',0) or 0):.1f}
          </td>
          <td style="padding:10px 12px">
            {float(p.get('current',0) or 0):.1f}
          </td>
          <td class="{pc}" style="padding:10px 12px">
            {pnl:+.1f}%
          </td>
          <td style="padding:10px 12px">
            {float(p.get('score',0) or 0):.0f}
          </td>
          <td style="padding:10px 12px">
            {em}&nbsp;{p.get('signal','')}
          </td>
          <td style="padding:10px 12px;font-size:11px;
                      color:#555">
            {p.get('action_desc','')}
          </td>
        </tr>"""

    port_section = f"""
    <p style="color:#666;font-size:13px;margin-bottom:10px">
      持倉總市值：
      <b style="color:#1F3864">NT${total_val:,}</b>
    </p>
    <table class="ptable">
      <tr>
        <th>持倉</th><th>成本</th><th>現價</th>
        <th>損益</th><th>評分</th>
        <th>建議</th><th>說明</th>
      </tr>
      {port_rows if port_rows else
       '<tr><td colspan="7" style="text-align:center;'
       'color:#AAA;padding:20px">尚無庫存資料</td></tr>'}
    </table>"""

    # 飆股基因區塊
    flying_section = build_flying_stock_html(
        flying_results=flying_scan,
        top_flying=top_flying,
    )

    # 自我學習診斷
    diagnosis_html = _build_diagnosis_html(learning)

    # 國際連動摘要
    ai_sentiment = intl_linkage.get("ai_sentiment","—")
    intl_detail  = intl_linkage.get("detail",{})
    intl_tags    = "".join([
        f'<span style="background:#F0F4F8;padding:2px 8px;'
        f'border-radius:8px;font-size:12px;margin:2px;'
        f'color:{"#196F3D" if v["chg"]>0 else "#922B21"}">'
        f'{k} {v["chg"]:+.1f}%</span>'
        for k, v in list(intl_detail.items())[:5]
    ])

    intl_html = f"""
    <div style="background:#fff;border-radius:12px;
                padding:14px 18px;margin-bottom:20px;
                box-shadow:0 2px 8px rgba(0,0,0,.07)">
      <div style="font-size:13px;font-weight:500;
                  color:#1F3864;margin-bottom:8px">
        🌐 國際AI族群連動
        <span style="background:#EBF5FB;color:#1A5276;
                      padding:2px 8px;border-radius:8px;
                      font-size:12px;margin-left:8px">
          {ai_sentiment}
        </span>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">
        {intl_tags if intl_tags
         else '<span style="color:#AAA;font-size:12px">'
              '資料擷取中</span>'}
      </div>
    </div>"""

    # 統計數字
    strong_flying = len([
        r for r in flying_scan if r.get("flying_score",0) >= 75
    ])

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>台股日報 {today}</title>
{css}
</head>
<body>
<div class="container">

  <div class="header">
    <h1>📊 台股智能分析深度日報 v6</h1>
    <div class="meta">{today}　含飆股基因 + 自我學習 + 產業鏈分析</div>
    <div class="stats">
      <div class="stat">
        <b>{macro_score:.0f}/100</b>總經
      </div>
      <div class="stat">
        <b>{market_state}</b>市場
      </div>
      <div class="stat">
        <b>{len(portfolio_advice)}</b>持倉
      </div>
      <div class="stat">
        <b>{strong_flying}</b>強飆股
      </div>
      <div class="stat">
        <b>{len(deep_results)}</b>深度報告
      </div>
    </div>
  </div>

  {intl_html}

  <div class="sec-title">🏆 十大買入推薦</div>
  <div class="top10-grid">
    {top10_cards if top10_cards
     else '<p style="color:#AAA;padding:20px">資料累積中</p>'}
  </div>

  <div class="sec-title">🧠 自我學習引擎</div>
  {diagnosis_html if diagnosis_html
   else '<p style="color:#AAA;padding:20px">累積預測記錄中</p>'}

  <div class="sec-title">🧬 飆股基因分析</div>
  {flying_section}

  <div class="sec-title">🔬 深度研究報告（8大分析模組）</div>
  {deep_html if deep_html
   else '<p style="color:#AAA;padding:20px">'
        '第6天起自動產出</p>'}

  <div class="sec-title">💼 庫存操作建議</div>
  {port_section}

  <div class="footer">
    ⚠️ 本報告由 AI 輔助產出，僅供參考，
    不構成投資建議。台股投資有風險，損益自負。<br>
    每日 23:30 自動更新　v6.0
  </div>

</div>
</body>
</html>"""


def save_report(html: str) -> None:
    Path("reports").mkdir(exist_ok=True)
    date_str = pd.Timestamp.today().strftime("%Y-%m-%d")
    Path(f"reports/{date_str}.html").write_text(
        html, encoding="utf-8"
    )
    Path("reports/index.html").write_text(
        html, encoding="utf-8"
    )
