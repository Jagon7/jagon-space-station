# Jagon Space Station

台股每日情報儀表板，部署在 GitHub Pages：<https://jagon7.github.io/jagon-space-station/>

## 自動更新流程

1. `Daily Stock Data Fetch`（每天 19:00 台灣時間）抓盤後資料並 commit 到 `data/`。
2. `ETF Holdings Fetch`（平日 21:20、隔日 08:05）跑 `scripts/fetch_etf.py`：90 檔台股 ETF 每日持股（20 家投信官網）、證交所 ETF 規模、收盤價，累積在 `data/etf/`。
3. 上述跑完後觸發 `Deploy to GitHub Pages`：`npm run build` 先由 `scripts/build_etf_views.py` 產生 ETF 頁資料（`public/data/etf/`），再以 `next build` 靜態輸出（`out/`）部署到 Pages。
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

靜態輸出不支援 middleware / 伺服器端執行，頁面時間等內容以建置當下為準。
