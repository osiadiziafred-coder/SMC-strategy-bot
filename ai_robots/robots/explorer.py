"""Explorer robot — maps unknown environments using AI navigation."""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from ai_robots.core.brain import Brain, Decision
from ai_robots.core.environment import Environment
from ai_robots.core.robot import Robot, RobotState


class ExplorerRobot(Robot):
    """Autonomously explores a grid, avoiding hazards and seeking goals."""

    def __init__(self, name: str = "explorer", use_llm: bool = False):
        brain = Brain(personality="curious explorer", use_llm=use_llm)
        super().__init__(name=name, brain=brain, state=RobotState.EXPLORING)
        self.memory["visited"] = set()
        self.memory["discovered_goals"] = []
        self.memory["discovered_hazards"] = []

    def step(self, env: Environment, extra_context: Optional[Dict] = None) -> Decision:
        readings = self.sense(env)
        pos = readings.get("position")
        if pos:
            self.memory["visited"].add(pos)
        for goal in readings.get("goals", []):
            if goal not in self.memory["discovered_goals"]:
                self.memory["discovered_goals"].append(goal)
        for hazard in readings.get("hazards", []):
            if hazard not in self.memory["discovered_hazards"]:
                self.memory["discovered_hazards"].append(hazard)

        if pos and env.is_goal(pos[0], pos[1]):
            decision = Decision("complete", {}, reasoning="Reached the goal!")
            self.act(env, decision)
            return decision

        return super().step(env, extra_context=extra_context)

    def exploration_report(self) -> Dict:
        return {
            "visited_cells": len(self.memory.get("visited", set())),
            "goals_found": len(self.memory.get("discovered_goals", [])),
            "hazards_found": len(self.memory.get("discovered_hazards", [])),
            "actions_taken": len(self.action_log),
            "final_state": self.state.value,
        }

    @classmethod
    def demo_map(cls) -> str:
        return """
        . . . # . G
        . # . . . .
        . . . X . .
        R . . . # .
        . . X . . .
        """
