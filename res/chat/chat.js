/* chat.js — QWebChannel 桥接 + 消息渲染 */
'use strict';

marked.setOptions({ breaks: true, gfm: true });

const Chat = (() => {
  let bridge = null;
  let streamBubble = null; // 当前流式气泡的 content div
  let streamId = null;
  let streamText = '';

  /* ─── 初始化 QWebChannel ─── */
  function init() {
    if (typeof QWebChannel === 'undefined') return;
    new QWebChannel(qt.webChannelTransport, ch => {
      bridge = ch.objects.bridge;
    });
  }

  /* ─── 从 Python 添加完整消息 ─── */
  function appendMessage(msg) {
    // 如果有正在流式输出的气泡先结束它
    if (streamBubble) _finalizeStream();
    const row = _buildRow(msg);
    document.getElementById('messages').appendChild(row);
    scrollToBottom();
  }

  /* ─── 流式追加 delta ─── */
  function startStream(msgOrId, role, name, avatarSrc) {
    if (streamBubble) _finalizeStream();
    // 兼容对象调用 Chat.startStream({id,role,name,avatar}) 和旧式四参数调用
    const msg = (msgOrId && typeof msgOrId === 'object')
      ? msgOrId
      : { id: msgOrId, role, name, avatar: avatarSrc };
    streamId = msg.id;
    streamText = '';
    const row = _buildRow({ ...msg, content: [{ type: 'text', text: '' }] });
    row.dataset.streamId = streamId;
    document.getElementById('messages').appendChild(row);
    streamBubble = row.querySelector('.bubble-content');
    streamBubble.classList.add('typing-cursor');
    scrollToBottom();
  }

  function appendDelta(id, delta) {
    if (streamId !== id || !streamBubble) return;
    streamText += delta;
    streamBubble.innerHTML = marked.parse(streamText);
    _bindCodeCopy(streamBubble);
    scrollToBottom();
  }

  function endStream(id, finalText) {
    if (streamId !== id || !streamBubble) return;
    streamBubble.classList.remove('typing-cursor');
    if (finalText !== undefined) {
      streamBubble.innerHTML = marked.parse(finalText);
      _bindCodeCopy(streamBubble);
    }
    streamBubble = null;
    streamId = null;
    streamText = '';
    scrollToBottom();
  }

  function _finalizeStream() {
    if (!streamBubble) return;
    streamBubble.classList.remove('typing-cursor');
    streamBubble = null;
    streamId = null;
    streamText = '';
  }

  function _buildRow(msg) {
    const isUser = msg.role === 'user';
    const row = document.createElement('div');
    row.className = 'msg-row' + (isUser ? ' user' : '');

    // 头像
    const av = document.createElement('div');
    av.className = 'avatar ' + (isUser ? 'user-av' : 'pet-av');
    if (msg.avatar) {
      const img = document.createElement('img');
      img.src = msg.avatar;
      img.onerror = () => { av.textContent = (msg.name || (isUser ? '我' : '宠'))[0]; };
      av.appendChild(img);
    } else {
      av.textContent = (msg.name || (isUser ? '我' : '宠'))[0];
    }

    // 消息体
    const body = document.createElement('div');
    body.className = 'msg-body';
    const nameEl = document.createElement('div');
    nameEl.className = 'msg-name';
    nameEl.textContent = msg.name || (isUser ? '我' : '宠物');
    body.appendChild(nameEl);

    const blocks = msg.content || [];
    const hasMixed = blocks.length > 1;
    if (hasMixed) {
      // 多 block 合并到一个气泡
      const bubble = document.createElement('div');
      bubble.className = 'bubble ' + (isUser ? 'user-bubble' : 'pet-bubble');
      for (const block of blocks) {
        bubble.appendChild(_buildBlockInner(block, isUser));
      }
      body.appendChild(bubble);
    } else {
      for (const block of blocks) {
        body.appendChild(_buildBlock(block, isUser));
      }
    }

    if (isUser) {
      row.appendChild(body);
      row.appendChild(av);
    } else {
      row.appendChild(av);
      row.appendChild(body);
    }
    return row;
  }

  // 气泡内部元素（不带外层 bubble div）
  function _buildBlockInner(block, isUser) {
    const t = block.type;
    if (t === 'text') {
      const content = document.createElement('div');
      content.className = 'bubble-content';
      content.innerHTML = marked.parse(block.text || ' ');
      _bindCodeCopy(content);
      return content;
    }
    if (t === 'image') {
      const img = document.createElement('img');
      img.className = 'chat-img';
      img.src = block.src || '';
      img.alt = block.alt || '图片';
      img.onclick = () => openLightbox(block.src);
      return img;
    }
    return document.createElement('div');
  }

  function _buildBlock(block, isUser) {
    const t = block.type;
    if (t === 'text') {
      const bubble = document.createElement('div');
      bubble.className = 'bubble ' + (isUser ? 'user-bubble' : 'pet-bubble');
      const content = document.createElement('div');
      content.className = 'bubble-content';
      content.innerHTML = marked.parse(block.text || ' ');
      _bindCodeCopy(content);
      bubble.appendChild(content);
      return bubble;
    }
    if (t === 'image') {
      const bubble = document.createElement('div');
      bubble.className = 'bubble ' + (isUser ? 'user-bubble' : 'pet-bubble');
      const img = document.createElement('img');
      img.className = 'chat-img';
      img.src = block.src || '';
      img.alt = block.alt || '图片';
      img.onclick = () => openLightbox(block.src);
      bubble.appendChild(img);
      return bubble;
    }
    if (t === 'code') {
      const bubble = document.createElement('div');
      bubble.className = 'bubble ' + (isUser ? 'user-bubble' : 'pet-bubble');
      const pre = document.createElement('pre');
      const code = document.createElement('code');
      code.textContent = block.text || '';
      const btn = document.createElement('button');
      btn.className = 'copy-btn';
      btn.textContent = '复制';
      btn.onclick = () => _copy(block.text || '', btn);
      pre.appendChild(btn);
      pre.appendChild(code);
      bubble.appendChild(pre);
      return bubble;
    }
    if (t === 'card') {
      const card = document.createElement('div');
      card.className = 'card';
      if (block.title) {
        const title = document.createElement('div');
        title.className = 'card-title';
        title.textContent = block.title;
        card.appendChild(title);
      }
      if (block.body) {
        const body = document.createElement('div');
        body.className = 'card-body';
        body.innerHTML = marked.parse(block.body);
        card.appendChild(body);
      }
      if (block.actions && block.actions.length) {
        const acts = document.createElement('div');
        acts.className = 'card-actions';
        for (const a of block.actions) {
          const btn = document.createElement('button');
          btn.className = 'card-btn';
          btn.textContent = a.label;
          btn.onclick = () => bridge && bridge.cardAction(a.value || a.label);
          acts.appendChild(btn);
        }
        card.appendChild(acts);
      }
      return card;
    }
    // fallback
    const d = document.createElement('div');
    return d;
  }

  /* ─── 代码复制按钮 ─── */
  function _bindCodeCopy(el) {
    el.querySelectorAll('pre').forEach(pre => {
      if (pre.querySelector('.copy-btn')) return;
      const code = pre.querySelector('code');
      if (!code) return;
      const btn = document.createElement('button');
      btn.className = 'copy-btn';
      btn.textContent = '复制';
      btn.onclick = () => _copy(code.textContent, btn);
      pre.insertBefore(btn, pre.firstChild);
    });
  }

  function _copy(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
      btn.textContent = '已复制';
      setTimeout(() => { btn.textContent = '复制'; }, 1500);
    });
  }

  /* ─── 灯箱 ─── */
  function openLightbox(src) {
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox').classList.add('open');
  }

  function closeLightbox() {
    document.getElementById('lightbox').classList.remove('open');
  }

  function scrollToBottom() {
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  }

  function clear() {
    document.getElementById('messages').innerHTML = '';
  }

  // 自动初始化
  document.addEventListener('DOMContentLoaded', init);

  return { appendMessage, startStream, appendDelta, endStream, scrollToBottom, clear, openLightbox, closeLightbox };
})();
