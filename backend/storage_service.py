#!/usr/bin/env python3
"""Authenticated local access to explicitly shared Mac folders; no replica or mount driver.

Original aeroandroid code, Apache-2.0. Paths are walked through directory descriptors
without following symlinks. Every operation reloads the share list so revocation is immediate.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import ctypes
import errno
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import stat
import sys
import subprocess
import threading
import uuid

CHUNK_SIZE = 1024 * 1024
MAX_REQUEST = 2 * CHUNK_SIZE
DIRECTORY_MIME = "vnd.android.document/directory"
NOFOLLOW = os.O_NOFOLLOW | os.O_CLOEXEC
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW


def atomic_json(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream)
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def filename(value):
    if not isinstance(value, str) or value in ("", ".", "..") or "/" in value or "\0" in value:
        raise OSError(errno.EINVAL, "Invalid document name")
    if len(os.fsencode(value)) > 255:
        raise OSError(errno.ENAMETOOLONG, "Document name is too long")
    return value


def child_document(parent, name):
    return parent + ("/" if parent.split(":", 1)[1] else "") + name


def check_file_id(info, expected):
    if expected is not None:
        if not isinstance(expected, str):
            raise OSError(errno.EINVAL, "Invalid file identity")
        if expected != f"{info.st_dev}:{info.st_ino}":
            raise OSError(errno.ESTALE, "Document changed on the Mac; reopen it")


def integer(value, maximum=(1 << 63) - 1):
    if type(value) is not int or not 0 <= value <= maximum:
        raise OSError(errno.EINVAL, "Invalid offset or length")
    return value


def rename_exclusive(directory_fd, source, destination):
    """Atomic rename that never replaces an existing destination, even during a race."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        operation = libc.renameatx_np
        flag = 0x00000004  # RENAME_EXCL
    elif hasattr(libc, "renameat2"):
        operation = libc.renameat2
        flag = 1  # RENAME_NOREPLACE
    else:
        raise OSError(errno.ENOTSUP, "Atomic rename is unavailable on this host")
    operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    operation.restype = ctypes.c_int
    if operation(directory_fd, os.fsencode(source), directory_fd, os.fsencode(destination), flag):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


