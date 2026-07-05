# coding:utf-8
import base64
import hashlib
import json
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1


class ChatStore:
    def __init__(self, root_dir):
        self.root_dir = Path(root_dir)
        self.sessions_dir = self.root_dir / 'sessions'
        self.images_dir = self.root_dir / 'images'
        self.index_file = self.root_dir / 'index.json'
        self.search_db = self.root_dir / 'search.sqlite3'
        self.summary_file = self.root_dir / 'summaries.json'
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def today(self):
        return datetime.now().strftime('%Y-%m-%d')

    def load_today(self):
        return self.load_date(self.today())

    def load_stored_today(self):
        return self.load_stored_date(self.today())

    def load_stored_date(self, date_text):
        messages = []
        path = self._session_path(date_text)
        if not path.is_file():
            return messages
        with path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return messages

    def load_date(self, date_text):
        messages = []
        path = self._session_path(date_text)
        if not path.is_file():
            return messages
        with path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    stored = json.loads(line)
                except json.JSONDecodeError:
                    continue
                messages.append(self.to_runtime_message(stored))
        return messages

    def append(self, role, content, source='chat_window', pet_name=''):
        now = datetime.now()
        date_text = now.strftime('%Y-%m-%d')
        message = {
            'schema_version': SCHEMA_VERSION,
            'id': now.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8],
            'created_at': now.isoformat(timespec='seconds'),
            'role': role,
            'source': source,
            'pet_name': pet_name,
            'content': self._persist_content_images(self._normalize_content(content), date_text),
        }
        self._session_path(date_text).parent.mkdir(parents=True, exist_ok=True)
        with self._session_path(date_text).open('a', encoding='utf-8') as f:
            f.write(json.dumps(message, ensure_ascii=False) + '\n')
        self._update_index(date_text, message)
        try:
            self._index_message(date_text, message)
        except Exception as e:
            print('Chat search index failed:', e)
        return self.to_runtime_message(message)

    def clear_today(self):
        date_text = self.today()
        session = self._session_path(date_text)
        if session.exists():
            session.unlink()
        image_dir = self.images_dir / date_text
        if image_dir.exists():
            shutil.rmtree(image_dir)
        self._remove_index_date(date_text)
        self.delete_search_date(date_text)
        self.delete_summary(date_text)

    def clear_all(self):
        if self.root_dir.exists():
            shutil.rmtree(self.root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def delete_date(self, date_text):
        session = self._session_path(date_text)
        if session.exists():
            session.unlink()
        image_dir = self.images_dir / date_text
        if image_dir.exists():
            shutil.rmtree(image_dir)
        self._remove_index_date(date_text)
        self.delete_search_date(date_text)
        self.delete_summary(date_text)

    def list_sessions(self):
        index = self._read_index()
        sessions = index.get('sessions', {})
        return [{'date': key, **value} for key, value in sorted(sessions.items(), reverse=True)]

    def to_runtime_message(self, stored_message):
        return {
            'role': stored_message.get('role', 'user'),
            'content': self._resolve_runtime_content(stored_message.get('content', [])),
        }

    def content_text_for_memory(self, content):
        if isinstance(content, str):
            return content.strip()
        parts = []
        for block in content or []:
            block_type = block.get('type')
            if block_type in ('text', 'code') and block.get('text'):
                parts.append(block.get('text', ''))
            elif block_type == 'image':
                parts.append('[图片]')
        return '\n'.join(part.strip() for part in parts if part and part.strip()).strip()

    def content_for_llm(self, content):
        if isinstance(content, str):
            return content
        blocks = []
        for block in content or []:
            block_type = block.get('type')
            if block_type == 'text':
                blocks.append({'type': 'text', 'text': block.get('text', '')})
            elif block_type == 'image':
                data_url = self._image_src_to_data_url(block.get('src', ''))
                if data_url:
                    blocks.append({'type': 'image_url', 'image_url': {'url': data_url}})
                else:
                    blocks.append({'type': 'text', 'text': '[图片已不存在]'})
            elif block_type == 'code':
                blocks.append({'type': 'text', 'text': block.get('text', '')})
        return blocks or ''

    def _session_path(self, date_text):
        return self.sessions_dir / (date_text + '.jsonl')

    def _normalize_content(self, content):
        if isinstance(content, str):
            return [{'type': 'text', 'text': content}]
        normalized = []
        for block in content or []:
            block_type = block.get('type') or block.get('tag')
            if block_type == 'text':
                normalized.append({'type': 'text', 'text': block.get('text', '')})
            elif block_type == 'image':
                normalized.append({'type': 'image', 'src': block.get('src') or block.get('path') or '', 'alt': block.get('alt') or '图片'})
            elif block_type == 'code':
                normalized.append({'type': 'code', 'language': block.get('language', ''), 'text': block.get('text', '')})
        return normalized

    def _persist_content_images(self, content, date_text):
        persisted = []
        for block in content:
            if block.get('type') != 'image':
                persisted.append(block)
                continue
            src = block.get('src', '')
            if not src.startswith('data:image/'):
                persisted.append(block)
                continue
            image = self._decode_data_url(src)
            if image is None:
                persisted.append(block)
                continue
            mime, data = image
            suffix = '.jpg' if mime in ('image/jpeg', 'image/jpg') else '.png'
            sha = hashlib.sha256(data).hexdigest()
            image_dir = self.images_dir / date_text
            image_dir.mkdir(parents=True, exist_ok=True)
            filename = datetime.now().strftime('%Y%m%d-%H%M%S-') + sha[:8] + suffix
            path = image_dir / filename
            if not path.exists():
                path.write_bytes(data)
            persisted.append({
                'type': 'image',
                'src': str(Path('images') / date_text / filename).replace('\\', '/'),
                'mime': mime,
                'alt': block.get('alt') or '图片',
                'bytes': len(data),
                'sha256': sha,
            })
        return persisted

    def _resolve_runtime_content(self, content):
        runtime = []
        for block in content or []:
            if block.get('type') == 'image':
                next_block = dict(block)
                src = next_block.get('src', '')
                if src and not src.startswith('data:') and not src.startswith('file:'):
                    next_block['src'] = (self.root_dir / src).resolve().as_uri()
                runtime.append(next_block)
            else:
                runtime.append(block)
        if len(runtime) == 1 and runtime[0].get('type') == 'text':
            return runtime[0].get('text', '')
        return runtime

    def _decode_data_url(self, src):
        if ',' not in src:
            return None
        header, payload = src.split(',', 1)
        if ';base64' not in header:
            return None
        mime = header.replace('data:', '').split(';', 1)[0]
        try:
            return mime, base64.b64decode(payload)
        except Exception:
            return None

    def _image_src_to_data_url(self, src):
        if not src:
            return ''
        if src.startswith('data:image/'):
            return src
        path = self._src_to_path(src)
        if path is None or not path.is_file():
            return ''
        suffix = path.suffix.lower()
        mime = 'image/jpeg' if suffix in ('.jpg', '.jpeg') else 'image/png'
        return 'data:%s;base64,%s' % (mime, base64.b64encode(path.read_bytes()).decode('ascii'))

    def _src_to_path(self, src):
        if src.startswith('file:///'):
            # URL解码，处理中文路径
            from urllib.parse import unquote
            decoded = unquote(src.replace('file:///', '', 1))
            return Path(decoded)
        path = Path(src)
        if path.is_absolute():
            return path
        return self.root_dir / path

    def _connect_search_db(self):
        conn = sqlite3.connect(str(self.search_db))
        conn.row_factory = sqlite3.Row
        self._ensure_search_schema(conn)
        return conn

    def _ensure_search_schema(self, conn):
        conn.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                created_at TEXT,
                role TEXT,
                source TEXT,
                pet_name TEXT,
                text TEXT NOT NULL,
                json TEXT NOT NULL
            )
        ''')
        conn.execute('CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(text, content="messages", content_rowid="rowid")')
        conn.commit()

    def _index_message(self, date_text, message):
        text = self.content_text_for_memory(message.get('content', ''))
        if not text:
            return False
        with self._connect_search_db() as conn:
            old = conn.execute('SELECT rowid FROM messages WHERE id=?', (message.get('id'),)).fetchone()
            if old:
                conn.execute('DELETE FROM messages_fts WHERE rowid=?', (old['rowid'],))
            conn.execute('''
                INSERT OR REPLACE INTO messages(id, date, created_at, role, source, pet_name, text, json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                message.get('id'),
                date_text,
                message.get('created_at', ''),
                message.get('role', ''),
                message.get('source', ''),
                message.get('pet_name', ''),
                text,
                json.dumps(message, ensure_ascii=False),
            ))
            row = conn.execute('SELECT rowid FROM messages WHERE id=?', (message.get('id'),)).fetchone()
            if row:
                conn.execute('INSERT INTO messages_fts(rowid, text) VALUES (?, ?)', (row['rowid'], text))
            conn.commit()
        return True

    def rebuild_search_index(self):
        indexed = 0
        with self._connect_search_db() as conn:
            conn.execute('DELETE FROM messages_fts')
            conn.execute('DELETE FROM messages')
            conn.commit()
        for path in sorted(self.sessions_dir.glob('*.jsonl')):
            date_text = path.stem
            for message in self.load_stored_date(date_text):
                if self._index_message(date_text, message):
                    indexed += 1
        return indexed

    def search_messages(self, query, limit=50, date_from='', date_to=''):
        query = (query or '').strip()
        if not query:
            return []
        limit = max(1, min(200, int(limit or 50)))
        params = []
        filters = []
        if date_from:
            filters.append('m.date >= ?')
            params.append(date_from)
        if date_to:
            filters.append('m.date <= ?')
            params.append(date_to)
        where_extra = (' AND ' + ' AND '.join(filters)) if filters else ''
        results = []
        try:
            with self._connect_search_db() as conn:
                sql = 'SELECT m.* FROM messages_fts f JOIN messages m ON m.rowid=f.rowid WHERE messages_fts MATCH ?%s ORDER BY rank LIMIT ?' % where_extra
                rows = conn.execute(sql, [query, *params, limit]).fetchall()
                results = [dict(row) for row in rows]
                if len(results) < limit:
                    like_sql = 'SELECT * FROM messages m WHERE m.text LIKE ?%s ORDER BY created_at DESC LIMIT ?' % where_extra
                    seen = {r.get('id') for r in results}
                    for row in conn.execute(like_sql, ['%' + query + '%', *params, limit]).fetchall():
                        item = dict(row)
                        if item.get('id') not in seen:
                            results.append(item)
                            seen.add(item.get('id'))
                        if len(results) >= limit:
                            break
        except Exception as e:
            print('Chat search failed:', e)
        for item in results:
            text = item.get('text', '')
            item['snippet'] = text[:220]
        return results

    def clear_search_index(self):
        if self.search_db.exists():
            self.search_db.unlink()

    def delete_search_date(self, date_text):
        try:
            with self._connect_search_db() as conn:
                rows = conn.execute('SELECT rowid FROM messages WHERE date=?', (date_text,)).fetchall()
                for row in rows:
                    conn.execute('DELETE FROM messages_fts WHERE rowid=?', (row['rowid'],))
                conn.execute('DELETE FROM messages WHERE date=?', (date_text,))
                conn.commit()
        except Exception as e:
            print('Delete chat search date failed:', e)

    def _read_summaries(self):
        if not self.summary_file.is_file():
            return {'schema_version': SCHEMA_VERSION, 'summaries': {}}
        try:
            data = json.loads(self.summary_file.read_text(encoding='utf-8'))
        except Exception:
            return {'schema_version': SCHEMA_VERSION, 'summaries': {}}
        data.setdefault('schema_version', SCHEMA_VERSION)
        data.setdefault('summaries', {})
        return data

    def _write_summaries(self, data):
        self.summary_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def save_summary(self, date_text, summary, message_count=0, model=''):
        data = self._read_summaries()
        summaries = data.setdefault('summaries', {})
        now = datetime.now().isoformat(timespec='seconds')
        old = summaries.get(date_text, {})
        summaries[date_text] = {
            'date': date_text,
            'created_at': old.get('created_at') or now,
            'updated_at': now,
            'message_count': int(message_count or 0),
            'model': model or '',
            'summary': summary or '',
        }
        self._write_summaries(data)
        return summaries[date_text]

    def load_summary(self, date_text):
        return self._read_summaries().get('summaries', {}).get(date_text)

    def list_summaries(self):
        summaries = self._read_summaries().get('summaries', {})
        return [summaries[key] for key in sorted(summaries.keys(), reverse=True)]

    def delete_summary(self, date_text):
        data = self._read_summaries()
        existed = data.get('summaries', {}).pop(date_text, None) is not None
        if existed:
            self._write_summaries(data)
        return existed

    def build_summary_source(self, date_text, max_chars=12000):
        messages = self.load_stored_date(date_text)
        lines = []
        for message in messages:
            text = self.content_text_for_memory(message.get('content', ''))
            if not text:
                continue
            created_at = message.get('created_at', '')
            time_text = created_at[11:16] if len(created_at) >= 16 else ''
            role = '用户' if message.get('role') == 'user' else '宠物'
            lines.append('[%s][%s] %s' % (time_text, role, text))
        source = '\n'.join(lines)
        max_chars = max(1000, int(max_chars or 12000))
        if len(source) > max_chars:
            half = max_chars // 2
            source = source[:half] + '\n...（中间省略）...\n' + source[-half:]
        return source, len(messages)

    def _read_index(self):
        if not self.index_file.is_file():
            return {'schema_version': SCHEMA_VERSION, 'sessions': {}}
        try:
            return json.loads(self.index_file.read_text(encoding='utf-8'))
        except Exception:
            return {'schema_version': SCHEMA_VERSION, 'sessions': {}}

    def _write_index(self, index):
        self.index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')

    def _update_index(self, date_text, message):
        index = self._read_index()
        sessions = index.setdefault('sessions', {})
        item = sessions.setdefault(date_text, {'message_count': 0, 'image_count': 0, 'preview': ''})
        item['message_count'] = int(item.get('message_count', 0)) + 1
        item['image_count'] = int(item.get('image_count', 0)) + sum(1 for block in message.get('content', []) if block.get('type') == 'image')
        item['updated_at'] = message.get('created_at')
        item['preview'] = self._preview(message.get('content', []))
        self._write_index(index)

    def _remove_index_date(self, date_text):
        index = self._read_index()
        index.setdefault('sessions', {}).pop(date_text, None)
        self._write_index(index)

    def _preview(self, content):
        for block in content or []:
            if block.get('type') == 'text' and block.get('text'):
                return block['text'][:80]
        if any(block.get('type') == 'image' for block in content or []):
            return '[图片]'
        return ''
