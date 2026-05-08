"""
Reddit 爬虫模块
使用 Reddit 公开 JSON 端点抓取 r/Nothing 数据
"""

import requests
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class RedditScraper:
    """Reddit 数据爬虫"""

    BASE_URL = "https://www.reddit.com"
    USER_AGENT = "weeklyreport-bot/0.2 (+https://github.com/jason3535/nothing-weekly-dashboard)"

    def __init__(self, subreddit: str, request_delay: float = 2.0):
        self.subreddit = subreddit
        self.request_delay = request_delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json",
        })

    def _make_request(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        """发送请求并处理响应"""
        try:
            time.sleep(self.request_delay)  # 速率限制
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"请求失败: {url}, 错误: {e}")
            return None

    def get_posts(self, sort: str = "new", limit: int = 100, time_filter: Optional[str] = None) -> list:
        """
        获取帖子列表

        Args:
            sort: 排序方式 (new, hot, top, rising)
            limit: 获取数量（最大100/次）；超过100会自动分页
            time_filter: 时间范围 (hour, day, week, month, year, all)，仅 sort=top/controversial 有效。

        Returns:
            帖子列表
        """
        posts = []
        after = None
        fetched = 0

        while fetched < limit:
            batch_limit = min(100, limit - fetched)
            url = f"{self.BASE_URL}/r/{self.subreddit}/{sort}.json"
            params = {"limit": batch_limit}
            # t 仅在 sort=top/controversial 时有效，其他排序传了会被忽略，但仍传 None 以避免误导
            if time_filter and sort in ("top", "controversial"):
                params["t"] = time_filter
            if after:
                params["after"] = after

            data = self._make_request(url, params)
            if not data or "data" not in data:
                break

            children = data["data"].get("children", [])
            if not children:
                break

            for child in children:
                post_data = child.get("data", {})
                post = self._parse_post(post_data)
                if post:
                    posts.append(post)

            after = data["data"].get("after")
            fetched += len(children)

            if not after:
                break

            print(f"已获取 {fetched} 篇帖子...")

        return posts

    def get_post_comments(self, post_id: str, limit: int = 50) -> list:
        """获取帖子评论"""
        url = f"{self.BASE_URL}/r/{self.subreddit}/comments/{post_id}.json"
        params = {"limit": limit, "sort": "top"}

        data = self._make_request(url, params)
        if not data or len(data) < 2:
            return []

        comments = []
        self._extract_comments(data[1].get("data", {}).get("children", []), comments)
        return comments

    def _extract_comments(self, children: list, comments: list, depth: int = 0):
        """递归提取评论"""
        for child in children:
            if child.get("kind") != "t1":
                continue

            comment_data = child.get("data", {})
            comment = {
                "id": comment_data.get("id"),
                "body": comment_data.get("body", ""),
                "author": comment_data.get("author"),
                "score": comment_data.get("score", 0),
                "created_utc": comment_data.get("created_utc"),
                "depth": depth,
            }
            comments.append(comment)

            # 递归获取回复
            replies = comment_data.get("replies")
            if replies and isinstance(replies, dict):
                reply_children = replies.get("data", {}).get("children", [])
                self._extract_comments(reply_children, comments, depth + 1)

    def _parse_post(self, data: dict) -> Optional[dict]:
        """解析帖子数据"""
        if not data:
            return None

        created_utc = data.get("created_utc", 0)
        created_time = datetime.utcfromtimestamp(created_utc) if created_utc else None

        return {
            "id": data.get("id"),
            "title": data.get("title", ""),
            "selftext": data.get("selftext", ""),
            "author": data.get("author"),
            "score": data.get("score", 0),
            "upvote_ratio": data.get("upvote_ratio", 0),
            "num_comments": data.get("num_comments", 0),
            "created_utc": created_utc,
            "created_time": created_time.isoformat() if created_time else None,
            "url": data.get("url"),
            "permalink": f"https://www.reddit.com{data.get('permalink', '')}",
            "link_flair_text": data.get("link_flair_text"),
            "is_self": data.get("is_self", True),
        }

    def search_posts(self, query: str, limit: int = 100, time_filter: str = "week") -> list:
        """搜索帖子"""
        posts = []
        after = None
        fetched = 0

        while fetched < limit:
            batch_limit = min(100, limit - fetched)
            url = f"{self.BASE_URL}/r/{self.subreddit}/search.json"
            params = {
                "q": query,
                "restrict_sr": "on",
                "sort": "new",
                "t": time_filter,
                "limit": batch_limit,
            }
            if after:
                params["after"] = after

            data = self._make_request(url, params)
            if not data or "data" not in data:
                break

            children = data["data"].get("children", [])
            if not children:
                break

            for child in children:
                post_data = child.get("data", {})
                post = self._parse_post(post_data)
                if post:
                    posts.append(post)

            after = data["data"].get("after")
            fetched += len(children)

            if not after:
                break

        return posts


