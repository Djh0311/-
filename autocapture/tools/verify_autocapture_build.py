#!/usr/bin/env python3
"""Fail-closed verifier for the offline autocapture foundation.

The verifier deliberately validates the candidate tree before importing any
candidate module.  It uses only the Python standard library and emits stable,
value-free reason codes on failure.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple


MANIFEST_RELATIVE = "autocapture/build-manifest.json"
MANIFEST_SCHEMA = "autocapture-build-manifest.v1"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024

EXPECTED_FILES = frozenset(
    {
        "autocapture/__init__.py",
        "autocapture/addon.py",
        "autocapture/policy.py",
        "autocapture/lease.py",
        "autocapture/shape.py",
        "autocapture/publisher.py",
        MANIFEST_RELATIVE,
        "autocapture/tools/verify_autocapture_build.py",
        "autocapture/tests/__init__.py",
        "autocapture/tests/fakes.py",
        "autocapture/tests/test_addon.py",
        "autocapture/tests/test_policy_and_lease.py",
        "autocapture/tests/test_shape.py",
        "autocapture/tests/test_publisher.py",
        "autocapture/tests/test_verifier.py",
        "docs/design/autocapture-shape-discovery-v1.md",
    }
)

EXPECTED_DIRECTORIES = frozenset(
    {
        "autocapture",
        "autocapture/tools",
        "autocapture/tests",
        "docs/design",
    }
)

PRODUCTION_FILES = (
    "autocapture/__init__.py",
    "autocapture/addon.py",
    "autocapture/policy.py",
    "autocapture/lease.py",
    "autocapture/shape.py",
    "autocapture/publisher.py",
)

PYTHON_FILES = tuple(sorted(path for path in EXPECTED_FILES if path.endswith(".py")))

REQUIRED_VERIFIER_TESTS = frozenset(
    {
        "test_baseline_temp_copy_passes",
        "test_arbitrary_flow_alias_names_are_tainted_after_manifest_rehash",
        "test_addon_bootstrap_escape_is_rejected_after_manifest_rehash",
        "test_body_escape_paths_are_rejected_after_manifest_rehash",
        "test_body_load_outside_addon_is_rejected_after_manifest_rehash",
        "test_cache_and_capture_residue_are_rejected",
        "test_clobber_primitive_is_rejected_after_manifest_rehash",
        "test_callable_capability_alias_is_rejected_after_manifest_rehash",
        "test_contiguous_sensitive_canary_is_rejected_without_echo",
        "test_dead_code_publisher_proof_is_rejected_after_manifest_rehash",
        "test_deleted_sensitive_rule_is_rejected_after_manifest_rehash",
        "test_direct_target_unlink_is_rejected_after_manifest_rehash",
        "test_dynamic_builtins_import_is_rejected_after_manifest_rehash",
        "test_dynamic_flow_attribute_is_rejected_after_manifest_rehash",
        "test_dynamic_os_capability_is_rejected_after_manifest_rehash",
        "test_dynamic_value_hash_key_is_rejected_after_manifest_rehash",
        "test_duplicate_schema_key_classifier_is_rejected_after_manifest_rehash",
        "test_encoded_dynamic_value_hash_key_is_rejected_after_manifest_rehash",
        "test_dunder_capability_lookup_is_rejected_after_manifest_rehash",
        "test_early_raw_content_read_is_rejected_after_manifest_rehash",
        "test_endpoint_selector_gate_removal_or_reversal_is_rejected_after_manifest_rehash",
        "test_endpoint_selector_request_surface_is_exact_after_manifest_rehash",
        "test_endpoint_selector_response_order_is_rejected_after_manifest_rehash",
        "test_every_required_file_is_required",
        "test_extra_regular_file_and_directory_are_rejected",
        "test_flow_container_aliases_are_rejected_after_manifest_rehash",
        "test_flow_default_capture_is_rejected_after_manifest_rehash",
        "test_flow_mutation_is_rejected_after_manifest_rehash",
        "test_forbidden_import_is_rejected_after_manifest_rehash",
        "test_forbidden_request_field_is_rejected_after_manifest_rehash",
        "test_forbidden_response_header_is_rejected_after_manifest_rehash",
        "test_host_only_endpoint_selector_is_rejected_after_manifest_rehash",
        "test_loader_exact_export_and_disarmed_state_are_rejected_after_manifest_rehash",
        "test_loader_mitmproxy_import_and_auto_arm_are_rejected_after_manifest_rehash",
        "test_manifest_duplicate_json_key_is_rejected",
        "test_manifest_missing_duplicate_extra_and_mismatch_are_rejected",
        "test_missing_reopen_guard_is_rejected_after_manifest_rehash",
        "test_non_regular_node_is_rejected",
        "test_os_open_callsite_escape_is_rejected_after_manifest_rehash",
        "test_os_capability_surface_is_closed_after_manifest_rehash",
        "test_owned_target_cleanup_is_rejected_after_manifest_rehash",
        "test_raw_and_value_hash_output_keys_are_rejected_after_manifest_rehash",
        "test_renamed_flow_parameter_remains_tainted_after_manifest_rehash",
        "test_required_fault_test_deletion_is_rejected_after_manifest_rehash",
        "test_reversed_metadata_gate_is_rejected_after_manifest_rehash",
        "test_schema_key_classifier_bypass_is_rejected_after_manifest_rehash",
        "test_semantic_manifest_swap_is_rejected",
        "test_split_endpoint_selector_is_rejected_after_manifest_rehash",
        "test_statically_disabled_sensitive_rule_is_rejected_after_manifest_rehash",
        "test_split_sensitive_rule_is_rejected_after_manifest_rehash",
        "test_sensitive_execution_helpers_are_required_after_manifest_rehash",
        "test_symlink_inside_candidate_is_rejected",
        "test_symlink_scope_escape_is_rejected",
        "test_target_alias_clobber_is_rejected_after_manifest_rehash",
        "test_unused_sensitive_rule_is_rejected_after_manifest_rehash",
        "test_unreachable_publish_link_is_rejected_after_manifest_rehash",
        "test_unreachable_sensitive_gate_is_rejected_after_manifest_rehash",
    }
)

ALLOWED_IMPORT_ROOTS: Mapping[str, Set[str]] = {
    "autocapture/__init__.py": {
    },
    "autocapture/addon.py": {
        "autocapture",
        "dataclasses",
        "math",
        "os",
        "sys",
        "time",
    },
    "autocapture/policy.py": {
        "__future__",
        "dataclasses",
        "math",
        "re",
        "typing",
    },
    "autocapture/lease.py": {
        "__future__",
        "math",
        "typing",
    },
    "autocapture/shape.py": {
        "__future__",
        "dataclasses",
        "hashlib",
        "json",
        "math",
        "re",
        "typing",
    },
    "autocapture/publisher.py": {
        "__future__",
        "autocapture",
        "hashlib",
        "json",
        "os",
        "secrets",
        "stat",
        "typing",
    },
}

ALLOWED_OS_ATTRIBUTES: Mapping[str, Set[str]] = {
    "autocapture/addon.py": {
        "os.path",
        "os.path.basename",
        "os.path.dirname",
        "os.path.isabs",
        "os.path.join",
        "os.path.realpath",
    },
    "autocapture/publisher.py": {
        "os.O_CREAT",
        "os.O_DIRECTORY",
        "os.O_EXCL",
        "os.O_NOFOLLOW",
        "os.O_RDONLY",
        "os.O_WRONLY",
        "os.close",
        "os.fchmod",
        "os.fspath",
        "os.fstat",
        "os.fsync",
        "os.geteuid",
        "os.link",
        "os.lstat",
        "os.open",
        "os.path",
        "os.path.abspath",
        "os.path.basename",
        "os.path.isabs",
        "os.path.realpath",
        "os.read",
        "os.stat",
        "os.stat_result",
        "os.unlink",
        "os.write",
    },
}

ALLOWED_SYS_ATTRIBUTES: Mapping[str, Set[str]] = {
    "autocapture/addon.py": {
        "sys.modules",
        "sys.path",
        "sys.path.insert",
    },
}

INTERNAL_MODULES = frozenset({"addon", "policy", "lease", "shape", "publisher"})

FORBIDDEN_IMPORT_PREFIXES = (
    "aiohttp",
    "AppKit",
    "asyncio.subprocess",
    "boto",
    "botocore",
    "builtins",
    "certifi",
    "ctypes",
    "cv2",
    "email",
    "ftplib",
    "http",
    "httpx",
    "importlib",
    "inspect",
    "keyring",
    "logging",
    "marshal",
    "mitmproxy",
    "multiprocessing",
    "pickle",
    "playwright",
    "pyautogui",
    "Quartz",
    "requests",
    "selenium",
    "shelve",
    "shutil",
    "signal",
    "smtplib",
    "socket",
    "sqlite3",
    "ssl",
    "subprocess",
    "telnetlib",
    "tkinter",
    "traceback",
    "urllib",
    "webbrowser",
    "websockets",
)

FORBIDDEN_CALL_NAMES = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "eval",
        "exec",
        "globals",
        "input",
        "locals",
        "print",
        "repr",
        "vars",
    }
)

FORBIDDEN_QUALIFIED_CALL_PREFIXES = (
    "importlib.",
    "pickle.",
    "marshal.",
    "subprocess.",
    "socket.",
    "requests.",
    "urllib.",
    "http.",
    "httpx.",
    "aiohttp.",
    "webbrowser.",
)

FORBIDDEN_OS_CALLS = frozenset(
    {
        "os.exec",
        "os.execl",
        "os.execle",
        "os.execlp",
        "os.execlpe",
        "os.execv",
        "os.execve",
        "os.execvp",
        "os.execvpe",
        "os.fork",
        "os.getenv",
        "os.kill",
        "os.popen",
        "os.posix_spawn",
        "os.posix_spawnp",
        "os.spawnl",
        "os.spawnle",
        "os.spawnlp",
        "os.spawnlpe",
        "os.spawnv",
        "os.spawnve",
        "os.spawnvp",
        "os.spawnvpe",
        "os.startfile",
        "os.system",
    }
)

FORBIDDEN_OUTPUT_KEYS = frozenset(
    {
        "authorization",
        "body",
        "body_length",
        "cookie",
        "exception",
        "exception_detail",
        "full_url",
        "header",
        "headers",
        "local_path",
        "neighbor_content",
        "offset",
        "payload",
        "query",
        "raw",
        "raw_content",
        "raw_error",
        "raw_hash",
        "raw_length",
        "raw_payload",
        "raw_value",
        "raw_values",
        "scalar_value",
        "snippet",
        "traceback",
        "url",
        "uri",
        "value",
        "value_hash",
        "values",
    }
)

ALLOWED_RESPONSE_HEADERS = frozenset(
    {
        "content-encoding",
        "content-length",
        "content-type",
    }
)

SENSITIVE_MINIMUM = frozenset(
    {
        "access_token",
        "account_id",
        "api_key",
        "api_secret",
        "authorization",
        "captcha",
        "client_secret",
        "consignee_mobile",
        "consignee_name",
        "consignee_phone",
        "cookie",
        "credential",
        "delivery_address",
        "device_id",
        "home_address",
        "id_card",
        "idcard",
        "open_id",
        "openid",
        "passwd",
        "password",
        "personal_email",
        "receiver_mobile",
        "receiver_name",
        "receiver_phone",
        "recipient_mobile",
        "recipient_name",
        "recipient_phone",
        "refresh_token",
        "secret",
        "secret_key",
        "session",
        "session_id",
        "set_cookie",
        "sms_code",
        "token",
        "union_id",
        "unionid",
        "user_id",
        "verification_code",
    }
)

FORBIDDEN_ARTIFACT_SUFFIXES = (
    ".core",
    ".dump",
    ".har",
    ".pcap",
    ".pcapng",
    ".pyc",
    ".pyo",
    ".raw",
)

FORBIDDEN_ARTIFACT_PARTS = frozenset(
    {
        ".cache",
        "__pycache__",
        "cache",
        "dump",
        "raw",
        "tmp",
        "work",
    }
)

_FLOW = "FLOW"
_REQUEST = "REQUEST"
_REQUEST_METHOD = "REQUEST_METHOD"
_REQUEST_HOST = "REQUEST_HOST"
_REQUEST_PATH = "REQUEST_PATH"
_RESPONSE = "RESPONSE"
_RESPONSE_STATUS = "RESPONSE_STATUS"
_HEADERS = "HEADERS"
_BODY = "BODY"
_FLOW_OBJECT_ROLES = frozenset({_FLOW, _REQUEST, _RESPONSE, _HEADERS})
_CONTAINER_PREFIX = "CONTAINER:"


class VerificationFailure(RuntimeError):
    """Stable verifier failure with no candidate-derived detail."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise VerificationFailure(code)


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath((str(root), str(candidate))) == str(root)
    except (OSError, ValueError):
        return False


def _is_forbidden_artifact(relative: str) -> bool:
    lowered = relative.casefold()
    parts = tuple(part.casefold() for part in Path(relative).parts)
    return any(part in FORBIDDEN_ARTIFACT_PARTS for part in parts) or lowered.endswith(
        FORBIDDEN_ARTIFACT_SUFFIXES
    )


def _assert_root(root: Path) -> Path:
    try:
        absolute = root.absolute()
        metadata = os.lstat(absolute)
        resolved = absolute.resolve(strict=True)
    except (OSError, RuntimeError):
        _fail("REPO_ROOT_INVALID")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("REPO_ROOT_INVALID")
    return resolved


def _classify_link(root: Path, path: Path) -> None:
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError):
        _fail("SYMLINK_FORBIDDEN")
    if not _is_within(root, resolved):
        _fail("SCOPE_ESCAPE")
    _fail("SYMLINK_FORBIDDEN")


def _walk_controlled(root: Path, relative: str) -> Tuple[Set[str], Set[str]]:
    start = root / relative
    try:
        metadata = os.lstat(start)
    except OSError:
        _fail("MISSING_FILE")
    if stat.S_ISLNK(metadata.st_mode):
        _classify_link(root, start)
    if not stat.S_ISDIR(metadata.st_mode):
        _fail("NON_REGULAR_FILE")

    files: Set[str] = set()
    directories: Set[str] = {relative}
    pending: List[Tuple[Path, str]] = [(start, relative)]
    while pending:
        directory, directory_relative = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            _fail("INVENTORY_READ_FAILED")
        for entry in entries:
            child_relative = directory_relative + "/" + entry.name
            try:
                child_metadata = entry.stat(follow_symlinks=False)
            except OSError:
                _fail("INVENTORY_READ_FAILED")
            child = Path(entry.path)
            if stat.S_ISLNK(child_metadata.st_mode):
                _classify_link(root, child)
            if _is_forbidden_artifact(child_relative):
                _fail("FORBIDDEN_ARTIFACT")
            try:
                resolved = child.resolve(strict=True)
            except (OSError, RuntimeError):
                _fail("SCOPE_ESCAPE")
            if not _is_within(root, resolved):
                _fail("SCOPE_ESCAPE")
            if stat.S_ISDIR(child_metadata.st_mode):
                directories.add(child_relative)
                pending.append((child, child_relative))
            elif stat.S_ISREG(child_metadata.st_mode):
                files.add(child_relative)
            else:
                _fail("NON_REGULAR_FILE")
    return files, directories


