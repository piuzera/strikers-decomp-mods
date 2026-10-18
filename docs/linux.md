# Linux

1. Install Python 3.10+ and a current Dolphin desktop release. Python needs its
   standard `bz2` module (normally included in packaged Python).
2. Extract the release ZIP. In Dolphin, extract your USA Rev 0 game through
   **Properties → Filesystem → Extract Entire Disc** into a clean folder.
   The folder must contain `sys/main.dol` and `files/`.
3. Open a terminal in the release folder. Assuming `$HOME/Games` exists:

   ```sh
   python3 install.py install --source "$HOME/Games/clean-game" --output "$HOME/Games/strikers-mod"
   python3 install.py run --game "$HOME/Games/strikers-mod" --dolphin "/usr/bin/dolphin-emu"
   ```

Replace the paths as needed. If `dolphin-emu` is in your PATH, `--dolphin` can be
omitted. Flatpak-only Dolphin installations need a launch wrapper that forwards
arguments and access to the game/profile folders; that setup is not tested or
automated here. A native Dolphin executable is the documented route.

The launcher creates `strikers-mod-dolphin-user` beside the game and configures
48 MiB MEM1. Set up Controllers in Dolphin on first use; controls and saves in
this profile persist. Your normal Dolphin profile is separate. Always launch
with the same run command. Installation/verification does not launch Dolphin.

Clean-extraction patch reconstruction was tested on Linux. The combined build's
gameplay and final stadium polish were user-confirmed in Dolphin.
