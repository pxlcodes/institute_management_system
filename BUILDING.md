# Building the Windows production application

The supported release format is a **one-folder Windows build**. Keep the entire
folder together; the EXE depends on the adjacent `_internal` directory. This mode
starts faster and is easier to diagnose than a one-file executable.

## Build

Open PowerShell in the project directory and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_exe.ps1 -PythonPath "C:\Users\Expert\AppData\Local\Python\pythoncore-3.14-64\python.exe"
```

The script creates an isolated `.build-venv`, installs all normal and hardware
dependencies, runs the test suite, builds the EXE, runs a packaged dependency
and startup self-test, and creates:

```text
dist\ELH Management System\ELH Management System.exe
release\ELH-Management-System-Windows-x64.zip
release\ELH-Management-System-Windows-x64.zip.sha256
```

Use `-SkipTests` only for diagnosing a packaging problem. A production release
should always be built with the tests enabled.

To create a private build for this already-configured production machine, include its
current `.env` so the EXE uses the same MySQL database and device settings:

```powershell
.\build_exe.ps1 -PythonPath "C:\Users\Expert\AppData\Local\Python\pythoncore-3.14-64\python.exe" -IncludeProductionConfig
```

This copies configuration only. MySQL data stays on the server and is never copied,
modified, or replaced by the build. Keep the resulting ZIP private because it contains
database and SMS credentials.

## Deploy

1. Extract the release ZIP to a writable folder such as
   `C:\ELH Management System`. Do not run it directly from the ZIP.
2. Rename `environment.example` to `.env` and set the production database,
   hardware, backup, logging, and bootstrap-account values.
3. Do not distribute the development `.env`; it contains machine-specific secrets.
4. Start `ELH Management System.exe`. Python is not required on the target machine.
5. Run the System Administration health monitor and create a verified backup.

MySQL Server remains an external service. The target machine also needs network
access to the configured ZKTeco device and POS printer. MySQL backup/restore needs
`mysqldump.exe` and `mysql.exe`, which are normally installed with MySQL Server.

## Release security

For public or multi-computer distribution, sign both the EXE and final installer
with an organization code-signing certificate. PyInstaller packages Python code;
it does not provide source-code secrecy or trusted publisher signing.
