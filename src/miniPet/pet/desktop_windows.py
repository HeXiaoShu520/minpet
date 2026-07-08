# coding:utf-8


def show_chat_window(owner, history=None, append_message=None, content_for_llm=None, system_prompt_builder=None):
    from miniPet.windows.chat_window import ChatWindow
    from miniPet import config

    if owner.chat_window is None:
        owner.chat_window = ChatWindow(config.current_pet, owner, history=history, append_message=append_message, content_for_llm=content_for_llm, system_prompt_builder=system_prompt_builder)
    else:
        owner.chat_window.append_message = append_message
        owner.chat_window.content_for_llm = content_for_llm
        owner.chat_window.system_prompt_builder = system_prompt_builder
        if history is not None and owner.chat_window.history is not history:
            owner.chat_window.history = history
            owner.chat_window.reload_history()
        elif history is not None:
            owner.chat_window.reload_history()
    owner.chat_window.show_window()


def show_doubao_call_window(owner, append_message=None):
    from miniPet import config
    from miniPet.windows.doubao_call_window import DoubaoCallWindow

    if owner.doubao_call_window is None:
        owner.doubao_call_window = DoubaoCallWindow(config.current_pet, owner, append_message=append_message)
        owner.doubao_call_window.closed_signal.connect(owner._on_doubao_call_closed)
    else:
        owner.doubao_call_window.pet_name = config.current_pet
        owner.doubao_call_window.append_message = append_message
    owner.doubao_call_window.show_window()
