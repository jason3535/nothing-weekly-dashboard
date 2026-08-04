"""
Reddit 爬虫模块（RSS 版）

背景：2026-05 起 Reddit 封锁了未授权的 .json 公共端点（403 Blocked），同时 r/Nothing
社区迁移到了 r/NothingTech。原先基于 .json 的抓取已失效。

本模块改用 Reddit 的 Atom/RSS feed（.rss）抓取，无需 OAuth 凭证、结构化、未被封锁。
局限：
  - 每个 feed 最多 25 条且无法翻页 → 单次快照只覆盖最近若干小时。
    依赖 cron 高频运行 + 按周 union 累积来获得完整周覆盖。
  - RSS 不提供 score / 评论数 / 评论内容 → 这些字段降级为 0 / 空，
    下游"热度排序""热门评论"相应退化（不影响分类与情感分析）。
"""

import re
import time
import json
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import requests

ATOM_NS = "{http://www.w3.org/2005/Atom}"


class RedditRSSScraper:
    """基于 Reddit .rss feed 的数据爬虫"""

    BASE_URL = "https://www.reddit.com"
    # 用类浏览器 UA，避免被反爬验证页拦截
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

    def __init__(self, subreddit: str, request_delay: float = 2.0):
        self.subreddit = subreddit
        self.request_delay = request_delay
        self.session = requests.Session()
        # 不读环境变量代理：直连/代理两条路由下面显式控制。
        # Reddit 对 IP 的封锁两边摇摆(2026-05~07 封办公网直连、2026-08 封 Clash 出口)，
        # 单押一条路都会重现"整月空周报"事故，必须双路 fallback。
        self.session.trust_env = False
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "application/atom+xml, application/xml, text/xml, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._retry_wait = 30  # 429 退避秒数(动态跟随 Retry-After)
        # 依次尝试的路由：直连 → 本地 Clash 代理
        self.proxy_routes = [
            None,
            {"https": "http://127.0.0.1:7890", "http": "http://127.0.0.1:7890"},
        ]

    def _fetch_feed(self, path: str, params: Optional[dict] = None) -> list:
        """抓取单个 .rss feed 并解析为帖子列表（直连失败自动切代理，429 尊重 Retry-After）"""
        url = f"{self.BASE_URL}/r/{self.subreddit}/{path}"
        resp = None
        for proxies in self.proxy_routes:
            route = "direct" if proxies is None else "proxy"
            for attempt in (1, 2):
                try:
                    time.sleep(self.request_delay if attempt == 1 else self._retry_wait)
                    r = self.session.get(url, params=params, timeout=30, proxies=proxies)
                    r.raise_for_status()
                    resp = r
                    break
                except requests.RequestException as e:
                    print(f"请求失败({route} #{attempt}): {url}, 错误: {e}")
                    # 429 时按服务端 Retry-After 等待(缺省 30s)，避免持续触发限流
                    retry_after = 30
                    if getattr(e, "response", None) is not None and e.response.status_code == 429:
                        try:
                            retry_after = min(int(e.response.headers.get("retry-after", 30)), 120)
                        except (TypeError, ValueError):
                            pass
                    self._retry_wait = retry_after
            if resp is not None:
                break
        if resp is None:
            return []

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            print(f"解析失败: {url}, 错误: {e}")
            return []

        posts = []
        for entry in root.findall(f"{ATOM_NS}entry"):
            post = self._parse_entry(entry)
            if post:
                posts.append(post)
        return posts

    @staticmethod
    def _text(entry, tag: str) -> Optional[str]:
        el = entry.find(f"{ATOM_NS}{tag}")
        return el.text if el is not None else None

    def _parse_entry(self, entry) -> Optional[dict]:
        """把一个 Atom entry 解析成与原 .json 抓取一致的 post 结构"""
        raw_id = self._text(entry, "id") or ""
        post_id = raw_id.split("t3_")[-1] if raw_id else None
        if not post_id:
            return None

        title = (self._text(entry, "title") or "").strip()

        # 作者：<author><name>/u/xxx</name></author>
        author = None
        author_el = entry.find(f"{ATOM_NS}author/{ATOM_NS}name")
        if author_el is not None and author_el.text:
            author = author_el.text.strip().lstrip("/u/").strip()

        # 链接：<link href="..."/>
        permalink = None
        link_el = entry.find(f"{ATOM_NS}link")
        if link_el is not None:
            permalink = link_el.get("href")

        # 时间：<published>2026-06-01T02:23:35+00:00</published>
        published = self._text(entry, "published") or self._text(entry, "updated")
        created_utc = 0.0
        created_time = None
        if published:
            try:
                dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                created_utc = dt.timestamp()
                created_time = dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
            except ValueError:
                pass

        # 正文：content 内含 HTML，selftext 在 <!-- SC_OFF --><div class="md">...<!-- SC_ON -->
        content_el = entry.find(f"{ATOM_NS}content")
        selftext = ""
        is_self = True
        if content_el is not None and content_el.text:
            selftext, is_self = self._extract_selftext(content_el.text)

        return {
            "id": post_id,
            "title": title,
            "selftext": selftext,
            "author": author,
            "score": 0,            # RSS 不提供
            "upvote_ratio": 0,     # RSS 不提供
            "num_comments": 0,     # RSS 不提供
            "created_utc": created_utc,
            "created_time": created_time,
            "url": permalink,
            "permalink": permalink,
            "link_flair_text": None,  # RSS 不可靠提供
            "is_self": is_self,
        }

    @staticmethod
    def _extract_selftext(content_html: str) -> tuple:
        """从 content HTML 中提取正文文本，返回 (selftext, is_self)"""
        unescaped = html.unescape(content_html)
        # 自文本帖的正文被包在 SC_OFF/SC_ON 之间的 div.md 里
        m = re.search(r"<!-- SC_OFF -->(.*?)<!-- SC_ON -->", unescaped, re.S)
        if not m:
            return "", False  # 多为链接/图片帖，无正文
        body_html = m.group(1)
        # 去标签 + 压缩空白
        text = re.sub(r"<[^>]+>", " ", body_html)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text, True

    def get_posts(self) -> list:
        """聚合多个 feed（new / hot / top-week）并按 id 去重。
        记录帖子在 hot / top-week 榜的名次（1 起），作为热度信号（RSS 无 score 的替代）。"""
        all_posts = {}
        feeds = [
            ("new/.rss", None, None),
            (".rss", None, "hot_rank"),
            ("top/.rss", {"t": "week"}, "top_rank"),
        ]
        for path, params, rank_field in feeds:
            posts = self._fetch_feed(path, params)
            print(f"  {path} -> {len(posts)} 条")
            for i, p in enumerate(posts, 1):
                existing = all_posts.setdefault(p["id"], p)
                if rank_field:
                    existing[rank_field] = i
        return list(all_posts.values())

    def get_comments(self, post_id: str, limit: int = 50) -> list:
        """抓取单帖 comments/.rss。首条 entry 是帖子本体(t3_)，其余为评论(t1_)。
        返回与旧 .json 抓取兼容的评论结构；score 不可得(置 0)，
        feed 顺序即 Reddit 默认 best 排序 → 下游稳定排序后靠前的就是热评。"""
        entries = self._fetch_feed(f"comments/{post_id}/.rss")
        comments = []
        for c in entries:
            if not c or c.get("id") == post_id:
                continue  # 跳过帖子本体
            comments.append({
                "id": c["id"],
                "author": c.get("author"),
                "body": c.get("selftext", ""),
                "score": 0,  # RSS 不提供
                "created_utc": c.get("created_utc", 0),
            })
            if len(comments) >= limit:
                break
        return comments


