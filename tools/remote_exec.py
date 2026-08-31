#!/usr/bin/env python3
"""Run multi-line commands or local scripts on a remote host without SSH quote soup."""

from __future__ import annotations

import argparse
import base64
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import tempfile

DEFAULT_HOST = "vickrey10.cs.ubc.ca"
DEFAULT_REMOTE_DIR = "/home/kevinlb/bin/GizmoApp"
DEFAULT_REMOTE_TMP_PREFIX = "/tmp/caida-remote-exec."

ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Upload a local payload to a remote temporary directory and execute it "
            "through a generated bash wrapper. This avoids nested SSH/heredoc quoting."
        )
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Remote SSH host. Default: {DEFAULT_HOST}")
    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=10,
        help="SSH connection timeout in seconds. Default: 10.",
    )
    parser.add_argument(
        "--remote-dir",
        default=DEFAULT_REMOTE_DIR,
        help=f"Remote working directory, or empty to leave unchanged. Default: {DEFAULT_REMOTE_DIR}",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "bash", "python"),
        default="auto",
        help="How to run the uploaded payload. 'auto' uses .py suffix/shebang detection.",
    )
    parser.add_argument(
        "--python",
        action="store_true",
        help="Shortcut for --mode python. Uses .venv/bin/python under --remote-dir when present.",
    )
    parser.add_argument(
        "--python-bin",
        default="python3",
        help="Fallback Python executable when --remote-dir/.venv/bin/python is absent.",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Environment variable to export for the payload. Repeat as needed.",
    )
    parser.add_argument(
        "--script",
        type=Path,
        help="Local script file to upload and execute remotely.",
    )
    parser.add_argument(
        "--command",
        help="Inline bash command body to upload as a script and execute remotely.",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read a bash command body from stdin, upload it, and execute it remotely.",
    )
    parser.add_argument(
        "--keep-remote",
        action="store_true",
        help="Do not remove the remote temporary directory after execution.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the local SSH operations that would run without contacting the host.",
    )
    parser.add_argument(
        "payload_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the remote payload. Prefix with -- when needed.",
    )
    args = parser.parse_args()

    source_count = sum(bool(value) for value in (args.script, args.command is not None, args.stdin))
    if source_count != 1:
        parser.error("choose exactly one of --script, --command, or --stdin")
    if args.script and not args.script.is_file():
        parser.error(f"--script does not exist or is not a file: {args.script}")

    payload_args = strip_remainder_separator(args.payload_args)
    mode = "python" if args.python else args.mode
    env = parse_env(args.env)

    with tempfile.TemporaryDirectory(prefix="caida-remote-exec-local.") as local_tmp:
        local_tmp_path = Path(local_tmp)
        payload = build_payload(args, local_tmp_path)
        resolved_mode = resolve_mode(mode, payload)
        ssh_options = build_ssh_options(args.connect_timeout)
        remote_tmp = f"{DEFAULT_REMOTE_TMP_PREFIX}{secrets.token_hex(8)}"
        remote_payload = f"{remote_tmp}/payload{safe_payload_suffix(payload.suffix)}"
        remote_wrapper = f"{remote_tmp}/run.sh"
        wrapper = build_wrapper(
            remote_dir=args.remote_dir,
            remote_payload=remote_payload,
            mode=resolved_mode,
            python_bin=args.python_bin,
            env=env,
            payload_args=payload_args,
        )
        local_wrapper = local_tmp_path / "run.sh"
        local_wrapper.write_text(wrapper, encoding="utf-8")

        return run_remote_bundle(
            host=args.host,
            ssh_options=ssh_options,
            remote_tmp=remote_tmp,
            remote_payload=remote_payload,
            remote_wrapper=remote_wrapper,
            payload=payload,
            wrapper=local_wrapper,
            keep_remote=args.keep_remote,
            dry_run=args.dry_run,
        )


def strip_remainder_separator(values: list[str]) -> list[str]:
    if values and values[0] == "--":
        return values[1:]
    return values