def _verify_inventory(root: Path, *, require_manifest: bool) -> Set[str]:
    autocapture_files, autocapture_directories = _walk_controlled(root, "autocapture")
    design_files, design_directories = _walk_controlled(root, "docs/design")
    actual_files = autocapture_files | design_files
    actual_directories = autocapture_directories | design_directories

    expected = set(EXPECTED_FILES)
    if not require_manifest:
        expected.discard(MANIFEST_RELATIVE)
        actual_without_manifest = actual_files - {MANIFEST_RELATIVE}
        if actual_without_manifest != expected:
            if expected - actual_without_manifest:
                _fail("MISSING_FILE")
            _fail("EXTRA_FILE")
        if MANIFEST_RELATIVE not in actual_files and actual_files != expected:
            _fail("EXTRA_FILE")
    else:
        if actual_files != expected:
            if expected - actual_files:
                _fail("MISSING_FILE")
            _fail("EXTRA_FILE")

    if actual_directories != set(EXPECTED_DIRECTORIES):
        if set(EXPECTED_DIRECTORIES) - actual_directories:
            _fail("MISSING_FILE")
        _fail("EXTRA_DIRECTORY")
    return actual_files


def _read_regular(root: Path, relative: str, maximum: int = MAX_SOURCE_BYTES) -> bytes:
    path = root / relative
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        _fail("MISSING_FILE")
    if not _is_within(root, resolved):
        _fail("SCOPE_ESCAPE")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor: Optional[int] = None
    try:
        descriptor = os.open(str(path), flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size < 0 or before.st_size > maximum:
            _fail("NON_REGULAR_FILE")
        chunks: List[bytes] = []
        count = 0
        while True:
            chunk = os.read(descriptor, min(65536, maximum + 1 - count))
            if not chunk:
                break
            chunks.append(chunk)
            count += len(chunk)
            if count > maximum:
                _fail("FILE_BUDGET_EXCEEDED")
        after = os.fstat(descriptor)
        before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if before_identity != after_identity or count != after.st_size:
            _fail("FILE_CHANGED_DURING_READ")
        return b"".join(chunks)
    except VerificationFailure:
        raise
    except OSError:
        _fail("FILE_READ_FAILED")
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
    raise AssertionError("unreachable")


def _decode_source(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        _fail("NON_UTF8_SOURCE")
    raise AssertionError("unreachable")


def _parse_python(relative: str, source: str) -> ast.Module:
    try:
        return ast.parse(source, filename=relative, mode="exec")
    except (SyntaxError, ValueError, MemoryError):
        _fail("PYTHON_SYNTAX_INVALID")
    raise AssertionError("unreachable")


def _module_forbidden(module: str) -> bool:
    return any(module == prefix or module.startswith(prefix + ".") for prefix in FORBIDDEN_IMPORT_PREFIXES)


def _attribute_name(node: ast.AST, aliases: Mapping[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = _attribute_name(node.value, aliases)
        return base + "." + node.attr if base else node.attr
    return ""


def _import_aliases(tree: ast.Module) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".", 1)[0]] = item.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            module = node.module or ""
            for item in node.names:
                if item.name != "*":
                    aliases[item.asname or item.name] = module + "." + item.name
    return aliases


def _verify_imports(relative: str, tree: ast.Module) -> None:
    allowed = ALLOWED_IMPORT_ROOTS[relative]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(item.name == "*" for item in node.names):
                _fail("FORBIDDEN_IMPORT")
            modules = [item.name for item in node.names]
        elif isinstance(node, ast.ImportFrom):
            if any(item.name == "*" for item in node.names):
                _fail("FORBIDDEN_IMPORT")
            if node.level:
                if node.level != 1 or (node.module or "") not in INTERNAL_MODULES:
                    _fail("FORBIDDEN_IMPORT")
                continue
            modules = [node.module or ""]
            if (node.module or "").split(".", 1)[0] in {"os", "sys"}:
                _fail("FORBIDDEN_IMPORT")
        else:
            continue
        for module in modules:
            root = module.split(".", 1)[0]
            if root == "autocapture":
                allowed_internal = {"autocapture"} | {
                    "autocapture." + name for name in INTERNAL_MODULES
                }
                if module not in allowed_internal:
                    _fail("FORBIDDEN_IMPORT")
                continue
            if _module_forbidden(module) or root not in allowed:
                _fail("FORBIDDEN_IMPORT")


def _verify_calls(relative: str, tree: ast.Module) -> None:
    aliases = _import_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "__builtins__":
            _fail("FORBIDDEN_CAPABILITY")
        if isinstance(node, ast.Attribute):
            qualified = _attribute_name(node, aliases)
            if qualified == "os.environ" or qualified.endswith(".__dict__") or qualified.endswith(
                ".__globals__"
            ):
                _fail("FORBIDDEN_CAPABILITY")
            if qualified.startswith("os.") and qualified not in ALLOWED_OS_ATTRIBUTES.get(
                relative, set()
            ):
                _fail("FORBIDDEN_CAPABILITY")
            if qualified.startswith("sys.") and qualified not in ALLOWED_SYS_ATTRIBUTES.get(
                relative, set()
            ):
                _fail("FORBIDDEN_CAPABILITY")
            if qualified in FORBIDDEN_OS_CALLS:
                _fail("FORBIDDEN_CAPABILITY")
            if node.attr in {
                "__builtins__",
                "__class__",
                "__getattribute__",
                "__import__",
                "__subclasses__",
            }:
                _fail("FORBIDDEN_CAPABILITY")
        if not isinstance(node, ast.Call):
            continue
        qualified = _attribute_name(node.func, aliases)
        simple = node.func.id if isinstance(node.func, ast.Name) else ""
        if isinstance(node.func, ast.Subscript):
            dynamic_name = _constant_header(node.func.slice)
            if dynamic_name in FORBIDDEN_CALL_NAMES | {"open"}:
                _fail("FORBIDDEN_CAPABILITY")
        if simple in FORBIDDEN_CALL_NAMES:
            _fail("FORBIDDEN_CAPABILITY")
        if simple == "getattr":
            if len(node.args) < 2:
                _fail("FORBIDDEN_CAPABILITY")
            base = _attribute_name(node.args[0], aliases)
            attribute = _constant_header(node.args[1])
            safe_getattr = (
                relative == "autocapture/addon.py"
                and base == "publisher"
                and attribute == "publish"
                and len(node.args) == 3
                and not node.keywords
            ) or (
                relative == "autocapture/publisher.py"
                and base == "os"
                and attribute == "o_cloexec"
                and len(node.args) == 3
                and not node.keywords
            )
            if not safe_getattr:
                _fail("FORBIDDEN_CAPABILITY")
        if simple in {"delattr", "setattr"}:
            _fail("FORBIDDEN_CAPABILITY")
        if any(qualified.startswith(prefix) for prefix in FORBIDDEN_QUALIFIED_CALL_PREFIXES):
            _fail("FORBIDDEN_CAPABILITY")
        if qualified in FORBIDDEN_OS_CALLS:
            _fail("FORBIDDEN_CAPABILITY")
        if simple == "open":
            _fail("FORBIDDEN_CAPABILITY")
        if qualified.startswith("pathlib.Path.") and qualified.rsplit(".", 1)[-1] in {
            "open",
            "read_bytes",
            "read_text",
            "replace",
            "rename",
            "rmdir",
            "unlink",
            "write_bytes",
            "write_text",
        }:
            _fail("FORBIDDEN_CAPABILITY")


def _static_string(node: ast.AST, constants: Mapping[str, str]) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_string(node.left, constants)
        right = _static_string(node.right, constants)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts: List[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                formatted = _static_string(value.value, constants)
                if formatted is None:
                    return None
                parts.append(formatted)
            else:
                return None
        return "".join(parts)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "join"
        and len(node.args) == 1
        and not node.keywords
    ):
        separator = _static_string(node.func.value, constants)
        values = node.args[0]
        if separator is not None and isinstance(values, (ast.List, ast.Tuple)):
            parts = [_static_string(item, constants) for item in values.elts]
            if all(part is not None for part in parts):
                return separator.join(part for part in parts if part is not None)
    return None


def _static_string_bindings(tree: ast.Module) -> Mapping[str, str]:
    constants: Dict[str, str] = {}
    ambiguous: Set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            target: Optional[ast.AST] = None
            value: Optional[ast.AST] = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                value = node.value
            elif isinstance(node, ast.AnnAssign):
                target = node.target
                value = node.value
            if not isinstance(target, ast.Name) or value is None or target.id in ambiguous:
                continue
            result = _static_string(value, constants)
            if result is None:
                continue
            existing = constants.get(target.id)
            if existing is None:
                constants[target.id] = result
                changed = True
            elif existing != result:
                constants.pop(target.id, None)
                ambiguous.add(target.id)
                changed = True
    return constants


def _literal_output_keys(relative: str, tree: ast.Module) -> Iterable[str]:
    constants = _static_string_bindings(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if key is None:
                    _fail("FORBIDDEN_OUTPUT_KEY")
                value = _static_string(key, constants)
                if value is None:
                    _fail("FORBIDDEN_OUTPUT_KEY")
                yield value
        elif isinstance(node, ast.DictComp):
            _fail("FORBIDDEN_OUTPUT_KEY")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
            allowed_copy = (
                relative == "autocapture/shape.py"
                and len(node.args) == 1
                and not node.keywords
                and _attribute_name(node.args[0], {}) == "self._nodes"
            )
            if (node.args or any(keyword.arg is None for keyword in node.keywords)) and not allowed_copy:
                _fail("FORBIDDEN_OUTPUT_KEY")
            for keyword in node.keywords:
                if keyword.arg is not None:
                    yield keyword.arg
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, (ast.Store, ast.Del)):
            value = _static_string(node.slice, constants)
            if value is not None:
                yield value
            elif (
                isinstance(node.slice, ast.Constant)
                and not isinstance(node.slice.value, str)
            ):
                continue
            elif not isinstance(node.slice, (ast.Name, ast.Attribute)):
                _fail("FORBIDDEN_OUTPUT_KEY")


def _key_forbidden(value: str) -> bool:
    normalized = value.strip().casefold().replace("-", "_")
    if normalized in FORBIDDEN_OUTPUT_KEYS:
        return True
    tokens = tuple(token for token in normalized.split("_") if token)
    if "raw" in tokens or "header" in tokens or "headers" in tokens:
        return True
    if normalized.endswith("_url") or normalized.startswith("url_"):
        return True
    return False


def _verify_output_keys(relative: str, tree: ast.Module) -> None:
    for key in _literal_output_keys(relative, tree):
        if _key_forbidden(key):
            _fail("FORBIDDEN_OUTPUT_KEY")


def _raise_code(statement: ast.AST) -> Optional[str]:
    if not isinstance(statement, ast.Raise) or not isinstance(statement.exc, ast.Call):
        return None
    if _attribute_name(statement.exc.func, {}) != "RuntimeError" or len(statement.exc.args) != 1:
        return None
    value = statement.exc.args[0]
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _verify_addon_bootstrap(tree: ast.Module) -> None:
    assignments: Dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                assignments[target.id] = node.value
    required_assignments = {
        "_script_path": ("os.path.realpath", "__file__"),
        "_package_dir": ("os.path.dirname", "_script_path"),
        "_candidate_root": ("os.path.dirname", "_package_dir"),
    }
    for name, (call_name, argument_name) in required_assignments.items():
        value = assignments.get(name)
        if (
            not isinstance(value, ast.Call)
            or _attribute_name(value.func, {}) != call_name
            or len(value.args) != 1
            or _attribute_name(value.args[0], {}) != argument_name
            or value.keywords
        ):
            _fail("ADDON_BOOTSTRAP_INVALID")
    bootstrap_value = assignments.get("_bootstrap_root")
    if not isinstance(bootstrap_value, ast.Constant) or bootstrap_value.value is not None:
        _fail("ADDON_BOOTSTRAP_INVALID")

    bootstrap_ifs = [
        node
        for node in tree.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and _attribute_name(node.test.operand, {}) == "__package__"
    ]
    if len(bootstrap_ifs) != 1:
        _fail("ADDON_BOOTSTRAP_INVALID")
    bootstrap_if = bootstrap_ifs[0]
    if not any(
        isinstance(node, ast.If)
        and any(_raise_code(statement) == "ADDON_LOCATION_INVALID" for statement in node.body)
        for node in bootstrap_if.body
    ):
        _fail("ADDON_BOOTSTRAP_INVALID")
    membership_gates = [
        node
        for node in bootstrap_if.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and len(node.test.ops) == 1
        and isinstance(node.test.ops[0], ast.NotIn)
        and _attribute_name(node.test.left, {}) == "_candidate_root"
        and len(node.test.comparators) == 1
        and _attribute_name(node.test.comparators[0], {}) == "sys.path"
    ]
    if len(membership_gates) != 1:
        _fail("ADDON_BOOTSTRAP_INVALID")

    insert_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _attribute_name(node.func, {}) == "sys.path.insert"
    ]
    if len(insert_calls) != 1:
        _fail("ADDON_BOOTSTRAP_INVALID")
    insert_call = insert_calls[0]
    if (
        len(insert_call.args) != 2
        or insert_call.keywords
        or not isinstance(insert_call.args[0], ast.Constant)
        or insert_call.args[0].value != 0
        or _attribute_name(insert_call.args[1], {}) != "_candidate_root"
        or all(insert_call is not node for node in ast.walk(membership_gates[0]))
    ):
        _fail("ADDON_BOOTSTRAP_INVALID")

    top_level_tries = [node for node in tree.body if isinstance(node, ast.Try)]
    if len(top_level_tries) != 1:
        _fail("ADDON_BOOTSTRAP_INVALID")
    bootstrap_try = top_level_tries[0]
    imported_modules = {
        node.module
        for node in bootstrap_try.body
        if isinstance(node, ast.ImportFrom)
    }
    if imported_modules != {
        "autocapture.lease",
        "autocapture.policy",
        "autocapture.shape",
    }:
        _fail("ADDON_BOOTSTRAP_INVALID")

    origin_ifs = [
        node
        for node in bootstrap_try.body
        if isinstance(node, ast.If)
        and any(
            _raise_code(statement) == "ADDON_IMPORT_ORIGIN_INVALID"
            for statement in node.body
        )
    ]
    if len(origin_ifs) != 1 or not isinstance(origin_ifs[0].test, ast.BoolOp):
        _fail("ADDON_BOOTSTRAP_INVALID")
    origin_test = origin_ifs[0].test
    if not isinstance(origin_test.op, ast.Or) or len(origin_test.values) != 3:
        _fail("ADDON_BOOTSTRAP_INVALID")
    expected_origins = {
        "CapturePolicy": "policy.py",
        "RawLease": "lease.py",
        "ShapeAccumulator": "shape.py",
    }
    observed_origins: Dict[str, str] = {}
    for comparison in origin_test.values:
        if (
            not isinstance(comparison, ast.Compare)
            or len(comparison.ops) != 1
            or not isinstance(comparison.ops[0], ast.NotEq)
            or len(comparison.comparators) != 1
            or not isinstance(comparison.left, ast.Call)
            or _attribute_name(comparison.left.func, {}) != "os.path.realpath"
            or len(comparison.left.args) != 1
            or not isinstance(comparison.comparators[0], ast.Call)
            or _attribute_name(comparison.comparators[0].func, {}) != "os.path.join"
            or len(comparison.comparators[0].args) != 2
            or _attribute_name(comparison.comparators[0].args[0], {}) != "_package_dir"
            or not isinstance(comparison.comparators[0].args[1], ast.Constant)
            or not isinstance(comparison.comparators[0].args[1].value, str)
        ):
            _fail("ADDON_BOOTSTRAP_INVALID")
        origin_argument = comparison.left.args[0]
        if (
            not isinstance(origin_argument, ast.Attribute)
            or origin_argument.attr != "__file__"
            or not isinstance(origin_argument.value, ast.Subscript)
            or _attribute_name(origin_argument.value.value, {}) != "sys.modules"
            or not isinstance(origin_argument.value.slice, ast.Attribute)
            or origin_argument.value.slice.attr != "__module__"
            or not isinstance(origin_argument.value.slice.value, ast.Name)
        ):
            _fail("ADDON_BOOTSTRAP_INVALID")
        observed_origins[origin_argument.value.slice.value.id] = comparison.comparators[0].args[
            1
        ].value
    if observed_origins != expected_origins:
        _fail("ADDON_BOOTSTRAP_INVALID")

    path_deletes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.ctx, ast.Del)
        and _attribute_name(node.value, {}) == "sys.path"
    ]
    cleanup_if = bootstrap_try.finalbody[0] if len(bootstrap_try.finalbody) == 1 else None
    state_if = (
        cleanup_if.body[0]
        if isinstance(cleanup_if, ast.If) and len(cleanup_if.body) == 2
        else None
    )
    path_delete_statement = (
        cleanup_if.body[1]
        if isinstance(cleanup_if, ast.If) and len(cleanup_if.body) == 2
        else None
    )
    cleanup_test = cleanup_if.test if isinstance(cleanup_if, ast.If) else None
    state_test = state_if.test if isinstance(state_if, ast.If) else None
    if (
        len(path_deletes) != 1
        or not isinstance(path_deletes[0].slice, ast.Constant)
        or path_deletes[0].slice.value != 0
        or not isinstance(cleanup_if, ast.If)
        or cleanup_if.orelse
        or not isinstance(cleanup_test, ast.Compare)
        or _attribute_name(cleanup_test.left, {}) != "_bootstrap_root"
        or len(cleanup_test.ops) != 1
        or not isinstance(cleanup_test.ops[0], ast.IsNot)
        or len(cleanup_test.comparators) != 1
        or not isinstance(cleanup_test.comparators[0], ast.Constant)
        or cleanup_test.comparators[0].value is not None
        or not isinstance(state_if, ast.If)
        or state_if.orelse
        or len(state_if.body) != 1
        or _raise_code(state_if.body[0]) != "ADDON_BOOTSTRAP_STATE_INVALID"
        or not isinstance(state_test, ast.BoolOp)
        or not isinstance(state_test.op, ast.Or)
        or len(state_test.values) != 2
        or not isinstance(state_test.values[0], ast.UnaryOp)
        or not isinstance(state_test.values[0].op, ast.Not)
        or _attribute_name(state_test.values[0].operand, {}) != "sys.path"
        or not isinstance(state_test.values[1], ast.Compare)
        or len(state_test.values[1].ops) != 1
        or not isinstance(state_test.values[1].ops[0], ast.NotEq)
        or len(state_test.values[1].comparators) != 1
        or _attribute_name(state_test.values[1].comparators[0], {}) != "_bootstrap_root"
        or not isinstance(state_test.values[1].left, ast.Subscript)
        or _attribute_name(state_test.values[1].left.value, {}) != "sys.path"
        or not isinstance(state_test.values[1].left.slice, ast.Constant)
        or state_test.values[1].left.slice.value != 0
        or not isinstance(path_delete_statement, ast.Delete)
        or len(path_delete_statement.targets) != 1
        or path_delete_statement.targets[0] is not path_deletes[0]
    ):
        _fail("ADDON_BOOTSTRAP_INVALID")

    other_path_mutations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _attribute_name(node.func, {}).startswith("sys.path.")
        and node is not insert_call
    ]
    if other_path_mutations:
        _fail("ADDON_BOOTSTRAP_INVALID")