def scrape_weekly_data(
    config: dict,
    output_dir: Path,
    date_range: Optional[tuple] = None,
) -> dict:
    """
    抓取数据（RSS 版）

    Args:
        config: 配置字典
        output_dir: 输出目录
        date_range: (start_datetime, end_datetime) 可选，仅保留 created_utc 在该区间内的帖子。

    Returns:
        抓取结果统计
    """
    reddit_config = config.get("reddit", {})
    subreddit = reddit_config.get("subreddit", "NothingTech")
    request_delay = reddit_config.get("request_delay", 2)

    scraper = RedditRSSScraper(subreddit, request_delay)

    print(f"开始抓取 r/{subreddit} 数据（RSS）...")
    posts_list = scraper.get_posts()
    print(f"\n合并去重后共 {len(posts_list)} 篇")

    # 可选：按 created_utc 过滤到目标周
    if date_range is not None:
        start_dt, end_dt = date_range
        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp()
        before = len(posts_list)
        posts_list = [p for p in posts_list if start_ts <= p.get("created_utc", 0) <= end_ts]
        print(f"按日期过滤 [{start_dt.date()} ~ {end_dt.date()}]: {before} -> {len(posts_list)} 篇")

    # 逐帖抓 comments/.rss：恢复真实评论数(num_comments)与评论内容(热门评论用)。
    # 每帖一次请求(内置限速)，上限 80 帖防失控。
    comments_data = {}
    # 榜单在榜的优先(它们最可能进 TOP/热门讨论)，最多 40 帖；
    # 匿名配额 ~10 req/min，评论请求用 8s 间隔防 429。
    ranked = sorted(posts_list, key=lambda p: (
        p.get("top_rank", 99), p.get("hot_rank", 99), -p.get("created_utc", 0)))
    fetch_targets = ranked[:40]
    saved_delay = scraper.request_delay
    scraper.request_delay = 8
    print(f"抓取各帖评论({len(fetch_targets)} 帖, 8s 间隔)...")
    for idx, p in enumerate(fetch_targets, 1):
        comments = scraper.get_comments(p["id"])
        p["num_comments"] = len(comments)
        if comments:
            comments_data[p["id"]] = comments
        if idx % 10 == 0:
            print(f"  评论进度 {idx}/{len(fetch_targets)}")
    scraper.request_delay = saved_delay
    total_comments = sum(len(v) for v in comments_data.values())
    print(f"评论抓取完成: {total_comments} 条 / {len(comments_data)} 帖有评论")

    # 保存原始数据
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    raw_data = {
        "scraped_at": datetime.now().isoformat(),
        "subreddit": subreddit,
        "source": "rss",
        "posts": posts_list,
        "comments": comments_data,
    }

    output_file = output_dir / f"raw_data_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)

    print(f"\n原始数据已保存: {output_file}")

    return {
        "total_posts": len(posts_list),
        "total_comments": total_comments,
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
