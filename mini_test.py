import time
from reachy_mini import ReachyMini

robot = ReachyMini()

robot.wake_up()

import numpy as np
robot.goto_target(antennas=np.deg2rad([45, -45]), duration=1.0)
time.sleep(1)

robot.goto_sleep()