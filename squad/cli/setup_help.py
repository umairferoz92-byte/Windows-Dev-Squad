"""One-time administrator setup instructions for ``squad doctor --setup-help``."""

from __future__ import annotations


def setup_help_text() -> str:
    return """\
squad doctor --setup-help
=========================

One-time, manual administrator setup for isolation Level 1: a low-privilege
Windows user whose network access is blocked. You perform these steps yourself
in an elevated PowerShell. squad never asks for administrator rights.

What this achieves and why
--------------------------
Level 1 runs agent code as a dedicated standard (non-admin) account whose
network is blocked, so the code cannot reach the internet. It is the weakest
isolation: it only protects against network use and reading the main profile.
For any repository you care about, prefer Level 2 (Windows Sandbox) or Level 3
(a dev VM), which are simpler and stronger.

Correctness note
----------------
New-NetFirewallRule -LocalUser does NOT block ordinary (non-IPsec) traffic;
that parameter only matches IPsec-authenticated traffic. A hard per-user
network block requires a Windows Filtering Platform (WFP) filter keyed to the
user's SID. A tested, automated helper for this is scheduled for Phase 2.
Until it ships, `squad doctor` reports Level 1 as "not available" even if the
user below exists, unless a verified marker is present.

Step 1 - create the low-privilege user (elevated)
-------------------------------------------------
PowerShell (recommended; prompts for a password you choose):
    $pw = Read-Host -AsSecureString "Password for squad-agent"
    New-LocalUser -Name "squad-agent" -Password $pw -PasswordNeverExpires `
        -AccountNeverExpires -Description "squad isolation Level 1"
    Add-LocalGroupMember -Group "Users" -Member "squad-agent"
    # do NOT add this user to Administrators

Classic net.exe (password appears in your shell history; prefer New-LocalUser):
    net user squad-agent "CHANGE-ME-STRONG-PASSWORD" /add /expires:never

Step 2 - block that user's network
----------------------------------
Apply a WFP outbound+inbound BLOCK filter on the ALE AUTH CONNECT and
ALE AUTH RECV ACCEPT layers (IPv4 and IPv6) with FWPM_CONDITION_USER_ID equal
to the user's SID. Treat any script as untrusted until Step 3 passes. A
reviewed, tested helper ships in Phase 2.

Recommended alternative for this machine - Level 2 (Windows Sandbox):
    Enable-WindowsOptionalFeature -Online -FeatureName "Containers-DisposableClientVM" -All
    # then reboot. Requires Pro/Enterprise/Education and virtualization enabled.

Step 3 - verify (run as the agent user; both checks must FAIL)
--------------------------------------------------------------
Network must be blocked:
    Invoke-WebRequest https://example.com -UseBasicParsing -TimeoutSec 10
    # must throw (blocked or timed out). If it succeeds, the block is not working.

The agent must not read your profile:
    Test-Path "C:\\Users\\YOUR-ACCOUNT-NAME"
    # must be False (access denied).

Step 4 - record verification so doctor reports Level 1
------------------------------------------------------
Only after Step 3 fails correctly, write this marker file:
    %ProgramData%\\squad\\guard\\level1-firewall.json
with contents:
    {"user": "squad-agent", "sid": "S-1-5-...", "verified": true}

squad doctor reports Level 1 as available only when the user exists AND the
marker is present with "verified": true. This default-deny behavior is
intentional: a partially configured Level 1 is treated as unavailable.
"""
