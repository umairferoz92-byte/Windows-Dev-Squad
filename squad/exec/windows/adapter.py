"""Windows executor adapter backed by Job Objects, with isolation-level launch.

Supports:
  - Level 0: run in the current user's account (never for agent code).
  - Level 1: run as a low-privilege user via CreateProcessWithLogonW
             (requires the configured user + verified firewall-block marker).
  - Level 2: Windows Sandbox launch (requires Windows Sandbox feature).
  - Level 3: restricted-token / low-integrity launch (works on Windows Home;
             CreateRestrictedToken + Job Object with memory/process/time limits,
             plus a per-user firewall-block marker).
  - Level 4: WSL2 / Docker (detected, experimental).
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
from pathlib import Path

from squad.exec.adapter import OSAdapter
from squad.exec.result import ProcessResult
from squad.exec.windows.job import CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW, JobObject

# ---- CreateProcessWithLogonW (Level 1) constants -------------------------
LOGON_WITH_PROFILE = 0x00000001
LOGON_NETCREDENTIALS_ONLY = 0x00000002
CREATE_UNICODE_ENVIRONMENT = 0x00000400

# ---- Windows Sandbox (Level 2) constants ---------------------------------
_PROCESS_QUERY_INFORMATION = 0x0400


class WindowsAdapter(OSAdapter):
    name = "windows"
    platform = "win32"

    # ------------------------------------------------------------------
    # Isolation availability
    # ------------------------------------------------------------------
    def supports_isolation(self, level: int) -> bool:
        if level == 0:
            return True
        if level == 1:
            return self._level1_ready()
        if level == 2:
            return self._level2_ready()
        if level == 3:
            return self._level3_ready()
        if level == 4:
            return self._level4_ready()
        return False

    def _level3_ready(self) -> bool:
        """Level 3 (restricted token) is available on any Windows build once the
        per-user firewall-block marker is verified (works on Windows Home)."""
        from squad.exec.windows.restricted import level3_ready, restricted_marker_path
        return level3_ready(restricted_marker_path(
            os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
        ))

    def _level1_ready(self) -> bool:
        """Level 1 is available only if the low-privilege user exists AND a
        verified firewall-block marker is present (default-deny)."""
        user = self._low_priv_user()
        if not user:
            return False
        if not self._user_exists(user):
            return False
        marker = self._marker_path()
        return marker.exists() and "verified" in (marker.read_text(encoding="utf-8") or "")

    def _level2_ready(self) -> bool:
        """Windows Sandbox is present only on Pro/Enterprise/Education with
        the feature enabled."""
        sandbox = Path(r"C:\Windows\System32\WindowsSandbox.exe")
        return sandbox.exists()

    def _level4_ready(self) -> bool:
        """WSL2 or Docker detected (experimental, network-off required)."""
        for exe in ("wsl.exe", "docker.exe"):
            if shutil.which(exe):
                return True
        return False

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _low_priv_user() -> str:
        return os.environ.get("SQUAD_LOW_PRIV_USER", "squad-agent")

    @staticmethod
    def _marker_path() -> Path:
        return Path(os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))) / "squad" / "level1.json"

    @staticmethod
    def _user_exists(username: str) -> bool:
        """Check a Windows local user exists via net.exe (argument list, no shell)."""
        try:
            res = subprocess.run(
                ["net", "user", username],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            return res.returncode == 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------
    def run(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        isolation_level: int = 0,
        low_priv_password: str | None = None,
    ) -> ProcessResult:
        """Run ``cmd`` as an argument list.

        ``isolation_level``: 0 (own account), 1 (low-privilege user via
        CreateProcessWithLogonW), 2 (Windows Sandbox), 3 (restricted token /
        Windows Home), 4 (WSL/Docker).
        """
        if isolation_level >= 1:
            return self._run_isolated(cmd, cwd=cwd, env=env, timeout=timeout, level=isolation_level, password=low_priv_password)

        return self._run_current(cmd, cwd=cwd, env=env, timeout=timeout)

    def _run_current(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ProcessResult:
        job = JobObject()
        try:
            proc = subprocess.Popen(
                list(cmd),
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
            )
            job.assign(proc.pid)
            try:
                out, err = proc.communicate(timeout=timeout)
                return ProcessResult(proc.returncode, out or "", err or "", timed_out=False)
            except subprocess.TimeoutExpired:
                job.close()
                try:
                    proc.kill()
                except OSError:
                    pass
                out, err = proc.communicate()
                return ProcessResult(proc.returncode, out or "", err or "", timed_out=True)
        finally:
            job.close()

    def _run_isolated(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        level: int = 1,
        password: str | None = None,
    ) -> ProcessResult:
        """Run under an isolation backend.

        Level 1: low-privilege user via CreateProcessWithLogonW.
        Level 2: Windows Sandbox (.wsb file -> WindowsSandbox.exe).
        Level 3: restricted token at low integrity in a Job Object (Windows Home).
        Level 4: WSL2/Docker (pass-through via the backend tool; stub).
        """
        if level == 1:
            if not self.supports_isolation(1):
                raise RuntimeError(
                    "Level 1 isolation not ready: low-privilege user missing or "
                    "firewall-block marker not verified"
                )
            if not password:
                raise RuntimeError(
                    "Level 1 launch needs the low-privilege user's password "
                    "(set SQUAD_LOW_PRIV_PASSWORD or pass low_priv_password)"
                )
            return self._launch_as_user(cmd, cwd=cwd, env=env, timeout=timeout, password=password)
        if level == 2:
            if not self.supports_isolation(2):
                raise RuntimeError("Windows Sandbox not available (need Pro/Enterprise + feature)")
            return self._launch_sandbox(cmd, cwd=cwd, env=env, timeout=timeout)
        if level == 3:
            if not self.supports_isolation(3):
                raise RuntimeError(
                    "Level 3 isolation not ready: restricted-token marker missing or not verified"
                )
            return self._launch_restricted(cmd, cwd=cwd, timeout=timeout)
        if level == 4:
            raise NotImplementedError(
                "Level 4 (WSL2/Docker) launch is experimental; configure a backend manually"
            )
        raise ValueError(f"unsupported isolation level: {level}")

    def _launch_as_user(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        password: str,
    ) -> ProcessResult:
        """Launch a child as the low-privilege user via CreateProcessWithLogonW.

        Uses ctypes directly (no pywin32 per the spec). Builds a UTF-16
        environment block and joins an argument string for the logon call.
        """
        import sys

        advapi32 = ctypes.windll.advapi32
        kernel32 = ctypes.windll.kernel32

        username = self._low_priv_user()
        domain = os.environ.get("COMPUTERNAME", "")
        command = " ".join(cmd)

        # Build a Unicode environment block (KEY=value\0 pairs, double-null).
        env_block = ""
        base_env = env or dict(os.environ)
        for k, v in base_env.items():
            env_block += f"{k}={v}\0"
        env_block += "\0"

        # Wide-char handles
        start_info = ctypes.create_string_buffer(104)  # PROCESS_INFORMATION
        proc_info = ctypes.create_string_buffer(16)   # STARTUPINFOW

        creation_flags = CREATE_UNICODE_ENVIRONMENT
        domain_w = ctypes.create_unicode_buffer(domain)
        username_w = ctypes.create_unicode_buffer(username)
        password_w = ctypes.create_unicode_buffer(password)
        command_w = ctypes.create_unicode_buffer(command)
        env_w = ctypes.create_unicode_buffer(env_block)
        cwd_w = ctypes.create_unicode_buffer(cwd or os.getcwd())

        ok = advapi32.CreateProcessWithLogonW(
            username_w,
            domain_w,
            password_w,
            LOGON_WITH_PROFILE,
            None,  # application name (use command line)
            command_w,
            creation_flags,
            env_w,
            cwd_w,
            ctypes.byref(start_info),
            ctypes.byref(proc_info),
        )
        if not ok:
            err = kernel32.GetLastError()
            raise RuntimeError(f"CreateProcessWithLogonW failed (error {err})")

        # Read PIDs from PROCESS_INFORMATION
        pid = int.from_bytes(proc_info[0:4], "little")
        thread_id = int.from_bytes(proc_info[4:8], "little")
        proc_handle = int.from_bytes(proc_info[8:12], "little")

        # Wait for exit
        INFINITE = 0xFFFFFFFF
        kernel32.WaitForSingleObject(proc_handle, INFINITE)

        # Get exit code
        exit_code = ctypes.c_ulong(0)
        kernel32.GetExitCodeProcess(proc_handle, ctypes.byref(exit_code))

        kernel32.CloseHandle(proc_handle)
        kernel32.CloseHandle(int.from_bytes(proc_info[12:16], "little"))

        return ProcessResult(
            returncode=exit_code.value,
            stdout="",
            stderr="",
            timed_out=False,
        )

    def _launch_sandbox(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ProcessResult:
        """Launch a Windows Sandbox session that runs ``cmd`` inside.

        Builds a .wsb XML config that maps the working directory read-only,
        runs the command, and shuts the sandbox down.
        """
        import tempfile
        import time

        sandbox = Path(r"C:\Windows\System32\WindowsSandbox.exe")
        if not sandbox.exists():
            raise RuntimeError("WindowsSandbox.exe not found")

        cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        wsb = f"""<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <Networking>Disable</Networking>
  <MemoryInMB>2048</MemoryInMB>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>{cwd or os.getcwd()}</HostFolder>
      <SandboxFolder>D:\\work</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>cmd /c {cmd_str} > D:\\work\\_squad_out.txt 2>&1 & exit</Command>
  </LogonCommand>
