"""Base robot class and state management."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ai_robots.core.brain import Brain, Decision
from ai_robots.core.environment import Environment


class RobotState(Enum):
    IDLE = "idle"
    ACTIVE = "active"
    EXPLORING = "exploring"
    PATROLLING = "patrolling"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Robot:
    """A virtual robot with sensors, a brain, and an action loop."""

    name: str
    brain: Brain
    state: RobotState = RobotState.IDLE
    memory: Dict[str, Any] = field(default_factory=dict)
    action_log: List[str] = field(default_factory=list)
    energy: int = 100

    def wake(self) -> None:
        self.state = RobotState.ACTIVE
        self.log(f"{self.name} is now active.")

    def sleep(self) -> None:
        self.state = RobotState.IDLE
        self.log(f"{self.name} is sleeping.")

    def log(self, message: str) -> None:
        self.action_log.append(message)

    def sense(self, env: Environment, radius: int = 1) -> Dict:
        return env.sense(self.name, radius=radius)

    def think(self, context: Dict) -> Decision:
        return self.brain.decide(context)

    def act(self, env: Environment, decision: Decision) -> bool:
        if decision.action == "move":
            direction = decision.params.get("direction", "north")
            success = env.move_robot(self.name, direction)
            if success:
                self.energy = max(0, self.energy - 1)
                self.log(f"Moved {direction} to {env.robot_positions[self.name]}")
            else:
                self.log(f"Blocked — cannot move {direction}")
            return success
        if decision.action == "wait":
            self.log("Waiting...")
            return True
        if decision.action == "speak":
            message = decision.params.get("message", "...")
            self.log(f"Says: {message}")
            return True
        if decision.action == "complete":
            self.state = RobotState.COMPLETED
            self.log("Task completed!")
            return True
        if decision.action == "fail":
            self.state = RobotState.FAILED
            self.log(f"Failed: {decision.params.get('reason', 'unknown')}")
            return False
        self.log(f"Unknown action: {decision.action}")
        return False

    def step(self, env: Environment, extra_context: Optional[Dict] = None) -> Decision:
        """Run one sense-think-act cycle."""
        if self.state in (RobotState.COMPLETED, RobotState.FAILED, RobotState.IDLE):
            return Decision("wait", {})

        readings = self.sense(env)
        context = {
            "robot_name": self.name,
            "state": self.state.value,
            "readings": readings,
            "memory": self.memory,
            "energy": self.energy,
        }
        if extra_context:
            context.update(extra_context)

        decision = self.think(context)
        self.act(env, decision)
        return decision

    def run(self, env: Environment, max_steps: int = 100, extra_context: Optional[Dict] = None) -> List[Decision]:
        """Run the robot autonomously for up to max_steps."""
        self.wake()
        decisions: List[Decision] = []
        for _ in range(max_steps):
            if self.state in (RobotState.COMPLETED, RobotState.FAILED):
                break
            if self.energy <= 0:
                self.state = RobotState.FAILED
                self.log("Out of energy!")
                break
            decision = self.step(env, extra_context=extra_context)
            decisions.append(decision)
        return decisions