def _assigned_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    return None


def _literal_string_collection(node: ast.AST) -> Optional[Set[str]]:
    value = node
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in {"frozenset", "set", "tuple"}
        and len(value.args) == 1
        and not value.keywords
    ):
        value = value.args[0]
    if not isinstance(value, (ast.List, ast.Set, ast.Tuple)):
        return None
    result: Set[str] = set()
    for element in value.elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            return None
        result.add(element.value.strip().casefold())
    return result


def _literal_string_sequences(node: ast.AST) -> Optional[Set[Tuple[str, ...]]]:
    value = node
    if not isinstance(value, (ast.List, ast.Set, ast.Tuple)):
        return None
    result: Set[Tuple[str, ...]] = set()
    for element in value.elts:
        if not isinstance(element, (ast.List, ast.Tuple)):
            return None
        sequence: List[str] = []
        for item in element.elts:
            if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                return None
            sequence.append(item.value.strip().casefold())
        if not sequence:
            return None
        result.add(tuple(sequence))
    return result


def _without_docstring(function: ast.AST) -> List[ast.AST]:
    statements = list(getattr(function, "body", ()))
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    return statements


def _verify_regex_normalization_pipeline(
    function: ast.AST,
    input_name: str,
    *,
    tuple_output: bool,
) -> None:
    statements = _without_docstring(function)
    if len(statements) != 6:
        _fail("SENSITIVE_RULE_INVALID")

    expected_substitutions = (
        ("_ACRONYM_BOUNDARY.sub", input_name),
        ("_CAMEL_BOUNDARY.sub", "separated"),
        ("_LETTER_DIGIT_BOUNDARY.sub", "separated"),
        ("_DIGIT_LETTER_BOUNDARY.sub", "separated"),
    )
    for statement, (call_name, argument_name) in zip(
        statements[:4],
        expected_substitutions,
    ):
        if (
            not isinstance(statement, ast.Assign)
            or len(statement.targets) != 1
            or _attribute_name(statement.targets[0], {}) != "separated"
            or not isinstance(statement.value, ast.Call)
            or _attribute_name(statement.value.func, {}) != call_name
            or len(statement.value.args) != 2
            or statement.value.keywords
            or not isinstance(statement.value.args[0], ast.Constant)
            or statement.value.args[0].value != "\\1_\\2"
            or _attribute_name(statement.value.args[1], {}) != argument_name
        ):
            _fail("SENSITIVE_RULE_INVALID")

    lowered, returned = statements[4:]
    if (
        not isinstance(lowered, ast.Assign)
        or len(lowered.targets) != 1
        or not isinstance(lowered.targets[0], ast.Name)
        or lowered.targets[0].id != "lowered"
        or not isinstance(lowered.value, ast.Call)
        or _attribute_name(lowered.value.func, {}) != "separated.casefold"
        or lowered.value.args
        or lowered.value.keywords
    ):
        _fail("SENSITIVE_RULE_INVALID")
    if not isinstance(returned, ast.Return) or returned.value is None:
        _fail("SENSITIVE_RULE_INVALID")
    if tuple_output:
        tuple_call = returned.value
        if (
            not isinstance(tuple_call, ast.Call)
            or _attribute_name(tuple_call.func, {}) != "tuple"
            or len(tuple_call.args) != 1
            or tuple_call.keywords
            or not isinstance(tuple_call.args[0], ast.GeneratorExp)
        ):
            _fail("SENSITIVE_RULE_INVALID")
        generator = tuple_call.args[0]
        if (
            _attribute_name(generator.elt, {}) != "token"
            or len(generator.generators) != 1
            or generator.generators[0].is_async
            or _attribute_name(generator.generators[0].target, {}) != "token"
            or len(generator.generators[0].ifs) != 1
            or _attribute_name(generator.generators[0].ifs[0], {}) != "token"
            or not isinstance(generator.generators[0].iter, ast.Call)
            or _attribute_name(generator.generators[0].iter.func, {})
            != "_NON_TOKEN.split"
            or len(generator.generators[0].iter.args) != 1
            or generator.generators[0].iter.keywords
            or _attribute_name(generator.generators[0].iter.args[0], {}) != "lowered"
        ):
            _fail("SENSITIVE_RULE_INVALID")
    else:
        strip_call = returned.value
        if (
            not isinstance(strip_call, ast.Call)
            or not isinstance(strip_call.func, ast.Attribute)
            or strip_call.func.attr != "strip"
            or len(strip_call.args) != 1
            or strip_call.keywords
            or not isinstance(strip_call.args[0], ast.Constant)
            or strip_call.args[0].value != "_"
            or not isinstance(strip_call.func.value, ast.Call)
        ):
            _fail("SENSITIVE_RULE_INVALID")
        substitute = strip_call.func.value
        if (
            _attribute_name(substitute.func, {}) != "_NON_TOKEN.sub"
            or len(substitute.args) != 2
            or substitute.keywords
            or not isinstance(substitute.args[0], ast.Constant)
            or substitute.args[0].value != "_"
            or _attribute_name(substitute.args[1], {}) != "lowered"
        ):
            _fail("SENSITIVE_RULE_INVALID")


def _verify_shape_normalizer(tree: ast.Module) -> None:
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"_normalized_words", "normalize_sensitive_key"}
    }
    if set(functions) != {"_normalized_words", "normalize_sensitive_key"}:
        _fail("SENSITIVE_RULE_INVALID")
    _verify_regex_normalization_pipeline(
        functions["normalize_sensitive_key"],
        "key",
        tuple_output=False,
    )
    _verify_regex_normalization_pipeline(
        functions["_normalized_words"],
        "value",
        tuple_output=True,
    )


def _returns_constant(statement: ast.AST, value: bool) -> bool:
    return (
        isinstance(statement, ast.Return)
        and isinstance(statement.value, ast.Constant)
        and statement.value.value is value
    )


