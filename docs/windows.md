# Windows

1. Install Python 3.10+ from [python.org](https://www.python.org/downloads/windows/)
   and Dolphin from [dolphin-emu.org](https://dolphin-emu.org/).
2. Extract the release ZIP. Extract your USA Rev 0 game through Dolphin's
   **Properties → Filesystem → Extract Entire Disc** into `C:\Strikers\clean-game`.
   This folder must contain `sys\main.dol` and `files\`.
3. In the release folder, open PowerShell. Assuming `C:\Strikers` exists:

   ```powershell
   py -3 install.py install --source "C:\Strikers\clean-game" --output "C:\Strikers\game"
   py -3 install.py run --game "C:\Strikers\game" --dolphin "C:\Dolphin\Dolphin.exe"
   ```

Replace the paths with your own. If `py` is unavailable but `python` starts
Python 3.10+, use `python` instead. Use Dolphin's actual executable path, not a
desktop shortcut. Configure Controllers in the launched Dolphin on first use.

The launcher writes a separate profile at `C:\Strikers\game-dolphin-user` and
enforces 48 MiB MEM1. Use the same run command for later sessions. Do not launch
the game with Dolphin's normal 24 MiB profile. No administrator privileges are needed.

The installer is standard-library Python; this Windows procedure has not been
independently tested for v1.0.0. See the main README for release scope and limits.
