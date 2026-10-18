# Rigwise — Windows PC Control Center

Rigwise is a local-first Windows utility with a redesigned dashboard, live CPU/memory/disk meters, hardware summary, searchable optimization library, startup-app controls, and maintenance tools.

## Build the Windows executable

1. Open the **Actions** tab in this repository.
2. Choose **Build Rigwise for Windows**.
3. Open the latest run and wait for the build to finish.
4. Download the `Rigwise-Windows-exe` artifact and extract the ZIP to get `Rigwise.exe`.

A push to `main` starts a build automatically. Artifacts are kept for 14 days.

## Safety notes

- Review each optimization before applying it; performance results vary by computer.
- Registry tweaks save the previous values before changing them. Use **Optimize → Undo all** to restore backed-up settings.
- Some changes require administrator rights or a restart. Laptop power settings may reduce battery life.
- Temporary-file cleanup skips files Windows is currently using.
- The executable is not code-signed, so Windows may show a security warning.
