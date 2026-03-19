from __future__ import annotations

from importlib import import_module


__all__ = [
    "PresenceRuntime",
    "PresenceTurnResult",
    "TelegramBotRunner",
    "TelegramClient",
    "TelegramUpdate",
    "VoiceBridge",
    "VoiceSynthesisResult",
    "VoiceTranscriptionResult",
]


_EXPORTS = {
    "PresenceRuntime": (".runtime", "PresenceRuntime"),
    "PresenceTurnResult": (".runtime", "PresenceTurnResult"),
    "TelegramBotRunner": (".telegram", "TelegramBotRunner"),
    "TelegramClient": (".telegram", "TelegramClient"),
    "TelegramUpdate": (".telegram", "TelegramUpdate"),
    "VoiceBridge": (".voice", "VoiceBridge"),
    "VoiceSynthesisResult": (".voice", "VoiceSynthesisResult"),
    "VoiceTranscriptionResult": (".voice", "VoiceTranscriptionResult"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _EXPORTS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
