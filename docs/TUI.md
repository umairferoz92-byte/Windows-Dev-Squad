# Squad — Windows Terminal live view

`squad status` renders the live agent view (one card per agent: name, role,
step, status, cost against budget, files touched) with [rich](https://rich.readthedocs.io).

This ships the *rendering* (Phase 7). The live-refresh daemon arrives in Phase 8
(parallel squad) and Phase 10 (web gateway). Without an active run it shows an
idle snapshot, or you can load a state file:

```powershell
squad status                      # idle / no active run
squad status --state state.json   # render a JSON snapshot of agent cards
```

`state.json` example:

```json
[{"name": "ironman", "role": "coder", "step": 2, "status": "working",
  "cost": 0.001, "budget": 0.1, "files": ["src/main.py"]}]
```

## Windows Terminal profile named "Squad"

Add a profile to your Windows Terminal settings (`settings.json`, under
`profiles.list`) so you can open the squad TUI from the dropdown:

```json
{
  "name": "Squad",
  "commandline": "powershell.exe -NoExit -Command \"cd $env:USERPROFILE\\path\\to\\squad; .\\.venv\\Scripts\\squad.exe status\"",
  "icon": "ms-appx:///ProfileIcons/{9acb9455-ca41-5af7-950f-6bca1bc9722f}.png",
  "startingDirectory": "C:\\Users\\<you>\\Desktop\\Windows Dev Squad",
  "closeOnExit": "graceful"
}
```

Adjust `startingDirectory` and the `cd` path to the project, and the 
`squad.exe` path if your venv differs)Skip headless.

## In-view approvals

Approvals show the exact tool, folder, and reason, and expire in 5 minutes. The
`render_approval` helper renders that prompt for tests and the future live loop.