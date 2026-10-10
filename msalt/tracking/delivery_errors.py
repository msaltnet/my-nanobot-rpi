"""Sanitized Telegram delivery outcomes shared by tracking senders."""

from __future__ import annotations


class DeliveryRejected(RuntimeError):  # noqa: N818 - consumed by Issue #17
    """A complete Bot API response explicitly rejected the delivery."""


class DeliveryUnknown(RuntimeError):  # noqa: N818 - consumed by Issue #17
    """Telegram delivery has no confirmed ACK or explicit rejection."""