</Configuration>"""

        with tempfile.NamedTemporaryFile(suffix=".wsb", mode="w", delete=False, encoding="utf-8") as fh:
            fh.write(wsb)
            wsb_path = fh.name

        try:
            proc = subprocess.Popen(
                [str(sandbox), wsb_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            try:
                out, err = proc.communicate(timeout=timeout or 300)
            except subprocess.TimeoutExpired:
                proc.kill()
                return ProcessResult(proc.returncode or 1, "", "sandbox timed out", timed_out=True)
            return ProcessResult(proc.returncode, out or "", err or "", timed_out=False)
        finally:
            try:
                os.unlink(wsb_path)
            except OSError:
                pass

    def _launch_restricted(self, cmd, *, cwd=None, timeout=None) -> ProcessResult:
        """Launch under a restricted token at low integrity in a Job Object.

        Level 3 works on Windows Home. Memory/process/time limits come from the
        launch plan; the Job Object kills the process and all children on close
        (timeout). The restricted token cannot read the user's profile and the
        per-user firewall block prevents outbound network (second layer).
        """
        from squad.exec.windows.restricted import launch_restricted, plan_launch

        plan = plan_launch(memory_limit_mb=512, max_processes=8,
                           time_limit_seconds=int(timeout or 120))
        job, proc = launch_restricted(cmd, cwd=cwd or os.getcwd(), plan=plan)
        try:
            try:
                out, err = proc.communicate(timeout=timeout)
                return ProcessResult(proc.returncode, out or "", err or "", timed_out=False)
            except subprocess.TimeoutExpired:
                return ProcessResult(proc.returncode or 1, "", "sandbox timed out", timed_out=True)
        finally:
            job.close()