def scrape_weekly_data(
    config: dict,
    output_dir: Path,
    date_range: Optional[tuple] = None,
) -> dict:
    """
    抓取数据

    Args:
        config: 配置字典
        output_dir: 输出目录
        date_range: (start_datetime, end_datetime) 可选，仅保留 created_utc 在该区间内的帖子；
                    评论也只针对这些帖子拉取。不传则按抓取时点保留所有结果。

    Returns:
        抓取结果统计
    """
    reddit_config = config.get("reddit", {})
    subreddit = reddit_config.get("subreddit", "Nothing")
    posts_limit = reddit_config.get("posts_limit", 100)
    request_delay = reddit_config.get("request_delay", 2)

    scraper = RedditScraper(subreddit, request_delay)

    print(f"开始抓取 r/{subreddit} 数据...")

    # 1) 最新帖（分页，覆盖最近若干周）
    print("\n获取最新帖子（sort=new，分页）...")
    new_posts = scraper.get_posts(sort="new", limit=posts_limit)
    print(f"  累计 {len(new_posts)} 篇")

    # 2) 本周 top 帖（real time-filter，只在 sort=top 上有效）
    print("\n获取本周 top 帖子（sort=top, t=week）...")
    top_week_posts = scraper.get_posts(sort="top", limit=100, time_filter="week")
    print(f"  累计 {len(top_week_posts)} 篇")

    # 3) 本月 top 帖（覆盖到 4-5 周历史）
    print("\n获取本月 top 帖子（sort=top, t=month）...")
    top_month_posts = scraper.get_posts(sort="top", limit=100, time_filter="month")
    print(f"  累计 {len(top_month_posts)} 篇")

    # 合并去重
    all_posts = {p["id"]: p for p in new_posts}
    for p in top_week_posts + top_month_posts:
        if p["id"] not in all_posts:
            all_posts[p["id"]] = p

    posts_list = list(all_posts.values())
    print(f"\n合并去重后共 {len(posts_list)} 篇")

    # 可选：按 created_utc 过滤到目标周
    if date_range is not None:
        start_dt, end_dt = date_range
        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp()
        before = len(posts_list)
        posts_list = [p for p in posts_list if start_ts <= p.get("created_utc", 0) <= end_ts]
        print(f"按日期过滤 [{start_dt.date()} ~ {end_dt.date()}]: {before} -> {len(posts_list)} 篇")

    # 获取热门帖子的评论
    print("\n获取热门帖子评论...")
    top_posts = sorted(posts_list, key=lambda x: x.get("score", 0), reverse=True)[:10]
    comments_data = {}
    for post in top_posts:
        print(f"  获取评论: {post['title'][:50]}...")
        comments = scraper.get_post_comments(post["id"], limit=30)
        comments_data[post["id"]] = comments

    # 保存原始数据
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    raw_data = {
        "scraped_at": datetime.now().isoformat(),
        "subreddit": subreddit,
        "posts": posts_list,
        "comments": comments_data,
    }

    output_file = output_dir / f"raw_data_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)

    print(f"\n原始数据已保存: {output_file}")

    return {
        "total_posts": len(posts_list),
        "total_comments": sum(len(c) for c in comments_data.values()),
        "output_file": str(output_file),
    }


if __name__ == "__main__":
    import yaml

    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    output_dir = Path(__file__).parent.parent / "data"
    result = scrape_weekly_data(config, output_dir)
    print(f"\n抓取完成: {result}")
