# coding:utf-8


def show_chat_window(owner, history=None, append_message=None, content_for_llm=None, system_prompt_builder=None, clear_history_callback=None, send_callback=None, backend='builtin'):
    from windows.chat_window import ChatWindow
    import config

    if owner.chat_window is None:
        owner.chat_window = ChatWindow(config.pet_display_name(), owner, history=history, append_message=append_message, content_for_llm=content_for_llm, system_prompt_builder=system_prompt_builder, clear_history_callback=clear_history_callback, send_callback=send_callback, backend=backend)
    else:
        owner.chat_window.set_pet_name(config.pet_display_name())
        owner.chat_window.append_message = append_message
        owner.chat_window.content_for_llm = content_for_llm
        owner.chat_window.system_prompt_builder = system_prompt_builder
        owner.chat_window.clear_history_callback = clear_history_callback
        owner.chat_window.send_callback = send_callback
        owner.chat_window.set_backend(backend)
        if history is not None and owner.chat_window.history is not history:
            owner.chat_window.history = history
            owner.chat_window.reload_history()
        elif history is not None:
            owner.chat_window.reload_history()
    owner.chat_window.show_window()


def show_doubao_call_window(owner, append_message=None):
    import config
    from windows.doubao_call_window import DoubaoCallWindow

    if owner.doubao_call_window is None:
        owner.doubao_call_window = DoubaoCallWindow(config.pet_display_name(), owner, append_message=append_message)
        owner.doubao_call_window.closed_signal.connect(owner._on_doubao_call_closed)
    else:
        owner.doubao_call_window.pet_name = config.pet_display_name()
        owner.doubao_call_window.append_message = append_message
    owner.doubao_call_window.show_window()
