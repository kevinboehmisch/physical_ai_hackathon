import time
from reachy_mini import ReachyMini

# Connect to your local robot
robot = ReachyMini('localhost')

# Wake up the robot
robot.turn_on()

# Move the antennas to a happy position
robot.head.left_antenna.goal_position = 45
robot.head.right_antenna.goal_position = -45
time.sleep(1)

# Put the robot back to sleep safely
robot.turn_off()
