"""Chat channels module with plugin architecture."""

from yak.channels.base import BaseChannel
from yak.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
