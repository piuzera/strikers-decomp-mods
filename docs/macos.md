# macOS

1. Install Python 3.10+ from [python.org](https://www.python.org/downloads/macos/)
   (or your package manager) and Dolphin from [dolphin-emu.org](https://dolphin-emu.org/).
   Move Dolphin to `/Applications` and open it once normally.
2. Extract the release ZIP. Use Dolphin's **Properties → Filesystem → Extract
   Entire Disc** on your USA Rev 0 game. The chosen clean folder must contain
   `sys/main.dol` and `files/`.
3. Open Terminal in the extracted release folder. Assuming `$HOME/Games` exists:

   ```sh
   python3 install.py install --source "$HOME/Games/clean-game" --output "$HOME/Games/strikers-mod"
   python3 install.py run --game "$HOME/Games/strikers-mod" --dolphin "/Applications/Dolphin.app/Contents/MacOS/Dolphin"
   ```

Replace the game paths as needed. `--dolphin` may be omitted when Dolphin is
installed at the standard `/Applications` path. The launcher uses the executable
inside the app bundle, not `open -a`, so the memory settings are passed through.

A separate `strikers-mod-dolphin-user` folder is created beside the installed
game with the required 48 MiB MEM1 configuration. Configure Controllers in the
launched Dolphin on first use. Use the same command for later sessions.

The installer uses standard-library Python; macOS installation/gameplay has not
been independently tested for v1.0.0. The release does not include an unsigned
native installer, Homebrew dependency or Blender assets.
