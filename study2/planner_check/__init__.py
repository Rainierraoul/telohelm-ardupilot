"""ArduPilot's own path planner, flown on Study 2's zone flights (design: notes/PLANNER-CHECK-DESIGN-20261120.md).

Nothing in this folder is part of the scored build, and nothing here makes a model call.

One thing is done here when the folder is first imported: the environment variable MAVLINK20 is set to 1, before any
code loads the MAVLink library. Uploading a fence to the autopilot needs the second version of the MAVLink message
format, because only that version carries the field that says the items are fence items and not mission items. The
study's own processes switch to the second version by themselves at the first heartbeat from the autopilot, so this
changes only what happens before the first connection. The variable reaches only this process and its children.
"""
import os

os.environ['MAVLINK20'] = '1'
