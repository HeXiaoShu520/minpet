# coding:utf-8
import base64
import hashlib
import json
import shutil
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
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def today(self):
        return datetime.now().strftime('%Y-%m-%d')

    def load_today(self):
        return self.load_date(self.today())

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

    def list_sessions(self):
        index = self._read_index()
        sessions = index.get('sessions', {})
        return [{'date': key, **value} for key, value in sorted(sessions.items(), reverse=True)]

    def to_runtime_message(self, stored_message):
        return {
            'role': stored_message.get('role', 'user'),
            'content': self._resolve_runtime_content(stored_message.get('content', [])),
        }

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
            return Path(src.replace('file:///', '', 1))
        path = Path(src)
        if path.is_absolute():
            return path
        return self.root_dir / path

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
