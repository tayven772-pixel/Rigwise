# Rigwise — Windows PC Control Center

Rigwise is a local-first Windows utility with a live hardware dashboard, a searchable library of 70+ reversible Windows preferences, startup-app controls, maintenance tools, and a Game Mode with a local game library and live process monitoring.

## Build the Windows executable

1. Open the **Actions** tab in this repository.
2. Choose **Build Rigwise for Windows**.
3. Open the latest run and wait for the build to finish.
4. Download the `Rigwise-Windows-exe` artifact and extract the ZIP to get `Rigwise.exe`.

A push to `main` starts a build automatically. Artifacts are kept for 14 days.

## Safety notes

- Review each optimization before applying it; performance results vary by computer.
- Game Mode launches the selected executable directly and may set that process to Above normal priority. It does not close background apps, guarantee higher FPS, or automatically detect every child process started by a launcher.
- Registry tweaks save the previous values before changing them. Use **Optimize → Undo all** to restore backed-up settings.
- Some changes require administrator rights or a restart. Laptop power settings may reduce battery life.
- Temporary-file cleanup skips files Windows is currently using.
- The executable is not code-signed, so Windows may show a security warning.
