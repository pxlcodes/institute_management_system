"""External service adapters kept separate from business workflows."""

from .ai.agent import ExternalAIAgent

__all__ = ["ExternalAIAgent"]
