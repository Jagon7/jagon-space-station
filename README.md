# Jagon Space Station

台股每日情報儀表板，部署在 GitHub Pages：<https://jagon7.github.io/jagon-space-station/>

## 自動更新流程

1. `Daily Stock Data Fetch`（每天 19:00 台灣時間）與 `Morning ETF PCF Re-fetch`（每天 07:30）抓資料並 commit 到 `data/`。
2. 兩者跑完後觸發 `Deploy to GitHub Pages`：以 `next build` 靜態輸出（`out/`），讀取當下 `data/` 的 JSON，部署到 Pages。
3. 推送程式碼到 `main` 也會重新部署；可在 Actions 頁手動執行 `Deploy to GitHub Pages`。

首次啟用：repo **Settings → Pages → Build and deployment → Source** 選 **GitHub Actions**。

## 本機開發

```bash
npm ci
npm run dev                                         # http://localhost:3000
PAGES_BASE_PATH=/jagon-space-station npx next build  # 與線上相同的靜態輸出 → out/
```

靜態輸出不支援 middleware / 伺服器端執行，頁面時間等內容以建置當下為準。
