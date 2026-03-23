#!/bin/bash
# Nothing 周报自动更新脚本
# 每周五下午 5:00 执行

cd /Users/jason.lin/nothing-weekly-dashboard

# 记录日志
LOG_FILE="logs/cron_$(date +%Y%m%d_%H%M%S).log"
mkdir -p logs

echo "========================================" >> "$LOG_FILE"
echo "开始执行: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 运行爬虫和生成器
/usr/bin/python3 run.py >> "$LOG_FILE" 2>&1

echo "----------------------------------------" >> "$LOG_FILE"
echo "同步到 GitHub Pages..." >> "$LOG_FILE"
echo "----------------------------------------" >> "$LOG_FILE"

# 复制最新周报到根目录
cp output/week_*.html .
cp "$(ls output/week_*.html | sort -V | tail -1)" index.html

# 提交并推送到 GitHub
git add . >> "$LOG_FILE" 2>&1
git commit -m "Update weekly report $(date +%Y-%m-%d)" >> "$LOG_FILE" 2>&1
git push >> "$LOG_FILE" 2>&1

echo "========================================" >> "$LOG_FILE"
echo "执行完成: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 保留最近 10 周的日志
cd logs && ls -t cron_*.log | tail -n +11 | xargs -r rm
