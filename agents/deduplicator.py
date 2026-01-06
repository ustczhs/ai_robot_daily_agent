"""
去重Agent - 使用向量数据库进行语义去重
"""

import logging
from typing import List
from pathlib import Path
import chromadb
from chromadb.config import Settings

from utils.state import NewsItem


class DeduplicatorAgent:
    """去重Agent"""
    
    def __init__(self, config: dict, embeddings):
        self.config = config
        self.embeddings = embeddings
        self.logger = logging.getLogger(__name__)
        self.similarity_threshold = config['filtering']['similarity_threshold']
        
        # 初始化ChromaDB
        db_path = config['database']['vector_db_path']
        Path(db_path).mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # 获取或创建集合
        self.collection = self.client.get_or_create_collection(
            name="tech_news",
            metadata={"hnsw:space": "cosine"}
        )
    
    def deduplicate(self, items: List[NewsItem]) -> List[NewsItem]:
        """去重"""
        unique_items = []
        
        for i, item in enumerate(items):
            try:
                self.logger.info(f"   检查 {i+1}/{len(items)}: {item['title'][:50]}...")
                
                # 生成嵌入向量
                text = f"{item['title']} {item['content']}"
                embedding = self.embeddings.embed_query(text)
                item['embedding'] = embedding
                
                # 检查是否重复
                if not self._is_duplicate(item):
                    unique_items.append(item)
                    # 添加到数据库
                    self._add_to_db(item)
                    self.logger.debug(f"      ✓ 独特内容")
                else:
                    self.logger.debug(f"      ✗ 重复内容，已过滤")
                
            except Exception as e:
                self.logger.warning(f"   去重检查失败: {str(e)}")
                # 出错时保守处理，保留该条目
                unique_items.append(item)
        
        return unique_items
    
    def _is_duplicate(self, item: NewsItem) -> bool:
        """检查是否重复"""
        if not item['embedding']:
            return False
        
        # 查询相似内容
        results = self.collection.query(
            query_embeddings=[item['embedding']],
            n_results=1
        )
        
        if not results['distances'] or not results['distances'][0]:
            return False
        
        # 计算相似度（距离越小越相似）
        distance = results['distances'][0][0]
        similarity = 1 - distance  # 转换为相似度
        
        return similarity >= self.similarity_threshold
    
    def _add_to_db(self, item: NewsItem):
        """添加到数据库"""
        try:
            self.collection.add(
                embeddings=[item['embedding']],
                documents=[f"{item['title']} {item['content']}"],
                metadatas=[{
                    "title": item['title'],
                    "url": item['url'],
                    "source": item['source'],
                    "category": item.get('category', 'Unknown')
                }],
                ids=[item['url']]  # 使用URL作为唯一ID
            )
        except Exception as e:
            # 可能是ID重复，忽略
            self.logger.debug(f"添加到数据库失败: {str(e)}")
