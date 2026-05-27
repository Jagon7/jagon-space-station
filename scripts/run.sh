#!/bin/bash
# 台股情報站 — 每日執行腳本
# 流程：fetch_data.py → claude prompt（雷達分析） → Telegram + Notion

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

TODAY=$(date +%Y-%m-%d)
SCRIPTS_DIR="/Users/jagon/Desktop/jagon-space-station/scripts"
JSS_DIR="/Users/jagon/Desktop/jagon-space-station"
LOG_FILE="$SCRIPTS_DIR/radar.log"

# 防重複執行
LOCK_FILE="$SCRIPTS_DIR/.ran_$TODAY"
if [ -f "$LOCK_FILE" ]; then
    exit 0
fi
touch "$LOCK_FILE"

echo "======================================" >> "$LOG_FILE"
echo "[$TODAY $(date +%H:%M)] 台股情報站啟動" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

# ── Step 1: 抓取 TWSE / TPEx 真實資料 ───────────────────────
echo "[$(date +%H:%M)] Step 1 — 抓取盤面資料..." >> "$LOG_FILE"
JSS_DATA_DIR="$JSS_DIR/data" python3 "$SCRIPTS_DIR/fetch_data.py" >> "$LOG_FILE" 2>&1
FETCH_STATUS=$?
if [ $FETCH_STATUS -ne 0 ]; then
    echo "[$(date +%H:%M)] ⚠ fetch_data.py 失敗（exit $FETCH_STATUS），繼續執行雷達分析" >> "$LOG_FILE"
fi

# ── Step 1.5: 漲停原因（Claude Code 訂閱搜網路）──────────────
echo "[$(date +%H:%M)] Step 1.5 — 搜尋漲停原因..." >> "$LOG_FILE"
REASONS_JSON=$(cat "$SCRIPTS_DIR/prompt_reasons.md" | timeout 15m claude --print \
  --allowedTools "Bash,WebSearch,WebFetch" \
  --output-format text \
  --max-turns 30 \
  2>> "$LOG_FILE")
echo "$REASONS_JSON" | python3 "$SCRIPTS_DIR/apply_reasons.py" >> "$LOG_FILE" 2>&1

# ── Step 2: Claude 早鳥雷達分析（Telegram + Notion）──────────
echo "[$(date +%H:%M)] Step 2 — 啟動早鳥雷達分析..." >> "$LOG_FILE"
PROMPT_FILE="$SCRIPTS_DIR/prompt.md"
PROMPT=$(sed "s/TODAY_DATE/$TODAY/g" "$PROMPT_FILE")

echo "$PROMPT" | timeout 30m claude --print \
  --allowedTools "Bash,WebSearch,WebFetch" \
  --output-format text \
  --max-turns 50 \
  >> "$LOG_FILE" 2>&1

echo "[$(date +%H:%M)] 完成" >> "$LOG_FILE"
