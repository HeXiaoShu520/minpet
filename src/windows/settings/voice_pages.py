# coding:utf-8
"""语音和回复显示设置页面。"""

import hashlib

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QPlainTextEdit
from qfluentwidgets import InfoBar, InfoBarPosition, PrimaryPushButton, SettingCard, SettingCardGroup, SwitchSettingCard
from qfluentwidgets import FluentIcon as FIF

import config
from base_page import MiniPetScrollPage
from clients.tts_client import TtsCacheWorker, TtsPreviewWorker, stop_tts
from widgets.setting_cards import ComboSettingCard, LineEditSettingCard, RangeSettingCard


VOICE_OPTIONS = [
    ('zh_female_vv_uranus_bigtts', 'vivi 2.0'),
    ('zh_female_xiaohe_uranus_bigtts', '小何 2.0'),
    ('zh_male_m191_uranus_bigtts', '云舟 2.0'),
    ('zh_male_taocheng_uranus_bigtts', '小天 2.0'),
    ('saturn_zh_female_cancan_tob', '知性灿灿'),
    ('saturn_zh_female_qingyingduoduo_cs_tob', '轻盈朵朵 2.0'),
    ('saturn_zh_female_tiaopigongzhu_tob', '调皮公主'),
    ('saturn_zh_female_keainvsheng_tob', '可爱女生'),
    ('zh_female_zhixingnv_uranus_bigtts', '知性女声 2.0'),
    ('zh_female_qinqienv_uranus_bigtts', '亲切女声 2.0'),
    ('zh_female_lingling_uranus_bigtts', '玲玲姐姐 2.0'),
    ('zh_female_jiaochuannv_uranus_bigtts', '娇喘女声 2.0'),
    ('zh_female_kailangjiejie_uranus_bigtts', '开朗姐姐 2.0'),
    ('zh_female_roumeinvyou_uranus_bigtts', '柔美女友2.0'),
    ('zh_female_sophie_uranus_bigtts', '魅力苏菲2.0'),
    ('zh_female_mengyatou_uranus_bigtts', '萌丫头'),
    ('zh_female_yingtaowanzi_uranus_bigtts', '樱桃丸子2.0'),
    ('zh_female_sajiaoxuemei_uranus_bigtts', '撒娇学妹2.0'),
]
VOICE_VALUE_TO_LABEL = dict(VOICE_OPTIONS)
VOICE_LABEL_TO_VALUE = {label: value for value, label in VOICE_OPTIONS}

DOUBAO_CALL_VOICE_OPTIONS = [
    ('zh_female_vv_jupiter_bigtts', 'vv 女声'),
    ('zh_female_xiaohe_jupiter_bigtts', '小何女声'),
    ('zh_male_yunzhou_jupiter_bigtts', '云舟男声'),
    ('zh_male_xiaotian_jupiter_bigtts', '小天男声'),
]

