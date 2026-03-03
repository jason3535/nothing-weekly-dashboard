"""
HTML 看板生成模块
使用 Jinja2 模板生成静态 HTML
"""

import json
import re
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


def get_available_weeks(output_dir: Path, current_year: int, current_week: int) -> list:
    """
    获取所有可用的周次列表

    Args:
        output_dir: 输出目录
        current_year: 当前年份
        current_week: 当前周次

    Returns:
        可用周次列表
    """
    weeks = []

    # 扫描已有的周报文件
    existing_files = sorted(output_dir.glob("week_*.html"), reverse=True)

    for file in existing_files:
        match = re.match(r"week_(\d{4})_(\d{2})\.html", file.name)
        if match:
            year = int(match.group(1))
            week = int(match.group(2))
            is_current = (year == current_year and week == current_week)
            weeks.append({
                "year": year,
                "week": week,
                "file": file.name,
                "display": f"{year} 年第 {week} 周",
                "current": is_current,
            })

    return weeks


def generate_dashboard(processed_data_path: Path, template_dir: Path, output_dir: Path) -> str:
    """
    生成 HTML 看板

    Args:
        processed_data_path: 处理后的数据文件路径
        template_dir: 模板目录
        output_dir: 输出目录

    Returns:
        生成的 HTML 文件路径
    """
    # 读取处理后的数据
    with open(processed_data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 生成输出文件名
    week_info = data.get("week_info", {})
    year = week_info.get("year", datetime.now().year)
    week_num = week_info.get("week_number", datetime.now().isocalendar()[1])

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"week_{year}_{week_num:02d}.html"

    # 获取可用周次列表
    available_weeks = get_available_weeks(output_dir, year, week_num)
    data["available_weeks"] = available_weeks

    # 设置 Jinja2 环境
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("dashboard.html")

    # 渲染模板
    html_content = template.render(**data)

    # 写入文件
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 更新所有已存在的周报文件，刷新周次选择器
    update_all_week_selectors(output_dir, template_dir, available_weeks)

    print(f"看板已生成: {output_file}")
    return str(output_file)


def update_all_week_selectors(output_dir: Path, template_dir: Path, available_weeks: list):
    """
    更新所有周报文件的周次选择器

    Args:
        output_dir: 输出目录
        template_dir: 模板目录
        available_weeks: 可用周次列表
    """
    for week in available_weeks:
        file_path = output_dir / week["file"]
        if not file_path.exists():
            continue

        # 读取文件内容
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 生成新的选择器 HTML
        selector_options = []
        for w in available_weeks:
            selected = "selected" if w["file"] == week["file"] else ""
            selector_options.append(
                f'<option value="{w["file"]}" {selected}>{w["display"]}</option>'
            )

        new_selector = "\n                    ".join(selector_options)

        # 替换选择器内容
        pattern = r'(<select id="weekSelector"[^>]*>)(.*?)(</select>)'
        replacement = rf'\1\n                    {new_selector}\n                \3'
        new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

        # 写回文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)


if __name__ == "__main__":
    import sys

    project_dir = Path(__file__).parent.parent
    data_dir = project_dir / "data"
    template_dir = project_dir / "templates"
    output_dir = project_dir / "output"

    # 查找最新的处理后数据文件
    processed_files = sorted(data_dir.glob("processed_data_*.json"))

    if not processed_files:
        print("未找到处理后的数据文件，请先运行 processor.py")
        sys.exit(1)

    latest_processed = processed_files[-1]
    print(f"使用处理后数据: {latest_processed}")

    output_file = generate_dashboard(latest_processed, template_dir, output_dir)
    print(f"\n生成完成: {output_file}")
