"""
报告生成Agent - 生成结构化的技术日报
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from collections import defaultdict
from langchain.prompts import ChatPromptTemplate

from utils.state import NewsItem


class ReporterAgent:
    """报告生成Agent"""
    
    def __init__(self, config: dict, llm):
        self.config = config
        self.llm = llm
        self.logger = logging.getLogger(__name__)
        self.output_dir = Path(config['report']['output_dir'])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def generate_report(self, items: List[NewsItem]) -> str:
        """生成报告"""
        # 按类别分组
        categorized = self._categorize_items(items)
        
        # 生成报告内容
        report_content = self._build_report(categorized, items)
        
        # 保存报告
        report_path = self._save_report(report_content)
        
        return str(report_path)
    
    def _categorize_items(self, items: List[NewsItem]) -> Dict[str, List[NewsItem]]:
        """按类别分组"""
        categorized = defaultdict(list)
        
        for item in items:
            category = item.get('category', '其他')
            categorized[category].append(item)
        
        # 按质量分数排序
        for category in categorized:
            categorized[category].sort(
                key=lambda x: x.get('quality_score', 0),
                reverse=True
            )
        
        return dict(categorized)
    
    def _build_report(self, categorized: Dict[str, List[NewsItem]], all_items: List[NewsItem]) -> str:
        """构建报告内容"""
        today = datetime.now().strftime('%Y年%m月%d日')
        
        # 报告头部
        report = f"""# 🤖 AI与机器人技术日报

**日期**: {today}  
**生成时间**: {datetime.now().strftime('%H:%M:%S')}

---

## 📊 今日概览

- **收集资讯**: {len(all_items)} 条
- **技术类别**: {len(categorized)} 个
- **信息来源**: {len(set(item['source'] for item in all_items))} 个

---

## 🔥 技术分类

"""
        
        # 按类别生成内容
        max_items = self.config['report']['max_items_per_category']
        
        for category, items in categorized.items():
            report += f"\n### {category}\n\n"
            
            for i, item in enumerate(items[:max_items], 1):
                # 生成幽默点评
                comment = self._generate_comment(item)
                
                report += f"{i}. **[{item['title']}]({item['url']})**\n"
                report += f"   - 📰 来源: {item['source']}\n"
                report += f"   - ⭐ 评分: {item.get('quality_score', 0):.1f}/10\n"
                report += f"   - 💬 {comment}\n\n"
        
        # 生成分析部分
        if self.config['report']['include_trend_analysis']:
            report += "\n---\n\n"
            report += self._generate_trend_analysis(all_items)
        
        if self.config['report']['include_insights']:
            report += "\n---\n\n"
            report += self._generate_insights(all_items)
        
        if self.config['report']['include_predictions']:
            report += "\n---\n\n"
            report += self._generate_predictions(all_items)
        
        # 报告尾部
        report += f"\n---\n\n*本报告由AI自动生成 | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
        
        return report
    
    def _generate_comment(self, item: NewsItem) -> str:
        """生成幽默点评"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个技术博主，擅长用简洁幽默的语言点评技术新闻。

要求：
1. 一句话概括核心内容（20-40字）
2. 可以带一点幽默或调侃
3. 要专业但不枯燥
4. 避免过度夸张

示例：
- "又一个声称超越GPT-4的模型，不过这次好像是真的有点东西"
- "机器人终于学会开门了，距离统治人类又近了一步（笑）"
- "这个优化让训练速度提升3倍，钱包终于可以松口气了"
"""),
            ("user", "标题：{title}\n内容：{content}\n\n请生成一句点评：")
        ])
        
        try:
            chain = prompt | self.llm
            response = chain.invoke({
                "title": item['title'],
                "content": item['content'][:200]
            })
            return response.content.strip()
        except:
            return "值得关注的技术进展"
    
    def _generate_trend_analysis(self, items: List[NewsItem]) -> str:
        """生成趋势分析"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个技术趋势分析专家。基于今日收集的技术资讯，分析当前的技术趋势。

要求：
1. 识别热点话题和技术方向
2. 分析技术发展趋势
3. 3-5个要点，每个2-3句话
4. 专业但易懂
"""),
            ("user", "今日资讯标题：\n{titles}\n\n请分析技术趋势：")
        ])
        
        try:
            titles = "\n".join(f"- {item['title']}" for item in items[:20])
            chain = prompt | self.llm
            response = chain.invoke({"titles": titles})
            
            return f"## 📈 趋势分析\n\n{response.content.strip()}\n"
        except Exception as e:
            self.logger.warning(f"生成趋势分析失败: {str(e)}")
            return ""
    
    def _generate_insights(self, items: List[NewsItem]) -> str:
        """生成前沿洞察"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个技术洞察专家。基于今日资讯，提供前沿洞察。

要求：
1. 发现不明显但重要的信号
2. 连接不同领域的技术
3. 提出独特观点
4. 2-4个洞察，每个2-3句话
"""),
            ("user", "今日资讯：\n{summaries}\n\n请提供前沿洞察：")
        ])
        
        try:
            summaries = "\n".join(
                f"- [{item.get('category', '未分类')}] {item['title']}"
                for item in items[:15]
            )
            chain = prompt | self.llm
            response = chain.invoke({"summaries": summaries})
            
            return f"## 🔮 前沿洞察\n\n{response.content.strip()}\n"
        except Exception as e:
            self.logger.warning(f"生成前沿洞察失败: {str(e)}")
            return ""
    
    def _generate_predictions(self, items: List[NewsItem]) -> str:
        """生成方向预测"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个技术预测专家。基于今日资讯，预测未来技术方向。

要求：
1. 基于当前趋势推测未来发展
2. 关注3-6个月的短期预测
3. 2-3个预测方向
4. 有理有据，避免空泛
"""),
            ("user", "今日资讯类别分布：\n{categories}\n\n请预测技术方向：")
        ])
        
        try:
            # 统计类别分布
            category_count = defaultdict(int)
            for item in items:
                category_count[item.get('category', '其他')] += 1
            
            categories = "\n".join(
                f"- {cat}: {count}条"
                for cat, count in sorted(category_count.items(), key=lambda x: x[1], reverse=True)
            )
            
            chain = prompt | self.llm
            response = chain.invoke({"categories": categories})
            
            return f"## 🎯 方向预测\n\n{response.content.strip()}\n"
        except Exception as e:
            self.logger.warning(f"生成方向预测失败: {str(e)}")
            return ""
    
    def _save_report(self, content: str) -> Path:
        """保存报告"""
        filename = f"ai_robot_daily_{datetime.now().strftime('%Y%m%d')}.md"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return filepath
