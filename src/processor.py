"""
数据处理模块
清洗、分类、统计 Reddit 数据
"""

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Optional

from deep_translator import GoogleTranslator


class DataProcessor:
    """数据处理器"""

    def __init__(self, config: dict):
        self.config = config
        self.keywords = config.get("keywords", {})
        self.categories = config.get("categories", [])
        self.sentiment_keywords = config.get("sentiment", {})
        self.exclude_keywords = config.get("exclude_keywords", [])
        self.translator = GoogleTranslator(source='en', target='zh-CN')
        self._translation_cache = {}

        # 需要保护的专有名词（不翻译）
        self.protected_terms = [
            # 品牌和产品名称（按优先级排序，更具体的模式在前）
            r'Nothing\s+Phone\s*\d*[a-z]*',  # Nothing Phone, Nothing Phone 3, Nothing Phone 3a, etc.
            r'Nothing\s+OS\s*\d*',          # Nothing OS, Nothing OS 4
            r'NothingOS\s*\d*',             # NothingOS, NothingOS4
            r'Glyph\s+Matrix',              # Glyph Matrix
            r'Essential\s+Space',           # Essential Space
            r'\bNothing\b',                 # Nothing (品牌名)
            r'\bCMF\b',                     # CMF
            r'\bGlyph\b',                   # Glyph
            r'\bEssential\b',               # Essential
            r'Phone\s+\d+[a-z]*',           # Phone 3, Phone 3a, Phone 3a pro
            r'nothing\s+phone',             # 小写形式
            r'nothing\s+os',                # 小写形式
            r'glyph\s+matrix',              # 小写形式
            r'essential\s+space',           # 小写形式
            # 型号相关
            r'\d[a-z]+\s+pro',              # 3a pro, 2 pro
            r'\d[a-z]+',                    # 3a, 2a
        ]

    def _translate(self, text: str) -> str:
        """翻译文本（带缓存和错误处理）"""
        if not text or not text.strip():
            return text

        # 检查缓存
        if text in self._translation_cache:
            return self._translation_cache[text]

        try:
            # 限制文本长度
            text_to_translate = text[:500] if len(text) > 500 else text

            # 保护专有名词：用占位符替换，翻译后再恢复
            # 首先收集所有不重叠的匹配
            matches = []
            for pattern in self.protected_terms:
                # 查找所有匹配
                for match in re.finditer(pattern, text_to_translate, re.IGNORECASE):
                    matches.append({
                        'start': match.start(),
                        'end': match.end(),
                        'text': match.group()
                    })


            # 如果没有匹配，直接翻译
            if not matches:
                translated = self.translator.translate(text_to_translate)
                self._translation_cache[text] = translated
                time.sleep(0.3)
                return translated

            # 按起始位置排序并合并重叠区间
            matches.sort(key=lambda x: x['start'])
            non_overlapping = []
            current = matches[0]

            for match in matches[1:]:
                if match['start'] <= current['end']:  # 重叠
                    # 合并区间，保留更长的匹配文本
                    current['end'] = max(current['end'], match['end'])
                    # 选择更具体的匹配（更长的文本）
                    if len(match['text']) > len(current['text']):
                        current['text'] = match['text']
                else:
                    non_overlapping.append(current)
                    current = match

            non_overlapping.append(current)

            # 生成占位符并替换
            placeholder_map = {}
            protected_text_parts = []
            last_end = 0

            for i, match in enumerate(non_overlapping):
                # 添加前一段文本
                protected_text_parts.append(text_to_translate[last_end:match['start']])

                # 生成占位符并添加 - 使用 [[和]] 包裹，避免被翻译
                placeholder = f"[[PROTECTED_{i}]]"
                placeholder_map[placeholder] = match['text']
                protected_text_parts.append(placeholder)

                last_end = match['end']

            # 添加最后一段文本
            protected_text_parts.append(text_to_translate[last_end:])
            protected_text = ''.join(protected_text_parts)

            # 翻译保护后的文本
            translated = self.translator.translate(protected_text)

            # 恢复专有名词
            for placeholder, original_term in placeholder_map.items():
                translated = translated.replace(placeholder, original_term)

            self._translation_cache[text] = translated
            time.sleep(0.3)  # 避免请求过快
            return translated
        except Exception as e:
            print(f"  翻译失败: {str(e)[:50]}")
            return text  # 翻译失败返回原文

    def process(self, raw_data: dict) -> dict:
        """
        处理原始数据

        Args:
            raw_data: 爬虫抓取的原始数据

        Returns:
            处理后的结构化数据
        """
        posts = raw_data.get("posts", [])
        comments = raw_data.get("comments", {})

        # 过滤软件相关帖子
        software_posts = self._filter_software_posts(posts)

        # 分类帖子
        categorized_posts = self._categorize_posts(software_posts)

        # 情感分析
        analyzed_posts = self._analyze_sentiment(categorized_posts)

        # 统计数据
        stats = self._calculate_stats(analyzed_posts, comments)

        # 生成 TOP 问题
        top_issues = self._extract_top_issues(analyzed_posts)

        # 趋势分析
        trends = self._analyze_trends(analyzed_posts)

        # 热门讨论
        hot_discussions = self._get_hot_discussions(analyzed_posts)

        # 热门评论（只从软件相关帖子中获取）
        software_post_ids = {p["id"] for p in analyzed_posts}
        hot_comments = self._get_hot_comments(comments, software_post_ids)

        return {
            "generated_at": datetime.now().isoformat(),
            "week_info": self._get_week_info(),
            "stats": stats,
            "top_issues": top_issues,
            "trends": trends,
            "hot_discussions": hot_discussions,
            "hot_comments": hot_comments,
            "categorized_posts": {
                cat["id"]: [p for p in analyzed_posts if p.get("category") == cat["id"]]
                for cat in self.categories
            },
            "all_posts": analyzed_posts,
        }

    def _filter_software_posts(self, posts: list) -> list:
        """过滤出软件相关帖子"""
        software_keywords = self.keywords.get("software", [])
        all_keywords = []
        for key in self.keywords:
            all_keywords.extend(self.keywords[key])

        filtered = []
        for post in posts:
            text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()

            # 先检查是否包含排除关键词
            should_exclude = False
            for exclude_kw in self.exclude_keywords:
                if exclude_kw.lower() in text:
                    should_exclude = True
                    break

            if should_exclude:
                continue

            # 检查是否包含任何相关关键词
            for keyword in all_keywords:
                if keyword.lower() in text:
                    filtered.append(post)
                    break

        return filtered

    def _categorize_posts(self, posts: list) -> list:
        """给帖子分类"""
        categorized = []

        for post in posts:
            text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
            category = self._determine_category(text)
            post["category"] = category
            categorized.append(post)

        return categorized

    def _determine_category(self, text: str) -> str:
        """确定帖子分类"""
        category_scores = defaultdict(int)

        # UI/UX
        for keyword in self.keywords.get("ui_ux", []):
            if keyword.lower() in text:
                category_scores["ui_ux"] += 1

        # 性能
        for keyword in self.keywords.get("performance", []):
            if keyword.lower() in text:
                category_scores["performance"] += 1

        # 相机
        for keyword in self.keywords.get("camera", []):
            if keyword.lower() in text:
                category_scores["camera"] += 1

        # Glyph
        for keyword in self.keywords.get("glyph", []):
            if keyword.lower() in text:
                category_scores["glyph"] += 1

        # 连接
        for keyword in self.keywords.get("connectivity", []):
            if keyword.lower() in text:
                category_scores["connectivity"] += 1

        if not category_scores:
            return "other"

        return max(category_scores, key=category_scores.get)

    def _analyze_sentiment(self, posts: list) -> list:
        """情感分析"""
        negative_keywords = self.sentiment_keywords.get("negative", [])
        positive_keywords = self.sentiment_keywords.get("positive", [])

        for post in posts:
            text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()

            negative_count = sum(1 for kw in negative_keywords if kw.lower() in text)
            positive_count = sum(1 for kw in positive_keywords if kw.lower() in text)

            if negative_count > positive_count:
                sentiment = "negative"
            elif positive_count > negative_count:
                sentiment = "positive"
            else:
                sentiment = "neutral"

            post["sentiment"] = sentiment
            post["sentiment_score"] = positive_count - negative_count

        return posts

    def _calculate_stats(self, posts: list, comments: dict) -> dict:
        """计算统计数据"""
        total_posts = len(posts)
        total_comments = sum(len(c) for c in comments.values())

        # 情感分布
        sentiment_dist = defaultdict(int)
        for post in posts:
            sentiment_dist[post.get("sentiment", "neutral")] += 1

        # 分类分布
        category_dist = defaultdict(int)
        for post in posts:
            category_dist[post.get("category", "other")] += 1

        # 热度计算（基于得分和评论）
        total_score = sum(p.get("score", 0) for p in posts)
        total_engagement = sum(p.get("num_comments", 0) for p in posts)

        # 热门问题数（热度 > 20 的帖子）
        def calc_heat(post):
            return post.get("score", 0) + post.get("num_comments", 0) * 2
        hot_issues_count = sum(1 for p in posts if calc_heat(p) > 20)

        negative_ratio = sentiment_dist["negative"] / total_posts * 100 if total_posts > 0 else 0

        return {
            "total_posts": total_posts,
            "total_comments": total_comments,
            "total_score": total_score,
            "total_engagement": total_engagement,
            "hot_issues_count": hot_issues_count,
            "avg_comments": round(total_engagement / total_posts, 1) if total_posts > 0 else 0,
            "sentiment_distribution": dict(sentiment_dist),
            "category_distribution": dict(category_dist),
            "negative_ratio": round(negative_ratio, 1),
        }

    def _extract_top_issues(self, posts: list, top_n: int = 10) -> list:
        """提取 TOP 问题"""
        # 按热度排序（得分 + 评论数 * 2）
        def calc_heat(post):
            return post.get("score", 0) + post.get("num_comments", 0) * 2

        # 展示所有高热度帖子，让产品经理自行判断
        sorted_posts = sorted(posts, key=calc_heat, reverse=True)[:top_n]

        print("  翻译 TOP 问题标题...")
        top_issues = []
        for i, post in enumerate(sorted_posts, 1):
            category_name = self._get_category_name(post.get("category", "other"))
            category_color = self._get_category_color(post.get("category", "other"))

            # 翻译标题
            title_cn = self._translate(post.get("title", ""))

            top_issues.append({
                "rank": i,
                "title": title_cn,
                "title_en": post.get("title", ""),
                "category": post.get("category"),
                "category_name": category_name,
                "category_color": category_color,
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "heat": calc_heat(post),
                "sentiment": post.get("sentiment"),
                "permalink": post.get("permalink"),
                "created_time": post.get("created_time"),
            })

        return top_issues

    def _analyze_trends(self, posts: list) -> dict:
        """趋势分析"""
        # 按天统计
        daily_counts = defaultdict(int)
        daily_sentiment = defaultdict(lambda: defaultdict(int))

        for post in posts:
            created_time = post.get("created_time")
            if created_time:
                date = created_time[:10]  # YYYY-MM-DD
                daily_counts[date] += 1
                daily_sentiment[date][post.get("sentiment", "neutral")] += 1

        # 按分类统计
        category_trends = defaultdict(int)
        for post in posts:
            category_trends[post.get("category", "other")] += 1

        return {
            "daily_counts": dict(daily_counts),
            "daily_sentiment": {k: dict(v) for k, v in daily_sentiment.items()},
            "category_trends": dict(category_trends),
        }

    def _get_hot_discussions(self, posts: list, top_n: int = 5) -> list:
        """获取热门讨论"""
        sorted_posts = sorted(posts, key=lambda x: x.get("num_comments", 0), reverse=True)[:top_n]

        print("  翻译热门讨论...")
        hot_discussions = []
        for post in sorted_posts:
            # 翻译标题和内容
            title_cn = self._translate(post.get("title", ""))
            selftext = post.get("selftext", "") or ""
            selftext_short = selftext[:200] if len(selftext) > 200 else selftext
            selftext_cn = self._translate(selftext_short) if selftext_short else ""

            hot_discussions.append({
                "title": title_cn,
                "title_en": post.get("title", ""),
                "selftext": selftext_cn + ("..." if len(selftext) > 200 else ""),
                "selftext_en": selftext_short,
                "author": post.get("author"),
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "category": post.get("category"),
                "category_name": self._get_category_name(post.get("category", "other")),
                "sentiment": post.get("sentiment"),
                "permalink": post.get("permalink"),
                "created_time": post.get("created_time"),
            })

        return hot_discussions

    def _get_hot_comments(self, comments: dict, software_post_ids: set, top_n: int = 3) -> list:
        """获取热门评论"""
        # 只从软件相关帖子中获取评论
        all_comments = []
        for post_id, post_comments in comments.items():
            if post_id not in software_post_ids:
                continue  # 跳过非软件相关帖子的评论
            for comment in post_comments:
                comment["post_id"] = post_id
                all_comments.append(comment)

        # 过滤软件相关评论
        all_keywords = []
        for key in self.keywords:
            all_keywords.extend(self.keywords[key])

        filtered_comments = []
        for comment in all_comments:
            body = (comment.get("body", "") or "").lower()

            # 排除不相关内容
            should_exclude = False
            for exclude_kw in self.exclude_keywords:
                if exclude_kw.lower() in body:
                    should_exclude = True
                    break
            if should_exclude:
                continue

            # 检查是否包含软件相关关键词
            is_software_related = False
            for keyword in all_keywords:
                if keyword.lower() in body:
                    is_software_related = True
                    break
            if is_software_related:
                filtered_comments.append(comment)

        # 按 score 排序
        sorted_comments = sorted(filtered_comments, key=lambda x: x.get("score", 0), reverse=True)[:top_n]

        print("  翻译热门评论...")
        hot_comments = []
        for comment in sorted_comments:
            body = comment.get("body", "") or ""
            body_short = body[:300] if len(body) > 300 else body
            body_cn = self._translate(body_short) if body_short else ""

            # 构建评论链接
            post_id = comment.get("post_id", "")
            comment_id = comment.get("id", "")
            permalink = f"https://www.reddit.com/r/Nothing/comments/{post_id}/comment/{comment_id}/"

            hot_comments.append({
                "body": body_cn + ("..." if len(body) > 300 else ""),
                "body_en": body_short,
                "author": comment.get("author"),
                "score": comment.get("score", 0),
                "post_id": post_id,
                "permalink": permalink,
            })

        return hot_comments

    def _get_week_info(self) -> dict:
        """获取当前周信息"""
        now = datetime.now()
        week_number = now.isocalendar()[1]
        year = now.year

        # 计算本周的起止日期
        start_of_week = now - timedelta(days=now.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        return {
            "year": year,
            "week_number": week_number,
            "start_date": start_of_week.strftime("%Y-%m-%d"),
            "end_date": end_of_week.strftime("%Y-%m-%d"),
            "display": f"{year} 年第 {week_number} 周（{start_of_week.strftime('%m月%d日')} - {end_of_week.strftime('%m月%d日')}）",
        }

    def _get_category_name(self, category_id: str) -> str:
        """获取分类名称"""
        for cat in self.categories:
            if cat["id"] == category_id:
                return cat["name"]
        return "其他"

    def _get_category_color(self, category_id: str) -> str:
        """获取分类颜色"""
        for cat in self.categories:
            if cat["id"] == category_id:
                return cat["color"]
        return "#6B7280"


def process_data(config: dict, raw_data_path: Path, output_dir: Path) -> dict:
    """
    处理数据主函数

    Args:
        config: 配置字典
        raw_data_path: 原始数据文件路径
        output_dir: 输出目录

    Returns:
        处理结果
    """
    # 读取原始数据
    with open(raw_data_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # 处理数据
    processor = DataProcessor(config)
    processed_data = processor.process(raw_data)

    # 添加配置信息
    processed_data["categories"] = config.get("categories", [])

    # 保存处理后的数据
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"processed_data_{timestamp}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(processed_data, f, ensure_ascii=False, indent=2)

    print(f"处理后数据已保存: {output_file}")

    return {
        "output_file": str(output_file),
        "stats": processed_data["stats"],
    }


if __name__ == "__main__":
    import yaml
    import sys

    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 查找最新的原始数据文件
    data_dir = Path(__file__).parent.parent / "data"
    raw_files = sorted(data_dir.glob("raw_data_*.json"))

    if not raw_files:
        print("未找到原始数据文件，请先运行 scraper.py")
        sys.exit(1)

    latest_raw = raw_files[-1]
    print(f"使用原始数据: {latest_raw}")

    result = process_data(config, latest_raw, data_dir)
    print(f"\n处理完成: {result}")
