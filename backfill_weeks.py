#!/usr/bin/env python3
"""
回填指定多个 ISO 周的报告。

策略：
  1. 把所有现有 raw_data_*.json 合并去重，得到最大历史帖子池；
  2. 再做一次新抓取（sort=new 分页 + top week + top month），把最新的得分/评论数也合进来；
  3. 对每个目标周，按 created_utc 过滤、补抓 top10 帖子的评论，调用 processor + generator；
  4. 写出 output/week_YYYY_WW.html。

用法：
    .venv/bin/python backfill_weeks.py 2026-14 2026-15 2026-16 2026-17 2026-18
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

from src.processor import process_data
from src.generator import generate_dashboard
from src.scraper import RedditScraper
from run import parse_week


PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
TEMPLATE_DIR = PROJECT_DIR / "templates"
OUTPUT_DIR = PROJECT_DIR / "output"


def load_existing_pool() -> tuple:
    """合并现有所有 raw_data_*.json，返回 (posts_by_id, comments_by_post_id)"""
    posts_by_id = {}
    comments_by_post_id = {}

    files = sorted(DATA_DIR.glob("raw_data_*.json"))
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:
            print(f"  跳过 {f.name}: {e}")
            continue

        for p in data.get("posts", []):
            pid = p.get("id")
            if not pid:
                continue
            existing = posts_by_id.get(pid)
            # 保留 score+num_comments 总和最大的版本（更新过的统计）
            if existing is None:
                posts_by_id[pid] = p
            else:
                if (p.get("score", 0) + p.get("num_comments", 0)) > (
                    existing.get("score", 0) + existing.get("num_comments", 0)
                ):
                    posts_by_id[pid] = p

        for pid, comments in data.get("comments", {}).items():
            # 用评论最多的那一份
            if pid not in comments_by_post_id or len(comments) > len(comments_by_post_id[pid]):
                comments_by_post_id[pid] = comments

    return posts_by_id, comments_by_post_id


def fresh_scrape(config: dict) -> tuple:
    """一次性大抓取：sort=new 分页 300 + top week + top month。返回 (posts_by_id, comments_by_post_id)"""
    rc = config.get("reddit", {})
    subreddit = rc.get("subreddit", "Nothing")
    delay = rc.get("request_delay", 2)

    scraper = RedditScraper(subreddit, delay)

    print("  sort=new 分页抓 300 篇...")
    new_posts = scraper.get_posts(sort="new", limit=300)
    print(f"    {len(new_posts)} 篇")

    print("  sort=top, t=month...")
    top_month = scraper.get_posts(sort="top", limit=100, time_filter="month")
    print(f"    {len(top_month)} 篇")

    print("  sort=top, t=week...")
    top_week = scraper.get_posts(sort="top", limit=100, time_filter="week")
    print(f"    {len(top_week)} 篇")

    posts_by_id = {}
    for p in new_posts + top_month + top_week:
        pid = p.get("id")
        if pid and pid not in posts_by_id:
            posts_by_id[pid] = p

    return posts_by_id, {}, scraper


def merge_pools(*pools) -> dict:
    """合并多个 posts_by_id；以更高 score+num_comments 的为准"""
    merged = {}
    for pool in pools:
        for pid, p in pool.items():
            existing = merged.get(pid)
            if existing is None or (
                (p.get("score", 0) + p.get("num_comments", 0))
                > (existing.get("score", 0) + existing.get("num_comments", 0))
            ):
                merged[pid] = p
    return merged


def filter_by_week(posts_by_id: dict, week: dict) -> list:
    start = datetime.fromisoformat(week["start_date"]).timestamp()
    end = datetime.fromisoformat(week["end_date"]).replace(
        hour=23, minute=59, second=59
    ).timestamp()
    return [p for p in posts_by_id.values() if start <= p.get("created_utc", 0) <= end]


def main(week_args):
    if not week_args:
        print("用法: backfill_weeks.py 2026-14 2026-15 ...")
        sys.exit(1)

    weeks = [parse_week(w) for w in week_args]
    print(f"目标周: {[w['display'] for w in weeks]}")

    with open(PROJECT_DIR / "config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 1. 合并历史
    print("\n[1] 合并现有 raw_data 池...")
    hist_posts, hist_comments = load_existing_pool()
    print(f"   历史去重后: {len(hist_posts)} 帖, {len(hist_comments)} 帖含评论")

    # 2. 新抓取一次
    print("\n[2] 重新抓取 Reddit (sort=new 分页 + top month/week)...")
    fresh_posts, _, scraper = fresh_scrape(config)
    print(f"   新抓取: {len(fresh_posts)} 帖")

    # 3. 合并
    all_posts = merge_pools(hist_posts, fresh_posts)
    print(f"\n   总池: {len(all_posts)} 帖")

    # 4. 对每周过滤、补抓评论、处理、生成
    for week in weeks:
        wkey = f"{week['year']}_{week['week_number']:02d}"
        print(f"\n=== 处理 {week['display']} ===")
        wk_posts = filter_by_week(all_posts, week)
        print(f"  本周帖子: {len(wk_posts)}")

        if not wk_posts:
            print("  无帖子，仍然生成空白报告（保留时间一致性）")

        # 补抓 top10 帖子的评论（若历史里没有）
        wk_top = sorted(wk_posts, key=lambda x: x.get("score", 0), reverse=True)[:10]
        wk_comments = {}
        for p in wk_top:
            pid = p["id"]
            if pid in hist_comments and hist_comments[pid]:
                wk_comments[pid] = hist_comments[pid]
            else:
                print(f"    抓评论: {p['title'][:50]}...")
                try:
                    wk_comments[pid] = scraper.get_post_comments(pid, limit=30)
                except Exception as e:
                    print(f"    评论抓取失败: {e}")
                    wk_comments[pid] = []

        # 写到一个临时 raw_data 文件
        raw_path = DATA_DIR / f"raw_data_backfill_{wkey}.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "scraped_at": datetime.now().isoformat(),
                    "subreddit": config.get("reddit", {}).get("subreddit", "Nothing"),
                    "posts": wk_posts,
                    "comments": wk_comments,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        print(f"  raw 已存: {raw_path.name}")

        # process + generate
        result = process_data(config, raw_path, DATA_DIR, target_week=week)
        stats = result["stats"]
        print(
            f"  统计: total_posts={stats['total_posts']}, "
            f"negative_ratio={stats['negative_ratio']}%, "
            f"分类={stats['category_distribution']}"
        )
        out_path = generate_dashboard(Path(result["output_file"]), TEMPLATE_DIR, OUTPUT_DIR)
        print(f"  HTML: {out_path}")


if __name__ == "__main__":
    main(sys.argv[1:])
