#!/usr/bin/env python3
"""Local Android subsystem controller. No HTTP listener; one JSON response per call."""
from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import re
import shutil
import shlex
import signal
import socket
import subprocess
import sys
import time
import uuid

PACKAGE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+\Z")
COMPANION = "dev.dan.androidsubsystem"
AUTHORITY = COMPANION + ".bridge"
DEFAULTS = {"android": 16, "image_tag": "default", "port": 5580, "memory_mb": 4096, "cores": 4,
            "resolution": "1280x960/200", "fps": 30, "bitrate": "12M"}


class SubsystemError(Exception):
    pass


def atomic_json(path: Path, value):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError) as e:
        raise SubsystemError(f"Cannot read {path}: {e}") from e


def package_name(value):
    if not isinstance(value, str) or not PACKAGE.fullmatch(value):
        raise SubsystemError("Invalid Android package name")
    return value


def shared_path(value):
    """Restrict guest file operations to the designated exchange directory."""
    if not isinstance(value, str) or not value.startswith("/sdcard/Download/MacBridge/"):
        raise SubsystemError("Guest files must be inside /sdcard/Download/MacBridge/")
    if any(x in value for x in ("\n", "\r", "\x00")) or ".." in PurePosixPath(value).parts:
        raise SubsystemError("Invalid shared file path")
    if not re.fullmatch(r"[/A-Za-z0-9._ -]+", value):
        raise SubsystemError("Unsupported characters in shared file name")
    return value


