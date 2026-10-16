import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from collection_adapter import p32_result_entry as entry
from collection_adapter.p31_context_codes_export import FILES


class ResultEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.name = 'p31_confirmed_units_' + 'a' * 32
        self.bundle = self.root / self.name
        self.bundle.mkdir(mode=0o700)
        self.manifest = dict(schema_version='p31-business-manifest/v7',
            result_name=self.name, window_ref='result:' + 'b' * 32,
            record_count=3, product_count=2, sku_count=3, category_count=1,
            store_record_count=1, public_text_record_count=2,
            public_code_record_count=2, files=list(FILES), coverage_status='PARTIAL',
            complete_result_promotion=False, target_system_import_verified=False,
            live_attempts_consumed=0)
        for filename in FILES:
            path = self.bundle / filename
            # Deliberately not business data: the entry must not parse these files.
            path.write_text('SYNTHETIC_CONTENT_NOT_FOR_DISPLAY')
            path.chmod(0o600)
        self.save_manifest()

    def save_manifest(self):
        (self.bundle / 'manifest.json').write_text(json.dumps(self.manifest))

    def inspect(self):
        # Root precheck is covered by its own tests; use an isolated synthetic root.
        with patch.object(entry, '_root', return_value=self.root, create=True):
            return entry.inspect_result(self.root, self.name)

    def test_available_files_are_not_claimed_as_verified_business_data(self):
        result = self.inspect()
        self.assertEqual(result['status'], 'LOCAL_FILES_PRESENT')
        self.assertEqual(result['declared_counts']['record_count'], 3)
        self.assertFalse(result['business_data_revalidated'])
        self.assertFalse(result['all_store_products_complete'])
        self.assertEqual(result['images'], 'EXCLUDED_BY_USER')
        self.assertEqual(set(result['files']), set(FILES))
        self.assertNotIn('SYNTHETIC_CONTENT', json.dumps(result))

    def test_missing_file_has_actionable_fixed_failure(self):
        (self.bundle / 'records.csv').unlink()
        result = self.inspect()
        self.assertEqual(result['status'], 'RESULT_UNAVAILABLE')
        self.assertEqual(result['code'], 'P32_RESULT_FILE_MISSING')
        self.assertNotIn('files', result)

    def test_manifest_mismatch_is_not_accepted(self):
        for field, value in [('result_name', 'p31_confirmed_units_' + 'c' * 32),
                             ('coverage_status', 'COMPLETE'), ('record_count', -1)]:
            with self.subTest(field=field):
                old = self.manifest[field]
                self.manifest[field] = value
                self.save_manifest()
                self.assertEqual(self.inspect()['code'], 'P32_MANIFEST_INVALID')
                self.manifest[field] = old

    def test_symlink_or_nonprivate_file_is_rejected(self):
        path = self.bundle / 'records.csv'
        path.chmod(0o644)
        self.assertEqual(self.inspect()['code'], 'P32_RESULT_FILE_UNSAFE')
        path.unlink()
        path.symlink_to(self.bundle / 'stores.csv')
        self.assertEqual(self.inspect()['code'], 'P32_RESULT_FILE_UNSAFE')

    def test_invalid_name_and_missing_bundle(self):
        self.assertEqual(entry.inspect_result(self.root, '../escape')['code'], 'P32_RESULT_NAME_INVALID')
        with patch.object(entry, '_root', return_value=self.root, create=True):
            result = entry.inspect_result(self.root, 'p31_confirmed_units_' + 'd' * 32)
        self.assertEqual(result['code'], 'P32_RESULT_NOT_FOUND')

    def test_cli_failure_redacts_exception_and_exits_nonzero(self):
        with patch.object(entry, '_root', side_effect=OSError('SYNTHETIC_PRIVATE_ERROR'), create=True):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = entry.main(['--json'])
        self.assertEqual(code, 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result['status'], 'RESULT_UNAVAILABLE')
        self.assertNotIn('SYNTHETIC_PRIVATE_ERROR', output.getvalue())

    def test_cli_success_shows_existing_files_and_partial_scope(self):
        result = self.inspect()
        with patch.object(entry, 'inspect_result', return_value=result):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = entry.main([])
        self.assertEqual(code, 0)
        self.assertIn('3 行，2 个商品，3 个 SKU，1 个分类', output.getvalue())
        self.assertIn('PARTIAL', output.getvalue())
        self.assertIn(str(self.bundle / 'records.csv'), output.getvalue())
        self.assertNotIn('SYNTHETIC_CONTENT', output.getvalue())


if __name__ == '__main__':
    unittest.main()
