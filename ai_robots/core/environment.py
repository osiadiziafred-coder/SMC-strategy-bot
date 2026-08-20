"""2D grid simulation environment for virtual robots."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Dict, List, Optional, Set, Tuple

Position = Tuple[int, int]


class CellType(Enum):
    EMPTY = "."
    WALL = "#"
    GOAL = "G"
    HAZARD = "X"
    ROBOT = "R"


@dataclass
class Environment:
    """A grid world where robots can move, sense, and interact."""

    width: int
    height: int
    walls: Set[Position] = field(default_factory=set)
    goals: Set[Position] = field(default_factory=set)
    hazards: Set[Position] = field(default_factory=set)
    robot_positions: Dict[str, Position] = field(default_factory=dict)

    DIRECTIONS: ClassVar[Dict[str, Position]] = {
        "north": (0, -1),
        "south": (0, 1),
        "east": (1, 0),
        "west": (-1, 0),
    }

    def is_valid(self, x: int, y: int) -> bool:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        return (x, y) not in self.walls

    def is_goal(self, x: int, y: int) -> bool:
        return (x, y) in self.goals

    def is_hazard(self, x: int, y: int) -> bool:
        return (x, y) in self.hazards

    def place_robot(self, name: str, x: int, y: int) -> None:
        if not self.is_valid(x, y):
            raise ValueError(f"Cannot place robot at invalid position ({x}, {y})")
        self.robot_positions[name] = (x, y)

    def move_robot(self, name: str, direction: str) -> bool:
        if name not in self.robot_positions:
            return False
        dx, dy = self.DIRECTIONS.get(direction, (0, 0))
        x, y = self.robot_positions[name]
        new_x, new_y = x + dx, y + dy
        if not self.is_valid(new_x, new_y):
            return False
        if any(pos == (new_x, new_y) for pos in self.robot_positions.values()):
            return False
        self.robot_positions[name] = (new_x, new_y)
        return True

    def get_neighbors(self, x: int, y: int) -> List[Tuple[str, Position]]:
        neighbors = []
        for direction, (dx, dy) in self.DIRECTIONS.items():
            nx, ny = x + dx, y + dy
            if self.is_valid(nx, ny):
                neighbors.append((direction, (nx, ny)))
        return neighbors

    def sense(self, name: str, radius: int = 1) -> Dict:
        """Return sensor readings around a robot."""
        if name not in self.robot_positions:
            return {}
        x, y = self.robot_positions[name]
        readings: Dict = {
            "position": (x, y),
            "walls": [],
            "goals": [],
            "hazards": [],
            "open_directions": [],
            "blocked_directions": [],
        }
        for direction, (dx, dy) in self.DIRECTIONS.items():
            for step in range(1, radius + 1):
                nx, ny = x + dx * step, y + dy * step
                if not (0 <= nx < self.width and 0 <= ny < self.height):
                    if step == 1:
                        readings["blocked_directions"].append(direction)
                    break
                if (nx, ny) in self.walls:
                    if step == 1:
                        readings["blocked_directions"].append(direction)
                    readings["walls"].append((nx, ny))
                    break
                if step == 1:
                    readings["open_directions"].append(direction)
                if (nx, ny) in self.goals:
                    readings["goals"].append((nx, ny))
                if (nx, ny) in self.hazards:
                    readings["hazards"].append((nx, ny))
        return readings

    def render(self, highlight: Optional[str] = None) -> str:
        grid = [[CellType.EMPTY.value for _ in range(self.width)] for _ in range(self.height)]
        for wx, wy in self.walls:
            grid[wy][wx] = CellType.WALL.value
        for gx, gy in self.goals:
            grid[gy][gx] = CellType.GOAL.value
        for hx, hy in self.hazards:
            grid[hy][hx] = CellType.HAZARD.value
        for name, (rx, ry) in self.robot_positions.items():
            grid[ry][rx] = name[0].upper() if name else CellType.ROBOT.value
        lines = []
        for row in grid:
            lines.append(" ".join(row))
        header = f"Environment ({self.width}x{self.height})"
        if highlight:
            header += f" — {highlight}"
        return header + "\n" + "\n".join(lines)

    @classmethod
    def from_ascii_map(cls, name: str, ascii_map: str) -> "Environment":
        """Build an environment from an ASCII layout string."""
        rows = [line.strip() for line in ascii_map.strip().splitlines() if line.strip()]
        height = len(rows)
        width = max(len(row.replace(" ", "")) for row in rows)
        env = cls(width=width, height=height)
        for y, row in enumerate(rows):
            cells = row.replace(" ", "")
            for x, cell in enumerate(cells):
                if cell == "#":
                    env.walls.add((x, y))
                elif cell == "G":
                    env.goals.add((x, y))
                elif cell == "X":
                    env.hazards.add((x, y))
                elif cell in ("R", "S", "E"):
                    env.place_robot(name, x, y)
        return env