def _verify_shape_sensitive_classifier(tree: ast.Module) -> None:
    literal_sets: Dict[str, Set[str]] = {}
    literal_sequences: Optional[Set[Tuple[str, ...]]] = None
    singular_words: Optional[Dict[str, str]] = None
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        for target in targets:
            if not isinstance(target, ast.Name) or value is None:
                continue
            if target.id in {
                "_SENSITIVE_SCHEMA_COLLAPSED_FRAGMENTS",
                "_SENSITIVE_SCHEMA_VERSION_ANCHORS",
                "_SENSITIVE_SCHEMA_WORDS",
            }:
                candidate = _literal_string_collection(value)
                if candidate is None:
                    _fail("SENSITIVE_RULE_INVALID")
                literal_sets[target.id] = candidate
            elif target.id == "_SENSITIVE_SCHEMA_SEQUENCES":
                literal_sequences = _literal_string_sequences(value)
                if literal_sequences is None:
                    _fail("SENSITIVE_RULE_INVALID")
            elif target.id == "_SENSITIVE_SCHEMA_SINGULAR_WORDS":
                if not isinstance(value, ast.Dict):
                    _fail("SENSITIVE_RULE_INVALID")
                parsed: Dict[str, str] = {}
                for key, item in zip(value.keys, value.values):
                    if (
                        not isinstance(key, ast.Constant)
                        or not isinstance(key.value, str)
                        or not isinstance(item, ast.Constant)
                        or not isinstance(item.value, str)
                    ):
                        _fail("SENSITIVE_RULE_INVALID")
                    parsed[key.value.strip().casefold()] = item.value.strip().casefold()
                singular_words = parsed

    word_minimum = {
        "authorization",
        "captcha",
        "cookie",
        "credential",
        "credentials",
        "header",
        "headers",
        "openid",
        "passwd",
        "password",
        "raw",
        "secret",
        "session",
        "snippet",
        "token",
        "traceback",
        "unionid",
        "uid",
        "uuid",
        "guid",
    }
    sequence_minimum = {
        tuple(value.split("_"))
        for value in SENSITIVE_MINIMUM
        if "_" in value and value != "secret_key"
    } | {
        ("access", "key"),
        ("private", "key"),
        ("value", "hash"),
        ("otp", "code"),
        ("oauth", "code"),
        ("sess", "id"),
        ("user", "guid"),
        ("user", "uid"),
        ("user", "uuid"),
        ("device", "guid"),
        ("device", "uid"),
        ("device", "uuid"),
        ("recipient", "tel"),
        ("receiver", "tel"),
        ("consignee", "tel"),
    }
    collapsed_minimum = {
        value.replace("_", "")
        for value in SENSITIVE_MINIMUM
        if value not in {"secret_key", "session_id"}
    } | {
        "accesskey",
        "neighborcontent",
        "oauthcode",
        "privatekey",
        "pwd",
        "rawerror",
        "rawpayload",
        "rawvalue",
        "sessid",
        "snippet",
        "traceback",
        "valuehash",
    }
    singular_minimum = {
        "addresses": "address",
        "cards": "card",
        "codes": "code",
        "cookies": "cookie",
        "credentials": "credential",
        "emails": "email",
        "guids": "guid",
        "ids": "id",
        "keys": "key",
        "mobiles": "mobile",
        "names": "name",
        "passwords": "password",
        "phones": "phone",
        "secrets": "secret",
        "sessions": "session",
        "tels": "tel",
        "tokens": "token",
        "uids": "uid",
        "uuids": "uuid",
    }
    version_anchor_minimum = {
        "account",
        "api",
        "client",
        "consignee",
        "delivery",
        "device",
        "home",
        "open",
        "personal",
        "receiver",
        "recipient",
        "union",
        "user",
        "verification",
    }
    if (
        set(literal_sets) != {
            "_SENSITIVE_SCHEMA_COLLAPSED_FRAGMENTS",
            "_SENSITIVE_SCHEMA_VERSION_ANCHORS",
            "_SENSITIVE_SCHEMA_WORDS",
        }
        or not word_minimum.issubset(literal_sets["_SENSITIVE_SCHEMA_WORDS"])
        or not collapsed_minimum.issubset(
            literal_sets["_SENSITIVE_SCHEMA_COLLAPSED_FRAGMENTS"]
        )
        or literal_sequences is None
        or not sequence_minimum.issubset(literal_sequences)
        or singular_words is None
        or any(
            singular_words.get(plural) != singular
            for plural, singular in singular_minimum.items()
        )
        or not version_anchor_minimum.issubset(
            literal_sets["_SENSITIVE_SCHEMA_VERSION_ANCHORS"]
        )
    ):
        _fail("SENSITIVE_RULE_INCOMPLETE")

    classifiers = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_schema_key_has_sensitive_semantics"
    ]
    four_state_classifiers = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "classify_schema_key"
    ]
    if len(classifiers) != 1 or len(four_state_classifiers) != 1:
        _fail("SENSITIVE_RULE_INVALID")

    classifier = classifiers[0]
    statements = _without_docstring(classifier)
    if not statements or not _returns_constant(statements[-1], False):
        _fail("SENSITIVE_RULE_INVALID")
    nodes = list(_function_nodes(classifier))
    true_gates = [
        node
        for node in nodes
        if isinstance(node, ast.If)
        and len(node.body) == 1
        and _returns_constant(node.body[0], True)
    ]

    def gate_mentions(*names: str) -> bool:
        return any(
            all(
                any(
                    _attribute_name(child, {}) == name
                    for child in ast.walk(gate.test)
                    if isinstance(child, (ast.Name, ast.Attribute))
                )
                for name in names
            )
            for gate in true_gates
        )

    collapsed_assignments = [
        node
        for node in statements
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and _attribute_name(node.targets[0], {}) == "collapsed_letters"
    ]
    classifier_names = {
        _attribute_name(node, {})
        for node in nodes
        if isinstance(node, (ast.Name, ast.Attribute))
    }
    word_loops = [
        node
        for node in nodes
        if isinstance(node, ast.For)
        and _attribute_name(node.target, {}) == "word"
        and isinstance(node.iter, ast.Call)
        and _attribute_name(node.iter.func, {}) == "_normalized_words"
        and len(node.iter.args) == 1
        and not node.iter.keywords
        and _attribute_name(node.iter.args[0], {}) == "key"
    ]
    words_list_assignments = [
        node
        for node in statements
        if isinstance(node, ast.AnnAssign)
        and _attribute_name(node.target, {}) == "words_list"
        and isinstance(node.value, ast.List)
        and not node.value.elts
    ]
    word_loop_nodes = (
        list(
            _function_nodes(
                ast.Module(body=[word_loops[0]], type_ignores=[])
            )
        )
        if len(word_loops) == 1
        else []
    )
    word_loop_names = {
        _attribute_name(node, {})
        for node in word_loop_nodes
        if isinstance(node, (ast.Name, ast.Attribute))
    }
    canonical_assignments = [
        node
        for node in word_loop_nodes
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and _attribute_name(node.targets[0], {}) == "canonical"
        and isinstance(node.value, ast.Call)
        and _attribute_name(node.value.func, {})
        == "_SENSITIVE_SCHEMA_SINGULAR_WORDS.get"
        and len(node.value.args) == 2
        and not node.value.keywords
        and all(_attribute_name(argument, {}) == "word" for argument in node.value.args)
    ]
    words_assignments = [
        node
        for node in statements
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and _attribute_name(node.targets[0], {}) == "words"
        and isinstance(node.value, ast.Call)
        and _attribute_name(node.value.func, {}) == "tuple"
        and len(node.value.args) == 1
        and not node.value.keywords
        and _attribute_name(node.value.args[0], {}) == "words_list"
    ]
    sequence_loops = [
        node
        for node in nodes
        if isinstance(node, ast.For)
        and _attribute_name(node.target, {}) == "sequence"
        and _attribute_name(node.iter, {}) == "_SENSITIVE_SCHEMA_SEQUENCES"
    ]
    sequence_loop_nodes = (
        list(
            _function_nodes(
                ast.Module(body=[sequence_loops[0]], type_ignores=[])
            )
        )
        if len(sequence_loops) == 1
        else []
    )
    has_cursor_start = any(
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and _attribute_name(node.targets[0], {}) == "cursor"
        and isinstance(node.value, ast.Constant)
        and node.value.value == 0
        for node in sequence_loop_nodes
    )
    has_ordered_advance = any(
        isinstance(node, ast.AugAssign)
        and _attribute_name(node.target, {}) == "cursor"
        and isinstance(node.op, ast.Add)
        and isinstance(node.value, ast.Constant)
        and node.value.value == 1
        for node in sequence_loop_nodes
    )
    has_word_scan = any(
        isinstance(node, ast.For)
        and _attribute_name(node.target, {}) == "word"
        and _attribute_name(node.iter, {}) == "words"
        for node in sequence_loop_nodes
    )
    has_sequence_index = any(
        isinstance(node, ast.Subscript)
        and _attribute_name(node.value, {}) == "sequence"
        and _attribute_name(node.slice, {}) == "cursor"
        for node in sequence_loop_nodes
    )
    has_sequence_completion = any(
        isinstance(node, ast.Compare)
        and _attribute_name(node.left, {}) == "cursor"
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.Eq)
        and len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Call)
        and _attribute_name(node.comparators[0].func, {}) == "len"
        and len(node.comparators[0].args) == 1
        and _attribute_name(node.comparators[0].args[0], {}) == "sequence"
        for node in sequence_loop_nodes
    )
    if (
        len(collapsed_assignments) != 1
        or not isinstance(collapsed_assignments[0].value, ast.Call)
        or _attribute_name(collapsed_assignments[0].value.func, {}) != "join"
        or len(words_list_assignments) != 1
        or len(word_loops) != 1
        or len(canonical_assignments) != 1
        or not {
            "_SENSITIVE_SCHEMA_VERSION_ANCHORS",
            "canonical.endswith",
            "canonical.isdigit",
            "words_list.append",
            "words_list.extend",
        }.issubset(word_loop_names)
        or len(words_assignments) != 1
        or len(sequence_loops) != 1
        or not has_cursor_start
        or not has_ordered_advance
        or not has_word_scan
        or not has_sequence_index
        or not has_sequence_completion
        or not gate_mentions("_is_sensitive_sentinel")
        or not gate_mentions(
            "collapsed_letters",
            "_SENSITIVE_SCHEMA_COLLAPSED_FRAGMENTS",
        )
        or not gate_mentions(
            "_SYNTHETIC_SENTINEL_WORDS.issubset",
            "word_set",
        )
        or not gate_mentions("normalize_sensitive_key", "SENSITIVE_KEY_TOKENS")
        or not gate_mentions("word_set.intersection", "_SENSITIVE_SCHEMA_WORDS")
        or "_SENSITIVE_SCHEMA_SEQUENCES" not in classifier_names
        or len(true_gates) < 6
    ):
        _fail("SENSITIVE_RULE_INVALID")

    four_state = four_state_classifiers[0]
    constants: Dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if (
            len(targets) == 1
            and isinstance(targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            constants[targets[0].id] = node.value.value
    if {
        "SENSITIVE": "SENSITIVE",
        "REGISTERED_SAFE": "REGISTERED_SAFE",
        "SAFE_UNREGISTERED": "SAFE_UNREGISTERED",
        "TRUE_UNKNOWN": "TRUE_UNKNOWN",
    }.items() - constants.items():
        _fail("SENSITIVE_RULE_INVALID")

    four_statements = _without_docstring(four_state)
    four_nodes = list(_function_nodes(four_state))
    sensitive_positions = [
        index
        for index, statement in enumerate(four_statements)
        if isinstance(statement, ast.If)
        and any(
            isinstance(child, ast.Call)
            and _attribute_name(child.func, {})
            == "_schema_key_has_sensitive_semantics"
            and len(child.args) == 1
            and _attribute_name(child.args[0], {}) == "key"
            for child in ast.walk(statement.test)
        )
        and len(statement.body) == 1
        and isinstance(statement.body[0], ast.Return)
        and _attribute_name(statement.body[0].value, {}) == "SENSITIVE"
    ]
    structure_positions = [
        index
        for index, statement in enumerate(four_statements)
        if isinstance(statement, ast.If)
        and any(
            isinstance(child, ast.Call)
            and _attribute_name(child.func, {})
            == "_has_conservative_schema_key_structure"
            and len(child.args) == 1
            and _attribute_name(child.args[0], {}) == "key"
            for child in ast.walk(statement.test)
        )
    ]
    returns = [
        _attribute_name(node.value, {})
        for node in four_nodes
        if isinstance(node, ast.Return)
    ]
    names = {
        _attribute_name(node, {})
        for node in four_nodes
        if isinstance(node, (ast.Name, ast.Attribute))
    }
    if (
        len(sensitive_positions) != 1
        or len(structure_positions) != 1
        or sensitive_positions[0] >= structure_positions[0]
        or returns.count("SENSITIVE") != 1
        or returns.count("REGISTERED_SAFE") != 1
        or returns.count("SAFE_UNREGISTERED") != 1
        or returns.count("TRUE_UNKNOWN") < 2
        or not {
            "_schema_key_has_sensitive_semantics",
            "_has_conservative_schema_key_structure",
            "registered_schema_keys",
            "frozenset",
        }.issubset(names)
    ):
        _fail("SENSITIVE_RULE_INVALID")


def _class_method(tree: ast.Module, class_name: str, method_name: str) -> ast.AST:
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    if len(classes) != 1:
        _fail("SENSITIVE_RULE_INVALID")
    methods = [
        node
        for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == method_name
    ]
    if len(methods) != 1:
        _fail("SENSITIVE_RULE_INVALID")
    return methods[0]


def _module_function(tree: ast.Module, function_name: str) -> ast.AST:
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(functions) != 1:
        _fail("SENSITIVE_RULE_INVALID")
    return functions[0]


def _verify_unique_schema_key_classifier(trees: Mapping[str, ast.Module]) -> None:
    """Require every production key decision to use shape's one classifier."""

    shape_tree = trees["autocapture/shape.py"]
    policy_tree = trees["autocapture/policy.py"]
    publisher_tree = trees["autocapture/publisher.py"]
    classifier_definitions = [
        (relative, node)
        for relative in PRODUCTION_FILES
        for node in ast.walk(trees[relative])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "classify_schema_key"
    ]
    if len(classifier_definitions) != 1 or classifier_definitions[0][0] != "autocapture/shape.py":
        _fail("SENSITIVE_RULE_INVALID")

    for tree, required_imports in (
        (policy_tree, {"REGISTERED_SAFE", "classify_schema_key"}),
        (
            publisher_tree,
            {
                "REGISTERED_SAFE",
                "SAFE_UNREGISTERED",
                "SanitizedShape",
                "classify_schema_key",
            },
        ),
    ):
        imports = [
            node
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "autocapture.shape"
        ]
        if len(imports) != 1 or {item.name for item in imports[0].names} != required_imports:
            _fail("SENSITIVE_RULE_INVALID")

    duplicate_names = {
        "schema_key_is_allowed_control",
        "_has_sensitive_words",
        "_identifier_words",
        "_is_conservative_schema_identifier",
    }
    for tree in (policy_tree, publisher_tree):
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in duplicate_names
            for node in tree.body
        ):
            _fail("SENSITIVE_RULE_INVALID")

    expected_owners = (
        (policy_tree, _class_method(policy_tree, "CapturePolicy", "validated"), 1),
        (shape_tree, _class_method(shape_tree, "SanitizedShape", "validate"), 2),
        (shape_tree, _class_method(shape_tree, "ShapeAccumulator", "__init__"), 1),
        (shape_tree, _class_method(shape_tree, "ShapeAccumulator", "stage_json_bytes"), 1),
        (publisher_tree, _module_function(publisher_tree, "_valid_pointer"), 1),
        (publisher_tree, _class_method(publisher_tree, "AtomicShapePublisher", "__init__"), 1),
    )
    all_calls: Set[int] = set()
    for tree, owner, expected_count in expected_owners:
        aliases = _import_aliases(tree)
        qualified = (
            "classify_schema_key"
            if tree is shape_tree
            else "autocapture.shape.classify_schema_key"
        )
        calls = [
            node
            for node in _function_nodes(owner)
            if isinstance(node, ast.Call)
            and _attribute_name(node.func, aliases) == qualified
            and len(node.args) == 2
            and not node.keywords
        ]
        if len(calls) != expected_count:
            _fail("SENSITIVE_RULE_UNUSED")
        all_calls.update(id(call) for call in calls)

    for tree in (policy_tree, shape_tree, publisher_tree):
        aliases = _import_aliases(tree)
        qualified = (
            "classify_schema_key"
            if tree is shape_tree
            else "autocapture.shape.classify_schema_key"
        )
        discovered = {
            id(node)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and _attribute_name(node.func, aliases) == qualified
        }
        if not discovered.issubset(all_calls):
            _fail("SENSITIVE_RULE_UNUSED")

    def has_live_classifier_decision(
        tree: ast.Module,
        owner: ast.AST,
        operator: type,
        states: Set[str],
    ) -> bool:
        aliases = _import_aliases(tree)
        qualified = (
            "classify_schema_key"
            if tree is shape_tree
            else "autocapture.shape.classify_schema_key"
        )
        for node in _function_nodes(owner):
            if (
                not isinstance(node, ast.Compare)
                or not isinstance(node.left, ast.Call)
                or _attribute_name(node.left.func, aliases) != qualified
                or len(node.left.args) != 2
                or node.left.keywords
                or len(node.ops) != 1
                or not isinstance(node.ops[0], operator)
                or len(node.comparators) != 1
            ):
                continue
            comparison = node.comparators[0]
            if isinstance(comparison, ast.Tuple):
                observed = {
                    _attribute_name(item, aliases).rsplit(".", 1)[-1]
                    for item in comparison.elts
                }
            else:
                observed = {
                    _attribute_name(comparison, aliases).rsplit(".", 1)[-1]
                }
            if observed == states:
                return True
        return False

    if not all(
        (
            has_live_classifier_decision(tree, owner, operator, states)
            for tree, owner, operator, states in (
                (policy_tree, _class_method(policy_tree, "CapturePolicy", "validated"), ast.Eq, {"REGISTERED_SAFE"}),
                (shape_tree, _class_method(shape_tree, "SanitizedShape", "validate"), ast.NotEq, {"REGISTERED_SAFE"}),
                (shape_tree, _class_method(shape_tree, "SanitizedShape", "validate"), ast.NotIn, {"REGISTERED_SAFE", "SAFE_UNREGISTERED"}),
                (shape_tree, _class_method(shape_tree, "ShapeAccumulator", "__init__"), ast.NotEq, {"REGISTERED_SAFE"}),
                (publisher_tree, _module_function(publisher_tree, "_valid_pointer"), ast.NotIn, {"REGISTERED_SAFE", "SAFE_UNREGISTERED"}),
                (publisher_tree, _class_method(publisher_tree, "AtomicShapePublisher", "__init__"), ast.NotEq, {"REGISTERED_SAFE"}),
            )
        )
    ):
        _fail("SENSITIVE_RULE_UNUSED")

    stage = _class_method(shape_tree, "ShapeAccumulator", "stage_json_bytes")
    stage_source = {
        node.value
        for node in _function_nodes(stage)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    stage_names = {
        _attribute_name(node, {})
        for node in _function_nodes(stage)
        if isinstance(node, (ast.Name, ast.Attribute))
    }
    if (
        not {"SENSITIVE_KEY", "UNKNOWN_SCHEMA_KEY"}.issubset(stage_source)
        or not {"SENSITIVE", "TRUE_UNKNOWN"}.issubset(stage_names)
    ):
        _fail("SENSITIVE_RULE_UNUSED")
    stage_assignments = [
        node
        for node in _function_nodes(stage)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "key_classification"
    ]
    if (
        len(stage_assignments) != 1
        or not isinstance(stage_assignments[0].value, ast.Call)
        or _attribute_name(stage_assignments[0].value.func, {})
        != "classify_schema_key"
        or len(stage_assignments[0].value.args) != 2
        or stage_assignments[0].value.keywords
    ):
        _fail("SENSITIVE_RULE_UNUSED")

    def stage_gate(expected_state: str, error_code: str) -> bool:
        return any(
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and _attribute_name(node.test.left, {}) == "key_classification"
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.Eq)
            and len(node.test.comparators) == 1
            and _attribute_name(node.test.comparators[0], {}) == expected_state
            and len(node.body) == 1
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Call)
            and _attribute_name(node.body[0].value.func, {}) == "_fail"
            and len(node.body[0].value.args) == 1
            and not node.body[0].value.keywords
            and isinstance(node.body[0].value.args[0], ast.Constant)
            and node.body[0].value.args[0].value == error_code
            for node in _function_nodes(stage)
        )

    if not (
        stage_gate("SENSITIVE", "SENSITIVE_KEY")
        and stage_gate("TRUE_UNKNOWN", "UNKNOWN_SCHEMA_KEY")
    ):
        _fail("SENSITIVE_RULE_UNUSED")


