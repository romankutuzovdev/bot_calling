# CI/CD: push to GitHub → Windows Server updates

Push to `main` triggers GitHub Actions on a **self-hosted runner** installed on your Windows Server.
The runner runs `webapp/scripts/deploy_update.ps1` (git pull + restart uvicorn on `0.0.0.0:8080`).

## One-time setup on Windows Server

### 1. Repo already cloned

```powershell
cd C:\
git clone https://github.com/romankutuzovdev/bot_calling.git
cd C:\bot_calling
```

### 2. Install app once (venv + deps)

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\webapp\scripts\install_windows.ps1
```

Or minimal web-only:

```powershell
cd C:\bot_calling
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r webapp\requirements-web.txt
```

### 3. Register GitHub self-hosted runner

1. Open: https://github.com/romankutuzovdev/bot_calling/settings/actions/runners/new  
2. OS: **Windows**, Architecture: **x64**  
3. On the server, in PowerShell **as Admin**:

```powershell
mkdir C:\actions-runner
cd C:\actions-runner
# download+extract using the commands shown on that GitHub page
.\config.cmd --url https://github.com/romankutuzovdev/bot_calling --token PASTE_TOKEN_FROM_GITHUB
# labels: leave default (self-hosted, Windows, X64)
.\run.cmd
```

To run runner as a service (survives reboot):

```powershell
cd C:\actions-runner
.\svc.cmd install
.\svc.cmd start
```

### 4. Voice sample (not in git)

Copy manually once:

`C:\bot_calling\voices\my_voice_22k.wav`

### 5. Firewall

```powershell
New-NetFirewallRule -DisplayName "Bot Calling 8080" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
```

## Daily use

On your Mac:

```bash
cd ~/Desktop/bot_calling
git add -A
git commit -m "your message"
git push origin main
```

On the server the runner will:
1. `git reset --hard origin/main`
2. refresh web pip deps
3. restart the bot on port **8080**

Check run: https://github.com/romankutuzovdev/bot_calling/actions

## Manual deploy (without waiting for Actions)

```powershell
cd C:\bot_calling
Set-ExecutionPolicy -Scope Process Bypass
.\webapp\scripts\deploy_update.ps1
```

## Notes

- Runner must stay online (`run.cmd` or Windows service).
- WAV / models are gitignored — copy by hand.
- XTTS (torch) is heavy; `deploy_update.ps1` installs web deps only. Install XTTS once with `install_windows.ps1` if needed.
