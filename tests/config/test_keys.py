"""Tests for .env key loading."""

import os

from squad.config.keys import load_keys


def test_load_keys_from_dotenv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        'OPENROUTER_API_KEY=sk-123\n# a comment\nGARBAGE\nANTHROPIC_API_KEY="sk-456"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    load_keys()
    assert os.environ.get("OPENROUTER_API_KEY") == "sk-123"
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-456"


def test_existing_env_wins(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=sk-from-file\n", encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-already-set")
    monkeypatch.chdir(tmp_path)
    load_keys()
    assert os.environ.get("OPENROUTER_API_KEY") == "sk-already-set"


def test_credential_manager_keys_silent_when_unavailable(monkeypatch):
    """If advapi32 can't be loaded (non-Windows / missing lib), no crash."""
    from squad.config import keys

    def _boom(*args, **kwargs):
        raise OSError("no advapi32 here")

    monkeypatch.setattr(keys.ctypes, "WinDLL", _boom)
    keys.load_credential_manager_keys()  # must not raise


def test_credential_manager_keys_loads_api_key_creds(tmp_path, monkeypatch):
    """*API_KEY* Generic credentials are read into os.environ; others ignored."""
    import ctypes

    from squad.config import keys

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("SQUAD_EXTRA_API_KEY", raising=False)
    monkeypatch.delenv("OTHER_STUFF", raising=False)

    creds = {"OPENROUTER_API_KEY": "sk-cm-123", "SQUAD_EXTRA_API_KEY": "sk-extra"}
    ignored = {"OTHER_STUFF": "not-a-key"}

    class FakeAdvapi32:
        def __init__(self):
            self.enumerated = list(creds) + list(ignored)
            self._arr = None

        def CredEnumerateW(self, target, flags, count_ptr, pparray):
            n = len(self.enumerated)
            arr = (ctypes.POINTER(keys.CREDENTIAL) * n)()
            for i, name in enumerate(self.enumerated):
                cred = keys.CREDENTIAL()
                cred.Type = keys._CRED_TYPE_GENERIC
                cred.TargetName = name
                arr[i] = ctypes.pointer(cred)
            # Keep the array alive on the fake so its buffer isn't GC'd before
            # the caller walks it; cast to POINTER(POINTER(...)) so each element
            # is a POINTER(CREDENTIAL), matching the CredEnumerateW contract.
            self._arr = arr
            # Subscript writes propagate back through ctypes.pointer(); the
            # `.contents` setter does NOT (a CPython ctypes quirk).
            count_ptr[0] = n
            pparray[0] = ctypes.cast(arr, ctypes.POINTER(ctypes.POINTER(keys.CREDENTIAL)))
            return True

        def CredReadW(self, target, ctype, flags, pcred_out):
            if target not in creds:
                return False
            data = creds[target].encode("utf-16-le")
            buf = ctypes.create_string_buffer(data)
            cred = keys.CREDENTIAL()
            cred.Type = keys._CRED_TYPE_GENERIC
            cred.CredentialBlobSize = len(data)
            cred.CredentialBlob = ctypes.cast(buf, ctypes.c_void_p)
            pcred_out[0] = ctypes.pointer(cred)
            return True

        def CredFree(self, ptr):
            return None

    fake = FakeAdvapi32()
    monkeypatch.setattr(keys.ctypes, "WinDLL", lambda *a, **k: fake)

    keys.load_credential_manager_keys()
    assert os.environ.get("OPENROUTER_API_KEY") == "sk-cm-123"
    assert os.environ.get("SQUAD_EXTRA_API_KEY") == "sk-extra"
    assert "OTHER_STUFF" not in os.environ


def test_credential_manager_keys_keeps_existing_env(monkeypatch):
    """A value already in os.environ is not overwritten by the credential store."""
    import ctypes

    from squad.config import keys

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-already-set")

    class FakeAdvapi32:
        def __init__(self):
            self._arr = None

        def CredEnumerateW(self, target, flags, count_ptr, pparray):
            cred = keys.CREDENTIAL()
            cred.Type = keys._CRED_TYPE_GENERIC
            cred.TargetName = "OPENROUTER_API_KEY"
            arr = (ctypes.POINTER(keys.CREDENTIAL) * 1)()
            arr[0] = ctypes.pointer(cred)
            self._arr = arr
            count_ptr[0] = 1
            pparray[0] = ctypes.cast(arr, ctypes.POINTER(ctypes.POINTER(keys.CREDENTIAL)))
            return True

        def CredReadW(self, target, ctype, flags, pcred_out):
            data = "sk-from-cm".encode("utf-16-le")
            buf = ctypes.create_string_buffer(data)
            cred = keys.CREDENTIAL()
            cred.Type = keys._CRED_TYPE_GENERIC
            cred.CredentialBlobSize = len(data)
            cred.CredentialBlob = ctypes.cast(buf, ctypes.c_void_p)
            pcred_out[0] = ctypes.pointer(cred)
            return True

        def CredFree(self, ptr):
            return None

    monkeypatch.setattr(keys.ctypes, "WinDLL", lambda *a, **k: FakeAdvapi32())
    keys.load_credential_manager_keys()
    assert os.environ.get("OPENROUTER_API_KEY") == "sk-already-set"
