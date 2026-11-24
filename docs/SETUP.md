# Setting up to fly the studies again

This guide covers what each study used. A new run makes new model calls and flies new simulations, so it will not reproduce the paper's numbers. To check those, use the study records and `reproduce.py`, as the [README](../README.md) describes.

Study 1 and the earlier comparison ran on one Apple Mac (M4 Pro chip, macOS 27.2), and the sections below describe that setup. Paths in them are relative to `study1/`. Study 2 ran on Linux, on Deakin University's computing cluster, and the last section says what differed.

## The Python environment

Use Python 3.12 (Study 1 used 3.12.13). From `study1/`, install the learning-core wheel first, then the tested packages:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-deps protocol/telohelm-0.1.0.dev0-py3-none-any.whl
.venv/bin/python -m pip install --no-deps -r requirements-tested.txt
```

`requirements-tested.txt` pins the exact versions the study ran with, so install it with `--no-deps`. pip's resolver would refuse the list, because SciPy 1.14.1 declares that it needs NumPy below 2.3 while the study ran NumPy 2.5.4. SciPy prints a warning about this when it loads.

The wheel is Telohelm's learning core, and its Python source is identical to Telohelm 0.1.0. Its SHA-256 is `bb2c6e779b7526c85fb6ced29bd0db01f0d30a88a16e2252f2f058cab3ce2f8c`, the value the protocol names, and the runner refuses to start with any other version of the core.

## ArduPilot

The study used ArduPilot Copter 4.7.2 at commit `fb773567`, built for its software-in-the-loop simulator (SITL), which runs the autopilot's own code on an ordinary computer. ArduPilot is not part of this repository.

```sh
git clone --depth 1 --branch Copter-4.7.2 --recurse-submodules --shallow-submodules https://github.com/ArduPilot/ardupilot.git ~/Development/ardupilot
cd ~/Development/ardupilot
uv venv --python 3.12 .venv-build
uv pip install --python .venv-build/bin/python setuptools empy==3.3.4 pexpect future pymavlink
```

On macOS one build flag has to change before the build links. ArduPilot asks for Apple's old linker with `-ld_classic`, which the installed Xcode no longer provides. In `Tools/ardupilotwaf/boards.py`, replace `-ld_classic` with `-no_fixup_chains`. This changes no flight code.

```sh
sed -i '' "s/'-Wl,-dead_strip,-ld_classic',/'-Wl,-dead_strip,-no_fixup_chains',/" Tools/ardupilotwaf/boards.py
PATH="$PWD/.venv-build/bin:$PATH" ./waf configure --board sitl
PATH="$PWD/.venv-build/bin:$PATH" ./waf copter -j8
```

On Linux the change should not be needed, but this was not tried. The study's code looks for ArduPilot in `~/Development/ardupilot`, or in the folder named by the environment variable `ARDUPILOT_HOME`.

## Gazebo

Gazebo flights, which the Split-S racing track uses, need Gazebo Harmonic (Gazebo Sim 8.15.0, installed from Homebrew) and ArduPilot's Gazebo plugin at commit `f116b035` (https://github.com/ArduPilot/ardupilot_gazebo). Before building the plugin, apply `ardupilot/gazebo/ardupilot_gazebo/CMakeLists.patch`. It leaves out the camera-streaming plugins, so the flight plugin builds without OpenCV and GStreamer. The study flew in the world `ardupilot/gazebo/worlds/splits_open.sdf`.

```bash
cd ~/Development
git clone https://github.com/ArduPilot/ardupilot_gazebo.git
cd ardupilot_gazebo
git checkout f116b035
git apply <this repository>/study1/ardupilot/gazebo/ardupilot_gazebo/CMakeLists.patch
mkdir build && cd build
cmake ..
make -j8
```

The study's build used CMake's default settings, as above. The runner itself tells Gazebo where to look: it sets `GZ_SIM_SYSTEM_PLUGIN_PATH` to the plugin's build folder and `GZ_SIM_RESOURCE_PATH` to this repository's model folder and the plugin's own `models` folder (`ardupilot/scored.py`).

`ardupilot/scored.py` names the plugin's build folder and model folder on the author's computer. Edit those two paths to yours. That changes the source fingerprint, as any change to the code does.

## The model endpoint

Learning calls went to Claude Sonnet 5.5 through Deakin University's model gateway, an endpoint that speaks Anthropic's interface. `ardupilot/claude_provider.py` reads the address and key from the environment variables `GEM_BASE_URL` and `GEM_API_KEY`. The model string was `bedrock/au.anthropic.claude-sonnet-5-5`. The gateway is not public, so most readers will use another endpoint, and that needs its own model string.

## Starting a run

From `study1/`:

```sh
.venv/bin/python protocol/run_scored.py run <new folder> --protocol 2
```

Read `PROTOCOL-2.md` before you do. It limits how many simulators run at once, to four on instances 10 to 13, and the runner checks the ports before each flight.

## Study 2

Study 2 flew on one node type of Deakin University's cluster (two Intel Xeon Gold 6448Y processors, Linux), with Python 3.12.15. Paths in this section are relative to `study2/`.

The packages are pinned in `cluster/requirements-mac.txt`, which holds the Mac's versions and was installed on the cluster without dependency resolution. The learning core is the study's own build, `protocol/telohelm-0.1.0.dev0+paper3.2-py3-none-any.whl`, with SHA-256 `36d36b86028643cdec9c3bbc5c90b6e6abe5dcdf31e5877367c38df995ab34b5`. It is Study 1's build of the core with a patch to the sandbox that contains a running procedure (`protocol/wheel3/sandbox.patch`); `protocol/wheel3/WHEEL3.json` records how it was built, and the runner refuses any other build.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-deps protocol/telohelm-0.1.0.dev0+paper3.2-py3-none-any.whl
.venv/bin/python -m pip install --no-deps -r cluster/requirements-mac.txt
```

ArduPilot was Copter 4.7.2 at commit `fb773567`, as in Study 1, built for Linux; the build commands were not recorded, and the macOS build-flag change above was not part of that build. Study 2 used ArduPilot's own simulator. Gazebo was used only for Study 1's gate course. Learning calls went to the same model through the same gateway, under the label `bedrock/au.anthropic.claude-sonnet-5-5`.

The scheduler is `protocol/run_scored3.py`, and `PROTOCOL-3.md` sections 4.5 to 4.8 describe the platform, the fixed command delay and the sandbox it expects. The batch scripts that launched the run on the cluster are specific to that cluster and are not in this repository, so a new run needs its own launcher. The 86 fingerprinted files and the frozen protocol are what a new run has to keep.

