"""Detached live capture, rolling segments and independent edit snapshots."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import fcntl
from fractions import Fraction
import importlib.util
import json
import math
import os
from pathlib import Path
import queue
import re
import select
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from .common import load_session, read_json, write_json


_CAPTURE = "capture.json"
_LEASE = "capture.lease"
_STOP = "capture.stop"
_ACTIVE = {"starting", "capturing", "reconnecting", "stopping"}
_MIN_FREE = 512 * 1024**2
_SEGMENT_SECONDS = 2
_MAX_ATTEMPTS = 4
_STALL_SECONDS = 60
_CHANNEL = re.compile(r"[a-zA-Z0-9_]{1,25}")
_QUALITY = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_+.-]*(?:,[a-zA-Z0-9][a-zA-Z0-9_+.-]*)*")
_CHAT_HOST = "irc.chat.twitch.tv"


@contextmanager
def _locked(path):
    with path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _ms():
    return time.time_ns() // 1_000_000


def _positive_ms(seconds, name):
    if isinstance(seconds, bool) or not isinstance(seconds, (float, int)):
        raise ValueError(f"Invalid {name}: expected a positive number.")
    if not math.isfinite(seconds) or seconds <= 0 or seconds > 7 * 24 * 3600:
        raise ValueError(f"Invalid {name}: expected a duration between 1 ms and 7 days.")
    milliseconds = round(seconds * 1000)
    if milliseconds < 1:
        raise ValueError(f"Invalid {name}: expected at least 1 ms.")
    return milliseconds


def _duration_minutes(minutes, name):
    if isinstance(minutes, bool) or not isinstance(minutes, (float, int)):
        raise ValueError(f"Invalid {name}: expected a positive number.")
    return _positive_ms(minutes * 60, name)


def _state(session):
    if not (session / _CAPTURE).is_file():
        raise ValueError(f"Capture session not found: {session}")
    return read_json(session / _CAPTURE)


def _lease_held(session):
    with (session / _LEASE).open("a+b") as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False


def _active_state(session):
    state = _state(session)
    if state["state"] in _ACTIVE and not _lease_held(session):
        state.update(
            state="failed", reason="interrupted", stopped_at_ms=_ms(),
            last_error="The capture worker exited without recording its final state.",
        )
        write_json(session / _CAPTURE, state)
    return state


def _suffix(state):
    segments = state.get("segments", [])
    if not segments:
        return []
    chain = segments[-1]["chain"]
    start = len(segments) - 1
    while start and segments[start - 1]["chain"] == chain:
        start -= 1
    return segments[start:]


def _coverage(state):
    segments = _suffix(state)
    if not segments:
        return 0
    return min(state["buffer_ms"], segments[-1]["end_ms"] - segments[0]["start_ms"])


def _status(state):
    return {
        **{key: value for key, value in state.items() if key not in {"segments", "token"}},
        "available_seconds": _coverage(state) / 1000,
        "segment_count": len(state.get("segments", [])),
    }


def start_capture(
    channel, session_dir, buffer_minutes=5, quality="720p60,720p,best", max_minutes=120,
    *, source_file=None,
):
    """Start a capture worker that survives the calling CLI process."""
    if not isinstance(channel, str) or not _CHANNEL.fullmatch(channel):
        raise ValueError("Invalid Twitch channel: use a Twitch login with letters, numbers or underscores.")
    if not isinstance(quality, str) or not _QUALITY.fullmatch(quality):
        raise ValueError("Invalid capture quality: use comma-separated quality names.")
    buffer_ms = _duration_minutes(buffer_minutes, "buffer_minutes")
    max_ms = _duration_minutes(max_minutes, "max_minutes")
    local = Path(source_file).expanduser().resolve() if source_file is not None else None
    if local is not None and not local.is_file():
        raise ValueError(f"Capture source file not found: {local}")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ValueError("FFmpeg and ffprobe are required to start capture.")
    streamlink = shutil.which("streamlink")
    if local is None and not streamlink:
        if importlib.util.find_spec("streamlink") is None:
            raise ValueError("Streamlink is required to capture Twitch.")
        streamlink = [sys.executable, "-m", "streamlink"]
    elif streamlink:
        streamlink = [streamlink]

    session = Path(session_dir).expanduser().resolve()
    session.mkdir(parents=True, exist_ok=True)
    with _locked(session / "capture.lock"):
        if (session / _CAPTURE).exists():
            raise ValueError(f"A capture already exists in {session}. Start a new session.")
        if shutil.disk_usage(session).free < _MIN_FREE:
            raise ValueError("Available disk space is below 512 MiB.")
        (session / "segments").mkdir()
        token = uuid.uuid4().hex
        state = {
            "state": "starting", "channel": channel.lower(), "pid": None,
            "capture_id": uuid.uuid4().hex, "token": token,
            "buffer_ms": buffer_ms, "max_ms": max_ms,
            "quality": quality, "source_file": str(local) if local else None,
            "streamlink": streamlink, "started_at_ms": _ms(), "stopped_at_ms": None,
            "last_error": None, "reason": None, "attempt": 0,
            "chat": "disabled" if local else "connecting", "segments": [],
        }
        write_json(session / _CAPTURE, state)
        with (session / _LEASE).open("a+b") as lease:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                with (session / "capture.log").open("ab") as log:
                    worker = subprocess.Popen(
                        [
                            sys.executable, "-m", "chat_clipper.capture", "worker",
                            str(session), str(lease.fileno()), token,
                        ],
                        cwd=Path(__file__).resolve().parents[1], stdin=subprocess.DEVNULL,
                        stdout=log, stderr=log, start_new_session=True,
                        pass_fds=(lease.fileno(),),
                    )
            except OSError as error:
                state.update(
                    state="failed", reason="worker_start", last_error=str(error),
                    stopped_at_ms=_ms(),
                )
                write_json(session / _CAPTURE, state)
                raise
            state["pid"] = worker.pid
            write_json(session / _CAPTURE, state)
        threading.Thread(target=worker.wait, daemon=True).start()
        return _status(state)


def capture_status(session_dir):
    session = Path(session_dir).expanduser().resolve()
    if not (session / _CAPTURE).is_file():
        raise ValueError(f"Capture session not found: {session}")
    with _locked(session / "capture.lock"):
        return _status(_active_state(session))


def stop_capture(session_dir):
    """Ask the lease holder to stop; the stored PID is only for display."""
    session = Path(session_dir).expanduser().resolve()
    if not (session / _CAPTURE).is_file():
        raise ValueError(f"Capture session not found: {session}")
    with _locked(session / "capture.lock"):
        state = _active_state(session)
        if state["state"] not in _ACTIVE:
            return _status(state)
        write_json(session / _STOP, {"token": state["token"]})
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        result = capture_status(session)
        if result["state"] not in _ACTIVE:
            return result
        time.sleep(0.1)
    return capture_status(session)


def _stop_requested(session, state, event):
    if event.is_set():
        return True
    try:
        return read_json(session / _STOP).get("token") == state["token"]
    except FileNotFoundError:
        return False


def _save_state(session, state, /, **updates):
    if all(state.get(key) == value for key, value in updates.items()):
        return
    state.update(updates)
    with _locked(session / "capture.lock"):
        write_json(session / _CAPTURE, state)


def _terminate(child, timeout=2):
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def _start_pipeline(state, run, directory, remaining_ms):
    """Return FFmpeg and, for Twitch, its Streamlink producer."""
    producer = None
    if state["source_file"]:
        source = ["-re", "-i", state["source_file"]]
    else:
        producer = subprocess.Popen(
            [
                *state["streamlink"], "--no-config", "--loglevel", "warning",
                "--stream-timeout", "25", "--http-timeout", "15", "--stdout",
                f"https://www.twitch.tv/{state['channel']}", state["quality"],
            ],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        )
        source = ["-i", "pipe:0"]
    try:
        ffmpeg = subprocess.Popen(
            [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning",
                *source, "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
                "-t", f"{remaining_ms / 1000:.3f}", "-f", "segment",
                "-segment_format", "mpegts", "-segment_time", str(_SEGMENT_SECONDS),
                "-segment_format_options", "mpegts_flags=+initial_discontinuity",
                "-segment_list", f"{run}.csv",
                "-segment_list_type", "csv", f"{run}-%06d.ts",
            ],
            cwd=directory, stdin=producer.stdout if producer else subprocess.DEVNULL,
        )
    except OSError:
        _terminate(producer)
        raise
    finally:
        if producer:
            producer.stdout.close()
    return ffmpeg, producer


def _remove_unindexed(directory, run, state):
    (directory / f"{run}.csv").unlink(missing_ok=True)
    retained = {item["name"] for item in state["segments"]}
    for path in directory.glob(f"{run}-*.ts"):
        if path.name not in retained:
            path.unlink(missing_ok=True)


def _pipeline_guardian(session, run, remaining_ms):
    """Own the input and muxer. EOF on the control pipe means the worker died."""
    directory = session / "segments"
    control = sys.stdin.fileno()
    interrupted = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: interrupted.set())
    signal.signal(signal.SIGINT, lambda *_: interrupted.set())
    worker_lost = False
    reason = None
    deadline = time.monotonic() + remaining_ms / 1000
    ffmpeg, producer = _start_pipeline(_state(session), run, directory, remaining_ms)
    try:
        while ffmpeg.poll() is None and not interrupted.is_set():
            ready, _, _ = select.select([control], [], [], 0.2)
            if ready:
                worker_lost = not os.read(control, 1)
                break
            if time.monotonic() >= deadline:
                reason = "limit"
                break
            if shutil.disk_usage(session).free < _MIN_FREE:
                reason = "disk"
                break
    finally:
        # Let FFmpeg close its last TS segment after the Streamlink pipe reaches EOF.
        _terminate(producer)
        if producer and ffmpeg.poll() is None:
            try:
                ffmpeg.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        _terminate(ffmpeg)
    if worker_lost:
        with _locked(session / "capture.lock"):
            _remove_unindexed(directory, run, _state(session))
        return
    write_json(directory / f"{run}.result.json", {
        "ffmpeg_code": ffmpeg.returncode,
        "streamlink_code": producer.returncode if producer else None,
        "reason": reason,
    })


def _finish_guardian(guardian):
    try:
        with guardian.stdin as control:
            control.write(b"q")
    except BrokenPipeError:
        pass
    try:
        guardian.wait(timeout=7)
    except subprocess.TimeoutExpired:
        _terminate(guardian)


def _new_segments(directory, run, offset, state):
    """FFmpeg lists a segment only after closing its output file."""
    additions = []
    try:
        index = (directory / f"{run}.csv").open(encoding="utf-8")
    except FileNotFoundError:
        return additions, offset
    with index:
        index.seek(offset)
        while line := index.readline():
            if not line.endswith("\n"):
                break
            offset = index.tell()
            name, _, _ = next(csv.reader([line]))
            if not re.fullmatch(rf"{run}-\d{{6}}\.ts", name):
                raise ValueError("Unexpected filename in FFmpeg's segment index.")
            path = directory / name
            try:
                start, duration, format_start, frame = _video_timing(path)
            except (ValueError, subprocess.TimeoutExpired) as error:
                print(f"Could not use closed segment {name}: {error}", flush=True)
                continue
            start_ms, end_ms = round(start * 1000), round((start + duration) * 1000)
            prior = additions or state["segments"]
            previous = prior[-1] if prior else None
            contiguous = (
                previous and previous["run"] == run
                and int(previous["name"][-9:-3]) + 1 == int(name[-9:-3])
                and previous["start_ms"] < start_ms
                and abs(previous["end_ms"] - start_ms) <= max(2, min(50, round(frame * 1000)))
            )
            if contiguous:
                chain = previous["chain"]
                anchor_ms = previous["anchor_ms"]
            else:
                chain = name
                anchor_ms = path.stat().st_mtime_ns // 1_000_000 - end_ms
            additions.append({
                "name": name, "run": run, "chain": chain, "anchor_ms": anchor_ms,
                "start_ms": start_ms, "end_ms": end_ms,
                "end_us": round((start + duration) * 1_000_000),
                "format_start_us": round(format_start * 1_000_000),
            })
    return additions, offset


def _record_closed(session, state, additions):
    if not additions:
        return
    segments = state["segments"] + additions
    last = segments[-1]
    cutoff = last["anchor_ms"] + last["end_ms"] - state["buffer_ms"]
    keep = []
    expired = []
    for segment in segments:
        end = segment["anchor_ms"] + segment["end_ms"]
        (expired if end <= cutoff else keep).append(segment)
    with _locked(session / "capture.lock"):
        state["segments"] = keep
        if state["state"] != "stopping":
            state.update(state="capturing", last_error=None)
        write_json(session / _CAPTURE, state)
        for segment in expired:
            (session / "segments" / segment["name"]).unlink(missing_ok=True)
        if cutoff > 0:
            for path in (session / "chat").glob("*.jsonl"):
                if path.stem.isdecimal() and (int(path.stem) + 1) * 60_000 <= cutoff:
                    path.unlink(missing_ok=True)


def _parse_message(line, channel):
    if line.startswith("@"):
        _, _, line = line.partition(" ")
    prefix, marker, body = line.partition(f" PRIVMSG #{channel} :")
    if not marker or not prefix.startswith(":") or "!" not in prefix:
        return None
    author = prefix[1:].split("!", 1)[0]
    if not _CHANNEL.fullmatch(author):
        return None
    return {"wall_ms": _ms(), "author": author, "text": body[:500]}


def _chat_listener(channel, events, finished):
    context = ssl.create_default_context()
    for attempt in range(_MAX_ATTEMPTS):
        try:
            events.put_nowait("connecting")
            with socket.create_connection((_CHAT_HOST, 6697), timeout=5) as raw:
                with context.wrap_socket(raw, server_hostname=_CHAT_HOST) as conn:
                    conn.settimeout(1)
                    nickname = f"justinfan{int(uuid.uuid4().hex[:8], 16)}"
                    conn.sendall(f"PASS SCHMOOPIIE\r\nNICK {nickname}\r\n".encode())
                    pending = b""
                    last_second = sent_this_second = 0
                    joined = join_requested = False
                    last_line = time.monotonic()
                    join_deadline = last_line + 10
                    while not finished.is_set():
                        if not joined and time.monotonic() >= join_deadline:
                            raise ConnectionError("Twitch did not confirm the chat join.")
                        try:
                            chunk = conn.recv(4096)
                        except socket.timeout:
                            if time.monotonic() - last_line > 360:
                                raise ConnectionError("Twitch chat stopped responding.")
                            continue
                        if not chunk:
                            raise ConnectionError("Twitch chat disconnected.")
                        last_line = time.monotonic()
                        pending += chunk
                        while b"\r\n" in pending:
                            line, pending = pending.split(b"\r\n", 1)
                            line = line.decode("utf-8", errors="replace")
                            command_line = line.partition(" ")[2] if line.startswith("@") else line
                            command_head, _, trailing = command_line.partition(" :")
                            fields = command_head.split()
                            prefix = fields.pop(0) if fields and fields[0].startswith(":") else ""
                            if not fields:
                                continue
                            command, *params = fields
                            if command == "PING":
                                conn.sendall(f"PONG :{trailing or ' '.join(params)}\r\n".encode())
                            elif command == "376" and not join_requested:
                                conn.sendall(f"JOIN #{channel}\r\n".encode())
                                join_requested = True
                            elif (
                                command == "366" and params[:2] == [nickname, f"#{channel}"]
                                or command == "JOIN" and prefix.startswith(f":{nickname}!")
                                and f"#{channel}" in (*params, trailing)
                            ):
                                joined = True
                                events.put_nowait("connected")
                            elif command == "RECONNECT" or command == "NOTICE" and params == ["*"]:
                                raise ConnectionError("Twitch chat requested reconnection.")
                            message = _parse_message(line, channel)
                            if message:
                                second = message["wall_ms"] // 1000
                                if second != last_second:
                                    last_second, sent_this_second = second, 0
                                if sent_this_second < 15:
                                    events.put_nowait(message)
                                    sent_this_second += 1
                        if len(pending) > 65536:
                            raise ConnectionError("Twitch chat sent an oversized IRC line.")
                    return
        except (OSError, queue.Full) as error:
            print(f"Chat attempt {attempt + 1}: {error}", flush=True)
        if finished.wait(min(2 ** attempt, 8)):
            return
    try:
        events.put_nowait("unavailable")
    except queue.Full:
        pass


def _drain_chat(session, state, events):
    messages = {}
    chat = state["chat"]
    while True:
        try:
            item = events.get_nowait()
        except queue.Empty:
            break
        if isinstance(item, str):
            chat = item
        else:
            chat = "connected"
            messages.setdefault(item["wall_ms"] // 60_000, []).append(item)
    if messages:
        folder = session / "chat"
        folder.mkdir(exist_ok=True)
        for bucket, rows in messages.items():
            with (folder / f"{bucket}.jsonl").open("a", encoding="utf-8") as output:
                output.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    _save_state(session, state, chat=chat)


def _exit_reason(session, state, stopped, deadline):
    if _stop_requested(session, state, stopped):
        return "user"
    if time.monotonic() >= deadline:
        return "limit"
    if shutil.disk_usage(session).free < _MIN_FREE:
        return "disk"
    return None


def _capture_attempt(session, state, events, stopped, deadline):
    run = uuid.uuid4().hex[:12]
    directory = session / "segments"
    offset = 0
    last_segment = time.monotonic()
    reason = None
    remaining_ms = max(1, round((deadline - time.monotonic()) * 1000))
    guardian = subprocess.Popen(
        [sys.executable, "-m", "chat_clipper.capture", "pipeline", str(session), run, str(remaining_ms)],
        stdin=subprocess.PIPE,
    )
    report_path = directory / f"{run}.result.json"
    try:
        while guardian.poll() is None:
            _drain_chat(session, state, events)
            additions, offset = _new_segments(directory, run, offset, state)
            _record_closed(session, state, additions)
            if additions:
                last_segment = time.monotonic()
            reason = _exit_reason(session, state, stopped, deadline)
            if reason:
                _save_state(session, state, state="stopping")
                break
            if time.monotonic() - last_segment > _STALL_SECONDS:
                reason = "stall"
                break
            stopped.wait(0.2)
    finally:
        _finish_guardian(guardian)
        additions, _ = _new_segments(directory, run, offset, state)
        _record_closed(session, state, additions)
        _remove_unindexed(directory, run, state)
    report = read_json(report_path) if report_path.exists() else {}
    report_path.unlink(missing_ok=True)
    return reason or report.get("reason"), report.get("ffmpeg_code", guardian.returncode), report.get("streamlink_code")


def _finalize(session, state, reason, error=None):
    updates = {
        "state": "failed" if error else "stopped",
        "reason": reason,
        "last_error": error,
        "stopped_at_ms": _ms(),
        "chat": "stopped" if state["chat"] in {"connected", "connecting"} else state["chat"],
    }
    _save_state(session, state, **updates)
    (session / _STOP).unlink(missing_ok=True)


def _worker(session, lease_fd, token):
    session = Path(session)
    # The inherited descriptor keeps the lease continuously held after the caller exits.
    with os.fdopen(lease_fd, "a+b"):
        with _locked(session / "capture.lock"):
            state = _state(session)
            if state["token"] != token or state["pid"] != os.getpid():
                return
        stopped = threading.Event()
        chat_finished = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stopped.set())
        signal.signal(signal.SIGTERM, lambda *_: stopped.set())
        events = queue.Queue(maxsize=2000)
        deadline = time.monotonic() + state["max_ms"] / 1000
        try:
            if not state["source_file"]:
                threading.Thread(
                    target=_chat_listener, args=(state["channel"], events, chat_finished), daemon=True
                ).start()
            attempts = 1 if state["source_file"] else _MAX_ATTEMPTS
            last_error = None
            for attempt in range(1, attempts + 1):
                reason = _exit_reason(session, state, stopped, deadline)
                if reason:
                    break
                _save_state(session, state, attempt=attempt)
                reason, ffmpeg_code, streamlink_code = _capture_attempt(
                    session, state, events, stopped, deadline
                )
                reason = _exit_reason(session, state, stopped, deadline) or reason
                if reason in {"user", "limit", "disk"}:
                    break
                if state["source_file"] and not reason and ffmpeg_code == 0 and state["segments"]:
                    reason = "source_ended"
                    break
                last_error = (
                    "Capture stalled before a closed segment arrived."
                    if reason == "stall"
                    else f"Capture input ended (FFmpeg {ffmpeg_code}, Streamlink {streamlink_code})."
                )
                if attempt == attempts:
                    reason = "reconnect_exhausted" if not state["source_file"] else "capture_error"
                    break
                _save_state(session, state, state="reconnecting", last_error=last_error)
                retry_at = time.monotonic() + min(2 ** attempt, 8)
                while time.monotonic() < retry_at:
                    reason = _exit_reason(session, state, stopped, deadline)
                    if reason:
                        break
                    _drain_chat(session, state, events)
                    stopped.wait(0.2)
                if reason:
                    break
            _drain_chat(session, state, events)
            errors = {
                "disk": "Available disk space fell below 512 MiB.",
                "capture_error": last_error,
                "reconnect_exhausted": last_error,
            }
            _finalize(session, state, reason, errors.get(reason))
        except Exception as error:
            print(f"Capture failed: {error}", file=sys.stderr, flush=True)
            _finalize(session, state, "capture_error", str(error))
        finally:
            chat_finished.set()


def _snapshot_chat(session, stage, first_ms, end_ms):
    folder = session / "chat"
    if not folder.is_dir():
        return False
    output = stage / "chat.jsonl"
    with output.open("w", encoding="utf-8") as target:
        for bucket in range(first_ms // 60_000, end_ms // 60_000 + 1):
            path = folder / f"{bucket}.jsonl"
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if first_ms <= row["wall_ms"] < end_ms:
                    row["time"] = (row.pop("wall_ms") - first_ms) / 1000
                    target.write(json.dumps(row, ensure_ascii=False) + "\n")
    if output.stat().st_size:
        return True
    output.unlink()
    return False


def _stage_snapshot(session, stage, requested_ms):
    with _locked(session / "capture.lock"):
        state = _active_state(session)
        available_ms = _coverage(state)
        wanted_ms = available_ms if requested_ms is None else requested_ms
        if not wanted_ms or wanted_ms > available_ms:
            raise ValueError(
                f"Requested duration exceeds the available contiguous buffer "
                f"({available_ms / 1000:.3f} seconds)."
            )
        segments = _suffix(state)
        last = segments[-1]
        first_ms = last["end_ms"] - wanted_ms
        selected = [segment for segment in segments if segment["end_ms"] > first_ms]
        # MPEG-TS retains one PTS timeline across segments, including audio boundaries.
        with (stage / "snapshot.ts").open("wb") as joined:
            for segment in selected:
                name = segment["name"]
                if not re.fullmatch(r"[a-f0-9]{12}-\d{6}\.ts", name):
                    raise ValueError("Invalid buffered segment filename.")
                segment_file = session / "segments" / name
                if not segment_file.is_file() or segment_file.is_symlink():
                    raise ValueError(f"A required buffered segment is no longer available: {name}")
                with segment_file.open("rb") as source:
                    shutil.copyfileobj(source, joined, length=1024**2)
        has_chat = _snapshot_chat(
            session, stage, last["anchor_ms"] + first_ms, last["anchor_ms"] + last["end_ms"]
        )
        metadata = {
            "capture_id": state["capture_id"],
            "capture_session": session.name,
            "capture_path": str(session),
            "capture_chain": last["chain"],
            "channel": state["channel"],
            "requested_seconds": wanted_ms / 1000,
            "source_start_ms": first_ms,
            "source_end_ms": last["end_ms"],
            "wall_start_ms": last["anchor_ms"] + first_ms,
            "wall_end_ms": last["anchor_ms"] + last["end_ms"],
        }
        if has_chat:
            metadata["chat_timing"] = "approximate"
        source_end_us = last.get("end_us")
        format_start_us = selected[0].get("format_start_us")
        skip_us = None
        if source_end_us is not None and format_start_us is not None:
            skip_us = source_end_us - format_start_us - wanted_ms * 1000
        return wanted_ms, skip_us, metadata, has_chat


def _run_media(command, cwd, timeout):
    result = subprocess.run(
        command, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
        text=True, timeout=timeout,
    )
    if result.returncode:
        error = result.stderr.strip() or f"exit status {result.returncode}"
        raise ValueError(f"{command[0]} failed: {error}")
    return result.stdout


def _video_timing(path):
    timing = json.loads(_run_media(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
            "stream=start_time,duration,avg_frame_rate:format=start_time", "-of", "json", str(path),
        ],
        None, 10,
    ))
    try:
        video = timing["streams"][0]
        start = float(video["start_time"])
        duration = float(video["duration"])
        format_start = float(timing["format"]["start_time"])
    except (IndexError, KeyError, ValueError) as error:
        raise ValueError(f"No playable video timing in {path.name}.") from error
    if not all(map(math.isfinite, (start, duration, format_start))) or duration <= 0:
        raise ValueError(f"Invalid video timing in {path.name}.")
    try:
        frame_seconds = 1 / float(Fraction(video["avg_frame_rate"]))
    except (KeyError, ValueError, ZeroDivisionError):
        frame_seconds = 1 / 30
    return start, duration, format_start, frame_seconds


def _render_snapshot(stage, wanted_ms, skip_us):
    wanted_seconds = wanted_ms / 1000
    if skip_us is None:
        # Older capture indexes only have millisecond timestamps.
        start, duration, format_start, _ = _video_timing(stage / "snapshot.ts")
        skip_us = round((start + duration - format_start) * 1_000_000) - wanted_ms * 1000
    _run_media(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror",
            "-i", "snapshot.ts", "-ss", f"{max(skip_us, 0) / 1_000_000:.6f}",
            "-t", f"{wanted_seconds:.3f}", "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", "snapshot.mp4",
        ],
        stage, max(120, wanted_seconds * 3),
    )
    _, duration, _, frame_seconds = _video_timing(stage / "snapshot.mp4")
    aligned_duration = round(wanted_seconds / frame_seconds) * frame_seconds
    tolerance = 0.001 if abs(wanted_seconds - aligned_duration) <= 0.001 else frame_seconds
    if abs(duration - wanted_seconds) > tolerance:
        raise ValueError(
            f"Rendered video covers {duration:.3f} seconds of the requested {wanted_seconds:.3f}."
        )
    return duration


def _commit_snapshot(destination, stage, duration, metadata, has_chat):
    try:
        destination.mkdir()
        created = True
    except FileExistsError:
        created = False
    with _locked(destination / ".snapshot.lock"):
        if (destination / "session.json").exists():
            manifest = load_session(destination)
            if manifest["kind"] != "snapshot" or manifest["media"]:
                raise ValueError(f"Snapshot destination already has a session or media: {destination}")
        elif created:
            manifest = {
                "version": 1, "id": uuid.uuid4().hex,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "kind": "snapshot", "source": metadata["capture_path"],
                "metadata": {},
            }
        else:
            raise ValueError(f"Snapshot destination already exists: {destination}")
        manifest.update(media="snapshot.mp4", duration=duration)
        manifest["metadata"].update(metadata)
        files = ["snapshot.mp4"]
        if has_chat:
            files.append("chat.jsonl")
        if any((destination / name).exists() for name in files):
            raise ValueError(f"Snapshot destination already contains media: {destination}")
        moved = []
        try:
            for name in files:
                os.replace(stage / name, destination / name)
                moved.append(name)
            write_json(destination / "session.json", manifest)
        except Exception:
            for name in moved:
                (destination / name).unlink(missing_ok=True)
            raise
    return manifest


def snapshot_capture(session_dir, destination, seconds=300):
    """Save the most recent contiguous interval of closed video to a new edit session."""
    requested_ms = None if seconds is None else _positive_ms(seconds, "seconds")
    session = Path(session_dir).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    if not (session / _CAPTURE).is_file():
        raise ValueError(f"Capture session not found: {session}")
    if destination.is_relative_to(session):
        raise ValueError("Snapshot destination must be outside the capture directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".snapshot-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        wanted_ms, skip_us, metadata, has_chat = _stage_snapshot(session, stage, requested_ms)
        duration = _render_snapshot(stage, wanted_ms, skip_us)
        return _commit_snapshot(destination, stage, duration, metadata, has_chat)


def _main():
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    worker = subcommands.add_parser("worker")
    worker.add_argument("session")
    worker.add_argument("lease_fd", type=int)
    worker.add_argument("token")
    pipeline = subcommands.add_parser("pipeline")
    pipeline.add_argument("session", type=Path)
    pipeline.add_argument("run")
    pipeline.add_argument("remaining_ms", type=int)
    args = parser.parse_args()
    if args.command == "worker":
        _worker(args.session, args.lease_fd, args.token)
    else:
        _pipeline_guardian(args.session, args.run, args.remaining_ms)


if __name__ == "__main__":
    _main()
