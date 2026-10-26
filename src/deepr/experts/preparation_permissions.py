"""Actual-token private filesystem protection for operation storage.

No private writer may use a parent until its restrictive ACL/mode is verified.
This is not authentication or a hostile same-user filesystem sandbox. Windows
pywin32 availability in a clean core install remains unqualified; fail closed.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import Any


class PreparationStoreError(RuntimeError):
    """Private preparation storage failed without new execution authority."""


class StoreProtectionError(PreparationStoreError):
    """Private protection could not be established or verified."""


class PreparationPermissions:
    """Current-token/UID protection; never repairs unrelated existing storage."""

    def __init__(self) -> None:
        self.sid: Any = None
        self.security: Any = None
        if os.name == "nt":
            try:
                import pywintypes
                import win32api
                import win32con
                import win32security

                self.security = win32security
                try:
                    token = win32security.OpenThreadToken(win32api.GetCurrentThread(), win32con.TOKEN_QUERY, True)
                except pywintypes.error as error:
                    if error.winerror != 1008:
                        raise
                    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
                try:
                    self.sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
                finally:
                    token.Close()
            except Exception as error:
                raise StoreProtectionError("Current Windows token identity unavailable") from error

    def protect_new_directory(self, path: Path) -> None:
        path.mkdir(mode=0o700)
        if os.name == "nt":
            security = self.security
            system = security.CreateWellKnownSid(security.WinLocalSystemSid)
            acl = security.ACL()
            for sid in (self.sid, system):
                acl.AddAccessAllowedAceEx(security.ACL_REVISION, 3, 0x1F01FF, sid)
            security.SetNamedSecurityInfo(
                str(path),
                security.SE_FILE_OBJECT,
                security.OWNER_SECURITY_INFORMATION
                | security.DACL_SECURITY_INFORMATION
                | security.PROTECTED_DACL_SECURITY_INFORMATION,
                self.sid,
                None,
                acl,
                None,
            )
        self.verify(path, directory=True, protected=True)

    def prepare_tempfile(self, descriptor: int, path: Path) -> None:
        """Protect the same empty open file before any private payload write."""
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size != 0 or info.st_nlink != 1:
            raise StoreProtectionError("Expected a new empty private file")
        if sys.platform == "win32":
            import msvcrt

            self._set_empty_windows_owner(path, expected_handle=msvcrt.get_osfhandle(descriptor))
        self.verify(path, directory=False)

    def prepare_empty_lock(self, path: Path) -> None:
        """Correct only a known empty lock's creation owner, never its DACL."""
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != 0 or info.st_nlink != 1:
            raise StoreProtectionError("Expected an empty private lock")
        if sys.platform == "win32":
            self._set_empty_windows_owner(path)
        self.verify(path, directory=False)

    def _set_empty_windows_owner(self, path: Path, *, expected_handle: int | None = None) -> None:
        """TokenOwner may differ from TokenUser on an elevated Windows runner."""
        import ntsecuritycon
        import win32con
        import win32file

        handle = win32file.CreateFile(
            str(path),
            win32con.WRITE_OWNER | win32con.READ_CONTROL | ntsecuritycon.FILE_READ_ATTRIBUTES,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
            None,
            win32con.OPEN_EXISTING,
            win32file.FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        try:
            info = win32file.GetFileInformationByHandle(handle)
            if info[0] & 0x400 or info[5] != 0 or info[6] != 0 or info[7] != 1:
                raise StoreProtectionError("Unexpected empty Windows file identity")
            if expected_handle is not None:
                original = win32file.GetFileInformationByHandle(expected_handle)
                if (info[4], info[8], info[9]) != (original[4], original[8], original[9]):
                    raise StoreProtectionError("Windows tempfile handle identity changed")
            self.security.SetSecurityInfo(
                handle,
                self.security.SE_FILE_OBJECT,
                self.security.OWNER_SECURITY_INFORMATION,
                self.sid,
                None,
                None,
                None,
            )
            descriptor = self.security.GetSecurityInfo(
                handle, self.security.SE_FILE_OBJECT, self.security.OWNER_SECURITY_INFORMATION
            )
            if descriptor.GetSecurityDescriptorOwner() != self.sid:
                raise StoreProtectionError("Windows private owner assignment failed")
        finally:
            handle.Close()

    def verify(self, path: Path, *, directory: bool, protected: bool = False) -> None:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise StoreProtectionError("Links and reparse points are refused")
        if directory != stat.S_ISDIR(info.st_mode) or (not directory and info.st_nlink != 1):
            raise StoreProtectionError("Unexpected private storage entry")
        if sys.platform != "win32":
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600):
                raise StoreProtectionError("Private storage must be current-UID owner only")
            return
        self._verify_windows_acl(path, directory=directory, protected=protected)

    def _verify_windows_acl(self, path: Path, *, directory: bool, protected: bool) -> None:
        """Verify owner, exact principals and child-propagation protection."""
        security = self.security
        descriptor = security.GetNamedSecurityInfo(
            str(path),
            security.SE_FILE_OBJECT,
            security.OWNER_SECURITY_INFORMATION | security.DACL_SECURITY_INFORMATION,
        )
        if descriptor.GetSecurityDescriptorOwner() != self.sid:
            raise StoreProtectionError("Unexpected Windows owner")
        control, _ = descriptor.GetSecurityDescriptorControl()
        if protected and not control & 0x1000:
            raise StoreProtectionError("Windows DACL inheritance must be protected")
        acl = descriptor.GetSecurityDescriptorDacl()
        if acl is None or acl.GetAceCount() != 2:
            raise StoreProtectionError("Unexpected Windows private DACL")
        allowed = {str(self.sid), str(security.CreateWellKnownSid(security.WinLocalSystemSid))}
        observed = set()
        for index in range(acl.GetAceCount()):
            header, mask, sid = acl.GetAce(index)
            if header[0] != security.ACCESS_ALLOWED_ACE_TYPE or mask != 0x1F01FF or str(sid) not in allowed:
                raise StoreProtectionError("Unexpected Windows private ACE")
            inheritance = header[1] & 0x0F
            if inheritance != (3 if directory else 0):
                raise StoreProtectionError("Unexpected Windows ACE inheritance flags")
            observed.add(str(sid))
        if observed != allowed:
            raise StoreProtectionError("Missing private Windows principal")
