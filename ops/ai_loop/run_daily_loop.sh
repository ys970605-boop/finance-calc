#!/bin/bash
# calcmoney.kr Stage 0 자율루프 — 매일 08:30 launchd 실행
set -euo pipefail

LOCK="/tmp/calcmoney_ai_loop.lock"
LOG_DIR="$HOME/cursor/finance-calc/ops/ai_loop/reports"
TODAY=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/cycle-${TODAY}.log"

# 중복 실행 방지
if [ -f "$LOCK" ]; then
  PID=$(cat "$LOCK")
  if kill -0 "$PID" 2>/dev/null; then
    echo "$(date): 이미 실행 중 (PID $PID)" >> "$LOG_FILE"
    exit 0
  fi
  rm -f "$LOCK"
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# 로그 디렉토리 확인
mkdir -p "$LOG_DIR"

echo "$(date): AI 루프 사이클 시작" >> "$LOG_FILE"

# claude CLI로 루프 프롬프트 실행
# --print: 비대화형, 결과만 출력
# --max-turns: 무한 루프 방지
PROMPT_FILE="$HOME/cursor/finance-calc/ops/ai_loop/loop_prompt.md"

cd "$HOME/cursor/finance-calc"

/Users/yongseok/.local/bin/claude --print \
  --max-turns 30 \
  --model sonnet \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,Agent" \
  < "$PROMPT_FILE" \
  >> "$LOG_FILE" 2>&1

echo "$(date): AI 루프 사이클 완료" >> "$LOG_FILE"
