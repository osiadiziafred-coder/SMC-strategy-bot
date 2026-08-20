"""Python Smart Money Concepts (SMC) robot for XAUUSDm."""

from smc_robot.config import RobotConfig
from smc_robot.robot import SmcRobot
from smc_robot.summary import STRATEGY_SUMMARY, render_summary

__all__ = ["RobotConfig", "SmcRobot", "STRATEGY_SUMMARY", "render_summary"]
__version__ = "1.0.0"