class TTSPage(MiniPetScrollPage):
    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__('语音设置', parent, save_callback=lambda: self._save())
        self.worker = None
        self.preview_worker = None
        self._initializing = True
        cfg = config.tts_config
        self.apiGroup = SettingCardGroup('火山豆包 TTS', self.scrollWidget)
        self.enabledCard = SwitchSettingCard(FIF.VOLUME, '聊天回复语音播报', '开启后，宠物的 AI 回复会自动转成语音播放', parent=self.apiGroup)
        self.enabledCard.setChecked(bool(cfg.get('enabled', False)))
        self.apiKeyCard = LineEditSettingCard(FIF.VPN, 'API Key', '控制台 > API Key 管理中获取的 X-Api-Key', password=True, placeholder='火山引擎 API Key', parent=self.apiGroup)
        self.apiKeyCard.setText(cfg.get('api_key', ''))
        self.voiceCard = ComboSettingCard(VOICE_OPTIONS, FIF.PEOPLE, '音色', '选择后会生成并播放一句音色预览', self.apiGroup)
        self.voiceCard.setCurrentValue(cfg.get('voice_name', config.DEFAULT_TTS_CONFIG['voice_name']))
        self.voiceCard.comboBox.currentTextChanged.connect(self._preview_voice)
        self.maxCharsCard = LineEditSettingCard(FIF.FONT_SIZE, '最大字数', '过长回复会截断后播放，避免请求过大', placeholder='200', parent=self.apiGroup)
        self.maxCharsCard.lineEdit.setFixedWidth(120)
        self.maxCharsCard.setText(cfg.get('max_chars', config.DEFAULT_TTS_CONFIG['max_chars']))
        self.testTextCard = SettingCard(FIF.EDIT, '测试文本', '留空则使用当前音色的默认预览文案', self.apiGroup)
        self.testTextEdit = QPlainTextEdit(self.testTextCard)
        self.testTextEdit.setPlaceholderText('你好呀，我是小月，有什么需要帮助的吗')
        self.testTextEdit.setPlainText(cfg.get('test_text', ''))
        self._style_editor(self.testTextEdit)
        self.testTextCard.hBoxLayout.addStretch(1)
        self.testTextCard.hBoxLayout.addWidget(self.testTextEdit, 0, Qt.AlignRight)
        self.testTextCard.hBoxLayout.addSpacing(16)

        voice_chat_cfg = config.voice_chat_config
        voice_chat_defaults = config.DEFAULT_VOICE_CHAT_CONFIG
        wake_cfg = config.wake_word_config
        wake_defaults = config.DEFAULT_WAKE_WORD_CONFIG
        self.wakeGroup = SettingCardGroup('本地 AI 语音对话', self.scrollWidget)
        self.continuousVoiceCard = SwitchSettingCard(FIF.CHAT, '连续对话', '开启后每轮回复结束会自动进入下一次接听；关闭后回到语音球待机', parent=self.wakeGroup)
        self.continuousVoiceCard.setChecked(bool(voice_chat_cfg.get('continuous', voice_chat_defaults['continuous'])))
        self.wakeEnabledCard = SwitchSettingCard(FIF.MICROPHONE, '小月小月唤醒', '打开语音球后使用本地 Vosk 模型监听；命中后再打开火山流式 ASR', parent=self.wakeGroup)
        self.wakeEnabledCard.setChecked(bool(wake_cfg.get('enabled', wake_defaults['enabled'])))
        self.wakeWordsCard = LineEditSettingCard(FIF.MESSAGE, '唤醒词', '多个词用逗号分隔，例如：小月小月,小月', placeholder='小月小月', parent=self.wakeGroup)
        self.wakeWordsCard.setText(wake_cfg.get('words', wake_defaults['words']))

        doubao_call_cfg = config.doubao_call_config
        self.doubaoCallGroup = SettingCardGroup('豆包通话', self.scrollWidget)
        self.doubaoCallSpeakerCard = ComboSettingCard(DOUBAO_CALL_VOICE_OPTIONS, FIF.PEOPLE, '通话音色', '豆包通话语音回复使用的发音人', self.doubaoCallGroup)
        self.doubaoCallSpeakerCard.setCurrentValue(doubao_call_cfg.get('speaker', config.DEFAULT_DOUBAO_CALL_CONFIG['speaker']))

        self.linkGroup = SettingCardGroup('相关链接', self.scrollWidget)
        self.linkCard = SettingCard(FIF.LINK, '火山语音资源', '服务开通、在线体验和 API 教程', self.linkGroup)
        self.serviceBtn = PrimaryPushButton('服务开通', self.linkCard)
        self.experienceBtn = PrimaryPushButton('在线体验', self.linkCard)
        self.apiDocBtn = PrimaryPushButton('API 教程', self.linkCard)
        self.linkCard.hBoxLayout.addStretch(1)
        self.linkCard.hBoxLayout.addWidget(self.serviceBtn, 0, Qt.AlignRight)
        self.linkCard.hBoxLayout.addSpacing(8)
        self.linkCard.hBoxLayout.addWidget(self.experienceBtn, 0, Qt.AlignRight)
        self.linkCard.hBoxLayout.addSpacing(8)
        self.linkCard.hBoxLayout.addWidget(self.apiDocBtn, 0, Qt.AlignRight)
        self.linkCard.hBoxLayout.addSpacing(16)
        self.serviceBtn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://console.volcengine.com/speech/new/setting/activate?_vtm_=a106466.b106468.0_0.0_0.0.44_7656326907147814435&projectName=default.')))
        self.experienceBtn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://console.volcengine.com/speech/new/experience/tts?projectName=default')))
        self.apiDocBtn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://www.volcengine.com/docs/6561/2528925?lang=zh')))

        self.actionCard = SettingCard(FIF.VOLUME, '测试语音', '播放一段测试语音', self.apiGroup)
        self.testBtn = PrimaryPushButton('测试语音', self.actionCard)
        self.actionCard.hBoxLayout.addStretch(1)
        self.actionCard.hBoxLayout.addWidget(self.testBtn, 0, Qt.AlignRight)
        self.actionCard.hBoxLayout.addSpacing(16)
        self.testBtn.clicked.connect(self._test)

        for card in [self.enabledCard, self.apiKeyCard, self.voiceCard, self.maxCharsCard, self.testTextCard, self.actionCard]:
            self.apiGroup.addSettingCard(card)
        for card in [self.continuousVoiceCard, self.wakeEnabledCard, self.wakeWordsCard]:
            self.wakeGroup.addSettingCard(card)
        self.doubaoCallGroup.addSettingCard(self.doubaoCallSpeakerCard)
        self.linkGroup.addSettingCard(self.linkCard)
        self.expandLayout.addWidget(self.apiGroup)
        self.expandLayout.addWidget(self.wakeGroup)
        self.expandLayout.addWidget(self.doubaoCallGroup)
        self.expandLayout.addWidget(self.linkGroup)
        self._initializing = False

    def _style_editor(self, editor):
        editor.setFixedSize(520, 78)
        editor.setStyleSheet(
            'QPlainTextEdit{background:#ffffff;border:1px solid #dfe3e8;border-radius:8px;'
            'padding:8px 10px;font-size:14px;color:#1f2328;}'
            'QPlainTextEdit:focus{border:1px solid #8ab4f8;}'
        )

    def _voice_preview_path(self, voice_value, text=''):
        safe_name = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in voice_value)
        text = (text or '').strip()
        if text:
            digest = hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]
            safe_name = '%s_%s' % (safe_name, digest)
        return config.DATA_DIR / 'tts_preview' / (safe_name + '.pcm')

    def _preview_text(self, voice_value):
        custom_text = self.testTextEdit.toPlainText().strip()
        if custom_text:
            return custom_text
        voice_label = VOICE_VALUE_TO_LABEL.get(voice_value, voice_value)
        preview_name = voice_label.replace(' 2.0', '').replace('2.0', '').strip()
        return '你好呀，我是%s，有什么需要帮助的吗' % preview_name

    def _preview_voice(self):
        if self._initializing:
            return
        # 打断正在进行的预览，换新角色
        if self.preview_worker is not None:
            self.preview_worker.result_ready.disconnect(self._on_preview_result)
            stop_tts()
            self.preview_worker.wait(500)
            self.preview_worker = None
        voice_value = self.voiceCard.currentValue() or config.DEFAULT_TTS_CONFIG['voice_name']
        preview_text = self._preview_text(voice_value)
        self.preview_worker = TtsPreviewWorker(self._voice_preview_path(voice_value, preview_text), parent=self)
        self.preview_worker.result_ready.connect(self._on_preview_result)
        self.preview_worker.start()

    def _on_preview_result(self, success, text):
        self.preview_worker = None
        if not success:
            InfoBar.error('试听失败', text[:120], duration=5000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _collect(self):
        try:
            max_chars = max(1, int(self.maxCharsCard.text() or config.DEFAULT_TTS_CONFIG['max_chars']))
        except ValueError:
            max_chars = config.DEFAULT_TTS_CONFIG['max_chars']
        return {
            'enabled': self.enabledCard.isChecked(),
            'api_key': self.apiKeyCard.text(),
            'voice_name': self.voiceCard.currentValue() or config.DEFAULT_TTS_CONFIG['voice_name'],
            'max_chars': max_chars,
            'test_text': self.testTextEdit.toPlainText().strip(),
            'disable_emoji_filter': config.DEFAULT_TTS_CONFIG['disable_emoji_filter'],
            'max_length_to_filter_parenthesis': config.DEFAULT_TTS_CONFIG['max_length_to_filter_parenthesis'],
        }

    def _collect_voice_chat(self):
        return {
            'continuous': self.continuousVoiceCard.isChecked(),
        }

    def _collect_wake_word(self):
        defaults = config.DEFAULT_WAKE_WORD_CONFIG
        return {
            'enabled': self.wakeEnabledCard.isChecked(),
            'words': self.wakeWordsCard.text().strip() or defaults['words'],
            'model_dir': defaults['model_dir'],
            'sample_rate': defaults['sample_rate'],
            'chunk_ms': defaults['chunk_ms'],
            'restart_delay_ms': defaults['restart_delay_ms'],
        }

    def _collect_doubao_call(self):
        return {
            'speaker': self.doubaoCallSpeakerCard.currentValue() or config.DEFAULT_DOUBAO_CALL_CONFIG['speaker'],
        }

    def _save(self):
        config.save_tts_config(self._collect())
        config.save_voice_chat_config(self._collect_voice_chat())
        config.save_wake_word_config(self._collect_wake_word())
        config.save_doubao_call_config(self._collect_doubao_call())
        self.settings_changed.emit()
        InfoBar.success('保存成功', '语音配置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _test(self):
        cfg = self._collect()
        if not cfg.get('api_key'):
            InfoBar.error('缺少 API Key', '请先填写 API Key', duration=3000, position=InfoBarPosition.BOTTOM, parent=self.window())
            return
        stop_tts()
        self.testBtn.setEnabled(False)
        self.testBtn.setText('播放中...')
        voice_value = cfg['voice_name']
        preview_text = self._preview_text(voice_value)
        self.worker = TtsCacheWorker(preview_text, cfg, self._voice_preview_path(voice_value, preview_text), parent=self)
        self.worker.result_ready.connect(self._on_test_result)
        self.worker.start()

    def _on_test_result(self, success, text):
        self.testBtn.setEnabled(True)
        self.testBtn.setText('测试连接')
        if success:
            InfoBar.success('测试成功', '语音已播放完成', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())
        else:
            InfoBar.error('测试失败', text[:120], duration=5000, position=InfoBarPosition.BOTTOM, parent=self.window())


class ReplyDisplayPage(MiniPetScrollPage):
    def __init__(self, parent=None):
        super().__init__('回复显示设置', parent, save_callback=lambda: self._save())
        cfg = config.typewriter_config
        defaults = config.DEFAULT_TYPEWRITER_CONFIG

        self.displayGroup = SettingCardGroup('AI 回复显示', self.scrollWidget)
        self.enabledCard = SwitchSettingCard(FIF.MESSAGE, 'AI 回复逐字显示', '开启后，AI 回复文字会一字一字显示；关闭后直接显示完整回复', parent=self.displayGroup)
        self.enabledCard.setChecked(bool(cfg.get('enabled', defaults['enabled'])))
        self.speedCard = RangeSettingCard(8, 120, 1, FIF.MESSAGE, '逐字显示速度', '每个字的最大显示间隔，单位毫秒，数值越小越快', self.displayGroup)
        self.speedCard.setValue(int(cfg.get('speed_ms', defaults['speed_ms'])))
        self.maxDurationCard = RangeSettingCard(500, 15000, 1, FIF.FONT_SIZE, '最长显示时长', '单条回复逐字显示的最长时间，单位毫秒', self.displayGroup)
        self.maxDurationCard.setValue(int(cfg.get('max_duration_ms', defaults['max_duration_ms'])))
        self.ttsDelayCard = RangeSettingCard(0, 3000, 1, FIF.VOLUME, '语音播报文字延迟', '开启语音播报时，回复文字延迟显示的时间，单位毫秒', self.displayGroup)
        self.ttsDelayCard.setValue(int(cfg.get('tts_delay_ms', defaults['tts_delay_ms'])))

        for card in [self.enabledCard, self.speedCard, self.maxDurationCard, self.ttsDelayCard]:
            self.displayGroup.addSettingCard(card)
        self.expandLayout.addWidget(self.displayGroup)

    def _collect(self):
        return {
            'enabled': self.enabledCard.isChecked(),
            'speed_ms': int(self.speedCard.value()),
            'max_duration_ms': int(self.maxDurationCard.value()),
            'tts_delay_ms': int(self.ttsDelayCard.value()),
        }

    def _save(self):
        config.save_typewriter_config(self._collect())
        InfoBar.success('保存成功', '回复显示设置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())