def _verify_sensitive_rules(trees: Mapping[str, ast.Module]) -> None:
    definitions: List[Set[str]] = []
    shape_tree = trees["autocapture/shape.py"]
    _verify_shape_normalizer(shape_tree)
    _verify_shape_sensitive_classifier(shape_tree)
    _verify_unique_schema_key_classifier(trees)
    for node in ast.walk(shape_tree):
        target_name: Optional[str] = None
        value: Optional[ast.AST] = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target_name = _assigned_name(node.targets[0])
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target_name = _assigned_name(node.target)
            value = node.value
        if target_name == "SENSITIVE_KEY_TOKENS" and value is not None:
            candidate = _literal_string_collection(value)
            if candidate is None:
                _fail("SENSITIVE_RULE_INVALID")
            definitions.append(candidate)
    if len(definitions) != 1:
        _fail("SENSITIVE_RULE_INVALID")
    if not SENSITIVE_MINIMUM.issubset(definitions[0]):
        _fail("SENSITIVE_RULE_INCOMPLETE")

    stage_method = _class_method(shape_tree, "ShapeAccumulator", "stage_json_bytes")
    stage_calls = [
        node
        for node in _function_nodes(stage_method)
        if isinstance(node, ast.Call)
        and _attribute_name(node.func, {}) == "classify_schema_key"
    ]
    if len(stage_calls) != 1:
        _fail("SENSITIVE_RULE_UNUSED")


def _verify_atomic_endpoint_selector(tree: ast.Module) -> None:
    """Lock the policy to one frozen request-tuple selector.

    The addon-side ordering gate is not enough: a hostile policy could turn a
    three-field call into a host-only decision.  This AST check therefore
    freezes both the data model and the actual selector shape.
    """

    endpoint_classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EndpointRule"
    ]
    if len(endpoint_classes) != 1:
        _fail("ENDPOINT_SELECTOR_INVALID")
    endpoint_class = endpoint_classes[0]
    frozen_decorators = [
        decorator
        for decorator in endpoint_class.decorator_list
        if isinstance(decorator, ast.Call)
        and _attribute_name(decorator.func, {}) == "dataclass"
        and not decorator.args
        and len(decorator.keywords) == 1
        and decorator.keywords[0].arg == "frozen"
        and isinstance(decorator.keywords[0].value, ast.Constant)
        and decorator.keywords[0].value.value is True
    ]
    endpoint_fields = {
        node.target.id
        for node in endpoint_class.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    if len(frozen_decorators) != 1 or endpoint_fields != {"method", "host", "path"}:
        _fail("ENDPOINT_SELECTOR_INVALID")
    _class_method(tree, "EndpointRule", "validated")

    policy_classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CapturePolicy"
    ]
    if len(policy_classes) != 1:
        _fail("ENDPOINT_SELECTOR_INVALID")
    policy_class = policy_classes[0]
    policy_fields = {
        node.target.id
        for node in policy_class.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    if "endpoint_rules" not in policy_fields or {
        "allowed_hosts",
        "allowed_methods",
        "allowed_paths",
    }.intersection(policy_fields):
        _fail("ENDPOINT_SELECTOR_INVALID")
    if any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"allows_host", "allows_method", "allows_path"}
        for node in tree.body
    ):
        _fail("ENDPOINT_SELECTOR_INVALID")

    validated = _class_method(tree, "CapturePolicy", "validated")
    validated_calls = [
        node
        for node in _function_nodes(validated)
        if isinstance(node, ast.Call)
    ]
    endpoint_rule_refs = [
        node
        for node in _function_nodes(validated)
        if isinstance(node, ast.Attribute)
        and _attribute_name(node, {}) == "self.endpoint_rules"
    ]
    if (
        not endpoint_rule_refs
        or sum(
            1
            for node in validated_calls
            if _attribute_name(node.func, {}) == "_is_immutable_collection"
            and len(node.args) == 1
            and _attribute_name(node.args[0], {}) == "self.endpoint_rules"
        )
        != 1
        or sum(
            1
            for node in validated_calls
            if _attribute_name(node.func, {}) == "_has_duplicate_tuple_items"
            and len(node.args) == 1
            and _attribute_name(node.args[0], {}) == "self.endpoint_rules"
        )
        != 1
        or sum(
            1
            for node in validated_calls
            if isinstance(node.func, ast.Attribute)
            and node.func.attr == "validated"
            and _attribute_name(node.func.value, {}) == "rule"
            and not node.args
            and not node.keywords
        )
        != 1
    ):
        _fail("ENDPOINT_SELECTOR_INVALID")

    selector = _class_method(tree, "CapturePolicy", "select_endpoint")
    arguments = selector.args
    if (
        [argument.arg for argument in arguments.args] != ["self", "method", "host", "path"]
        or arguments.posonlyargs
        or arguments.vararg is not None
        or arguments.kwarg is not None
        or arguments.defaults
        or arguments.kw_defaults
    ):
        _fail("ENDPOINT_SELECTOR_INVALID")
    selector_nodes = list(_function_nodes(selector))
    selector_calls = [
        node for node in selector_nodes if isinstance(node, ast.Call)
    ]
    for function_name, argument_name in (
        ("_valid_http_method", "method"),
        ("_valid_exact_host", "host"),
        ("_valid_static_path", "path"),
    ):
        matching_calls = [
            node
            for node in selector_calls
            if _attribute_name(node.func, {}) == function_name
            and len(node.args) == 1
            and not node.keywords
            and _attribute_name(node.args[0], {}) == argument_name
        ]
        if len(matching_calls) != 1:
            _fail("ENDPOINT_SELECTOR_INVALID")

    endpoint_calls = [
        node
        for node in selector_calls
        if _attribute_name(node.func, {}) == "EndpointRule"
    ]
    if (
        len(endpoint_calls) != 1
        or len(endpoint_calls[0].args) != 3
        or endpoint_calls[0].keywords
        or tuple(_attribute_name(argument, {}) for argument in endpoint_calls[0].args)
        != ("method", "host", "path")
    ):
        _fail("ENDPOINT_SELECTOR_INVALID")
    candidate_assignments = [
        node
        for node in selector_nodes
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "candidate"
        and node.value is endpoint_calls[0]
    ]
    if len(candidate_assignments) != 1:
        _fail("ENDPOINT_SELECTOR_INVALID")

    returns = [
        _attribute_name(node.value, {})
        for node in selector_nodes
        if isinstance(node, ast.Return)
    ]
    if any(returns.count(name) != 1 for name in (
        "ENDPOINT_METADATA_INVALID",
        "ENDPOINT_MATCH",
        "ENDPOINT_MISMATCH",
    )):
        _fail("ENDPOINT_SELECTOR_INVALID")
    membership_gates = [
        node
        for node in selector_nodes
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and len(node.test.ops) == 1
        and isinstance(node.test.ops[0], ast.In)
        and _attribute_name(node.test.left, {}) == "candidate"
        and len(node.test.comparators) == 1
        and _attribute_name(node.test.comparators[0], {}) == "self.endpoint_rules"
        and len(node.body) == 1
        and isinstance(node.body[0], ast.Return)
        and _attribute_name(node.body[0].value, {}) == "ENDPOINT_MATCH"
    ]
    if len(membership_gates) != 1:
        _fail("ENDPOINT_SELECTOR_INVALID")


def _flow_role(node: ast.AST, aliases: Mapping[str, str]) -> Optional[str]:
    if isinstance(node, ast.Name):
        if node.id == "flow":
            return _FLOW
        return aliases.get(node.id)
    if isinstance(node, ast.Attribute):
        base = _flow_role(node.value, aliases)
        if base is None and node.attr == "request":
            return _REQUEST
        if base is None and node.attr == "response":
            return _RESPONSE
        if base == _FLOW and node.attr == "request":
            return _REQUEST
        if base == _FLOW and node.attr == "response":
            return _RESPONSE
        if base == _REQUEST and node.attr == "method":
            return _REQUEST_METHOD
        if base == _REQUEST and node.attr == "host":
            return _REQUEST_HOST
        if base == _REQUEST and node.attr == "path":
            return _REQUEST_PATH
        if base == _RESPONSE and node.attr == "status_code":
            return _RESPONSE_STATUS
        if base == _RESPONSE and node.attr == "headers":
            return _HEADERS
        if base == _RESPONSE and node.attr == "raw_content":
            return _BODY
    if isinstance(node, ast.Subscript):
        base = _flow_role(node.value, aliases)
        if base is not None and base.startswith(_CONTAINER_PREFIX):
            return base[len(_CONTAINER_PREFIX) :]
    return None


def _containerized_role(role: str) -> str:
    return _CONTAINER_PREFIX + role


def _is_flow_object_role(role: Optional[str]) -> bool:
    return role in _FLOW_OBJECT_ROLES or (
        role is not None and role.startswith(_CONTAINER_PREFIX)
    )


def _merge_alias_role(existing: Optional[str], candidate: str) -> str:
    if existing is None or existing == candidate:
        return candidate
    if existing.startswith(_CONTAINER_PREFIX) or candidate.startswith(_CONTAINER_PREFIX):
        return _containerized_role(_FLOW)
    return _FLOW


def _value_alias_role(node: ast.AST, aliases: Mapping[str, str]) -> Optional[str]:
    direct = _flow_role(node, aliases)
    if direct is not None:
        return direct
    elements: Iterable[ast.AST]
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        elements = node.elts
    elif isinstance(node, ast.Dict):
        elements = tuple(item for item in list(node.keys) + list(node.values) if item is not None)
    elif (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"dict", "frozenset", "list", "set", "tuple"}
    ):
        elements = tuple(node.args) + tuple(
            keyword.value for keyword in node.keywords if keyword.arg is not None
        )
    else:
        return None
    roles = [
        role
        for element in elements
        for role in (_value_alias_role(element, aliases),)
        if role is not None
    ]
    if not roles:
        return None
    first = roles[0]
    if all(role == first for role in roles):
        return _containerized_role(first)
    return _containerized_role(_FLOW)


def _assignment_targets(node: ast.AST) -> Iterable[Tuple[ast.AST, ast.AST]]:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            yield target, node.value
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        yield node.target, node.value
    elif isinstance(node, ast.NamedExpr):
        yield node.target, node.value


def _payload_argument_name(function: ast.AST) -> Optional[str]:
    arguments = getattr(function, "args", None)
    if not isinstance(arguments, ast.arguments):
        return None
    positional = list(arguments.posonlyargs) + list(arguments.args)
    for argument in positional:
        if argument.arg not in {"self", "cls"}:
            return argument.arg
    return None


