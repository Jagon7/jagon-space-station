// 準時排程：GitHub Actions 的 schedule 常延後數小時甚至不跑，改由 Cloudflare Cron Trigger 每 5 分鐘醒來一次，
// 到了下表的時間（台灣時間）就呼叫 GitHub API 觸發對應 workflow（workflow_dispatch 會立即執行）。
// 原本 workflow 裡的 cron 留著當備援；各推播都有「已發送」紀錄，不會重複發。
const REPO = "Jagon7/jagon-space-station";
const WD = [1, 2, 3, 4, 5];          // 週一到週五
const TUE_SAT = [2, 3, 4, 5, 6];     // 美股收盤後的隔天早上
const ALL = [0, 1, 2, 3, 4, 5, 6];

// [台灣時間 HH:MM（5 分鐘的倍數）, 星期, workflow 檔名, inputs]
const PLAN = [
  ["04:15", TUE_SAT, "fetch-intel.yml"],
  ["05:45", TUE_SAT, "fetch-intel.yml"],
  ["07:10", TUE_SAT, "fetch-intel.yml"],
  ["07:55", WD, "morning.yml"],          // 盤前快報，程式等到 08:00 才發
  ["08:05", TUE_SAT, "fetch-etf.yml"],
  ["08:25", WD, "g85-morning.yml"],      // 85g 當沖標的，等到 08:30 才發
  ["08:35", TUE_SAT, "fetch-intel.yml"],
  ["08:40", WD, "flow-live.yml"],        // 即時資金流，跑到 13:35
  ["10:10", [6], "fetch.yml", { weekly: "true" }],  // 週六：補週五、月營收／季報、回測
  ["11:20", ALL, "fetch-intel.yml"],
  ["11:30", [6], "margin-backfill.yml"],  // 週六：補融資成本（推估融資維持率）
  ["11:35", TUE_SAT, "fetch-etf.yml"],
  ["14:20", ALL, "fetch-intel.yml"],
  ["14:30", ALL, "orderflow-ticks.yml"],   // 訂單流：補當天逐筆＋用每天的永豐流量繼續回補（週末也跑）
  ["15:45", WD, "fetch.yml"],            // 收盤行情
  ["16:00", [3, 6], "gooaye.yml"],       // 股癌新的一集（週三、週六下午上架）
  ["17:20", ALL, "fetch-intel.yml"],
  ["17:30", [3, 6], "gooaye.yml"],
  ["18:15", WD, "fetch.yml"],            // 三大法人、期貨
  ["19:40", WD, "etf-evening.yml"],      // ETF 持股變化，等到 20:00 才發
  ["19:45", WD, "broker-evening.yml"],   // 重點分點大額進出，等到 20:00 才發
  ["20:25", WD, "broker-evening.yml"],   // 分點資料晚出來時的備援
  ["20:20", ALL, "fetch-intel.yml"],
  ["20:40", ALL, "orderflow-ticks.yml"],   // 備援：14:30 沒跑成或流量還有剩
  ["21:00", [3, 6], "gooaye.yml"],
  ["21:20", WD, "fetch-etf.yml"],
  ["21:35", WD, "fetch.yml"],            // 融資融券（資料到齊後自動發每日戰報）
  ["22:00", WD, "active-cost.yml"],      // 主動式 ETF 建倉成本（停損監控）
  ["22:30", ALL, "gooaye.yml"],          // 特別集
  ["23:10", ALL, "freshness.yml"],       // 資料新鮮度檢查：有落後就發 LINE
  ["23:20", ALL, "fetch-intel.yml"],
  ["23:40", WD, "fetch.yml"],
  ["23:50", WD, "fetch-etf.yml"],
];

async function dispatch(env, file, inputs) {
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${file}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.DISPATCH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "jss-scheduler",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ ref: "main", ...(inputs ? { inputs } : {}) }),
  });
  console.log(file, r.status, r.status === 204 ? "" : await r.text());
}

export default {
  async scheduled(event, env, ctx) {
    const t = new Date(event.scheduledTime + 8 * 3600 * 1000);  // 台灣時間
    const hm = `${String(t.getUTCHours()).padStart(2, "0")}:${String(Math.floor(t.getUTCMinutes() / 5) * 5).padStart(2, "0")}`;
    const day = t.getUTCDay();
    const due = PLAN.filter(([at, days]) => at === hm && days.includes(day));
    ctx.waitUntil(Promise.all(due.map(([, , file, inputs]) => dispatch(env, file, inputs))));
  },
};
