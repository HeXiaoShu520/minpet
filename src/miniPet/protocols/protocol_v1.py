# coding:utf-8

PROTOCOL = 'minipet.v1'

SESSION_HELLO = 'session.hello'
SESSION_READY = 'session.ready'
SESSION_PING = 'session.ping'
SESSION_PONG = 'session.pong'
USER_INPUT = 'user.input'
SURFACE_SHOW = 'surface.show'
SURFACE_UPDATE = 'surface.update'
SURFACE_CLOSE = 'surface.close'
AGENT_STATE = 'agent.state'

V1_CAPABILITIES = [
    SESSION_HELLO,
    SESSION_READY,
    SESSION_PING,
    SESSION_PONG,
    USER_INPUT,
    SURFACE_SHOW,
    SURFACE_UPDATE,
    SURFACE_CLOSE,
]


def normalize_inbound_event(event):
    if not isinstance(event, dict):
        return {
            'version': '1.0',
            'type': SURFACE_SHOW,
            'payload': {
                'content': str(event),
            },
        }
    data = dict(event)
    data.setdefault('version', '1.0')
    data.setdefault('payload', {})
    return data


def hello_payload():
    return {
        'protocol': PROTOCOL,
        'capabilities': list(V1_CAPABILITIES),
    }
