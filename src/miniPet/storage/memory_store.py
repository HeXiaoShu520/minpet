# coding:utf-8
"""
自动总结记忆存储。

MemoryStore 保存从聊天中抽取出的长期有用信息，并按类别拼接成系统提示。
它不保存完整聊天记录，只维护 memories.json 中的结构化记忆项。
"""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

SCHEMA_VERSION = 1
MEMORY_CATEGORIES = ('user_preference', 'project_fact', 'relationship', 'task_context')
CATEGORY_LABELS = {
    'user_preference': '用户偏好',
    'project_fact': '项目事实',
    'relationship': '关系',
    'task_context': '任务上下文',
}


class MemoryStore:
    """长期记忆的增删改查、过期判断和 Prompt 拼接工具。"""

    def __init__(self, root_dir):
        self.root_dir = Path(root_dir)
        self.index_file = self.root_dir / 'memories.json'
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def is_expired(self, memory):
        expires_at = memory.get('expires_at') or ''
        if not expires_at:
            return False
        try:
            return datetime.fromisoformat(expires_at) <= datetime.now()
        except ValueError:
            return False

    def list_memories(self, category=None, include_expired=False):
        memories = self._read_index().get('memories', [])
        result = [m for m in memories if m.get('status', 'active') == 'active']
        if not include_expired:
            result = [m for m in result if not self.is_expired(m)]
        if category:
            result = [m for m in result if m.get('category') == category]
        return sorted(result, key=lambda m: m.get('updated_at') or m.get('created_at') or '', reverse=True)

    def list_by_category(self, include_expired=False):
        grouped = {category: [] for category in MEMORY_CATEGORIES}
        for memory in self.list_memories(include_expired=include_expired):
            category = memory.get('category')
            if category in grouped:
                grouped[category].append(memory)
        return grouped

    def get_memory(self, memory_id):
        for memory in self._read_index().get('memories', []):
            if memory.get('id') == memory_id and memory.get('status', 'active') == 'active':
                return dict(memory)
        return None

    def create_memory(self, category, text, importance=3, confidence=1.0, evidence='手动添加', source_date='', source_message_ids=None, expires_at=''):
        return self.upsert_memory(
            category,
            text,
            source_message_ids=source_message_ids or [],
            source_date=source_date,
            importance=importance,
            confidence=confidence,
            evidence=evidence,
            expires_at=expires_at or '',
        )

    def update_memory(self, memory_id, fields):
        memory = self.get_memory(memory_id)
        if not memory:
            return None
        return self.upsert_memory(
            fields.get('category', memory.get('category')),
            fields.get('text', memory.get('text')),
            source_message_ids=fields.get('source_message_ids', memory.get('source_message_ids', [])),
            source_date=fields.get('source_date', memory.get('source_date', '')),
            memory_id=memory_id,
            importance=fields.get('importance', memory.get('importance', 3)),
            confidence=fields.get('confidence', memory.get('confidence', 0.8)),
            evidence=fields.get('evidence', memory.get('evidence', '')),
            expires_at=fields.get('expires_at', memory.get('expires_at', '')),
        )

    def upsert_memory(self, category, text, source_message_ids=None, source_date='', memory_id='', importance=3, confidence=0.8, evidence='', expires_at=None):
        category = category if category in MEMORY_CATEGORIES else ''
        text = (text or '').strip()
        if not category or not text:
            return None
        index = self._read_index()
        memories = index.setdefault('memories', [])
        now_dt = datetime.now()
        now = now_dt.isoformat(timespec='seconds')
        if expires_at is None and category == 'task_context':
            expires_at = (now_dt + timedelta(days=14)).isoformat(timespec='seconds')
        importance = max(1, min(5, int(importance or 3)))
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.8
        if memory_id:
            for memory in memories:
                if memory.get('id') == memory_id and memory.get('status', 'active') == 'active':
                    memory['category'] = category
                    memory['text'] = text
                    memory['updated_at'] = now
                    memory['importance'] = importance
                    memory['confidence'] = confidence
                    memory['evidence'] = evidence or memory.get('evidence', '')
                    memory['expires_at'] = expires_at or ''
                    memory['source_message_ids'] = source_message_ids or memory.get('source_message_ids', [])
                    if source_date:
                        memory['source_date'] = source_date
                    self._write_index(index)
                    return memory
            return None
        for memory in memories:
            if memory.get('status', 'active') == 'active' and memory.get('category') == category and memory.get('text') == text:
                return memory
        memory = {
            'schema_version': SCHEMA_VERSION,
            'id': 'mem_' + datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:8],
            'created_at': now,
            'updated_at': now,
            'category': category,
            'text': text,
            'source_message_ids': source_message_ids or [],
            'source_date': source_date,
            'importance': importance,
            'confidence': confidence,
            'evidence': evidence or '',
            'expires_at': expires_at or '',
            'status': 'active',
        }
        memories.append(memory)
        self._write_index(index)
        return memory

    def delete_memory(self, memory_id):
        index = self._read_index()
        changed = False
        now = datetime.now().isoformat(timespec='seconds')
        for memory in index.get('memories', []):
            if memory.get('id') == memory_id and memory.get('status', 'active') == 'active':
                memory['status'] = 'deleted'
                memory['updated_at'] = now
                changed = True
                break
        if changed:
            self._write_index(index)
        return changed

    def build_memory_prompt(self):
        grouped = self.list_by_category()
        sections = []

        def sorted_items(categories, limit):
            items = []
            for category in categories:
                items.extend(grouped.get(category) or [])
            return sorted(
                items,
                key=lambda m: (int(m.get('importance', 3) or 3), float(m.get('confidence', 0.8) or 0.8), m.get('updated_at') or ''),
                reverse=True,
            )[:limit]

        profile = sorted_items(('user_preference', 'relationship'), 10)
        if profile:
            sections.append('USER PROFILE（用户画像，长期稳定偏好与关系）\n' + '\n'.join('- ' + m.get('text', '').strip() for m in profile))

        memory = sorted_items(('project_fact',), 10)
        if memory:
            sections.append('MEMORY（长期事实和项目知识）\n' + '\n'.join('- ' + m.get('text', '').strip() for m in memory))

        working = sorted_items(('task_context',), 8)
        if working:
            sections.append('WORKING CONTEXT（近期任务上下文，会过期）\n' + '\n'.join('- ' + m.get('text', '').strip() for m in working))

        if not sections:
            return ''
        return '以下是可供后续对话参考的记忆。仅在相关时使用，不要机械复述：\n\n' + '\n\n'.join(sections)

    def _read_index(self):
        if not self.index_file.is_file():
            return {'schema_version': SCHEMA_VERSION, 'memories': []}
        try:
            data = json.loads(self.index_file.read_text(encoding='utf-8'))
        except Exception:
            return {'schema_version': SCHEMA_VERSION, 'memories': []}
        data.setdefault('schema_version', SCHEMA_VERSION)
        data.setdefault('memories', [])
        return data

    def _write_index(self, index):
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
