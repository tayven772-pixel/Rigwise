# Rigwise — Windows EXE build

This repository builds `rigwise.py` into `Rigwise.exe` on a GitHub-hosted Windows runner.

## Build

1. Add the project file `rigwise.py` to the repository root.
2. Open the **Actions** tab and choose **Build Rigwise for Windows**.
3. If needed, select **Run workflow** on `main`.
4. Open the completed run and download the `Rigwise-Windows-exe` artifact. Extract the ZIP to get `Rigwise.exe`.

A push to `main` also starts a build automatically. Artifacts are retained for 14 days and are not published as a public release.

**Safety:** Rigwise can change Windows settings. Review each tweak before applying it and keep the app's backup file so you can restore settings. Windows may warn that the executable is unsigned.