class Controller:
    def __init__(self, root=None, runner=None):
        default = Path.home() / "Library/Application Support/AndroidSubsystem"
        self.root = Path(root or os.environ.get("ANDROID_SUBSYSTEM_HOME", default)).expanduser()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.logs = self.root / "logs"
        self.logs.mkdir(exist_ok=True)
        self.runner = runner or subprocess.run
        self.children = {}
        saved = read_json(self.root / "config.json", {})
        self.config = self.loaded_config(saved)
        self.validate_config(self.config)
        self.sdk = Path(os.environ.get("ANDROID_SUBSYSTEM_SDK",
                        self.config.get("sdk", str(Path.home() / "Library/Android/sdk")))).expanduser()
        self.avd_home = self.root / "avd"
        self.avd_home.mkdir(exist_ok=True)
        runtime = self.root / "runtime"
        java_home = self.config.get("java_home", os.environ.get("JAVA_HOME", ""))
        self.env = {**os.environ, "ANDROID_HOME": str(self.sdk),
                    "ANDROID_SDK_ROOT": str(self.sdk), "ANDROID_AVD_HOME": str(self.avd_home),
                    "PATH": os.pathsep.join([str(runtime / "bin"), str(Path(java_home) / "bin") if java_home else "",
                     str(self.sdk / "platform-tools"),
                     "/opt/homebrew/bin", "/usr/local/bin", os.environ.get("PATH", "")])}
        if java_home:
            self.env["JAVA_HOME"] = java_home

    @staticmethod
    def validate_config(c):
        if c.get("android") not in (16, 17):
            raise SubsystemError("Only Android 16 and 17 are supported")
        if c.get("image_tag", "default") not in ("default", "google_apis"):
            raise SubsystemError("Unknown Android system image type")
        if type(c.get("port")) is not int or c["port"] % 2 or not 5554 <= c["port"] <= 5680:
            raise SubsystemError("Emulator port must be even, between 5554 and 5680")
        for k, low, high in [("memory_mb", 2048, 16384), ("cores", 2, 12), ("fps", 15, 120)]:
            if type(c.get(k)) is not int or not low <= c[k] <= high:
                raise SubsystemError(f"Invalid {k}: expected {low}..{high}")
        if not re.fullmatch(r"[0-9]{3,4}x[0-9]{3,4}/[0-9]{2,3}", str(c.get("resolution"))):
            raise SubsystemError("Resolution must be WIDTHxHEIGHT/DPI")
        w, h, dpi = map(int, re.split(r"[x/]", c["resolution"]))
        if not (320 <= w <= 3840 and 320 <= h <= 3840 and 100 <= dpi <= 640):
            raise SubsystemError("Resolution or DPI outside supported range")
        if not re.fullmatch(r"[1-9][0-9]?M", str(c.get("bitrate"))):
            raise SubsystemError("Invalid video bitrate")

    @property
    def api(self):
        return self.config["android"] + 20

    def loaded_config(self, saved):
        config = {**DEFAULTS, **saved}
        # Existing installations must remain identifiable so they can be stopped
        # safely before migration. New installations always select AOSP.
        if "image_tag" not in saved and saved and (self.root / "avd" / f"MacAndroid_{config['android']}_arm64.ini").exists():
            config["image_tag"] = "google_apis"
        return config

    @property
    def image_tag(self):
        return self.config["image_tag"]

    @property
    def magisk_image_dir(self):
        base = self.root / "images" / str(self.config["android"])
        return base / "default" if self.image_tag == "default" else base

    @property
    def avd(self):
        if self.image_tag == "default":
            return f"MacAndroid_{self.config['android']}_AOSP_arm64"
        return f"MacAndroid_{self.config['android']}_arm64"

    @property
    def serial(self):
        return f"emulator-{self.config['port']}"

    def tool(self, name):
        paths = {"adb": self.sdk / "platform-tools/adb",
                 "emulator": self.sdk / "emulator/emulator",
                 "sdkmanager": self.sdk / "cmdline-tools/latest/bin/sdkmanager",
                 "avdmanager": self.sdk / "cmdline-tools/latest/bin/avdmanager"}
        candidate = paths.get(name)
        if candidate and candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        found = shutil.which(name, path=self.env["PATH"])
        if found:
            return found
        if name in ("sdkmanager", "avdmanager"):
            for prefix in [Path("/opt/homebrew"), Path("/usr/local")]:
                p = prefix / f"share/android-commandlinetools/cmdline-tools/latest/bin/{name}"
                if p.is_file():
                    return str(p)
        raise SubsystemError(f"Missing {name}. Run scripts/setup-mac.sh first.")

    def run(self, argv, timeout=30, check=True, input=None):
        try:
            r = self.runner(argv, text=True, input=input, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, env=self.env)
        except subprocess.TimeoutExpired as e:
            raise SubsystemError(f"Command timed out after {timeout}s: {Path(argv[0]).name}") from e
        except OSError as e:
            raise SubsystemError(str(e)) from e
        if check and r.returncode:
            raise SubsystemError((r.stderr or r.stdout or f"Exit {r.returncode}").strip()[-4000:])
        return r

    def adb(self, *args, timeout=30, check=True):
        if args and args[0] == "shell":
            args = ("shell", shlex.join(args[1:]))
        return self.run([self.tool("adb"), "-s", self.serial, *args], timeout, check)

    @contextlib.contextmanager
    def locked(self):
        with (self.root / "controller.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            # Other CLI requests may have selected a different port while this
            # request was waiting for the controller lock.
            saved = read_json(self.root / "config.json", None)
            if saved is not None:
                self.config = self.loaded_config(saved)
                self.validate_config(self.config)
            yield

    @staticmethod
    def ports_available(port):
        probes = []
        try:
            for value in (port, port + 1):
                probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                probes.append(probe)
                # A recently closed console can leave TCP TIME_WAIT entries.
                # listen() still rejects a real listener after address reuse.
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", value))
                probe.listen(1)
            return True
        except OSError:
            return False
        finally:
            for probe in probes:
                probe.close()

    def unconfirmed_shutdown(self):
        return bool(read_json(self.root / "emulator.json", {})) and not self.ports_available(self.config["port"])

    def select_start_port(self):
        current = self.config["port"]
        if self.ports_available(current):
            return
        if self.running_emulator() or self.device() or self.unconfirmed_shutdown():
            raise SubsystemError("安卓端口仍在使用，尚未确认旧子系统退出。请先停止子系统，再修改内存或重新启动。")
        # Do not stop or take control of a program occupying these ports.
        for port in range(5554, 5681, 2):
            if port != current and self.ports_available(port):
                candidate = {**self.config, "port": port}
                atomic_json(self.root / "config.json", candidate)
                self.config = candidate
                return
        raise SubsystemError("找不到可用的安卓端口对（5554–5681）。请关闭不需要的模拟器后重试。")

    def configured(self):
        return (self.avd_home / f"{self.avd}.ini").exists()

    def device(self):
        r = self.adb("get-state", timeout=5, check=False)
        if r.returncode or r.stdout.strip() != "device":
            return False
        actual = self.adb("emu", "avd", "name", timeout=5, check=False).stdout.splitlines()
        if not actual or actual[0].strip() != self.avd:
            raise SubsystemError(f"Port {self.config['port']} belongs to another emulator; refusing to control it")
        return True

    def ready(self):
        if not self.device():
            raise SubsystemError("Android subsystem is stopped; start it first")
        if self.adb("shell", "getprop", "sys.boot_completed", timeout=5).stdout.strip() != "1":
            raise SubsystemError("Android is still booting")
        api = self.adb("shell", "getprop", "ro.build.version.sdk").stdout.strip()
        if api != str(self.api):
            raise SubsystemError(f"Expected Android API {self.api}, got {api}")

    def diagnostic(self):
        checks = []
        checks.append({"name": "Apple Silicon Mac", "ok": platform.system() == "Darwin" and
                      platform.machine() == "arm64", "detail": platform.platform()})
        for name in ("adb", "emulator", "scrcpy", "sdkmanager", "avdmanager"):
            try:
                p = self.tool(name)
                checks.append({"name": name, "ok": True, "detail": p})
            except SubsystemError as e:
                checks.append({"name": name, "ok": False, "detail": str(e)})
        image = self.sdk / f"system-images/android-{self.api}/{self.image_tag}/arm64-v8a/system.img"
        checks.append({"name": f"Android {self.config['android']} ARM64 image", "ok": image.exists(),
                      "detail": str(image)})
        try:
            result = self.run([self.tool("emulator"), "-accel-check"], check=False)
            checks.append({"name": "Hardware acceleration", "ok": result.returncode == 0,
                          "detail": (result.stdout + result.stderr).strip()})
            help_text = self.run([self.tool("scrcpy"), "--help"]).stdout
            checks.append({"name": "Independent virtual displays", "ok": "--new-display" in help_text,
                          "detail": "scrcpy must support --new-display and --start-app"})
        except SubsystemError as e:
            checks.append({"name": "Runtime capability", "ok": False, "detail": str(e)})
        return {"checks": checks, "config": self.config, "root": str(self.root)}

    def configure(self, changes):
        allowed = set(DEFAULTS) | {"sdk", "java_home", "magisk_ramdisk"}
        if set(changes) - allowed:
            raise SubsystemError("Unknown configuration field")
        with self.locked():
            if self.running_emulator() or self.device() or self.unconfirmed_shutdown():
                raise SubsystemError("Stop Android before changing runtime settings")
            candidate = {**self.config, **changes}
            if candidate["image_tag"] != "default":
                raise SubsystemError("New runtime settings require the AOSP image; migrate with image_tag=default")
            if candidate["android"] != self.config["android"] or candidate["image_tag"] != self.image_tag:
                candidate.pop("magisk_ramdisk", None)
            self.validate_config(candidate)
            for field in ("sdk", "java_home"):
                if field in candidate and not Path(candidate[field]).is_absolute():
                    raise SubsystemError(f"{field} path must be absolute")
            atomic_json(self.root / "config.json", candidate)
            self.config = candidate
            return {"config": candidate}

    def create(self):
        with self.locked():
            if self.image_tag != "default":
                raise SubsystemError("Legacy Google image is retained only for migration; select the AOSP runtime")
            if self.configured():
                return {"avd": self.avd, "created": False}
            image = self.sdk / f"system-images/android-{self.api}/{self.image_tag}/arm64-v8a/system.img"
            if not image.is_file():
                raise SubsystemError(f"Android {self.config['android']} image missing. Run setup-mac.sh {self.config['android']}")
            self.run([self.tool("avdmanager"), "--verbose", "create", "avd", "--name", self.avd,
                      "--package", f"system-images;android-{self.api};{self.image_tag};arm64-v8a",
                      "--path", str(self.avd_home / f"{self.avd}.avd")], timeout=90, input="no\n")
            config_file = self.avd_home / f"{self.avd}.avd/config.ini"
            settings = dict(line.split("=", 1) for line in config_file.read_text().splitlines()
                            if "=" in line)
            settings.update({"hw.keyboard": "yes", "hw.gpu.enabled": "yes", "hw.gpu.mode": "auto",
                             "hw.ramSize": str(self.config["memory_mb"]), "hw.cpu.ncore": str(self.config["cores"]),
                             "disk.dataPartition.size": "8G", "hw.lcd.width": "1280", "hw.lcd.height": "960",
                             "hw.lcd.density": "200", "hw.audioInput": "no", "hw.audioOutput": "yes"})
            config_file.write_text("\n".join(f"{k}={v}" for k, v in settings.items()) + "\n")
            return {"avd": self.avd, "created": True}

    def process_matches(self, record):
        pid = record.get("pid", 0)
        if type(pid) is not int or pid <= 1:
            return False
        r = self.run(["/bin/ps", "-p", str(pid), "-o", "lstart=", "-o", "stat="], check=False)
        fields = r.stdout.strip().rsplit(None, 1)
        return (r.returncode == 0 and len(fields) == 2 and not fields[1].startswith("Z")
                and fields[0].strip() == record.get("birth"))

    def spawn(self, argv, log_name):
        log = self.logs / log_name
        with log.open("ab", buffering=0) as f:
            p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=f, stderr=f,
                                 env=self.env, start_new_session=True)
        self.children[p.pid] = p
        time.sleep(0.3)
        if p.poll() is not None:
            raise SubsystemError(f"Runtime exited ({p.returncode}). {log.read_text(errors='replace')[-3000:]}")
        birth = self.run(["/bin/ps", "-p", str(p.pid), "-o", "lstart="], check=False)
        if birth.returncode or not birth.stdout.strip():
            raise SubsystemError("Could not establish runtime process identity")
        return {"pid": p.pid, "birth": birth.stdout.strip(), "log": str(log)}

    def running_emulator(self):
        record = read_json(self.root / "emulator.json", {})
        return bool(record) and self.process_matches(record)

    def boot(self):
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise SubsystemError("This runtime requires an Apple Silicon Mac (M1–M5)")
        self.create()
        with self.locked():
            active = self.device()
            if not active and not self.running_emulator():
                self.select_start_port()
                argv = [self.tool("emulator"), "-avd", self.avd, "-port", str(self.config["port"]),
                        "-no-window", "-no-boot-anim", "-gpu", "auto", "-accel", "on",
                        "-memory", str(self.config["memory_mb"]), "-cores", str(self.config["cores"]),
                        "-no-snapshot", "-no-metrics"]
                if self.config.get("magisk_ramdisk"):
                    ramdisk = Path(self.config["magisk_ramdisk"]).resolve()
                    expected_dir = self.magisk_image_dir.resolve()
                    if ramdisk.parent != expected_dir or not ramdisk.is_file():
                        raise SubsystemError("Invalid private Magisk ramdisk; run provision-mac.py")
                    descriptor = read_json(expected_dir / "ramdisk.json", {})
                    if descriptor.get("api") != self.api or descriptor.get("image_tag") != self.image_tag or descriptor.get("sha256") != hashlib.sha256(ramdisk.read_bytes()).hexdigest():
                        raise SubsystemError("Magisk ramdisk version or digest does not match")
                    argv += ["-ramdisk", str(ramdisk), "-feature", "-SystemAsRoot"]
                atomic_json(self.root / "emulator.json", self.spawn(argv, "emulator.log"))
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                if self.device() and self.adb("shell", "getprop", "sys.boot_completed", check=False).stdout.strip() == "1":
                    break
                if not self.running_emulator() and not self.device():
                    raise SubsystemError("Emulator stopped during boot; inspect emulator.log")
                time.sleep(1)
            else:
                raise SubsystemError("Boot exceeded 240 seconds; emulator left running for diagnosis")
            self.ready()
            # A headless guest's default display can remain asleep even after
            # boot completes. Wake its power group before opening app displays.
            self.adb("shell", "input", "keyevent", "KEYCODE_WAKEUP", check=False)
            self.adb("shell", "wm", "dismiss-keyguard", check=False)
            self.adb("shell", "settings", "put", "global", "force_resizable_activities", "1")
            self.adb("shell", "settings", "put", "global", "enable_freeform_support", "1")
            self.adb("shell", "settings", "put", "global", "stay_on_while_plugged_in", "3")
            self.adb("shell", "mkdir", "-p", "/sdcard/Download/MacBridge")
            return {"state": "running", "android": self.config["android"], "serial": self.serial}

    def windows(self):
        saved = read_json(self.root / "windows.json", {})
        return {k: v for k, v in saved.items() if self.process_matches(v)}

    def status(self):
        try:
            connected = self.device()
            booted = connected and self.adb("shell", "getprop", "sys.boot_completed", timeout=5,
                                          check=False).stdout.strip() == "1"
            state = "running" if booted else "booting" if connected or self.running_emulator() else "stopped"
            error = None
        except SubsystemError as e:
            state, error = "unavailable", str(e)
        return {"state": state, "error": error, "android": self.config["android"],
                "serial": self.serial, "configured": self.configured(),
                "runtime_process_active": self.running_emulator(),
                "windows": self.windows(), "config": self.config, "logs": str(self.logs),
                "provision": read_json(self.root / "provision-report.json", {})}

    def stop(self):
        with self.locked():
            # Validate device ownership before affecting any process.
            connected = self.device()
            for record in self.windows().values():
                self.terminate(record)
            atomic_json(self.root / "windows.json", {})
            graphics = read_json(self.root / "graphics.json", {})
            self.terminate(graphics)
            if connected and type(graphics.get("port")) is int:
                self.adb("forward", "--remove", f"tcp:{graphics['port']}", check=False)
            (self.root / "graphics.json").unlink(missing_ok=True)
            if connected:
                self.adb("emu", "kill", check=False)
            else:
                self.terminate(read_json(self.root / "emulator.json", {}))
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if not self.running_emulator() and not self.device() and not self.unconfirmed_shutdown():
                    break
                time.sleep(0.2)
            else:
                raise SubsystemError("Emulator has not stopped yet; settings remain locked")
            (self.root / "emulator.json").unlink(missing_ok=True)
            for pid, child in list(self.children.items()):
                if child.poll() is not None:
                    child.wait()
                    self.children.pop(pid, None)
            return {"state": "stopped"}

    def native_session(self, package):
        package_name(package)
        self.boot()
        candidates = [Path(__file__).resolve().parents[1] / "MacBridge.apk",
                      Path(__file__).resolve().parents[1] / "artifacts/MacBridge.apk"]
        apk = next((p for p in candidates if p.is_file()), None)
        if apk is None:
            raise SubsystemError("MacBridge.apk is missing; build the guest bridge first")
        bridge_sha256 = hashlib.sha256(apk.read_bytes()).hexdigest()
        with self.locked():
            token_path = self.root / "surface-token"
            if not token_path.exists():
                token_path.write_text(uuid.uuid4().hex + uuid.uuid4().hex)
                os.chmod(token_path, 0o600)
            record = read_json(self.root / "graphics.json", {})
            forwards = self.adb("forward", "--list", check=False).stdout.splitlines()
            forward_line = f"{self.serial} tcp:{record.get('port')} tcp:7900"
            if not (record.get("bridge_sha256") == bridge_sha256
                    and self.process_matches(record) and forward_line in forwards):
                self.terminate(record)
                if type(record.get("port")) is int:
                    self.adb("forward", "--remove", f"tcp:{record['port']}", check=False)
                result = self.adb("install", "-r", str(apk), timeout=120)
                if "Success" not in result.stdout:
                    raise SubsystemError("Guest bridge install failed: " + result.stdout)
                self.adb("shell", "mkdir", "-p", "/data/local/tmp/mac-surface")
                self.adb("shell", "chmod", "700", "/data/local/tmp/mac-surface")
                self.adb("push", str(apk), "/data/local/tmp/mac-surface/bridge.apk", timeout=120)
                self.adb("push", str(token_path), "/data/local/tmp/mac-surface/token")
                self.adb("shell", "chmod", "600", "/data/local/tmp/mac-surface/token")
                self.adb("shell", "ime", "enable", COMPANION + "/.BridgeIme")
                self.adb("shell", "ime", "set", COMPANION + "/.BridgeIme")
                # Clean up only this bridge's stale guest process after an ADB disconnect.
                self.adb("shell", "sh", "-c", 'for p in $(pidof MacSurfaceBridge); do kill "$p"; done', check=False)
                command = "CLASSPATH=/data/local/tmp/mac-surface/bridge.apk app_process /system/bin --nice-name=MacSurfaceBridge dev.dan.androidsubsystem.SurfaceServer"
                (self.logs / "surface-bridge.log").write_text("")
                record = self.spawn([self.tool("adb"), "-s", self.serial, "shell", command], "surface-bridge.log")
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if "Mac Surface Bridge ready v1" in Path(record["log"]).read_text(errors="replace"):
                        break
                    if not self.process_matches(record):
                        raise SubsystemError("Guest surface bridge failed: " + Path(record["log"]).read_text(errors="replace")[-3000:])
                    time.sleep(0.1)
                else:
                    self.terminate(record)
                    raise SubsystemError("Guest surface bridge did not become ready; inspect surface-bridge.log")
                port = self.adb("forward", "tcp:0", "tcp:7900").stdout.strip()
                if not port.isdigit() or not 1024 <= int(port) <= 65535:
                    self.terminate(record)
                    raise SubsystemError("ADB did not allocate a valid graphics port")
                record.update({"port": int(port), "serial": self.serial,
                               "bridge_sha256": bridge_sha256})
                atomic_json(self.root / "graphics.json", record)
            w, h, dpi = map(int, re.split(r"[x/]", self.config["resolution"]))
            return {"port": record["port"], "token": token_path.read_text(), "version": 1,
                    "package": package, "width": min(w, 2560), "height": min(h, 2560), "dpi": dpi,
                    "fps": min(self.config["fps"], 30), "transport": "rgba-tcp-v1"}

    def terminate(self, record):
        if self.process_matches(record):
            try:
                os.kill(record["pid"], signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 5
            while self.process_matches(record) and time.monotonic() < deadline:
                time.sleep(0.05)
            child = self.children.pop(record["pid"], None)
            if child:
                try:
                    child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.children[record["pid"]] = child

    def apps(self):
        self.ready()
        # The companion supplies localized labels and icons. Use scrcpy as a fallback.
        try:
            data = self.bridge("apps")
            return {"apps": data["apps"]}
        except SubsystemError:
            output = self.run([self.tool("scrcpy"), "--serial", self.serial, "--list-apps"], timeout=60).stdout
            apps = []
            for line in output.splitlines():
                match = re.match(r"\s*[*-]\s+(.+?)\s{2,}([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)\s*$", line)
                if match:
                    apps.append({"label": match[1].strip(), "package": match[2]})
            if not apps:
                raise SubsystemError("Could not list apps; install the bundled Mac Bridge companion")
            return {"apps": sorted(apps, key=lambda a: a["label"].casefold())}

    def launch(self, package, label=None):
        package_name(package)
        self.boot()
        with self.locked():
            windows = self.windows()
            if package in windows:
                return {"package": package, "already_running": True, **windows[package]}
            help_text = self.run([self.tool("scrcpy"), "--help"]).stdout
            required = ["--new-display", "--start-app", "--display-ime-policy"]
            if any(flag not in help_text for flag in required):
                raise SubsystemError("scrcpy is too old; update it with brew upgrade scrcpy")
            title = (label or package).replace("\n", " ")[:120]
            argv = [self.tool("scrcpy"), "--serial", self.serial,
                    "--new-display=" + self.config["resolution"], "--start-app=" + package,
                    "--window-title=" + title, "--no-vd-system-decorations", "--display-ime-policy=local",
                    "--max-fps=" + str(self.config["fps"]), "--video-bit-rate=" + self.config["bitrate"],
                    "--video-codec=h264", "--audio-codec=raw"]
            if "--flex-display" in help_text:
                argv.append("--flex-display")
            if "--keep-active" in help_text:
                argv.append("--keep-active")
            record = self.spawn(argv, package + ".log")
            record.update({"package": package, "label": title})
            windows[package] = record
            atomic_json(self.root / "windows.json", windows)
            return record

    def close(self, package):
        package_name(package)
        with self.locked():
            windows = self.windows()
            if package in windows:
                self.terminate(windows.pop(package))
            atomic_json(self.root / "windows.json", windows)
            return {"package": package, "closed": True}

    def install(self, files):
        if not isinstance(files, list) or not files:
            raise SubsystemError("Select at least one APK")
        paths = [Path(p).expanduser().resolve() for p in files]
        if any(not p.is_file() or p.suffix.lower() != ".apk" for p in paths):
            raise SubsystemError("Every selected file must be an existing .apk; select all splits together")
        self.boot()
        with self.locked():
            args = ["install", "-r", str(paths[0])] if len(paths) == 1 else ["install-multiple", "-r", *map(str, paths)]
            result = self.adb(*args, timeout=240)
            if "Success" not in result.stdout:
                raise SubsystemError(result.stdout or "APK installation failed")
            return {"installed": [p.name for p in paths]}

    def uninstall(self, package):
        package_name(package)
        self.ready()
        self.close(package)
        with self.locked():
            result = self.adb("uninstall", package, timeout=90)
            if "Success" not in result.stdout:
                raise SubsystemError(result.stdout or "Uninstall failed")
            return {"uninstalled": package}

    def push(self, files):
        self.ready()
        paths = [Path(p).expanduser().resolve() for p in files]
        if not paths or any(not p.is_file() for p in paths):
            raise SubsystemError("Select existing files to import")
        imported = []
        with self.locked():
            for path in paths:
                # Normalize names to avoid adb remote-shell ambiguity, keep human-readable names.
                name = re.sub(r"[^A-Za-z0-9._ -]", "_", path.name)
                target = shared_path("/sdcard/Download/MacBridge/" + name)
                if self.adb("shell", "test", "-e", target, check=False).returncode == 0:
                    target = shared_path("/sdcard/Download/MacBridge/" + uuid.uuid4().hex[:8] + "-" + name)
                self.adb("push", str(path), target, timeout=240)
                imported.append(target)
            return {"imported": imported}

    def files(self):
        self.ready()
        out = self.adb("shell", "find", "/sdcard/Download/MacBridge", "-maxdepth", "1", "-type", "f").stdout
        return {"files": [s for s in out.splitlines() if s.startswith("/sdcard/Download/MacBridge/")]}

    def pull(self, remote, destination):
        self.ready()
        shared_path(remote)
        dest = Path(destination).expanduser().resolve()
        if not dest.is_dir():
            raise SubsystemError("Choose an existing destination folder")
        output = dest / PurePosixPath(remote).name
        if output.exists():
            raise SubsystemError(f"Destination exists; refusing to overwrite {output.name}")
        # Directory passing keeps leading option-like names from becoming adb options.
        self.adb("pull", remote, str(dest) + "/", timeout=240)
        return {"exported": str(output)}

    def bridge(self, endpoint):
        if endpoint not in {"apps", "notifications", "status"}:
            raise SubsystemError("Unknown bridge endpoint")
        result = self.adb("shell", "content", "query", "--uri", f"content://{AUTHORITY}/{endpoint}")
        match = re.search(r"payload=([A-Za-z0-9+/=]+)", result.stdout)
        if not match:
            raise SubsystemError("Mac Bridge companion unavailable")
        try:
            return json.loads(base64.b64decode(match[1], validate=True))
        except (ValueError, UnicodeError) as e:
            raise SubsystemError("Invalid companion response") from e

    def notifications(self):
        self.ready()
        data = self.bridge("notifications")
        return {"notifications": data.get("notifications", [])}

    def notification_settings(self):
        self.ready()
        # Permission is granted through Android's own settings UI.
        return self.launch(COMPANION, "Mac Bridge · 通知设置")

    def export_launcher(self, package, label, app_path, destination):
        package_name(package)
        app = Path(app_path).resolve()
        helper = app / "Contents/Resources/AndroidEntry"
        if not helper.is_file():
            raise SubsystemError("Build the Mac app before exporting launchers")
        folder = Path(destination).expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w .-]", "_", label, flags=re.UNICODE).strip(" .")[:60] or package
        target = folder / f"{safe} ({package}).app"
        if target.exists():
            raise SubsystemError("This launcher already exists")
        contents = target / "Contents"
        (contents / "MacOS").mkdir(parents=True)
        shutil.copy2(helper, contents / "MacOS/AndroidEntry")
        info = {"CFBundleIdentifier": "dev.dan.androidsubsystem.entry." + package,
                "CFBundleName": label, "CFBundleDisplayName": label,
                "CFBundleExecutable": "AndroidEntry", "CFBundlePackageType": "APPL",
                "CFBundleVersion": "1", "LSMinimumSystemVersion": "14.0",
                "LSUIElement": True, "AndroidPackage": package, "SubsystemAppPath": str(app)}
        with (contents / "Info.plist").open("wb") as f:
            plistlib.dump(info, f)
        self.run(["/usr/bin/codesign", "--force", "--sign", "-", str(target)])
        return {"launcher": str(target)}


