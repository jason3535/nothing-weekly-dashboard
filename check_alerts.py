#!/usr/bin/env python3
"""
Nothing 周报 - 紧急问题检测 & 飞书通知
抓取最新数据，检测热度 > 阈值的问题，通过 lark-cli 发送飞书消息。
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

from src.scraper import scrape_weekly_data
from src.processor import process_data

# 配置
HEAT_THRESHOLD = 150
LARK_USER_ID = "ou_b9c85caca4a45b2fb2206a928707f827"
ALERT_HISTORY_FILE = Path(__file__).parent / "data" / "alert_history.json"

CATEGORY_NAMES = {
    "camera": "相机",
    "performance": "性能",
    "ui_ux": "UI/UX",
    "glyph": "Glyph",
    "connectivity": "连接",
    "bloatware": "预装软件",
    "other": "其他",
}


def load_alert_history():
    """加载已通知过的帖子 ID，避免重复通知"""
    if ALERT_HISTORY_FILE.exists():
        with open(ALERT_HISTORY_FILE, "r") as f:
            return json.load(f)
    return {"alerted_ids": []}


def save_alert_history(history):
    with open(ALERT_HISTORY_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def send_lark_message(text):
    """通过 lark-cli 发送飞书消息"""
    cmd = [
        "lark-cli", "im", "+messages-send",
        "--user-id", LARK_USER_ID,
        "--as", "bot",
        "--text", text,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"飞书发送失败: {result.stderr}")
        return False
    print("飞书通知已发送")
    return True


def main():
    project_dir = Path(__file__).parent
    config_path = project_dir / "config.yaml"
    data_dir = project_dir / "data"

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 抓取最新数据
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] 开始检测紧急问题...")
    scrape_result = scrape_weekly_data(config, data_dir)
    raw_data_path = Path(scrape_result["output_file"])
    print(f"抓取完成: {scrape_result['total_posts']} 篇帖子")

    # 处理数据
    process_result = process_data(config, raw_data_path, data_dir)
    processed_path = Path(process_result["output_file"])

    with open(processed_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 检测高热度问题
    top_issues = data.get("top_issues", [])
    hot_issues = [issue for issue in top_issues if issue.get("heat", 0) >= HEAT_THRESHOLD]

    if not hot_issues:
        print(f"无热度 >= {HEAT_THRESHOLD} 的问题")
        return

    # 过滤已通知过的
    history = load_alert_history()
    alerted_ids = set(history["alerted_ids"])
    new_hot_issues = [i for i in hot_issues if i.get("permalink") not in alerted_ids]

    if not new_hot_issues:
        print(f"有 {len(hot_issues)} 个高热度问题，但均已通知过")
        return

    # 构建通知消息
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"[Nothing reddit 重点反馈] {now}", f"检测到 {len(new_hot_issues)} 个新的高热度问题 (热度>={HEAT_THRESHOLD}):", ""]

    for issue in new_hot_issues:
        cat = CATEGORY_NAMES.get(issue.get("category", ""), issue.get("category", ""))
        sentiment = {"positive": "正面", "negative": "负面", "neutral": "中性"}.get(issue.get("sentiment", ""), "")
        lines.append(
            f"#{issue['rank']} [{cat}] {issue['title']}\n"
            f"   热度: {issue['heat']} | 情感: {sentiment} | 评论: {issue.get('num_comments', 0)}\n"
            f"   {issue.get('permalink', '')}"
        )
        lines.append("")

    message = "\n".join(lines)
    print(f"\n--- 通知内容 ---\n{message}\n----------------")

    # 发送飞书通知
    if send_lark_message(message):
        # 记录已通知
        for issue in new_hot_issues:
            alerted_ids.add(issue.get("permalink"))
        history["alerted_ids"] = list(alerted_ids)
        save_alert_history(history)
        print(f"已记录 {len(new_hot_issues)} 个问题到通知历史")


if __name__ == "__main__":
    main()