class SharedFolders:
    def __init__(self, root):
        self.root = Path(root)

    def shares(self):
        try:
            config = json.loads((self.root / "storage-shares.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        entries = config.get("shares", []) if isinstance(config, dict) else None
        if not isinstance(entries, list):
            raise OSError(errno.EINVAL, "Invalid shared folder configuration")
        for item in entries:
            if (not isinstance(item, dict) or not re.fullmatch(r"[a-f0-9]{32}", str(item.get("id", "")))
                    or not isinstance(item.get("path"), str) or not Path(item["path"]).is_absolute()
                    or not isinstance(item.get("name"), str) or type(item.get("read_only")) is not bool):
                raise OSError(errno.EINVAL, "Invalid shared folder configuration")
        return entries

    @contextlib.contextmanager
    def locate(self, document, write=False):
        if not isinstance(document, str) or ":" not in document or "\0" in document:
            raise OSError(errno.EINVAL, "Invalid document identifier")
        share_id, relative = document.split(":", 1)
        parts = relative.split("/") if relative else []
        if any(part in ("", ".", "..") for part in parts):
            raise OSError(errno.EACCES, "Document is outside its shared folder")
        share = next((item for item in self.shares() if item["id"] == share_id), None)
        if share is None:
            raise OSError(errno.ENOENT, "Shared folder is no longer available")
        if write and share["read_only"]:
            raise OSError(errno.EROFS, "Shared folder is read-only")
        descriptors = []
        try:
            # O_NOFOLLOW on an absolute path only checks its final component.
            # Walk the approved canonical root as well, so replacing an ancestor
            # with a symlink cannot redirect an existing share into another tree.
            descriptor = os.open("/", DIRECTORY)
            descriptors.append(descriptor)
            for component in Path(share["path"]).parts[1:]:
                descriptor = os.open(component, DIRECTORY, dir_fd=descriptor)
                descriptors.append(descriptor)
            for component in parts[:-1]:
                descriptor = os.open(component, DIRECTORY, dir_fd=descriptor)
                descriptors.append(descriptor)
            yield share, descriptor, parts[-1] if parts else None
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def metadata(self, share, document, info, name):
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise OSError(errno.EACCES, "Only regular files and directories can be shared")
        directory = stat.S_ISDIR(info.st_mode)
        return {"document": document, "name": name,
                "mime": DIRECTORY_MIME if directory else mimetypes.guess_type(name)[0] or "application/octet-stream",
                "size": 0 if directory else info.st_size, "modified_ms": info.st_mtime_ns // 1_000_000,
                "directory": directory, "read_only": share["read_only"],
                "file_id": f"{info.st_dev}:{info.st_ino}"}

    @contextlib.contextmanager
    def open_file(self, document, write=False, append=False, expected_file_id=None):
        with self.locate(document, write) as (_share, parent, name):
            if name is None:
                raise OSError(errno.EISDIR, "Document is a directory")
            descriptor = os.open(name, (os.O_RDWR if write else os.O_RDONLY) | NOFOLLOW | os.O_NONBLOCK
                                 | (os.O_APPEND if append else 0), dir_fd=parent)
            try:
                info = os.fstat(descriptor)
                check_file_id(info, expected_file_id)
                if not stat.S_ISREG(info.st_mode):
                    raise OSError(errno.EACCES, "Document is not a regular file")
                yield descriptor
            finally:
                os.close(descriptor)

    def invoke(self, request):
        operation = request.get("op")
        document = request.get("document")
        if operation == "roots":
            return [{"id": item["id"], "name": item["name"], "document": item["id"] + ":",
                     "read_only": item["read_only"]} for item in self.shares()]
        if operation == "stat":
            with self.locate(document) as (share, parent, name):
                info = os.stat(name, dir_fd=parent, follow_symlinks=False) if name else os.fstat(parent)
                check_file_id(info, request.get("expected_file_id"))
                return self.metadata(share, document, info, name or share["name"])
        if operation == "list":
            offset = integer(request.get("offset", 0))
            limit = integer(request.get("limit", 256), 256)
            if limit == 0:
                raise OSError(errno.EINVAL, "Listing page size must be positive")
            with self.locate(document) as (share, parent, name):
                descriptor = os.open(name, DIRECTORY, dir_fd=parent) if name else os.dup(parent)
                try:
                    items = []
                    with os.scandir(descriptor) as entries:
                        for entry in entries:
                            try:
                                info = entry.stat(follow_symlinks=False)
                            except FileNotFoundError:
                                continue  # deleted on the Mac after the folder was read: list the rest
                            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                                continue
                            child = child_document(document, entry.name)
                            items.append(self.metadata(share, child, info, entry.name))
                    return sorted(items, key=lambda item: (not item["directory"], item["name"].casefold()))[offset:offset + limit]
                finally:
                    os.close(descriptor)
        if operation == "create":
            name = filename(request.get("name"))
            parent_document = request.get("parent")
            with self.locate(parent_document, write=True) as (share, parent, leaf):
                descriptor = os.open(leaf, DIRECTORY, dir_fd=parent) if leaf else os.dup(parent)
                try:
                    if request.get("mime") == DIRECTORY_MIME:
                        os.mkdir(name, 0o700, dir_fd=descriptor)
                    else:
                        created = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW, 0o600, dir_fd=descriptor)
                        os.close(created)
                    info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    child = child_document(parent_document, name)
                    return self.metadata(share, child, info, name)
                finally:
                    os.close(descriptor)
        if operation in ("rename", "delete"):
            with self.locate(document, write=True) as (share, parent, name):
                if name is None:
                    raise OSError(errno.EACCES, "A shared root cannot be renamed or deleted")
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                self.metadata(share, document, info, name)  # reject symbolic links and special files
                if operation == "delete":
                    if stat.S_ISDIR(info.st_mode):
                        os.rmdir(name, dir_fd=parent)
                    else:
                        os.unlink(name, dir_fd=parent)
                    return {}
                destination = filename(request.get("name"))
                if destination != name:
                    rename_exclusive(parent, name, destination)
                renamed = document.rsplit("/", 1)[0] + "/" + destination if "/" in document else document.split(":", 1)[0] + ":" + destination
                return self.metadata(share, renamed, os.stat(destination, dir_fd=parent, follow_symlinks=False), destination)
        if operation == "read":
            offset, size = integer(request.get("offset")), integer(request.get("size"), CHUNK_SIZE)
            with self.open_file(document, expected_file_id=request.get("expected_file_id")) as descriptor:
                data = os.pread(descriptor, size, offset)
            return {"data": base64.b64encode(data).decode("ascii")}
        if operation == "write":
            offset = integer(request.get("offset"))
            encoded = request.get("data")
            if not isinstance(encoded, str) or len(encoded) > 4 * ((CHUNK_SIZE + 2) // 3):
                raise OSError(errno.EINVAL, "Invalid write payload")
            try:
                data = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as error:
                raise OSError(errno.EINVAL, "Invalid write payload") from error
            if len(data) > CHUNK_SIZE or offset + len(data) > (1 << 63) - 1:
                raise OSError(errno.EINVAL, "Write exceeds supported range")
            append = request.get("append", False)
            if type(append) is not bool:
                raise OSError(errno.EINVAL, "Invalid append mode")
            with self.open_file(document, write=True, append=append, expected_file_id=request.get("expected_file_id")) as descriptor:
                written = 0
                while written < len(data):
                    count = (os.write(descriptor, data[written:]) if append else
                             os.pwrite(descriptor, data[written:], offset + written))
                    if count == 0:
                        raise OSError(errno.EIO, "Write did not complete")
                    written += count
            return {"written": written}
        if operation == "truncate":
            size = integer(request.get("size"))
            with self.open_file(document, write=True, expected_file_id=request.get("expected_file_id")) as descriptor:
                os.ftruncate(descriptor, size)
            return {}
        if operation == "fsync":
            with self.open_file(document, write=True, expected_file_id=request.get("expected_file_id")) as descriptor:
                os.fsync(descriptor)
            return {}
        raise OSError(errno.EINVAL, "Unknown storage operation")


class StorageServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, root, token):
        self.folders = SharedFolders(root)
        self.token = token
        super().__init__(("127.0.0.1", 0), StorageHandler)


class StorageHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # do not log document names, tokens or file contents

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def send_json(self, status, value):
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not hmac.compare_digest(self.headers.get("Authorization", "").encode("utf-8"),
                                   ("Bearer " + self.server.token).encode("ascii")):
            self.send_json(403, {"ok": False, "error": "Storage authorization failed", "code": errno.EACCES, "errno": "EACCES"})
            return
        try:
            if self.path != "/rpc":
                raise OSError(errno.ENOENT, "Unknown storage endpoint")
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_REQUEST:
                raise OSError(errno.EINVAL, "Storage request is too large or has no length")
            payload = self.rfile.read(length)
            if len(payload) != length:
                raise OSError(errno.EINVAL, "Incomplete storage request")
            request = json.loads(payload)
            if not isinstance(request, dict):
                raise OSError(errno.EINVAL, "Storage request must be an object")
            value = self.server.folders.invoke(request)
            self.send_json(200, {"ok": True, "data": value})
        except OSError as error:
            self.send_json(200, {"ok": False, "error": error.strerror or "Storage operation failed", "code": error.errno or errno.EIO,
                                 "errno": errno.errorcode.get(error.errno, "EIO")})
        except (ValueError, TypeError, KeyError, UnicodeError):
            self.send_json(200, {"ok": False, "error": "Invalid storage request or configuration", "code": errno.EINVAL, "errno": "EINVAL"})


def emulator_identity(root):
    try:
        record = json.loads((root / "emulator.json").read_text())
        if type(record.get("pid")) is int and record["pid"] > 1 and isinstance(record.get("birth"), str) and record["birth"]:
            return {"pid": record["pid"], "birth": record["birth"]}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def emulator_alive(root, expected):
    if not expected or emulator_identity(root) != expected:
        return False
    try:
        result = subprocess.run(["/bin/ps", "-p", str(expected["pid"]), "-o", "lstart=", "-o", "stat="],
                                capture_output=True, text=True, timeout=5)
        fields = result.stdout.strip().rsplit(None, 1)
        return (result.returncode == 0 and len(fields) == 2 and not fields[1].startswith("Z")
                and fields[0].strip() == expected["birth"])
    except (OSError, subprocess.SubprocessError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--watch-emulator", action="store_true",
                        help="Exit when the original owned emulator process stops")
    args = parser.parse_args()
    token = (args.root / "storage-token").read_text().strip()
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        raise ValueError("Invalid storage token")
    expected = emulator_identity(args.root) if args.watch_emulator else None
    if args.watch_emulator and not emulator_alive(args.root, expected):
        raise ValueError("An owned emulator must be running before storage starts")
    with StorageServer(args.root, token) as server:
        stopping = threading.Event()
        if args.watch_emulator:
            def watch():
                while not stopping.wait(1):
                    if not emulator_alive(args.root, expected):
                        server.shutdown()
                        return
            threading.Thread(target=watch, name="storage-emulator-watch", daemon=True).start()
        port_record = args.root / "storage-port.json"
        atomic_json(port_record, {"port": server.server_address[1]})
        try:
            server.serve_forever(poll_interval=0.25)
        finally:
            stopping.set()
            try:
                if json.loads(port_record.read_text()).get("port") == server.server_address[1]:
                    port_record.unlink(missing_ok=True)
            except (OSError, ValueError, AttributeError):
                pass


if __name__ == "__main__":
    main()