def dispatch(controller, action, params):
    table = {"diagnostic": lambda: controller.diagnostic(), "status": lambda: controller.status(),
             "configure": lambda: controller.configure(params), "create": lambda: controller.create(),
             "boot": lambda: controller.boot(), "stop": lambda: controller.stop(),
             "apps": lambda: controller.apps(), "launch": lambda: controller.launch(params["package"], params.get("label")),
             "native-session": lambda: controller.native_session(params["package"]),
             "close": lambda: controller.close(params["package"]), "install": lambda: controller.install(params["files"]),
             "uninstall": lambda: controller.uninstall(params["package"]), "push": lambda: controller.push(params["files"]),
             "files": lambda: controller.files(), "pull": lambda: controller.pull(params["remote"], params["destination"]),
             "notifications": lambda: controller.notifications(), "notification-settings": lambda: controller.notification_settings(),
             "export-launcher": lambda: controller.export_launcher(params["package"], params["label"], params["app_path"], params["destination"])}
    if action not in table:
        raise SubsystemError("Unknown action")
    return table[action]()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("params", nargs="?", default="{}")
    parser.add_argument("--root")
    args = parser.parse_args()
    try:
        params = json.loads(args.params)
        if not isinstance(params, dict):
            raise SubsystemError("Parameters must be a JSON object")
        result = dispatch(Controller(args.root), args.action, params)
        print(json.dumps({"ok": True, "data": result}, ensure_ascii=False))
    except (SubsystemError, ValueError, KeyError, TypeError, OSError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