def _flow_aliases(function: ast.AST, forced_flow_names: Iterable[str] = ()) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for name in forced_flow_names:
        aliases[name] = _FLOW
    arguments = getattr(function, "args", None)
    if isinstance(arguments, ast.arguments):
        for argument in list(arguments.posonlyargs) + list(arguments.args) + list(arguments.kwonlyargs):
            if argument.arg == "flow":
                aliases[argument.arg] = _FLOW
    changed = True
    while changed:
        changed = False
        for node in ast.walk(function):
            for target, value in _assignment_targets(node):
                role = _value_alias_role(value, aliases)
                alias_target: Optional[str] = None
                alias_role = role
                if isinstance(target, ast.Name):
                    alias_target = target.id
                elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                    alias_target = target.value.id
                    if role is not None:
                        alias_role = _containerized_role(role)
                if (
                    alias_target is not None
                    and alias_role is not None
                ):
                    merged = _merge_alias_role(aliases.get(alias_target), alias_role)
                    if aliases.get(alias_target) != merged:
                        aliases[alias_target] = merged
                        changed = True
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name):
                continue
            if node.func.attr not in {"append", "extend", "insert", "setdefault", "update"}:
                continue
            role = _value_alias_role(
                ast.Tuple(
                    elts=list(node.args)
                    + [keyword.value for keyword in node.keywords if keyword.arg is not None],
                    ctx=ast.Load(),
                ),
                aliases,
            )
            if role is not None:
                container_name = node.func.value.id
                merged = _merge_alias_role(aliases.get(container_name), role)
                if aliases.get(container_name) != merged:
                    aliases[container_name] = merged
                    changed = True
    return aliases


def _constant_header(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip().casefold()
    return None


def _target_mutates_flow(target: ast.AST, aliases: Mapping[str, str]) -> bool:
    if isinstance(target, ast.Attribute):
        return _flow_role(target.value, aliases) is not None
    if isinstance(target, ast.Subscript):
        return _flow_role(target.value, aliases) is not None
    if isinstance(target, (ast.List, ast.Tuple)):
        return any(_target_mutates_flow(item, aliases) for item in target.elts)
    return False


def _verify_flow_function(
    function: ast.AST,
    forced_flow_names: Iterable[str] = (),
) -> None:
    aliases = _flow_aliases(function, forced_flow_names)
    for node in ast.walk(function):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            defaults = list(node.args.defaults) + [
                value for value in node.args.kw_defaults if value is not None
            ]
            for default in defaults:
                role = _value_alias_role(default, aliases)
                if _is_flow_object_role(role) or role == _BODY:
                    _fail("FLOW_OBJECT_ESCAPE")
        for target, value in _assignment_targets(node):
            if _target_mutates_flow(target, aliases):
                _fail("FLOW_MUTATION_FORBIDDEN")
            value_role = _flow_role(value, aliases)
            if (
                _is_flow_object_role(value_role) or value_role == _BODY
            ) and not isinstance(target, ast.Name):
                _fail("FLOW_OBJECT_ESCAPE")

        if isinstance(node, (ast.Delete, ast.AugAssign)):
            targets: Sequence[ast.AST]
            if isinstance(node, ast.Delete):
                targets = node.targets
            else:
                targets = (node.target,)
            if any(_target_mutates_flow(target, aliases) for target in targets):
                _fail("FLOW_MUTATION_FORBIDDEN")

        if isinstance(node, ast.Attribute):
            base = _flow_role(node.value, aliases)
            allowed: Set[str]
            if base == _FLOW:
                allowed = {"request", "response"}
            elif base == _REQUEST:
                allowed = {"method", "host", "path"}
            elif base == _RESPONSE:
                allowed = {"headers", "raw_content", "status_code"}
            elif base == _HEADERS:
                allowed = {"get"}
            else:
                allowed = set()
            if base in {_FLOW, _REQUEST, _RESPONSE, _HEADERS} and node.attr not in allowed:
                _fail("FLOW_FIELD_FORBIDDEN")

        if isinstance(node, ast.Subscript) and _flow_role(node.value, aliases) == _HEADERS:
            header = _constant_header(node.slice)
            if header not in ALLOWED_RESPONSE_HEADERS:
                _fail("FLOW_HEADER_FORBIDDEN")

        if isinstance(node, (ast.For, ast.AsyncFor)) and _flow_role(node.iter, aliases) == _HEADERS:
            _fail("FLOW_HEADER_FORBIDDEN")

        if isinstance(node, ast.comprehension) and _flow_role(node.iter, aliases) == _HEADERS:
            _fail("FLOW_HEADER_FORBIDDEN")

        if isinstance(node, ast.Return) and node.value is not None:
            return_role = _flow_role(node.value, aliases)
            if _is_flow_object_role(return_role) or return_role == _BODY:
                _fail("FLOW_OBJECT_ESCAPE")

        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            if any(
                _is_flow_object_role(_flow_role(item, aliases))
                or _flow_role(item, aliases) == _BODY
                for item in node.elts
            ):
                _fail("FLOW_OBJECT_ESCAPE")
        if isinstance(node, ast.Dict):
            items = tuple(item for item in list(node.keys) + list(node.values) if item is not None)
            if any(
                _is_flow_object_role(_flow_role(item, aliases))
                or _flow_role(item, aliases) == _BODY
                for item in items
            ):
                _fail("FLOW_OBJECT_ESCAPE")

        if not isinstance(node, ast.Call):
            continue
        qualified_call = _attribute_name(node.func, {})
        observe_helper_call = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
            and node.func.attr == "_observe_response"
            and len(node.args) == 1
            and _flow_role(node.args[0], aliases) == _FLOW
            and not node.keywords
        )
        function_role = _flow_role(node.func.value, aliases) if isinstance(node.func, ast.Attribute) else None
        if function_role == _HEADERS and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            if not node.args:
                _fail("FLOW_HEADER_FORBIDDEN")
            header = _constant_header(node.args[0])
            if header not in ALLOWED_RESPONSE_HEADERS:
                _fail("FLOW_HEADER_FORBIDDEN")
        elif function_role in {_FLOW, _REQUEST, _RESPONSE, _HEADERS}:
            _fail("FLOW_FIELD_FORBIDDEN")

        if isinstance(node.func, ast.Name) and node.func.id in {"getattr", "setattr", "delattr"}:
            if node.args and _flow_role(node.args[0], aliases) is not None:
                _fail("FLOW_FIELD_FORBIDDEN")
        for argument in list(node.args) + [
            keyword.value for keyword in node.keywords if keyword.arg is not None
        ]:
            argument_role = _flow_role(argument, aliases)
            if _is_flow_object_role(argument_role):
                if observe_helper_call and argument is node.args[0]:
                    continue
                _fail("FLOW_OBJECT_ESCAPE")
            if argument_role == _BODY and qualified_call not in {
                "RawLease.from_proxy_bytes",
                "len",
                "type",
            }:
                _fail("FLOW_OBJECT_ESCAPE")


def _verify_raw_content_gate(tree: ast.Module, method: ast.AST) -> None:
    payload_name = _payload_argument_name(method)
    if payload_name is None:
        _fail("FLOW_BODY_GATE_INVALID")
    aliases = _flow_aliases(method, (payload_name,))
    nodes = list(_function_nodes(method))
    raw_reads = [
        node
        for node in nodes
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Load)
        and _flow_role(node, aliases) == _BODY
    ]
    if len(raw_reads) != 1:
        _fail("FLOW_BODY_GATE_INVALID")
    raw_read = raw_reads[0]

    all_raw_reads: Dict[int, ast.Attribute] = {}
    module_shell = ast.Module(
        body=[
            node
            for node in tree.body
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ],
        type_ignores=[],
    )
    for node in ast.walk(module_shell):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and _flow_role(node, {}) == _BODY
        ):
            all_raw_reads[id(node)] = node
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        forced_names: Tuple[str, ...] = ()
        if function.name in {"response", "_observe_response"}:
            candidate = _payload_argument_name(function)
            if candidate is not None:
                forced_names = (candidate,)
        function_aliases = _flow_aliases(function, forced_names)
        for node in _function_ast_nodes(function):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and _flow_role(node, function_aliases) == _BODY
            ):
                all_raw_reads[id(node)] = node
    if len(all_raw_reads) != 1 or id(raw_read) not in all_raw_reads:
        _fail("FLOW_BODY_GATE_INVALID")

    raw_assignment = any(
        (
            isinstance(node, ast.Assign)
            and node.value is raw_read
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "raw_content"
        )
        or (
            isinstance(node, ast.AnnAssign)
            and node.value is raw_read
            and isinstance(node.target, ast.Name)
            and node.target.id == "raw_content"
        )
        for node in nodes
    )
    if not raw_assignment:
        _fail("FLOW_BODY_GATE_INVALID")

    required_call_lines: Dict[str, int] = {}
    required_call_counts: Dict[str, int] = {}
    negative_gate_names: Set[str] = set()
    header_lines: Dict[str, int] = {}
    field_lines: Dict[str, int] = {}
    field_counts: Dict[str, int] = {}
    response_lines: List[int] = []
    selector_calls: List[ast.Call] = []
    actual_length_line: Optional[int] = None
    lease_line: Optional[int] = None
    for node in nodes:
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and isinstance(node.test.operand, ast.Call)
        ):
            gate_name = _attribute_name(node.test.operand.func, {})
            if any(isinstance(statement, ast.Return) for statement in node.body):
                negative_gate_names.add(gate_name)
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            role = _flow_role(node, aliases)
            if role in {
                _REQUEST_METHOD,
                _REQUEST_HOST,
                _REQUEST_PATH,
                _RESPONSE_STATUS,
                _HEADERS,
            }:
                field_lines.setdefault(role, node.lineno)
                field_counts[role] = field_counts.get(role, 0) + 1
            if role == _RESPONSE:
                response_lines.append(node.lineno)
        if not isinstance(node, ast.Call):
            continue
        qualified = _attribute_name(node.func, {})
        if qualified == "policy.allows_host":
            _fail("FLOW_BODY_GATE_INVALID")
        if qualified == "policy.select_endpoint":
            selector_calls.append(node)
        if qualified in {
            "policy.allows_content_type",
            "policy.allows_status",
            "self._declared_length",
            "self._identity_encoding",
        }:
            required_call_lines.setdefault(qualified, node.lineno)
            required_call_counts[qualified] = required_call_counts.get(qualified, 0) + 1
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and _flow_role(node.func.value, aliases) == _HEADERS
            and node.args
        ):
            header = _constant_header(node.args[0])
            if header is not None:
                header_lines.setdefault(header, node.lineno)
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "len"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "raw_content"
        ):
            actual_length_line = node.lineno
        if qualified == "RawLease.from_proxy_bytes":
            lease_line = node.lineno

    if (
        len(selector_calls) != 1
        or len(selector_calls[0].args) != 3
        or selector_calls[0].keywords
        or tuple(_flow_role(argument, aliases) for argument in selector_calls[0].args)
        != (_REQUEST_METHOD, _REQUEST_HOST, _REQUEST_PATH)
    ):
        _fail("FLOW_BODY_GATE_INVALID")
    selection_assignments = [
        node
        for node in nodes
        if isinstance(node, ast.Assign)
        and node.value is selector_calls[0]
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "endpoint_selection"
    ]
    if len(selection_assignments) != 1:
        _fail("FLOW_BODY_GATE_INVALID")

    def selection_gates(operator: type, expected_name: str) -> List[ast.If]:
        return [
            node
            for node in nodes
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and _attribute_name(node.test.left, {}) == "endpoint_selection"
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], operator)
            and len(node.test.comparators) == 1
            and _attribute_name(node.test.comparators[0], {}) == expected_name
            and any(isinstance(statement, ast.Return) for statement in node.body)
        ]

    metadata_gates = selection_gates(ast.Eq, "ENDPOINT_METADATA_INVALID")
    mismatch_gates = selection_gates(ast.NotEq, "ENDPOINT_MATCH")

    if not (
        len(metadata_gates) == 1
        and len(mismatch_gates) == 1
    ):
        _fail("FLOW_BODY_GATE_INVALID")
    metadata_gate = metadata_gates[0]
    mismatch_gate = mismatch_gates[0]
    if (
        len(metadata_gate.body) != 2
        or not isinstance(metadata_gate.body[0], ast.Expr)
        or not isinstance(metadata_gate.body[0].value, ast.Call)
        or _attribute_name(metadata_gate.body[0].value.func, {}) != "self._stop"
        or len(metadata_gate.body[0].value.args) != 1
        or metadata_gate.body[0].value.keywords
        or not isinstance(metadata_gate.body[0].value.args[0], ast.Constant)
        or metadata_gate.body[0].value.args[0].value != "REQUEST_METADATA_INVALID"
        or not isinstance(metadata_gate.body[1], ast.Return)
        or len(mismatch_gate.body) != 1
        or not isinstance(mismatch_gate.body[0], ast.Return)
    ):
        _fail("FLOW_BODY_GATE_INVALID")

    required_calls = {
        "policy.allows_content_type",
        "policy.allows_status",
        "self._declared_length",
        "self._identity_encoding",
    }
    required_fields = {
        _REQUEST_METHOD,
        _REQUEST_HOST,
        _REQUEST_PATH,
        _RESPONSE_STATUS,
        _HEADERS,
    }
    required_negative_gates = {
        "policy.allows_content_type",
        "policy.allows_status",
        "self._identity_encoding",
    }
    if (
        set(required_call_lines) != required_calls
        or any(required_call_counts.get(name) != 1 for name in required_calls)
        or set(header_lines) != ALLOWED_RESPONSE_HEADERS
        or set(field_lines) != required_fields
        or any(field_counts.get(name) != 1 for name in required_fields)
        or not required_negative_gates.issubset(negative_gate_names)
        or len(response_lines) != 1
        or selector_calls[0].lineno >= min(response_lines)
        or metadata_gate.lineno >= min(response_lines)
        or mismatch_gate.lineno >= min(response_lines)
    ):
        _fail("FLOW_BODY_GATE_INVALID")
    gate_lines = list(required_call_lines.values()) + list(header_lines.values()) + list(
        field_lines.values()
    )
    if not gate_lines or max(gate_lines) >= raw_read.lineno:
        _fail("FLOW_BODY_GATE_INVALID")
    if (
        actual_length_line is None
        or actual_length_line <= raw_read.lineno
        or lease_line is None
        or lease_line <= actual_length_line
    ):
        _fail("FLOW_BODY_GATE_INVALID")


