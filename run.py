#!/usr/bin/env python3
"""
Nothing 用户反馈看板 - 主入口
一键运行：抓取 → 处理 → 生成看板
"""

import sys
import argparse
from pathlib import Path

import yaml

from src.scraper import scrape_weekly_data
from src.processor import process_data
from src.generator import generate_dashboard


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

    # 步骤 1: 抓取数据
    if not args.skip_scrape:
        print("\n[1/3] 抓取 Reddit 数据...")
        scrape_result = scrape_weekly_data(config, data_dir)
        raw_data_path = Path(scrape_result["output_file"])
        print(f"抓取完成: {scrape_result['total_posts']} 篇帖子")
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
    process_result = process_data(config, raw_data_path, data_dir)
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
