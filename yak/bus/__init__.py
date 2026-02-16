"""Message bus module for decoupled channel-agent communication."""

from yak.bus.events import InboundMessage, OutboundMessage
from yak.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
