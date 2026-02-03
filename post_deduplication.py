#!/usr/bin/env python3
"""
日报后处理去重脚本 - 使用 Ollama LLM 对已生成的日报进行去重
"""

import re
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from langchain_ollama import OllamaLLM
from langchain.prompts import PromptTemplate


@dataclass
class NewsItem:
    """新闻条目数据类"""
    title: str
    content: str
    source: str
    url: str
    score: float
    category: str
    published_date: str
    raw_markdown: str  # 存储完整的原始 markdown 格式


class PostDeduplicator:
    """日报后处理去重器"""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = self._load_config(config_path)
        self.llm = self._init_llm()
        self.logger = logging.getLogger(__name__)

        # 设置日志
        logging.basicConfig(
            level=logging.INFO,  # 只显示重要信息
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    def _load_config(self, config_path: str) -> dict:
        """加载配置文件"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _init_llm(self) -> OllamaLLM:
        """初始化 Ollama LLM"""
        llm_config = self.config['llm']
        if llm_config['provider'].lower() != 'ollama':
            raise ValueError("此脚本需要使用 Ollama LLM，请在 config.yaml 中设置 provider: ollama")

        return OllamaLLM(
            model=llm_config['model'],
            base_url=llm_config.get('ollama_base_url', 'http://localhost:11434'),
            temperature=0.1  # 去重需要较低温度以保证一致性
        )

    def parse_markdown_report(self, file_path: str) -> List[NewsItem]:
        """解析 markdown 报告文件，提取新闻条目"""
        self.logger.info(f"开始解析报告文件: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        items = []
        current_category = ""

        # 按行分割内容
        lines = content.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # 检测技术分类
            if line.startswith('### '):
                current_category = line[4:].strip()
                self.logger.debug(f"发现分类: {current_category}")
                i += 1
                continue

            # 检测新闻条目开始（数字编号 + 标题）
            if re.match(r'^\d+\.\s+\*\*', line):
                self.logger.debug(f"找到新闻条目: {line[:50]}...")
                item = self._parse_news_item(lines, i, current_category)
                if item:
                    items.append(item)
                    self.logger.debug(f"成功解析新闻: {item.title[:30]}...")
                    # 跳过已处理的行
                    while i < len(lines) and lines[i].strip():
                        i += 1
                else:
                    self.logger.debug(f"解析新闻失败: {line[:50]}...")
                    i += 1
            else:
                i += 1

        self.logger.info(f"解析完成，共提取 {len(items)} 条新闻")
        return items

    def _parse_news_item(self, lines: List[str], start_idx: int, category: str) -> Optional[NewsItem]:
        """解析单个新闻条目"""
        try:
            # 收集完整的条目文本（用于保持原始格式）
            raw_lines = []
            i = start_idx

            # 第一行：编号 + 标题 + 链接
            title_line = lines[i].strip()
            raw_lines.append(title_line)

            # 第二行：链接行（如果存在）
            i += 1
            if i < len(lines) and '<a href=' in lines[i]:
                raw_lines.append(lines[i])
                i += 1

            # 后续行：来源、时间、评分、简介
            for _ in range(4):  # 通常有4行元数据
                if i < len(lines) and lines[i].strip():
                    raw_lines.append(lines[i])
                    i += 1

            # 合并所有原始行
            raw_markdown = '\n'.join(raw_lines)

            # 解析关键信息用于去重判断
            title_line = raw_lines[0]
            match = re.search(r'\d+\.\s+\*\*\[([^\]]+)\]\[([^\]]+)\]\*\*', title_line)
            if not match:
                match = re.search(r'\d+\.\s+\*\*(.+?)\*\*\[([^\]]+)\]\*\*', title_line)
                if not match:
                    return None
                title = match.group(1).strip()
                url = match.group(2).strip()
            else:
                title = match.group(1).strip()
                url = match.group(2).strip()

            # 从原始文本中提取其他信息
            source = "未知"
            published_date = ""
            score = 5.0
            content = ""

            for line in raw_lines[1:]:
                if '📰 来源:' in line:
                    source_match = re.search(r'📰 来源:\s*(.+)', line)
                    if source_match:
                        source = source_match.group(1).strip()
                elif '🕒 发布时间:' in line:
                    date_match = re.search(r'🕒 发布时间:\s*(.+)', line)
                    if date_match:
                        published_date = date_match.group(1).strip()
                elif '⭐ 评分:' in line:
                    score_match = re.search(r'⭐ 评分:\s*([\d.]+)/10', line)
                    if score_match:
                        score = float(score_match.group(1))
                elif '💬 简介:' in line:
                    content_match = re.search(r'💬 简介:\s*(.+)', line)
                    if content_match:
                        content = content_match.group(1).strip()

            return NewsItem(
                title=title,
                content=content,
                source=source,
                url=url,
                score=score,
                category=category,
                published_date=published_date,
                raw_markdown=raw_markdown
            )

        except Exception as e:
            self.logger.warning(f"解析新闻条目失败: {str(e)}")
            return None

    def deduplicate_news(self, items: List[NewsItem]) -> List[NewsItem]:
        """使用 LLM 对新闻进行去重"""
        self.logger.info(f"开始 LLM 去重处理，共 {len(items)} 条新闻")

        if len(items) <= 1:
            return items

        deduplicated = []
        removed_count = 0

        # 对每条新闻，检查是否与已保留的新闻重复
        for i, item in enumerate(items):
            self.logger.info(f"检查 {i+1}/{len(items)}: {item.title[:50]}...")

            is_duplicate = False
            duplicate_with = None

            # 与已保留的新闻比较
            for existing in deduplicated:
                if self._is_duplicate(item, existing):
                    is_duplicate = True
                    duplicate_with = existing.title[:30] + "..."
                    break

            if is_duplicate:
                self.logger.debug(f"  ✗ 重复 (与: {duplicate_with})")
                removed_count += 1
            else:
                deduplicated.append(item)
                self.logger.debug(f"  ✓ 保留")

        self.logger.info(f"去重完成: 原始 {len(items)} 条，去除 {removed_count} 条重复，保留 {len(deduplicated)} 条")
        return deduplicated

    def _is_duplicate(self, item1: NewsItem, item2: NewsItem) -> bool:
        """判断两条新闻是否重复"""
        prompt = PromptTemplate.from_template("""
请判断以下两条新闻是否描述相同的核心事件。

新闻A：
标题：{title_a}
来源：{source_a}
简介：{content_a}

新闻B：
标题：{title_b}
来源：{source_b}
简介：{content_b}

请只回答"是"或"否"，后面简要说明理由（不超过30字）。

判断标准：
- 如果描述的是同一事件、同一产品发布、同一公司动态，则为"是"
- 如果只是相关但不同的事件，则为"否"
- 即使来源不同，只要核心事件相同就是重复

回答格式：
[是/否] 理由
""")

        try:
            response = self.llm.invoke(prompt.format(
                title_a=item1.title,
                source_a=item1.source,
                content_a=item1.content[:200],  # 限制内容长度
                title_b=item2.title,
                source_b=item2.source,
                content_b=item2.content[:200]
            ))

            response = response.strip()

            # 解析响应
            if response.upper().startswith('是') or response.upper().startswith('YES'):
                return True
            elif response.upper().startswith('否') or response.upper().startswith('NO'):
                return False
            else:
                # 如果无法解析，保守处理为不重复
                self.logger.warning(f"LLM 响应无法解析: {response}")
                return False

        except Exception as e:
            self.logger.error(f"LLM 判断重复失败: {str(e)}")
            return False  # 出错时保守处理为不重复

    def generate_deduplicated_report(self, original_path: str, deduplicated_items: List[NewsItem]) -> str:
        """生成去重后的报告文件"""
        self.logger.info("生成去重后的报告文件...")

        # 读取原始文件
        with open(original_path, 'r', encoding='utf-8') as f:
            original_content = f.read()

        # 生成新文件名
        original_path_obj = Path(original_path)
        new_filename = original_path_obj.stem + "_deduplicated" + original_path_obj.suffix
        new_path = original_path_obj.parent / new_filename

        # 按分类重新组织内容
        category_items = {}
        for item in deduplicated_items:
            if item.category not in category_items:
                category_items[item.category] = []
            category_items[item.category].append(item)

        # 构建新的报告内容
        lines = original_content.split('\n')
        new_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # 复制标题和概览部分
            if line.startswith('# ') or line.startswith('**日期**') or line.startswith('---') or line.startswith('## 📊'):
                new_lines.append(line)
                i += 1
                continue

            # 处理技术分类
            if line.startswith('### '):
                category = line[4:].strip()
                new_lines.append(line)

                # 如果该分类有新闻，则重新生成
                if category in category_items and category_items[category]:
                    items = category_items[category]
                    self.logger.info(f"重新生成分类 {category}: {len(items)} 条新闻")

                    # 跳过原始内容，生成新内容
                    i = self._skip_category_content(lines, i + 1)

                    # 生成新的新闻条目
                    for j, item in enumerate(items, 1):
                        new_lines.extend(self._format_news_item(item, j))

                else:
                    # 如果分类为空，删除整个分类
                    self.logger.info(f"分类 {category} 无新闻，删除")
                    i = self._skip_category_content(lines, i + 1)

            else:
                new_lines.append(line)
                i += 1

        # 更新概览统计
        new_content = '\n'.join(new_lines)
        new_content = self._update_overview_stats(new_content, deduplicated_items)

        # 写入新文件
        with open(new_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        self.logger.info(f"去重后报告已生成: {new_path}")
        return str(new_path)

    def _skip_category_content(self, lines: List[str], start_idx: int) -> int:
        """跳过分类的内容部分"""
        i = start_idx
        while i < len(lines):
            line = lines[i].strip()
            # 检测下一个分类或结束
            if line.startswith('### ') or line.startswith('## 🔮') or line.startswith('---'):
                break
            i += 1
        return i

    def _format_news_item(self, item: NewsItem, number: int) -> List[str]:
        """格式化新闻条目为 markdown - 使用原始格式并重新编号"""
        # 使用原始 markdown，但更新编号
        lines = item.raw_markdown.split('\n')

        # 更新第一行的编号
        if lines and re.match(r'^\d+\.', lines[0]):
            # 替换开头的数字编号
            lines[0] = re.sub(r'^\d+\.', f'{number}.', lines[0])

        # 添加空行
        lines.append("")

        return lines

    def _update_overview_stats(self, content: str, items: List[NewsItem]) -> str:
        """更新报告开头的统计信息"""
        # 计算新的统计数据
        total_news = len(items)
        categories = len(set(item.category for item in items))
        sources = len(set(item.source for item in items))

        # 替换概览统计
        content = re.sub(
            r'- \*\*收集资讯\*\*: \d+ 条',
            f'- **收集资讯**: {total_news} 条',
            content
        )
        content = re.sub(
            r'- \*\*技术类别\*\*: \d+ 个',
            f'- **技术类别**: {categories} 个',
            content
        )
        content = re.sub(
            r'- \*\*信息来源\*\*: \d+ 个',
            f'- **信息来源**: {sources} 个',
            content
        )

        return content


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='日报后处理去重脚本')
    parser.add_argument('input_file', help='输入的日报 markdown 文件路径')
    parser.add_argument('--config', default='config/config.yaml', help='配置文件路径')

    args = parser.parse_args()

    # 初始化去重器
    deduplicator = PostDeduplicator(args.config)

    # 解析报告
    items = deduplicator.parse_markdown_report(args.input_file)

    # 去重处理
    deduplicated_items = deduplicator.deduplicate_news(items)

    # 生成新报告
    output_path = deduplicator.generate_deduplicated_report(args.input_file, deduplicated_items)

    print("✅ 去重处理完成!")
    print(f"📁 原始文件: {args.input_file}")
    print(f"📁 去重文件: {output_path}")
    print(f"📊 统计: {len(items)} → {len(deduplicated_items)} 条新闻")


if __name__ == "__main__":
    main()
