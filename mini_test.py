import time
from reachy_mini import ReachyMini

# Connect to the locally running daemon (e.g. the simulation on localhost:8000)
# media_backend='no_media' skips camera/audio setup (not needed here, avoids warnings)
with ReachyMini(host='localhost', connection_mode='localhost_only', media_backend='no_media') as robot:
    print("Connected, waking up...")
    robot.wake_up()

    # Move the antennas to a happy position (values in radians)
    print("Moving antennas...")
    robot.goto_target(antennas=[0.8, -0.8], duration=1.0)
    time.sleep(1)
    print("Antenna positions:", robot.get_present_antenna_joint_positions())

    # Put the robot back to sleep safely
    print("Going to sleep...")
    robot.goto_sleep()

print("Done!")