def parse_env(values: list[str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for value in values:
        name, separator, env_value = value.partition("=")
        if not separator:
            raise SystemExit(f"--env must use NAME=VALUE syntax: {value}")
        if not ENV_NAME_RE.fullmatch(name):
            raise SystemExit(f"Invalid environment variable name for --env: {name}")
        env[name] = env_value
    return env


def build_payload(args: argparse.Namespace, local_tmp: Path) -> Path:
    if args.script:
        return args.script.resolve()

    payload = local_tmp / "payload.sh"
    if args.command is not None:
        body = args.command
    else:
        body = sys.stdin.read()
    payload.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body.rstrip() + "\n", encoding="utf-8")
    return payload


def resolve_mode(mode: str, payload: Path) -> str:
    if mode != "auto":
        return mode
    if payload.suffix == ".py":
        return "python"
    try:
        with payload.open(encoding="utf-8", errors="ignore") as handle:
            first_line = handle.readline()
    except OSError:
        return "bash"
    return "python" if first_line.startswith("#!") and "python" in first_line else "bash"


def build_ssh_options(connect_timeout: int) -> list[str]:
    return ["-o", f"ConnectTimeout={connect_timeout}", "-o", "BatchMode=yes"]


def safe_payload_suffix(suffix: str) -> str:
    return suffix if re.fullmatch(r"\.[A-Za-z0-9_.-]+", suffix) else ""


def build_wrapper(
    *,
    remote_dir: str,
    remote_payload: str,
    mode: str,
    python_bin: str,
    env: dict[str, str],
    payload_args: list[str],
) -> str:
    lines = ["#!/usr/bin/env bash", "set -euo pipefail"]
    if remote_dir:
        lines.append(f"cd {shlex.quote(remote_dir)}")
    for name, value in env.items():
        lines.append(f"export {name}={shlex.quote(value)}")

    quoted_args = " ".join(shlex.quote(value) for value in payload_args)
    if mode == "python":
        venv_python = f"{remote_dir.rstrip('/')}/.venv/bin/python" if remote_dir else ""
        if venv_python:
            lines.extend(
                [
                    f"if [[ -x {shlex.quote(venv_python)} ]]; then",
                    f"  exec {shlex.quote(venv_python)} {shlex.quote(remote_payload)} {quoted_args}".rstrip(),
                    "fi",
                ]
            )
        lines.append(f"exec {shlex.quote(python_bin)} {shlex.quote(remote_payload)} {quoted_args}".rstrip())
    else:
        lines.append(f"exec /bin/bash {shlex.quote(remote_payload)} {quoted_args}".rstrip())
    return "\n".join(lines) + "\n"


def run_remote_bundle(
    *,
    host: str,
    ssh_options: list[str],
    remote_tmp: str,
    remote_payload: str,
    remote_wrapper: str,
    payload: Path,
    wrapper: Path,
    keep_remote: bool,
    dry_run: bool,
) -> int:
    command = ["ssh", *ssh_options, host, "/bin/bash", "-s"]
    bootstrap = build_bootstrap(
        remote_tmp=remote_tmp,
        remote_payload=remote_payload,
        remote_wrapper=remote_wrapper,
        payload_bytes=payload.read_bytes(),
        wrapper_bytes=wrapper.read_bytes(),
        keep_remote=keep_remote,
    )
    if dry_run:
        print(f"{format_command(command)} < generated bootstrap for {host}:{remote_tmp}")
        return 0
    result = subprocess.run(command, input=bootstrap.encode("utf-8"), check=False)
    return result.returncode


def build_bootstrap(
    *,
    remote_tmp: str,
    remote_payload: str,
    remote_wrapper: str,
    payload_bytes: bytes,
    wrapper_bytes: bytes,
    keep_remote: bool,
) -> str:
    payload_b64 = base64.b64encode(payload_bytes).decode("ascii")
    wrapper_b64 = base64.b64encode(wrapper_bytes).decode("ascii")
    lines = [
        "set -euo pipefail",
        f"mkdir -m 700 {shlex.quote(remote_tmp)}",
    ]
    if keep_remote:
        lines.append(f"echo 'Kept remote temporary directory: {shlex.quote(remote_tmp)}' >&2")
    else:
        lines.append(f"trap 'rm -rf {shlex.quote(remote_tmp)}' EXIT")
    lines.extend(
        [
            f"base64 -d > {shlex.quote(remote_payload)} <<'CAIDA_REMOTE_EXEC_PAYLOAD'",
            payload_b64,
            "CAIDA_REMOTE_EXEC_PAYLOAD",
            f"base64 -d > {shlex.quote(remote_wrapper)} <<'CAIDA_REMOTE_EXEC_WRAPPER'",
            wrapper_b64,
            "CAIDA_REMOTE_EXEC_WRAPPER",
            f"/bin/bash {shlex.quote(remote_wrapper)}",
        ]
    )
    return "\n".join(lines) + "\n"


def format_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


if __name__ == "__main__":
    sys.exit(main())
