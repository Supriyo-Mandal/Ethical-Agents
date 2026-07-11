from __future__ import annotations

from app.agents.base_agent import BaseAgent


class TransparencyAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="Transparency")
