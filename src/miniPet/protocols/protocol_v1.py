# coding:utf-8

PROTOCOL = 'minipet.v1'

SESSION_HELLO = 'session.hello'
SESSION_READY = 'session.ready'
SESSION_PING = 'session.ping'
SESSION_PONG = 'session.pong'
USER_COMMAND = 'user.command'
USER_ACTION = 'user.action'
USER_INPUT = 'user.input'
USER_DROP = 'user.drop'
SURFACE_SHOW = 'surface.show'
SURFACE_UPDATE = 'surface.update'
SURFACE_CLOSE = 'surface.close'
AGENT_STATE = 'agent.state'

SURFACE_KINDS = ['bubble', 'card', 'confirm', 'input', 'choice']
V1_CAPABILITIES = [
    SESSION_HELLO,
    SESSION_READY,
    SESSION_PING,
    SESSION_PONG,
    USER_COMMAND,
    USER_ACTION,
    USER_INPUT,
    USER_DROP,
    SURFACE_SHOW,
    SURFACE_UPDATE,
    SURFACE_CLOSE,
    AGENT_STATE,
]


def normalize_inbound_event(event):
    if not isinstance(event, dict):
        return {
            'version': '1.0',
            'type': SURFACE_SHOW,
            'payload': {
                'kind': 'bubble',
                'content': str(event),
            },
        }
    data = dict(event)
    data.setdefault('version', '1.0')
    data.setdefault('payload', {})
    return data


def hello_payload(client='miniPet'):
    return {
        'client': {
            'name': client,
        },
        'protocol': PROTOCOL,
        'concepts': ['session', 'user', 'surface', 'agent'],
        'surface_kinds': list(SURFACE_KINDS),
        'capabilities': list(V1_CAPABILITIES),
    }
