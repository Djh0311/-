from __future__ import annotations

import asyncio
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from autocapture.publisher import AtomicShapePublisher, PublisherError
from autocapture.shape import SanitizedShape, ShapeAccumulator
from autocapture.tests.fakes import ALLOWED_JSON_KEYS, SENSITIVE_SCHEMA_KEY_VARIANTS


def _shape_with_scalar(scalar: str = "synthetic") -> SanitizedShape:
    clock = lambda: 1.0
    accumulator = ShapeAccumulator(
        max_depth=16,
        max_nodes=200,
        max_paths=100,
        max_events=4,
        allowed_schema_keys=ALLOWED_JSON_KEYS,
        clock=clock,
        deadline=10.0,
    )
    raw = bytearray(
        json.dumps(
            {
                "items": [{"name": scalar}],
                "store": {"active": True, "count": 1},
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    try:
        accumulator.commit(accumulator.stage_json_bytes(raw))
    finally:
        for index in range(len(raw)):
            raw[index] = 0
    return accumulator.build()


def _publisher(
    root: object,
    target_name: str = "shape-bundle.json",
    allowed_schema_keys: frozenset = ALLOWED_JSON_KEYS,
) -> AtomicShapePublisher:
    return AtomicShapePublisher(
        os.path.realpath(os.path.abspath(os.fspath(root))),
        target_name,
        allowed_schema_keys=allowed_schema_keys,
    )


def _assert_code(test: unittest.TestCase, error: PublisherError, code: str) -> None:
    test.assertEqual(error.code, code)
    test.assertEqual(str(error), code)


class AtomicShapePublisherTests(unittest.TestCase):
    def test_success_is_canonical_private_and_has_closed_manifest(self) -> None:
        scalar = "".join(("SYNTHETIC", "_SCALAR", "_CANARY"))
        shape = _shape_with_scalar(scalar)
        with tempfile.TemporaryDirectory() as root:
            result = _publisher(root).publish(shape)
            target = Path(root, "shape-bundle.json")

            self.assertEqual(os.listdir(root), ["shape-bundle.json"])
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            payload = target.read_bytes()
            self.assertNotIn(scalar.encode("utf-8"), payload)
            self.assertEqual(payload, payload.rstrip(b"\n") + b"\n")
            self.assertEqual(json.loads(payload), result)
            self.assertEqual(
                set(result),
                {"schema_version", "manifest", "sanitized_shape"},
            )
            self.assertEqual(
                set(result["manifest"]),
                {
                    "schema_version",
                    "artifact_kind",
                    "sanitized_shape_digest",
                },
            )
            self.assertEqual(
                result["manifest"]["sanitized_shape_digest"],
                shape.sanitized_shape_digest,
            )
            self.assertEqual(
                result["sanitized_shape"]["sanitized_shape_digest"],
                shape.sanitized_shape_digest,
            )

    def test_wrong_type_and_subclass_are_rejected_before_filesystem_use(self) -> None:
        class DerivedShape(SanitizedShape):
            pass

        shape = _shape_with_scalar()
        derived = DerivedShape(
            event_count=shape.event_count,
            nodes=shape.nodes,
            sanitized_shape_digest=shape.sanitized_shape_digest,
            _allowed_schema_keys=shape._allowed_schema_keys,
        )
        for value in (object(), derived):
            with self.subTest(value_type=type(value).__name__):
                with tempfile.TemporaryDirectory() as root:
                    with self.assertRaises(PublisherError) as raised:
                        _publisher(root).publish(value)
                    _assert_code(
                        self,
                        raised.exception,
                        "PUBLISH_SHAPE_TYPE_INVALID",
                    )
                    self.assertEqual(os.listdir(root), [])

    def test_target_must_be_a_basename(self) -> None:
        invalid = (
            "",
            ".",
            "..",
            "../escape.json",
            "nested/shape.json",
            "nested\\shape.json",
            "/absolute.json",
        )
        for target_name in invalid:
            with self.subTest(target_name=target_name):
                with tempfile.TemporaryDirectory() as root:
                    with self.assertRaises(PublisherError) as raised:
                        _publisher(root, target_name)
                    _assert_code(
                        self,
                        raised.exception,
                        "PUBLISH_TARGET_NAME_INVALID",
                    )

    def test_publisher_key_policy_rejects_sensitive_or_unfrozen_keys(self) -> None:
        invalid_key_sets = tuple(
            frozenset((key,))
            for key in SENSITIVE_SCHEMA_KEY_VARIANTS
        ) + (
            frozenset(),
            frozenset(("apiKey",)),
            frozenset(("sk_live_abcdefghijklmnopqrstuvwxyz",)),
            frozenset(("field.with.dot",)),
        )
        for keys in invalid_key_sets:
            with self.subTest(key_count=len(keys)):
                with self.assertRaises(PublisherError) as raised:
                    AtomicShapePublisher(
                        "/not-observed",
                        allowed_schema_keys=keys,
                    )
                _assert_code(self, raised.exception, "PUBLISH_POLICY_INVALID")

    def test_root_must_exist_and_must_not_be_file_or_symlink(self) -> None:
        shape = _shape_with_scalar()
        with tempfile.TemporaryDirectory() as parent:
            missing = Path(parent, "missing")
            with self.assertRaises(PublisherError) as raised:
                _publisher(missing).publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_ROOT_INVALID")

            file_root = Path(parent, "file-root")
            file_root.write_bytes(b"fixed")
            with self.assertRaises(PublisherError) as raised:
                _publisher(file_root).publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_ROOT_INVALID")
            self.assertEqual(file_root.read_bytes(), b"fixed")

            real_root = Path(parent, "real-root")
            real_root.mkdir()
            linked_root = Path(parent, "linked-root")
            linked_root.symlink_to(real_root, target_is_directory=True)
            with self.assertRaises(PublisherError) as raised:
                AtomicShapePublisher(
                    str(linked_root),
                    allowed_schema_keys=ALLOWED_JSON_KEYS,
                )
            _assert_code(self, raised.exception, "PUBLISH_ROOT_INVALID")
            self.assertEqual(os.listdir(real_root), [])

            shared_root = Path(parent, "shared-root")
            shared_root.mkdir(mode=0o700)
            shared_root.chmod(0o755)
            with self.assertRaises(PublisherError) as raised:
                _publisher(shared_root).publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_ROOT_INVALID")
            self.assertEqual(os.listdir(shared_root), [])

    def test_root_must_be_absolute_canonical_and_identity_stable(self) -> None:
        shape = _shape_with_scalar()
        with tempfile.TemporaryDirectory() as raw_parent:
            parent = Path(raw_parent).resolve()

            with self.assertRaises(PublisherError) as raised:
                AtomicShapePublisher(
                    "relative-root",
                    allowed_schema_keys=ALLOWED_JSON_KEYS,
                )
            _assert_code(self, raised.exception, "PUBLISH_ROOT_INVALID")

            outside = parent / "outside"
            outside.mkdir(mode=0o700)
            alias = parent / "alias-parent"
            alias.symlink_to(parent, target_is_directory=True)
            with self.assertRaises(PublisherError) as raised:
                AtomicShapePublisher(
                    str(alias / "outside"),
                    allowed_schema_keys=ALLOWED_JSON_KEYS,
                )
            _assert_code(self, raised.exception, "PUBLISH_ROOT_INVALID")
            self.assertEqual(os.listdir(outside), [])

            root = parent / "stable-root"
            root.mkdir(mode=0o700)
            publisher = _publisher(root)
            moved = parent / "moved-root"
            root.rename(moved)
            root.mkdir(mode=0o700)
            with self.assertRaises(PublisherError) as raised:
                publisher.publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_ROOT_INVALID")
            self.assertEqual(os.listdir(root), [])
            self.assertEqual(os.listdir(moved), [])

    def test_root_open_cancellation_closes_local_descriptor(self) -> None:
        class SyntheticCancellation(BaseException):
            pass

        shape = _shape_with_scalar()
        with tempfile.TemporaryDirectory() as root:
            publisher = _publisher(root)
            opened_fds = []
            real_open = os.open

            def recording_open(*args, **kwargs):
                file_fd = real_open(*args, **kwargs)
                opened_fds.append(file_fd)
                return file_fd

            with mock.patch(
                "autocapture.publisher.os.open",
                side_effect=recording_open,
            ), mock.patch(
                "autocapture.publisher.os.fstat",
                side_effect=SyntheticCancellation(),
            ):
                with self.assertRaises(PublisherError) as raised:
                    publisher.publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_ABORTED")
            self.assertEqual(len(opened_fds), 1)
            with self.assertRaises(OSError):
                os.fstat(opened_fds[0])
            self.assertEqual(os.listdir(root), [])

    def test_existing_target_file_is_never_changed(self) -> None:
        shape = _shape_with_scalar()
        original = b"preexisting-target"
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "shape-bundle.json")
            target.write_bytes(original)
            before = target.stat()
            with self.assertRaises(PublisherError) as raised:
                _publisher(root).publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_TARGET_EXISTS")
            after = target.stat()
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
            self.assertEqual(os.listdir(root), ["shape-bundle.json"])

    def test_existing_target_symlink_is_never_followed_or_changed(self) -> None:
        shape = _shape_with_scalar()
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            outside = Path(other, "outside.json")
            outside.write_bytes(b"outside-stays-fixed")
            target = Path(root, "shape-bundle.json")
            target.symlink_to(outside)
            original_link = os.readlink(target)

            with self.assertRaises(PublisherError) as raised:
                _publisher(root).publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_TARGET_EXISTS")
            self.assertTrue(target.is_symlink())
            self.assertEqual(os.readlink(target), original_link)
            self.assertEqual(outside.read_bytes(), b"outside-stays-fixed")
            self.assertEqual(os.listdir(root), ["shape-bundle.json"])

    def test_digest_and_schema_are_recomputed_before_staging(self) -> None:
        shape = _shape_with_scalar()
        bad_digest = shape.to_model()
        bad_digest["sanitized_shape_digest"] = "sha256:" + ("0" * 64)
        bad_schema = shape.to_model()
        bad_schema["unexpected"] = "synthetic"

        cases = (
            (bad_digest, "PUBLISH_SHAPE_DIGEST_INVALID"),
            (bad_schema, "PUBLISH_SHAPE_SCHEMA_INVALID"),
        )
        for model, code in cases:
            with self.subTest(code=code):
                with tempfile.TemporaryDirectory() as root:
                    with mock.patch.object(
                        SanitizedShape,
                        "to_model",
                        autospec=True,
                        return_value=model,
                    ):
                        with self.assertRaises(PublisherError) as raised:
                            _publisher(root).publish(shape)
                    _assert_code(self, raised.exception, code)
                    self.assertEqual(os.listdir(root), [])

    def test_privacy_rejects_sensitive_pointer_without_staging(self) -> None:
        shape = _shape_with_scalar()
        marker = "".join(("SYNTHETIC", "_PRIVATE", "_CANARY"))
        for replacement in SENSITIVE_SCHEMA_KEY_VARIANTS + (
            "token",
            "apiKey",
            marker,
            "SYNTHETIC_SECRET_CANARY",
            "sk_live_abcdefghijklmnopqrstuvwxyz",
            "1234567890123456",
        ):
            with self.subTest(replacement_kind=replacement != "token"):
                model = shape.to_model()
                for node in model["nodes"]:
                    if node["path"] == "/store":
                        node["path"] = "/" + replacement
                    elif node["path"].startswith("/store/"):
                        node["path"] = "/" + replacement + node["path"][len("/store") :]
                        node["parent"] = "/" + replacement

                with tempfile.TemporaryDirectory() as root:
                    with mock.patch.object(
                        SanitizedShape,
                        "to_model",
                        autospec=True,
                        return_value=model,
                    ):
                        with self.assertRaises(PublisherError) as raised:
                            _publisher(root).publish(shape)
                    _assert_code(self, raised.exception, "PUBLISH_PRIVACY_REJECTED")
                    self.assertEqual(os.listdir(root), [])

    def test_safe_unregistered_pointer_publishes_and_reopens(self) -> None:
        registered = frozenset(("store",))
        accumulator = ShapeAccumulator(
            max_depth=16,
            max_nodes=200,
            max_paths=100,
            max_events=4,
            allowed_schema_keys=registered,
            clock=lambda: 1.0,
            deadline=10.0,
        )
        raw = bytearray(
            b'{"store":{"discoveryExtra":[{"nestedField":"synthetic"}]}}'
        )
        try:
            accumulator.commit(accumulator.stage_json_bytes(raw))
        finally:
            for index in range(len(raw)):
                raw[index] = 0
        shape = accumulator.build()

        with tempfile.TemporaryDirectory() as root:
            result = _publisher(
                root,
                allowed_schema_keys=registered,
            ).publish(shape)
            target = Path(root, "shape-bundle.json")
            reopened = json.loads(target.read_bytes())

        paths = {node["path"] for node in result["sanitized_shape"]["nodes"]}
        self.assertTrue(
            {
                "/store/discoveryExtra",
                "/store/discoveryExtra/*/nestedField",
            }.issubset(paths)
        )
        self.assertEqual(reopened, result)
        self.assertNotIn("synthetic", json.dumps(result, sort_keys=True))

    def test_pointer_classifier_rejects_sensitive_and_true_unknown_tampering(self) -> None:
        shape = _shape_with_scalar()
        cases = ("accessToken", "event.field")
        for replacement in cases:
            with self.subTest(replacement_kind=replacement):
                model = shape.to_model()
                for node in model["nodes"]:
                    if node["path"] == "/store":
                        node["path"] = "/" + replacement
                    elif node["path"].startswith("/store/"):
                        node["path"] = "/" + replacement + node["path"][len("/store") :]
                        node["parent"] = "/" + replacement

                with tempfile.TemporaryDirectory() as root:
                    with mock.patch.object(
                        SanitizedShape,
                        "to_model",
                        autospec=True,
                        return_value=model,
                    ):
                        with self.assertRaises(PublisherError) as raised:
                            _publisher(root).publish(shape)
                    _assert_code(self, raised.exception, "PUBLISH_PRIVACY_REJECTED")
                    self.assertEqual(os.listdir(root), [])

    def test_staging_write_failure_is_value_free_and_leaves_no_file(self) -> None:
        shape = _shape_with_scalar()
        fault_detail = "".join(("SYNTHETIC", "_FAULT", "_DETAIL"))
        with tempfile.TemporaryDirectory() as root:
            with mock.patch(
                "autocapture.publisher.os.write",
                side_effect=OSError(fault_detail),
            ):
                with self.assertRaises(PublisherError) as raised:
                    _publisher(root).publish(shape)
            _assert_code(
                self,
                raised.exception,
                "PUBLISH_STAGING_WRITE_FAILED",
            )
            self.assertNotIn(fault_detail, repr(raised.exception))
            self.assertNotIn(root, repr(raised.exception))
            self.assertEqual(os.listdir(root), [])

    def test_cancellation_is_sanitized_and_cleans_staging(self) -> None:
        shape = _shape_with_scalar()
        fault_detail = "".join(("SYNTHETIC", "_CANCEL", "_DETAIL"))
        with tempfile.TemporaryDirectory() as root:
            with mock.patch(
                "autocapture.publisher.os.write",
                side_effect=asyncio.CancelledError(fault_detail),
            ):
                with self.assertRaises(PublisherError) as raised:
                    _publisher(root).publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_ABORTED")
            self.assertNotIn(fault_detail, repr(raised.exception))
            self.assertEqual(os.listdir(root), [])

    def test_promotion_failure_cleans_staging_and_has_no_target(self) -> None:
        shape = _shape_with_scalar()
        with tempfile.TemporaryDirectory() as root:
            with mock.patch(
                "autocapture.publisher.os.link",
                side_effect=OSError("synthetic promotion detail"),
            ):
                with self.assertRaises(PublisherError) as raised:
                    _publisher(root).publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_PROMOTION_FAILED")
            self.assertEqual(os.listdir(root), [])

    def test_atomic_no_clobber_race_preserves_competing_target(self) -> None:
        shape = _shape_with_scalar()
        competing = b"competing-target-stays-fixed"
        with tempfile.TemporaryDirectory() as root:

            def install_competing_target(*_args: object, **_kwargs: object) -> None:
                Path(root, "shape-bundle.json").write_bytes(competing)
                raise FileExistsError()

            with mock.patch(
                "autocapture.publisher.os.link",
                side_effect=install_competing_target,
            ):
                with self.assertRaises(PublisherError) as raised:
                    _publisher(root).publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_TARGET_EXISTS")
            self.assertEqual(
                Path(root, "shape-bundle.json").read_bytes(),
                competing,
            )
            self.assertEqual(os.listdir(root), ["shape-bundle.json"])

    def test_post_commit_cancellation_is_resolved_by_inode_and_reopen(self) -> None:
        shape = _shape_with_scalar()
        real_link = os.link

        def commit_then_cancel(*args: object, **kwargs: object) -> None:
            real_link(*args, **kwargs)
            raise asyncio.CancelledError("synthetic post-commit cancellation")

        with tempfile.TemporaryDirectory() as root:
            with mock.patch(
                "autocapture.publisher.os.link",
                side_effect=commit_then_cancel,
            ):
                result = _publisher(root).publish(shape)
            self.assertEqual(
                result["manifest"]["sanitized_shape_digest"],
                shape.sanitized_shape_digest,
            )
            self.assertEqual(os.listdir(root), ["shape-bundle.json"])

    def test_staging_path_swap_is_detected_and_never_reported_success(self) -> None:
        shape = _shape_with_scalar()
        replacement = b"untrusted-staging-replacement"
        real_link = os.link

        def replace_source_then_link(
            source: str,
            target: str,
            *,
            src_dir_fd: int,
            dst_dir_fd: int,
            follow_symlinks: bool,
        ) -> None:
            os.unlink(source, dir_fd=src_dir_fd)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            replacement_fd = os.open(source, flags, 0o600, dir_fd=src_dir_fd)
            try:
                os.write(replacement_fd, replacement)
                os.fsync(replacement_fd)
            finally:
                os.close(replacement_fd)
            real_link(
                source,
                target,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
                follow_symlinks=follow_symlinks,
            )

        with tempfile.TemporaryDirectory() as root:
            with mock.patch(
                "autocapture.publisher.os.link",
                side_effect=replace_source_then_link,
            ):
                with self.assertRaises(PublisherError) as raised:
                    _publisher(root).publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_CLEANUP_FAILED")
            self.assertEqual(
                Path(root, "shape-bundle.json").read_bytes(),
                replacement,
            )

    def test_reopen_read_failure_retains_complete_sanitized_target(self) -> None:
        shape = _shape_with_scalar()
        with tempfile.TemporaryDirectory() as root:
            with mock.patch(
                "autocapture.publisher.os.read",
                side_effect=OSError("synthetic reopen detail"),
            ):
                with self.assertRaises(PublisherError) as raised:
                    _publisher(root).publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_REOPEN_FAILED")
            self.assertEqual(os.listdir(root), ["shape-bundle.json"])
            retained = json.loads(Path(root, "shape-bundle.json").read_bytes())
            self.assertEqual(
                retained["manifest"]["sanitized_shape_digest"],
                shape.sanitized_shape_digest,
            )

    def test_reopen_content_mismatch_retains_complete_sanitized_target(self) -> None:
        shape = _shape_with_scalar()
        with tempfile.TemporaryDirectory() as root:
            with mock.patch(
                "autocapture.publisher.os.read",
                side_effect=(b"{}\n", b""),
            ):
                with self.assertRaises(PublisherError) as raised:
                    _publisher(root).publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_REOPEN_INVALID")
            self.assertEqual(os.listdir(root), ["shape-bundle.json"])
            retained = json.loads(Path(root, "shape-bundle.json").read_bytes())
            self.assertEqual(
                retained["manifest"]["sanitized_shape_digest"],
                shape.sanitized_shape_digest,
            )

    def test_reopen_failure_does_not_delete_replacement_inode(self) -> None:
        shape = _shape_with_scalar()
        replacement = b"replacement-inode-stays-fixed"
        with tempfile.TemporaryDirectory() as root:

            def replace_then_fail(
                root_fd: int,
                target_name: str,
                _identity: object,
                _payload: object,
            ) -> dict:
                os.unlink(target_name, dir_fd=root_fd)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                file_fd = os.open(target_name, flags, 0o600, dir_fd=root_fd)
                try:
                    os.write(file_fd, replacement)
                    os.fsync(file_fd)
                finally:
                    os.close(file_fd)
                raise PublisherError("PUBLISH_REOPEN_FAILED")

            with mock.patch.object(
                AtomicShapePublisher,
                "_reopen_and_validate",
                side_effect=replace_then_fail,
            ):
                with self.assertRaises(PublisherError) as raised:
                    _publisher(root).publish(shape)
            _assert_code(self, raised.exception, "PUBLISH_REOPEN_FAILED")
            self.assertEqual(
                Path(root, "shape-bundle.json").read_bytes(),
                replacement,
            )
            self.assertEqual(os.listdir(root), ["shape-bundle.json"])


if __name__ == "__main__":
    unittest.main()
