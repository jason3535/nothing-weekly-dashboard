#!/usr/bin/env python3
"""
回填第8周（2026-02-16 ~ 2026-02-22）报告
从当前的原始数据中过滤出第8周的帖子，生成 week_2026_08.html
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import yaml

# 第8周时间范围（UTC）
WEEK8_START = datetime(2026, 2, 16, 0, 0, 0)
WEEK8_END   = datetime(2026, 2, 22, 23, 59, 59)

# 用于 monkeypatch：返回第8周中间某天（Feb 19），确保 isocalendar() = week 8
FAKE_NOW = datetime(2026, 2, 19, 12, 0, 0)


def filter_week8(raw_data: dict) -> dict:
    """从原始数据中保留第8周帖子"""
    start_ts = WEEK8_START.timestamp()
    end_ts   = WEEK8_END.timestamp()

    original = raw_data["posts"]
    filtered = [
        p for p in original
        if start_ts <= p.get("created_utc", 0) <= end_ts
    ]

    # 只保留对应帖子的评论
    kept_ids = {p["id"] for p in filtered}
    filtered_comments = {
        k: v for k, v in raw_data.get("comments", {}).items()
        if k in kept_ids
    }

    print(f"  原始帖子数: {len(original)}")
    print(f"  第8周帖子数 (Feb 16-22): {len(filtered)}")

    return {
        "scraped_at": raw_data["scraped_at"],
        "subreddit":  raw_data["subreddit"],
        "posts":      filtered,
        "comments":   filtered_comments,
    }


def main():
    project_dir = Path(__file__).parent

    # 加载配置
    with open(project_dir / "config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    data_dir     = project_dir / "data"
    template_dir = project_dir / "templates"
    output_dir   = project_dir / "output"

    # 找最新的原始数据文件
    raw_files = sorted(data_dir.glob("raw_data_*.json"))
    if not raw_files:
        print("错误: 未找到原始数据文件")
        sys.exit(1)

    latest_raw = raw_files[-1]
    print(f"读取原始数据: {latest_raw}")

    with open(latest_raw, encoding="utf-8") as f:
        raw_data = json.load(f)

    # 过滤出第8周数据
    print("\n[1/3] 过滤第8周数据...")
    week8_data = filter_week8(raw_data)

    # 保存第8周原始数据
    week8_raw_path = data_dir / "raw_data_week08_backfill.json"
    with open(week8_raw_path, "w", encoding="utf-8") as f:
        json.dump(week8_data, f, ensure_ascii=False, indent=2)
    print(f"  已保存: {week8_raw_path}")

    # 处理数据（monkeypatch datetime.now 返回第8周日期）
    print("\n[2/3] 处理数据（模拟第8周时间）...")
    from src.processor import DataProcessor, process_data
    import src.processor as proc_module

    with patch.object(proc_module, "datetime") as mock_dt:
        mock_dt.now.return_value = FAKE_NOW
        mock_dt.utcfromtimestamp = datetime.utcfromtimestamp
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        result = process_data(config, week8_raw_path, data_dir)

    processed_path = Path(result["output_file"])
    stats = result["stats"]
    print(f"处理完成: {stats['total_posts']} 篇软件相关帖子")
    print(f"  - 负面反馈: {stats['negative_ratio']}%")
    print(f"  - 分类分布: {stats['category_distribution']}")

    # 手动修正 week_info（以防 mock 不完整）
    with open(processed_path, encoding="utf-8") as f:
        processed = json.load(f)

    processed["week_info"] = {
        "year": 2026,
        "week_number": 8,
        "start_date": "2026-02-16",
        "end_date": "2026-02-22",
        "display": "2026 年第 8 周（02月16日 - 02月22日）",
    }

    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

    # 生成 HTML
    print("\n[3/3] 生成 HTML 看板...")
    from src.generator import generate_dashboard
    output_file = generate_dashboard(processed_path, template_dir, output_dir)
    print(f"看板已生成: {output_file}")

    print("\n完成！")
    import subprocess
    subprocess.run(["open", str(output_file)])


if __name__ == "__main__":
    main()