def _verify_flow_capabilities(tree: ast.Module) -> None:
    addon_classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ResponseCaptureAddon"
    ]
    if len(addon_classes) != 1:
        _fail("MITMPROXY_ADDON_MISSING")
    addon_class = addon_classes[0]
    response_handlers = [
        node
        for node in addon_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "response"
    ]
    observe_handlers = [
        node
        for node in addon_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_observe_response"
    ]
    if len(response_handlers) != 1 or len(observe_handlers) != 1:
        _fail("MITMPROXY_ADDON_INVALID")
    if _payload_argument_name(response_handlers[0]) is None:
        _fail("MITMPROXY_ADDON_INVALID")
    if _payload_argument_name(observe_handlers[0]) is None:
        _fail("MITMPROXY_ADDON_INVALID")

    addons_assignments: List[ast.AST] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if any(isinstance(target, ast.Name) and target.id == "addons" for target in targets):
            addons_assignments.append(node)
    if len(addons_assignments) != 1:
        _fail("MITMPROXY_ADDON_INVALID")
    addons_value = addons_assignments[0].value
    if (
        not isinstance(addons_value, ast.List)
        or len(addons_value.elts) != 1
        or not isinstance(addons_value.elts[0], ast.Call)
        or _attribute_name(addons_value.elts[0].func, {}) != "ResponseCaptureAddon"
        or addons_value.elts[0].args
        or addons_value.elts[0].keywords
    ):
        _fail("MITMPROXY_ADDON_INVALID")
    constructor_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _attribute_name(node.func, {}) == "ResponseCaptureAddon"
    ]
    if len(constructor_calls) != 1 or constructor_calls[0] is not addons_value.elts[0]:
        _fail("MITMPROXY_ADDON_INVALID")

    init_method = _class_method(tree, "ResponseCaptureAddon", "__init__")
    arm_method = _class_method(tree, "ResponseCaptureAddon", "arm")

    def state_assignments(method: ast.AST, state_name: str) -> List[ast.AST]:
        return [
            node
            for node in _function_nodes(method)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and _attribute_name(
                node.targets[0] if isinstance(node, ast.Assign) else node.target,
                {},
            )
            == "self._state"
            and _attribute_name(node.value, {}) == state_name
        ]

    def all_state_assignments(method: ast.AST) -> List[ast.AST]:
        return [
            node
            for node in _function_nodes(method)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and _attribute_name(
                node.targets[0] if isinstance(node, ast.Assign) else node.target,
                {},
            )
            == "self._state"
        ]

    if (
        len(state_assignments(init_method, "DISARMED")) != 1
        or len(all_state_assignments(init_method)) != 1
    ):
        _fail("MITMPROXY_ADDON_INVALID")
    if (
        len(state_assignments(arm_method, "ARMED")) != 1
        or len(all_state_assignments(arm_method)) != 1
    ):
        _fail("MITMPROXY_ADDON_INVALID")
    if any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Attribute) and target.attr == "_state"
            for target in (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
        )
        for node in tree.body
    ):
        _fail("MITMPROXY_ADDON_INVALID")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "arm":
            _fail("MITMPROXY_ADDON_INVALID")
    if any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"load", "configure", "running"}
        for node in ast.walk(tree)
    ):
        _fail("MITMPROXY_ADDON_INVALID")

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            forced_names: Tuple[str, ...] = ()
            if node.name in {"response", "_observe_response"}:
                payload_name = _payload_argument_name(node)
                if payload_name is None:
                    _fail("MITMPROXY_ADDON_INVALID")
                forced_names = (payload_name,)
            _verify_flow_function(node, forced_names)
    _verify_raw_content_gate(tree, observe_handlers[0])


def _qualified_calls(tree: ast.Module) -> Iterable[Tuple[str, ast.Call]]:
    aliases = _import_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield _attribute_name(node.func, aliases), node


def _static_truth(node: ast.AST) -> Optional[bool]:
    if isinstance(node, ast.Constant):
        try:
            return bool(node.value)
        except BaseException:
            return None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        value = _static_truth(node.operand)
        return None if value is None else not value
    return None


def _function_ast_nodes(function: ast.AST) -> Iterable[ast.AST]:
    body = getattr(function, "body", ())
    pending: List[ast.AST] = list(reversed(body))
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield node
        pending.extend(reversed(list(ast.iter_child_nodes(node))))


def _function_nodes(function: ast.AST) -> Iterable[ast.AST]:
    body = getattr(function, "body", ())
    pending: List[ast.AST] = list(reversed(body))
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield node
        if isinstance(node, (ast.If, ast.While)):
            truth = _static_truth(node.test)
            branches: Sequence[ast.AST]
            if truth is True:
                branches = node.body
            elif truth is False:
                branches = node.orelse
            else:
                branches = tuple(node.body) + tuple(node.orelse)
            children = [node.test] + list(branches)
        elif isinstance(node, ast.IfExp):
            truth = _static_truth(node.test)
            if truth is True:
                children = [node.test, node.body]
            elif truth is False:
                children = [node.test, node.orelse]
            else:
                children = [node.test, node.body, node.orelse]
        elif isinstance(node, ast.BoolOp):
            children = []
            for value in node.values:
                children.append(value)
                truth = _static_truth(value)
                if isinstance(node.op, ast.And) and truth is False:
                    break
                if isinstance(node.op, ast.Or) and truth is True:
                    break
        else:
            children = list(ast.iter_child_nodes(node))
        pending.extend(reversed(children))


def _node_mentions(
    node: ast.AST,
    qualified_name: str,
    aliases: Mapping[str, str],
) -> bool:
    return any(
        _attribute_name(child, aliases) == qualified_name
        for child in ast.walk(node)
        if isinstance(child, (ast.Name, ast.Attribute))
    )


def _target_aliases(function: ast.AST, aliases: Mapping[str, str]) -> Set[str]:
    target_aliases: Set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in _function_ast_nodes(function):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if value is None:
                continue
            value_mentions_target = _node_mentions(value, "self._target_name", aliases) or any(
                isinstance(child, ast.Name) and child.id in target_aliases
                for child in ast.walk(value)
            )
            if not value_mentions_target:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in target_aliases:
                    target_aliases.add(target.id)
                    changed = True
    return target_aliases


def _secure_publish_link(call: ast.Call, aliases: Mapping[str, str]) -> bool:
    if len(call.args) < 2:
        return False
    if _attribute_name(call.args[0], aliases) != "staging_name":
        return False
    if _attribute_name(call.args[1], aliases) != "self._target_name":
        return False
    keywords = {keyword.arg: keyword.value for keyword in call.keywords if keyword.arg is not None}
    follow = keywords.get("follow_symlinks")
    return (
        _attribute_name(keywords.get("src_dir_fd", ast.Constant(None)), aliases) == "root_fd"
        and _attribute_name(keywords.get("dst_dir_fd", ast.Constant(None)), aliases) == "root_fd"
        and isinstance(follow, ast.Constant)
        and follow.value is False
    )


def _verify_reopen_method(
    method: ast.AST,
    aliases: Mapping[str, str],
) -> None:
    calls = [
        (_attribute_name(node.func, aliases), node)
        for node in _function_nodes(method)
        if isinstance(node, ast.Call)
    ]
    secure_open = False
    has_fstat = False
    for qualified, call in calls:
        if qualified == "os.fstat":
            has_fstat = True
        if qualified != "os.open" or not call.args:
            continue
        keywords = {keyword.arg: keyword.value for keyword in call.keywords if keyword.arg is not None}
        if (
            _attribute_name(call.args[0], aliases) == "target_name"
            and _attribute_name(keywords.get("dir_fd", ast.Constant(None)), aliases) == "root_fd"
        ):
            secure_open = True
    attributes = {
        _attribute_name(node, aliases)
        for node in _function_nodes(method)
        if isinstance(node, ast.Attribute)
    }
    if not secure_open or not has_fstat or not {
        "os.O_NOFOLLOW",
        "os.O_RDONLY",
        "stat.S_ISREG",
    }.issubset(attributes):
        _fail("REOPEN_GUARD_MISSING")


def _verify_publisher_open_closure(
    tree: ast.Module,
    publisher_class: ast.ClassDef,
    aliases: Mapping[str, str],
) -> None:
    open_references = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and _attribute_name(node, aliases) == "os.open"
    ]
    open_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _attribute_name(node.func, aliases) == "os.open"
    ]
    if (
        len(open_references) != 4
        or len(open_calls) != 4
        or {id(node) for node in open_references} != {id(call.func) for call in open_calls}
    ):
        _fail("FORBIDDEN_CAPABILITY")

    methods: Dict[str, ast.AST] = {}
    for name in {"__init__", "_open_root", "_open_staging", "_reopen_and_validate"}:
        matches = [
            node
            for node in publisher_class.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ]
        if len(matches) != 1:
            _fail("FORBIDDEN_CAPABILITY")
        methods[name] = matches[0]

    calls_by_method: Dict[str, ast.Call] = {}
    for name, method in methods.items():
        calls = [
            node
            for node in _function_nodes(method)
            if isinstance(node, ast.Call) and _attribute_name(node.func, aliases) == "os.open"
        ]
        if len(calls) != 1:
            _fail("FORBIDDEN_CAPABILITY")
        calls_by_method[name] = calls[0]
    if {id(call) for call in calls_by_method.values()} != {id(call) for call in open_calls}:
        _fail("FORBIDDEN_CAPABILITY")

    constructor_call = calls_by_method["__init__"]
    if (
        len(constructor_call.args) != 2
        or constructor_call.keywords
        or _attribute_name(constructor_call.args[0], aliases) != "absolute"
        or _attribute_name(constructor_call.args[1], aliases) != "flags"
    ):
        _fail("FORBIDDEN_CAPABILITY")

    root_call = calls_by_method["_open_root"]
    if (
        len(root_call.args) != 2
        or root_call.keywords
        or _attribute_name(root_call.args[0], aliases) != "self._root_dir"
        or _attribute_name(root_call.args[1], aliases) != "flags"
    ):
        _fail("FORBIDDEN_CAPABILITY")

    staging_call = calls_by_method["_open_staging"]
    staging_keywords = {
        keyword.arg: keyword.value
        for keyword in staging_call.keywords
        if keyword.arg is not None
    }
    if (
        len(staging_call.args) != 3
        or set(staging_keywords) != {"dir_fd"}
        or _attribute_name(staging_call.args[0], aliases) != "name"
        or _attribute_name(staging_call.args[1], aliases) != "flags"
        or not isinstance(staging_call.args[2], ast.Constant)
        or staging_call.args[2].value != 0o600
        or _attribute_name(staging_keywords["dir_fd"], aliases) != "root_fd"
    ):
        _fail("FORBIDDEN_CAPABILITY")

    reopen_call = calls_by_method["_reopen_and_validate"]
    reopen_keywords = {
        keyword.arg: keyword.value
        for keyword in reopen_call.keywords
        if keyword.arg is not None
    }
    if (
        len(reopen_call.args) != 2
        or set(reopen_keywords) != {"dir_fd"}
        or _attribute_name(reopen_call.args[0], aliases) != "target_name"
        or _attribute_name(reopen_call.args[1], aliases) != "flags"
        or _attribute_name(reopen_keywords["dir_fd"], aliases) != "root_fd"
    ):
        _fail("FORBIDDEN_CAPABILITY")

    required_flags = {
        "__init__": {"os.O_DIRECTORY", "os.O_NOFOLLOW", "os.O_RDONLY"},
        "_open_root": {"os.O_DIRECTORY", "os.O_NOFOLLOW", "os.O_RDONLY"},
        "_open_staging": {"os.O_CREAT", "os.O_EXCL", "os.O_NOFOLLOW", "os.O_WRONLY"},
        "_reopen_and_validate": {"os.O_NOFOLLOW", "os.O_RDONLY"},
    }
    forbidden_write_flags = {
        "__init__": {"os.O_APPEND", "os.O_CREAT", "os.O_RDWR", "os.O_TRUNC", "os.O_WRONLY"},
        "_open_root": {"os.O_APPEND", "os.O_CREAT", "os.O_RDWR", "os.O_TRUNC", "os.O_WRONLY"},
        "_reopen_and_validate": {
            "os.O_APPEND",
            "os.O_CREAT",
            "os.O_RDWR",
            "os.O_TRUNC",
            "os.O_WRONLY",
        },
    }
    for name, method in methods.items():
        attributes = {
            _attribute_name(node, aliases)
            for node in _function_ast_nodes(method)
            if isinstance(node, ast.Attribute)
        }
        if not required_flags[name].issubset(attributes):
            _fail("FORBIDDEN_CAPABILITY")
        if forbidden_write_flags.get(name, set()) & attributes:
            _fail("FORBIDDEN_CAPABILITY")


def _exact_call_references(
    tree: ast.Module,
    aliases: Mapping[str, str],
    qualified_name: str,
    expected_count: int,
    reason: str,
) -> List[ast.Call]:
    references = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Name, ast.Attribute))
        and _attribute_name(node, aliases) == qualified_name
    ]
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _attribute_name(node.func, aliases) == qualified_name
    ]
    if (
        len(references) != expected_count
        or len(calls) != expected_count
        or {id(node) for node in references} != {id(call.func) for call in calls}
    ):
        _fail(reason)
    return calls


