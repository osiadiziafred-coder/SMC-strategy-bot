"""Guard robot — patrols waypoints and detects intruders."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ai_robots.core.brain import Brain, Decision
from ai_robots.core.environment import Environment
from ai_robots.core.robot import Robot, RobotState


class GuardRobot(Robot):
    """Patrols between waypoints and alerts on hazards or goals (intruders)."""

    def __init__(
        self,
        name: str = "guard",
        waypoints: Optional[List[Tuple[int, int]]] = None,
        use_llm: bool = False,
    ):
        brain = Brain(personality="vigilant guard", use_llm=use_llm)
        super().__init__(name=name, brain=brain, state=RobotState.PATROLLING)
        self.waypoints = waypoints or []
        self.memory["waypoint_index"] = 0
        self.memory["alerts"] = []

        def patrol_rule(context: Dict) -> Optional[Decision]:
            readings = context.get("readings", {})
            if readings.get("hazards"):
                return Decision(
                    "speak",
                    {"message": "ALERT: Hazard detected nearby!"},
                    reasoning="Hazard proximity alert.",
                )
            if readings.get("goals"):
                return Decision(
                    "speak",
                    {"message": "ALERT: Unauthorized object detected!"},
                    reasoning="Intruder/object alert.",
                )
            return None

        self.brain.custom_rules.insert(0, patrol_rule)

    def _current_waypoint(self) -> Optional[Tuple[int, int]]:
        if not self.waypoints:
            return None
        idx = self.memory.get("waypoint_index", 0)
        return self.waypoints[idx % len(self.waypoints)]

    def step(self, env: Environment, extra_context: Optional[Dict] = None) -> Decision:
        readings = self.sense(env)
        pos = readings.get("position")
        waypoint = self._current_waypoint()

        if waypoint and pos == waypoint:
            self.memory["waypoint_index"] = self.memory.get("waypoint_index", 0) + 1
            self.log(f"Waypoint {waypoint} secured.")

        if waypoint and pos:
            direction = Brain._direction_toward(pos, waypoint, readings.get("open_directions", []))
            if direction:
                decision = Decision(
                    "move",
                    {"direction": direction},
                    reasoning=f"Patrolling toward waypoint {waypoint}.",
                )
                self.act(env, decision)
                return decision

        return super().step(env, extra_context=extra_context)

    def patrol_report(self) -> Dict:
        return {
            "waypoints": len(self.waypoints),
            "cycles_completed": self.memory.get("waypoint_index", 0) // max(len(self.waypoints), 1),
            "alerts": self.memory.get("alerts", []),
            "actions_taken": len(self.action_log),
            "final_state": self.state.value,
        }

    @classmethod
    def demo_map(cls) -> str:
        return """
        G . . . G
        . # . # .
        . . S . .
        . # . # .
        G . . . G
        """
