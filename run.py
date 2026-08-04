#!/usr/bin/env python3
"""
Nothing 用户反馈看板 - 主入口
一键运行：抓取 → 处理 → 生成看板
"""

import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from src.scraper import scrape_weekly_data
from src.processor import process_data
from src.generator import generate_dashboard


def parse_week(week_str: str) -> dict:
    """解析 YYYY-WW 格式为 week_info（按 ISO week，周一起始）"""
    year_str, week_str_num = week_str.split("-")
    year = int(year_str)
    week = int(week_str_num)
    # ISO week 的周一
    start = datetime.fromisocalendar(year, week, 1)
    end = start + timedelta(days=6)
    return {
        "year": year,
        "week_number": week,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "display": f"{year} 年第 {week} 周（{start.strftime('%m月%d日')} - {end.strftime('%m月%d日')}）",
    }


def main():
    parser = argparse.ArgumentParser(description="Nothing 用户反馈看板生成器")
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="跳过抓取步骤，使用现有数据"
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="生成后自动打开看板"
    )
    parser.add_argument(
        "--week",
        type=str,
        default=None,
        help="目标周 YYYY-WW，如 2026-18。指定后按 created_utc 过滤并锁定 week_info；不指定则按当前周。",
    )
    parser.add_argument(
        "--raw-data",
        type=str,
        default=None,
        help="指定 raw_data 文件路径；不指定则使用 data/ 下最新的。",
    )
    args = parser.parse_args()

    project_dir = Path(__file__).parent
    config_path = project_dir / "config.yaml"
    data_dir = project_dir / "data"
    template_dir = project_dir / "templates"
    output_dir = project_dir / "output"

    # 加载配置
    print("=" * 50)
    print("Nothing 用户反馈看板生成器")
    print("=" * 50)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    target_week = parse_week(args.week) if args.week else None
    if target_week:
        print(f"\n目标周: {target_week['display']}")

    # 步骤 1: 抓取数据
    if args.raw_data:
        raw_data_path = Path(args.raw_data)
        print(f"\n[1/3] 使用指定 raw_data: {raw_data_path}")
    elif not args.skip_scrape:
        print("\n[1/3] 抓取 Reddit 数据...")
        # 若指定了目标周，则向 scraper 传入日期窗口
        date_range = None
        if target_week:
            start_dt = datetime.fromisoformat(target_week["start_date"])
            end_dt = datetime.fromisoformat(target_week["end_date"]).replace(hour=23, minute=59, second=59)
            date_range = (start_dt, end_dt)
        scrape_result = scrape_weekly_data(config, data_dir, date_range=date_range)
        raw_data_path = Path(scrape_result["output_file"])
        print(f"抓取完成: {scrape_result['total_posts']} 篇帖子")
        if scrape_result["total_posts"] == 0:
            # 抓到 0 帖 = 网络/代理/封锁问题，宁可不更新也不要生成空周报覆盖旧版
            print("错误: 抓取到 0 篇帖子，判定为抓取失败，中止生成（保留现有周报）")
            sys.exit(1)
    else:
        print("\n[1/3] 跳过抓取，使用现有数据...")
        raw_files = sorted(data_dir.glob("raw_data_*.json"))
        if not raw_files:
            print("错误: 未找到原始数据文件")
            sys.exit(1)
        raw_data_path = raw_files[-1]
        print(f"使用: {raw_data_path}")

    # 步骤 2: 处理数据
    print("\n[2/3] 处理数据...")
    process_result = process_data(config, raw_data_path, data_dir, target_week=target_week)
    processed_data_path = Path(process_result["output_file"])
    stats = process_result["stats"]
    print(f"处理完成: {stats['total_posts']} 篇软件相关帖子")
    print(f"  - 负面反馈: {stats['negative_ratio']}%")
    print(f"  - 分类分布: {stats['category_distribution']}")

    # 步骤 3: 生成看板
    print("\n[3/3] 生成 HTML 看板...")
    output_file = generate_dashboard(processed_data_path, template_dir, output_dir)
    print(f"看板已生成: {output_file}")

    print("\n" + "=" * 50)
    print("完成!")
    print("=" * 50)

    # 自动打开
    if args.open:
        import subprocess
        subprocess.run(["open", output_file])


if __name__ == "__main__":
    main()
