# Jagon Space Station

台股每日情報儀表板，部署在 GitHub Pages：<https://jagon7.github.io/jagon-space-station/>

## 自動更新流程

1. `Daily Stock Data Fetch`（每天 19:00 台灣時間）跑 `scripts/fetch_data.py` 抓盤後資料，接著跑
   `fetch_cb.py`（CB 時間軸）、`fetch_industry.py`（產業價值鏈，每週一）、`fetch_ranking.py`（成交排行），commit 到 `data/`。
2. `ETF Holdings Fetch`（平日 21:20、隔日 08:05）跑 `scripts/fetch_etf.py`：90 檔台股 ETF 每日持股（20 家投信官網）、證交所 ETF 規模、收盤價，累積在 `data/etf/`；
   另跑 `fetch_index_schedule.py`（臺灣指數公司、MSCI 指數審核日程）與 `fetch_cb.py`。
3. 上述跑完後觸發 `Deploy to GitHub Pages`：`npm run build` 先由 `scripts/build_views.py` 產生前端資料（`public/data/`），再以 `next build` 靜態輸出（`out/`）部署到 Pages。

| 頁面 | 資料 | 來源 |
|---|---|---|
| `/etf-flow` ETF 持股 | `data/etf/` | 各投信持股公告、證交所 ETF 淨值揭露、臺灣指數公司／MSCI 審核日程 |
| `/ranking` 成交排行 | `data/ranking/` | 證交所、櫃買中心當日行情 |
| `/cb-watch` CB 時間軸 | `data/cb/cases.json` | 證券商業同業公會承銷公告、櫃買中心發行資料、金管會申報案件 |
| `/industry` 產業細分類 | `data/industry/chain.json` | 櫃買中心產業價值鏈資訊平台 |
| `/etf-flow?tab=predict` 換股預估 | `data/rebalance/pred/` | 證交所、櫃買中心 OpenAPI，公開資訊觀測站財報、除權息公告 |
3. 推送程式碼到 `main` 也會重新部署；可在 Actions 頁手動執行 `Deploy to GitHub Pages`。

首次啟用：repo **Settings → Pages → Build and deployment → Source** 選 **GitHub Actions**。

## 本機開發

```bash
npm ci
npm run dev                                         # http://localhost:3000
PAGES_BASE_PATH=/jagon-space-station npx next build  # 與線上相同的靜態輸出 → out/
```

ETF 持股來源在 `scripts/etf_sources.py`（每家投信一個函式），追蹤清單在 `scripts/fetch_etf.py` 的 `ETF_LIST`；
同一家投信加 ETF 只要加一行。`python scripts/fetch_etf.py --before YYYY-MM-DD` 可補抓支援查日期的投信的歷史持股。

## ETF 換股預估（00919、0050、0051、0056、00929）

原本用 TEJ 匯出資料的換股試算表，改成只用官方公開資料、每天自動重算（`ETF Rebalance Prediction` workflow）：平日 18:17 開始抓當天資料與財報、算完後 **19:00 推播**到 LINE／Telegram／Discord（`notify.py --rebalance-alert`，用 Daily Notify 同一組 secrets）；隔日 09:20 只補歷史資料。00919、00929 的選股（緩衝區、替換上限、市值結構、配息頻率優先）與權重上限照臺灣指數公司編製規則（00919 V1.2.0、00929 V2.2.1），0050／0051／0056 照 FTSE Russell Ground Rules（FTSE TWSE Taiwan Index Series v5.2、Taiwan Dividend+ v4.2：每次最多納入／剔除 5 檔、DPS 依會計年度月數加權、含息六個月總報酬、外資上限調整後的 investability weight）：

1. `scripts/fetch_rebalance.py` 抓公開資料到 `data/rebalance/raw/`：每日行情（證交所 MI_INDEX、櫃買 afterTrading）、
   發行股數／產業別（OpenAPI）、董監持股（OpenAPI t187ap11）、外資持股（MI_QFIIS、櫃買 qfii）、
   財報（公開資訊觀測站彙總表＋OpenAPI 當季最新，財報季每天會納入新公布的公司）、除權息公告（t108sb27）、個股本益比。
   各來源限速，遇到流量限制就停，下次排程接著補；第一次補齊歷史資料需要幾次排程，補齊前頁面顯示「資料補齊中」。
2. `scripts/build_rebalance_pred.py` 照原試算表的公式算（`scripts/rebalance/etf919.py`、`ftse.py`、`etf929.py`），
   輸出 `data/rebalance/pred/<ETF>.json` 與計算過程 `<ETF>.xlsx`；網站「ETF 持股 → 換股預估」分頁顯示並提供 Excel 下載。
3. 參數（審核日期、預擬規模、人工覆寫納入／剔除）在 `config/rebalance.json`；授權資料（FTSE IW、IBES）可選擇放 `config/rebalance/`。

驗證計算邏輯跟原試算表一致（用試算表裡的原始資料當輸入，逐項比對）：

```bash
pip install python-calamine
python -m scripts.rebalance.verify_tej 919  919___2612.xlsx
python -m scripts.rebalance.verify_tej ftse 0050_0051_0056_2612.xlsx
python -m scripts.rebalance.verify_tej 929  00929_202612.xlsb
python -m scripts.rebalance.compare_inputs 919___2612.xlsx   # 公開資料 vs TEJ 輸入差異
```

靜態輸出不支援 middleware / 伺服器端執行，頁面時間等內容以建置當下為準。
