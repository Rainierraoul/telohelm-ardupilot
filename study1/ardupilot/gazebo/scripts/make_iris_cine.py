"""Make iris_cine (copy of iris_with_ardupilot) and iris_cine_standoffs (copy of iris_with_standoffs with an FPV and a
chase camera inside base_link). The nested model keeps the name iris_with_standoffs so every scoped reference in the
ArduPilot plugin resolves unchanged. Sensors add no mass, link or joint."""
import sys, re, os
M = sys.argv[1]
std = os.path.join(M, 'iris_cine_standoffs', 'model.sdf')
txt = open(std).read()
assert 'CINE_CAMS' not in txt
cams = """      <!-- CINE_CAMS: forward FPV camera and rigid chase camera, both on base_link -->
      <sensor name="fpv_cam" type="camera">
        <pose>0.15 0 0.05 0 -0.17 0</pose>
        <always_on>1</always_on><update_rate>30</update_rate><topic>/cine/fpv</topic>
        <camera><horizontal_fov>1.75</horizontal_fov>
          <image><width>1920</width><height>1080</height><format>R8G8B8</format></image>
          <clip><near>0.05</near><far>400</far></clip></camera>
      </sensor>
      <sensor name="chase_cam" type="camera">
        <pose>-3.6 0 1.5 0 0.30 0</pose>
        <always_on>1</always_on><update_rate>30</update_rate><topic>/cine/chase</topic>
        <camera><horizontal_fov>1.45</horizontal_fov>
          <image><width>1920</width><height>1080</height><format>R8G8B8</format></image>
          <clip><near>0.1</near><far>400</far></clip></camera>
      </sensor>
"""
lines = txt.splitlines(keepends=True)
in_base = False
for i, ln in enumerate(lines):
    if "<link name='base_link'>" in ln:
        in_base = True
    elif in_base and '</link>' in ln:
        lines.insert(i, cams); break
open(std, 'w').write(''.join(lines))
cfg = os.path.join(M, 'iris_cine_standoffs', 'model.config')
open(cfg, 'w').write(open(cfg).read().replace('<name>Iris with Standoffs</name>', '<name>iris_cine_standoffs (iris_with_standoffs with cinematic cameras)</name>'))
ard = os.path.join(M, 'iris_cine', 'model.sdf')
t = open(ard).read()
t = t.replace('<model name="iris_with_ardupilot">', '<model name="iris_cine">', 1)
t = t.replace('<uri>model://iris_with_standoffs</uri>', '<uri>model://iris_cine_standoffs</uri>\n      <name>iris_with_standoffs</name>', 1)
open(ard, 'w').write(t)
cfg = os.path.join(M, 'iris_cine', 'model.config')
c = open(cfg).read().replace('<name>Iris with ArduPilot</name>', '<name>iris_cine (iris_with_ardupilot with cinematic cameras)</name>')
c = c.replace('<uri>model://iris_with_standoffs</uri>', '<uri>model://iris_cine_standoffs</uri>')
open(cfg, 'w').write(c)
print('ok')