def _verify_publisher_io_closure(
    tree: ast.Module,
    publisher_class: ast.ClassDef,
    aliases: Mapping[str, str],
) -> None:
    class_methods: Dict[str, ast.AST] = {}
    for name in {
        "_open_root",
        "_open_staging",
        "_reopen_and_validate",
        "_unlink_if_owned",
        "publish",
    }:
        matches = [
            node
            for node in publisher_class.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ]
        if len(matches) != 1:
            _fail("FORBIDDEN_CAPABILITY")
        class_methods[name] = matches[0]

    module_functions: Dict[str, ast.AST] = {}
    for name in {"_read_exact", "_write_all"}:
        matches = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        ]
        if len(matches) != 1:
            _fail("FORBIDDEN_CAPABILITY")
        module_functions[name] = matches[0]

    link_calls = _exact_call_references(
        tree,
        aliases,
        "os.link",
        1,
        "NO_CLOBBER_GUARD_MISSING",
    )
    if (
        not _secure_publish_link(link_calls[0], aliases)
        or all(
            link_calls[0] is not node
            for node in _function_nodes(class_methods["publish"])
        )
    ):
        _fail("NO_CLOBBER_GUARD_MISSING")

    unlink_calls = _exact_call_references(
        tree,
        aliases,
        "os.unlink",
        3,
        "CLOBBER_PRIMITIVE_FORBIDDEN",
    )
    expected_unlinks = (
        ("_open_staging", "name", "root_fd"),
        ("_unlink_if_owned", "name", "root_fd"),
        ("publish", "staging_name", "root_fd"),
    )
    observed_unlinks: Set[int] = set()
    for method_name, name_argument, root_argument in expected_unlinks:
        matches = [
            node
            for node in _function_nodes(class_methods[method_name])
            if isinstance(node, ast.Call)
            and _attribute_name(node.func, aliases) == "os.unlink"
        ]
        if len(matches) != 1:
            _fail("CLOBBER_PRIMITIVE_FORBIDDEN")
        call = matches[0]
        keywords = {
            keyword.arg: keyword.value
            for keyword in call.keywords
            if keyword.arg is not None
        }
        if (
            len(call.args) != 1
            or set(keywords) != {"dir_fd"}
            or _attribute_name(call.args[0], aliases) != name_argument
            or _attribute_name(keywords["dir_fd"], aliases) != root_argument
        ):
            _fail("CLOBBER_PRIMITIVE_FORBIDDEN")
        observed_unlinks.add(id(call))
    if observed_unlinks != {id(call) for call in unlink_calls}:
        _fail("CLOBBER_PRIMITIVE_FORBIDDEN")

    owned_unlink_calls = _exact_call_references(
        tree,
        aliases,
        "self._unlink_if_owned",
        2,
        "CLOBBER_PRIMITIVE_FORBIDDEN",
    )
    for call in owned_unlink_calls:
        if (
            len(call.args) != 3
            or call.keywords
            or _attribute_name(call.args[0], aliases) != "root_fd"
            or _attribute_name(call.args[1], aliases) != "staging_name"
            or _attribute_name(call.args[2], aliases) != "staging_identity"
            or all(
                call is not node
                for node in _function_nodes(class_methods["publish"])
            )
        ):
            _fail("CLOBBER_PRIMITIVE_FORBIDDEN")

    fchmod_calls = _exact_call_references(
        tree,
        aliases,
        "os.fchmod",
        1,
        "FORBIDDEN_CAPABILITY",
    )
    fchmod_call = fchmod_calls[0]
    if (
        len(fchmod_call.args) != 2
        or fchmod_call.keywords
        or _attribute_name(fchmod_call.args[0], aliases) != "file_fd"
        or not isinstance(fchmod_call.args[1], ast.Constant)
        or fchmod_call.args[1].value != 0o600
        or all(
            fchmod_call is not node
            for node in _function_nodes(class_methods["_open_staging"])
        )
    ):
        _fail("FORBIDDEN_CAPABILITY")

    write_calls = _exact_call_references(
        tree,
        aliases,
        "os.write",
        1,
        "FORBIDDEN_CAPABILITY",
    )
    write_call = write_calls[0]
    if (
        len(write_call.args) != 2
        or write_call.keywords
        or _attribute_name(write_call.args[0], aliases) != "file_fd"
        or all(
            write_call is not node
            for node in _function_nodes(module_functions["_write_all"])
        )
    ):
        _fail("FORBIDDEN_CAPABILITY")

    read_calls = _exact_call_references(
        tree,
        aliases,
        "os.read",
        1,
        "FORBIDDEN_CAPABILITY",
    )
    read_call = read_calls[0]
    if (
        len(read_call.args) != 2
        or read_call.keywords
        or _attribute_name(read_call.args[0], aliases) != "file_fd"
        or all(
            read_call is not node
            for node in _function_nodes(module_functions["_read_exact"])
        )
    ):
        _fail("FORBIDDEN_CAPABILITY")

    helper_specs = {
        "_write_all": (2, ("staging_fd", "payload"), class_methods["publish"]),
        "_read_exact": (
            2,
            ("file_fd", None),
            class_methods["_reopen_and_validate"],
        ),
        "self._open_root": (0, (), class_methods["publish"]),
        "self._open_staging": (1, ("root_fd",), class_methods["publish"]),
    }
    for qualified_name, (argument_count, argument_names, owner) in helper_specs.items():
        calls = _exact_call_references(
            tree,
            aliases,
            qualified_name,
            1,
            "FORBIDDEN_CAPABILITY",
        )
        call = calls[0]
        if (
            len(call.args) != argument_count
            or call.keywords
            or any(
                expected is not None
                and _attribute_name(argument, aliases) != expected
                for argument, expected in zip(call.args, argument_names)
            )
            or all(call is not node for node in _function_nodes(owner))
        ):
            _fail("FORBIDDEN_CAPABILITY")


def _verify_publisher_safety(tree: ast.Module) -> None:
    aliases = _import_aliases(tree)
    for qualified, call in _qualified_calls(tree):
        if qualified in {
            "os.replace",
            "os.rename",
            "pathlib.Path.replace",
            "pathlib.Path.rename",
        }:
            _fail("CLOBBER_PRIMITIVE_FORBIDDEN")

    publisher_classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AtomicShapePublisher"
    ]
    if len(publisher_classes) != 1:
        _fail("NO_CLOBBER_GUARD_MISSING")
    publisher_class = publisher_classes[0]
    _verify_publisher_open_closure(tree, publisher_class, aliases)
    _verify_publisher_io_closure(tree, publisher_class, aliases)
    publish_methods = [
        node
        for node in publisher_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "publish"
    ]
    if len(publish_methods) != 1:
        _fail("NO_CLOBBER_GUARD_MISSING")
    publish_method = publish_methods[0]
    publish_calls = [
        (_attribute_name(node.func, aliases), node)
        for node in _function_nodes(publish_method)
        if isinstance(node, ast.Call)
    ]

    secure_links = [
        call
        for qualified, call in publish_calls
        if qualified == "os.link" and _secure_publish_link(call, aliases)
    ]
    if len(secure_links) != 1:
        _fail("NO_CLOBBER_GUARD_MISSING")
    link_call = secure_links[0]
    target_aliases = _target_aliases(publish_method, aliases)

    target_mutators = {
        "os.chmod",
        "os.chown",
        "os.open",
        "os.remove",
        "os.truncate",
        "os.unlink",
        "os.utime",
    }
    for qualified, call in publish_calls:
        mentions_target = any(
            _node_mentions(argument, "self._target_name", aliases)
            or any(
                isinstance(child, ast.Name) and child.id in target_aliases
                for child in ast.walk(argument)
            )
            for argument in list(call.args)
            + [keyword.value for keyword in call.keywords if keyword.arg is not None]
        )
        if mentions_target and qualified in target_mutators:
            _fail("CLOBBER_PRIMITIVE_FORBIDDEN")
        if (
            mentions_target
            and qualified == "self._unlink_if_owned"
            and call.lineno < link_call.lineno
        ):
            _fail("CLOBBER_PRIMITIVE_FORBIDDEN")

    reopen_calls = [
        (qualified, call)
        for qualified, call in publish_calls
        if qualified.startswith("self.")
        and "reopen" in qualified.rsplit(".", 1)[-1].casefold()
        and len(call.args) >= 2
        and _attribute_name(call.args[1], aliases) == "self._target_name"
        and call.lineno > link_call.lineno
    ]
    if len(reopen_calls) != 1:
        _fail("REOPEN_GUARD_MISSING")
    reopen_name = reopen_calls[0][0].rsplit(".", 1)[-1]
    reopen_methods = [
        node
        for node in publisher_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == reopen_name
    ]
    if len(reopen_methods) != 1:
        _fail("REOPEN_GUARD_MISSING")
    _verify_reopen_method(reopen_methods[0], aliases)


def _verify_fault_test_inventory(tree: ast.Module) -> None:
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "StrictVerifierFaultInjectionTests"
    ]
    if len(classes) != 1:
        _fail("VERIFIER_TESTS_INCOMPLETE")
    discovered = {
        node.name
        for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }
    if not REQUIRED_VERIFIER_TESTS.issubset(discovered):
        _fail("VERIFIER_TESTS_INCOMPLETE")


def _verify_global_body_surface(trees: Mapping[str, ast.Module]) -> None:
    raw_loads = [
        node
        for relative in PRODUCTION_FILES
        for node in ast.walk(trees[relative])
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Load)
        and node.attr == "raw_content"
    ]
    if len(raw_loads) != 1:
        _fail("FLOW_BODY_GATE_INVALID")


def _semantic_checks(root: Path, *, require_manifest: bool) -> Mapping[str, bytes]:
    actual_files = _verify_inventory(root, require_manifest=require_manifest)
    canary = "".join(("SYNTHETIC", "_PRIVATE", "_CANARY")).encode("ascii")
    trees: Dict[str, ast.Module] = {}
    snapshot: Dict[str, bytes] = {}

    for relative in sorted(actual_files):
        maximum = MAX_MANIFEST_BYTES if relative == MANIFEST_RELATIVE else MAX_SOURCE_BYTES
        data = _read_regular(root, relative, maximum)
        snapshot[relative] = data
        if canary in data:
            _fail("SENSITIVE_CANARY_LEAK")
        if relative.endswith(".py"):
            trees[relative] = _parse_python(relative, _decode_source(data))

    for relative in PRODUCTION_FILES:
        tree = trees[relative]
        _verify_imports(relative, tree)
        _verify_calls(relative, tree)
        _verify_output_keys(relative, tree)

    _verify_sensitive_rules(trees)
    _verify_atomic_endpoint_selector(trees["autocapture/policy.py"])
    _verify_global_body_surface(trees)
    _verify_addon_bootstrap(trees["autocapture/addon.py"])
    _verify_flow_capabilities(trees["autocapture/addon.py"])
    _verify_publisher_safety(trees["autocapture/publisher.py"])
    _verify_fault_test_inventory(trees["autocapture/tests/test_verifier.py"])
    return snapshot


def _no_duplicate_object(pairs: Sequence[Tuple[str, object]]) -> MutableMapping[str, object]:
    result: Dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("MANIFEST_JSON_INVALID")
        result[key] = value
    return result


def _load_manifest(raw: bytes) -> Mapping[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_object)
    except VerificationFailure:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        _fail("MANIFEST_JSON_INVALID")
    if not isinstance(value, Mapping):
        _fail("MANIFEST_SCHEMA_INVALID")
    return value


def _expected_manifest_entries(snapshot: Mapping[str, bytes]) -> List[Mapping[str, object]]:
    entries: List[Mapping[str, object]] = []
    for relative in sorted(EXPECTED_FILES - {MANIFEST_RELATIVE}):
        data = snapshot.get(relative)
        if data is None:
            _fail("MANIFEST_MISMATCH")
        entries.append(
            {
                "path": relative,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return entries


def _verify_manifest(snapshot: Mapping[str, bytes]) -> int:
    raw = snapshot.get(MANIFEST_RELATIVE)
    if raw is None:
        _fail("MISSING_FILE")
    manifest = _load_manifest(raw)
    if set(manifest) != {"schema_version", "hash_algorithm", "entries"}:
        _fail("MANIFEST_SCHEMA_INVALID")
    if manifest.get("schema_version") != MANIFEST_SCHEMA or manifest.get("hash_algorithm") != "sha256":
        _fail("MANIFEST_SCHEMA_INVALID")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        _fail("MANIFEST_SCHEMA_INVALID")

    seen: Set[str] = set()
    normalized: List[Mapping[str, object]] = []
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {"path", "bytes", "sha256"}:
            _fail("MANIFEST_SCHEMA_INVALID")
        path = entry.get("path")
        byte_count = entry.get("bytes")
        digest = entry.get("sha256")
        if (
            not isinstance(path, str)
            or path in seen
            or path == MANIFEST_RELATIVE
            or path.startswith("/")
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or type(byte_count) is not int
            or byte_count < 0
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            _fail("MANIFEST_SCHEMA_INVALID")
        seen.add(path)
        normalized.append({"path": path, "bytes": byte_count, "sha256": digest})

    expected = _expected_manifest_entries(snapshot)
    if normalized != expected:
        _fail("MANIFEST_MISMATCH")
    return len(expected)


def _assert_snapshot_current(root: Path, snapshot: Mapping[str, bytes]) -> None:
    try:
        actual = _verify_inventory(root, require_manifest=True)
        if actual != set(snapshot):
            _fail("TREE_CHANGED_DURING_VERIFY")
        for relative in sorted(actual):
            maximum = MAX_MANIFEST_BYTES if relative == MANIFEST_RELATIVE else MAX_SOURCE_BYTES
            if _read_regular(root, relative, maximum) != snapshot[relative]:
                _fail("TREE_CHANGED_DURING_VERIFY")
        if _verify_inventory(root, require_manifest=True) != actual:
            _fail("TREE_CHANGED_DURING_VERIFY")
    except VerificationFailure as failure:
        if failure.code == "TREE_CHANGED_DURING_VERIFY":
            raise
        _fail("TREE_CHANGED_DURING_VERIFY")


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    offset = 0
    while offset < len(view):
        try:
            written = os.write(descriptor, view[offset:])
        except OSError:
            _fail("MANIFEST_WRITE_FAILED")
        if written <= 0:
            _fail("MANIFEST_WRITE_FAILED")
        offset += written


def _write_manifest(root: Path) -> int:
    snapshot = dict(_semantic_checks(root, require_manifest=False))
    entries = _expected_manifest_entries(snapshot)
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "hash_algorithm": "sha256",
        "entries": entries,
    }
    payload = (
        json.dumps(manifest, ensure_ascii=True, sort_keys=True, indent=2, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")
    parent = root / "autocapture"
    temporary = parent / ".build-manifest.tmp"
    destination = parent / "build-manifest.json"
    descriptor: Optional[int] = None
    try:
        descriptor = os.open(str(temporary), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(str(temporary), str(destination))
        directory_descriptor = os.open(
            str(parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except VerificationFailure:
        raise
    except OSError:
        _fail("MANIFEST_WRITE_FAILED")
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            if temporary.exists() and not temporary.is_symlink():
                temporary.unlink()
        except OSError:
            pass
    snapshot[MANIFEST_RELATIVE] = payload
    _verify_manifest(snapshot)
    _assert_snapshot_current(root, snapshot)
    return len(entries)


def _strict_verify(root: Path) -> int:
    snapshot = _semantic_checks(root, require_manifest=True)
    count = _verify_manifest(snapshot)
    _assert_snapshot_current(root, snapshot)
    return count


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify the offline autocapture build")
    parser.add_argument("--repo-root", default=".")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--strict", action="store_true")
    mode.add_argument("--write-manifest", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        root = _assert_root(Path(arguments.repo_root))
        if arguments.write_manifest:
            count = _write_manifest(root)
            status = "AUTOCAPTURE_BUILD_MANIFEST_WRITTEN"
        else:
            count = _strict_verify(root)
            status = "AUTOCAPTURE_STRICT_VERIFY_PASS"
        print(
            json.dumps(
                {
                    "status": status,
                    "file_count": len(EXPECTED_FILES),
                    "manifest_entries": count,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except VerificationFailure as failure:
        print(
            json.dumps(
                {
                    "status": "AUTOCAPTURE_STRICT_VERIFY_FAIL",
                    "reason": failure.code,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        print(
            '{"reason":"VERIFIER_INTERRUPTED","status":"AUTOCAPTURE_STRICT_VERIFY_FAIL"}',
            file=sys.stderr,
        )
        return 130
    except SystemExit as exit_signal:
        code = exit_signal.code
        return code if isinstance(code, int) else 2
    except BaseException:
        print(
            '{"reason":"VERIFIER_INTERNAL_ERROR","status":"AUTOCAPTURE_STRICT_VERIFY_FAIL"}',
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
