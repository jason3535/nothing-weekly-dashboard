#!/bin/bash
# Nothing 周报 launchd wrapper：带代理环境跑 cron_job.sh，失败自动重试
# (Reddit 拒绝非代理直连——403/429，这正是 2026 周24-30 空周报的根因)
# 最多 3 次、间隔 10 分钟。由 launchd com.jason.weekly-dashboard 每周五 17:00 调用。
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
export https_proxy=http://127.0.0.1:7890
export http_proxy=http://127.0.0.1:7890
cd /Users/jason.lin/nothing-weekly-dashboard || exit 1
for i in 1 2 3; do
  echo "=== weekly attempt $i $(date '+%F %T') ==="
  bash cron_job.sh && { echo "=== ok $(date '+%F %T') ==="; exit 0; }
  echo "=== attempt $i failed rc=$? ==="
  [ "$i" -lt 3 ] && sleep 600
done
echo "=== all attempts failed $(date '+%F %T') ==="
exit 1
