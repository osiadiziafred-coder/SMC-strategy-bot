"""AI brain for robot decision-making — rule-based and optional LLM."""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Decision:
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""


class Brain:
    """
    Hybrid AI brain: uses rule-based logic by default,
    with optional OpenAI LLM integration when API key is set.
    """

    def __init__(
        self,
        personality: str = "helpful",
        use_llm: bool = False,
        custom_rules: Optional[List[Callable[[Dict], Optional[Decision]]]] = None,
    ):
        self.personality = personality
        self.use_llm = use_llm and bool(os.environ.get("OPENAI_API_KEY"))
        self.custom_rules = custom_rules or []
        self.decision_history: List[Decision] = []

    def decide(self, context: Dict) -> Decision:
        for rule in self.custom_rules:
            decision = rule(context)
            if decision is not None:
                self._record(decision)
                return decision

        if self.use_llm:
            llm_decision = self._llm_decide(context)
            if llm_decision:
                self._record(llm_decision)
                return llm_decision

        decision = self._rule_based_decide(context)
        self._record(decision)
        return decision

    def _record(self, decision: Decision) -> None:
        self.decision_history.append(decision)

    def _rule_based_decide(self, context: Dict) -> Decision:
        readings = context.get("readings", {})
        open_dirs = readings.get("open_directions", [])
        goals = readings.get("goals", [])
        hazards = readings.get("hazards", [])
        memory = context.get("memory", {})

        if goals:
            goal = goals[0]
            pos = readings.get("position", (0, 0))
            direction = self._direction_toward(pos, goal, open_dirs)
            if direction:
                return Decision(
                    "move",
                    {"direction": direction},
                    reasoning="Moving toward detected goal.",
                )

        if hazards and not open_dirs:
            return Decision("fail", {"reason": "Surrounded by hazards"}, reasoning="No safe moves.")

        visited: set = memory.get("visited", set())
        unvisited = [d for d in open_dirs if self._next_pos(readings.get("position", (0, 0)), d) not in visited]
        if unvisited:
            direction = random.choice(unvisited)
            return Decision(
                "move",
                {"direction": direction},
                reasoning="Exploring unvisited area.",
            )

        if open_dirs:
            safe = [d for d in open_dirs if not self._direction_has_hazard(d, readings)]
            direction = random.choice(safe if safe else open_dirs)
            return Decision(
                "move",
                {"direction": direction},
                reasoning="Random safe movement.",
            )

        return Decision("wait", {}, reasoning="No valid moves available.")

    def _llm_decide(self, context: Dict) -> Optional[Decision]:
        try:
            from openai import OpenAI

            client = OpenAI()
            readings = context.get("readings", {})
            prompt = (
                f"You are a robot brain with personality: {self.personality}.\n"
                f"Robot state: {context.get('state')}\n"
                f"Sensor readings: {readings}\n"
                f"Energy: {context.get('energy')}\n"
                "Respond with ONE action as JSON: "
                '{"action": "move|wait|speak|complete", '
                '"params": {"direction": "north|south|east|west"} or {"message": "..."}, '
                '"reasoning": "why"}'
            )
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=150,
            )
            import json

            data = json.loads(response.choices[0].message.content)
            return Decision(
                data.get("action", "wait"),
                data.get("params", {}),
                reasoning=data.get("reasoning", "LLM decision"),
            )
        except Exception:
            return None

    @staticmethod
    def _direction_toward(pos: tuple, target: tuple, open_dirs: List[str]) -> Optional[str]:
        dx = target[0] - pos[0]
        dy = target[1] - pos[1]
        preferred = []
        if dx > 0:
            preferred.append("east")
        elif dx < 0:
            preferred.append("west")
        if dy > 0:
            preferred.append("south")
        elif dy < 0:
            preferred.append("north")
        for direction in preferred:
            if direction in open_dirs:
                return direction
        return open_dirs[0] if open_dirs else None

    @staticmethod
    def _next_pos(pos: tuple, direction: str) -> tuple:
        offsets = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
        dx, dy = offsets.get(direction, (0, 0))
        return (pos[0] + dx, pos[1] + dy)

    @staticmethod
    def _direction_has_hazard(direction: str, readings: Dict) -> bool:
        pos = readings.get("position", (0, 0))
        hazards = readings.get("hazards", [])
        offsets = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
        dx, dy = offsets.get(direction, (0, 0))
        return (pos[0] + dx, pos[1] + dy) in hazards
