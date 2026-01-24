#!/usr/bin/env python3
"""
分析为什么特定帖子没有被包含在周报中
"""

import json
import yaml
import re
from pathlib import Path

def analyze_posts():
    # 帖子ID列表
    post_ids = ["1qfxhxc", "1qhzqc7"]

    # 加载配置
    config_path = Path("config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 加载原始数据
    raw_data_path = Path("data/raw_data_20260123_181644.json")
    with open(raw_data_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # 加载最新处理数据
    processed_files = sorted(Path("data").glob("processed_data_*.json"))
    if processed_files:
        latest_processed = processed_files[-1]
        print(f"使用处理数据文件: {latest_processed.name}")
        with open(latest_processed, "r", encoding="utf-8") as f:
            processed_data = json.load(f)
    else:
        processed_data = None

    # 获取排除关键词
    exclude_keywords = config.get("exclude_keywords", [])
    print(f"\n排除关键词 ({len(exclude_keywords)} 个):")
    for kw in exclude_keywords:
        print(f"  - {kw}")

    # 获取所有关键词
    keywords = config.get("keywords", {})
    all_keywords = []
    for key in keywords:
        all_keywords.extend(keywords[key])
    print(f"\n关键词总数: {len(all_keywords)}")

    # 分析每个帖子
    posts = raw_data.get("posts", [])

    for post_id in post_ids:
        print(f"\n{'='*60}")
        print(f"分析帖子: {post_id}")
        print(f"{'='*60}")

        # 在原始数据中查找帖子
        post = None
        for p in posts:
            if p.get("id") == post_id:
                post = p
                break

        if not post:
            print(f"帖子 {post_id} 未在原始数据中找到")
            print("可能原因: 不在抓取时间范围内，或超出posts_limit限制")
            continue

        print(f"标题: {post.get('title', 'N/A')}")
        print(f"作者: {post.get('author', 'N/A')}")
        print(f"得分: {post.get('score', 0)}")
        print(f"评论数: {post.get('num_comments', 0)}")
        print(f"创建时间: {post.get('created_time', 'N/A')}")

        # 检查是否在处理数据中
        in_processed = False
        if processed_data:
            for p in processed_data.get("all_posts", []):
                if p.get("id") == post_id:
                    in_processed = True
                    print(f"✓ 在处理数据中找到 (分类: {p.get('category', 'N/A')}, 情感: {p.get('sentiment', 'N/A')})")
                    break

        if not in_processed:
            print("✗ 未在处理数据中找到")

            # 分析排除原因
            title = post.get("title", "").lower()
            selftext = post.get("selftext", "").lower()
            full_text = f"{title} {selftext}"

            print("\n分析排除原因:")

            # 检查排除关键词
            excluded_by = []
            for kw in exclude_keywords:
                if kw.lower() in full_text:
                    excluded_by.append(kw)

            if excluded_by:
                print(f"  1. 包含排除关键词: {', '.join(excluded_by)}")

            # 检查是否包含任何相关关键词
            has_keyword = False
            matching_keywords = []
            for kw in all_keywords:
                if kw.lower() in full_text:
                    has_keyword = True
                    matching_keywords.append(kw)

            if not has_keyword:
                print("  2. 不包含任何软件相关关键词")
            else:
                print(f"  2. 包含关键词: {', '.join(matching_keywords[:5])}..." if len(matching_keywords) > 5 else f"  2. 包含关键词: {', '.join(matching_keywords)}")

            # 检查分类关键词
            print("\n分类关键词匹配:")
            for category, cat_keywords in keywords.items():
                matches = []
                for kw in cat_keywords:
                    if kw.lower() in full_text:
                        matches.append(kw)
                if matches:
                    print(f"  {category}: {', '.join(matches[:3])}..." if len(matches) > 3 else f"  {category}: {', '.join(matches)}")

            # 检查情感关键词
            sentiment_keywords = config.get("sentiment", {})
            negative_matches = [kw for kw in sentiment_keywords.get("negative", []) if kw.lower() in full_text]
            positive_matches = [kw for kw in sentiment_keywords.get("positive", []) if kw.lower() in full_text]

            print(f"\n情感分析匹配:")
            print(f"  负面词汇: {len(negative_matches)} 个")
            print(f"  正面词汇: {len(positive_matches)} 个")

            # 检查帖子内容（前200字符）
            selftext_preview = selftext[:200] + "..." if len(selftext) > 200 else selftext
            print(f"\n正文预览: {selftext_preview}")

if __name__ == "__main__":
    analyze_posts()