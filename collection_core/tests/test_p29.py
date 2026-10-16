import copy
import csv
from dataclasses import fields, replace
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from collection_core.p0 import P0Context
from collection_core.p28 import build_p28_batch
from collection_core.p28_result_views import render_p28_result
from collection_core.p29 import P29Error, render_collection, snapshot_from_views
from collection_core.result_publisher import publish_result_set, ResultPublishError
from collection_core.tests.test_p28 import scenario
from parser_candidate.p28_profile import p28_registry


WINDOW = 'result:' + 'a' * 32


def association():
    out = {'schema_version': 'p26-result-association-check/v1', 'window_ref': WINDOW,
        'merchant_container': '$.data.poi_info', 'store_name_match': True,
        'public_string_id_ready': True, 'numeric_id_is_negative': True,
        'public_id_fields_equal_as_text': False, 'food_success_code': True,
        'product_success_code': True, 'same_observation_gap_valid': True,
        'raw_payload_persisted': False, 'sensitive_values_processed': False}
    for label in ('food', 'product'):
        for key in ('wm_poi_id', 'poi_id_str'):
            out[label + '_' + key + '_ready'] = True
            out[label + '_' + key + '_matches_public_string_id'] = key == 'poi_id_str'
            out[label + '_' + key + '_matches_numeric_id'] = key == 'wm_poi_id'
    out['wm_poi_id_equal_between_requests'] = out['poi_id_str_equal_between_requests'] = True
    return out


def snapshot(index=1, modify=None):
    events, context, evidence = scenario()
    if modify:
        modify(events)
    refs = {f.name: getattr(context, f.name) + '_' + str(index)
            for f in fields(P0Context) if f.name.endswith('_ref')}
    context = replace(context, **refs, observed_at=f'2026-10-09T16:35:{index:02d}+00:00')
    evidence = {**evidence, 'evidence_ref': context.evidence_ref}
    binding = build_p28_batch(events, p28_registry(), context, evidence)
    views = render_p28_result(binding)
    categories = []
    for c in events[1].payload['data']['food_spu_tags']:
        categories.append({'category_ref': c['tag'], 'category_name': c['name'],
            'source_page_number': 0, 'source_has_next_page': False,
            'source_reported_product_count': 0,
            'loaded_product_ids': [str(p['id']) for p in c['dynamic_spus']],
            'folded_product_ids': ['909'], 'page_semantics': 'UNCONFIRMED',
            'termination_semantics': 'UNCONFIRMED'})
    return snapshot_from_views(views, categories, association(), WINDOW)


class P29CollectionTests(unittest.TestCase):
    def test_repeated_snapshots_deduplicate_whole_rows_and_keep_history(self):
        first = snapshot()
        def change(events):
            p = events[1].payload['data']['food_spu_tags'][0]['dynamic_spus'][0]
            p['name'] = 'New synthetic name'
            p['skus'][1]['price'] = 19.25
        second = snapshot(2, change)
        v = render_collection([first, second]); out = json.loads(v.json_bytes)
        self.assertEqual((out['observation_count'], out['input_record_count'], out['record_count'],
                          out['deduplicated_record_count']), (2, 4, 2, 2))
        self.assertEqual({r['collection_observation_index'] for r in out['records']}, {'2'})
        self.assertEqual({r['observed_at'] for r in out['records']}, {second['view']['observed_at']})
        self.assertEqual({r['product'] for r in out['records']}, {'New synthetic name'})
        self.assertEqual([r['sku_price_yuan'] for r in out['records']], ['12.50', '19.25'])
        self.assertEqual(v.snapshots[0]['view'], first['view'])
        self.assertEqual(out['coverage_status'], 'PARTIAL')

    def test_later_empty_spec_never_borrows_earlier_text(self):
        def earlier(events):
            events[1].payload['data']['food_spu_tags'][0]['dynamic_spus'][0]['skus'][0]['spec'] = 'Synthetic earlier'
        out = json.loads(render_collection([snapshot(1, earlier), snapshot(2)]).json_bytes)
        self.assertEqual((out['records'][0]['sku_spec'], out['records'][0]['sku_spec_state']), ('', 'SOURCE_EMPTY'))

    def test_sku_not_repeated_later_remains_a_complete_older_observation(self):
        def fewer(events):
            events[1].payload['data']['food_spu_tags'][0]['dynamic_spus'][0]['skus'].pop()
        first, second = snapshot(), snapshot(2, fewer)
        out = json.loads(render_collection([first, second]).json_bytes)
        self.assertEqual([r['collection_observation_index'] for r in out['records']], ['2', '1'])
        self.assertEqual(out['records'][1]['observed_at'], first['view']['observed_at'])

    def test_cross_category_memberships_and_same_name_distinct_ids_remain(self):
        def expand(events):
            categories = events[1].payload['data']['food_spu_tags']
            second = copy.deepcopy(categories[0]); second.update(tag='synthetic-b', name='Synthetic B')
            categories.append(second)
            new = copy.deepcopy(categories[0]['dynamic_spus'][0]); new['id'] = 102
            for i, sku in enumerate(new['skus']): sku['id'] = 2001 + i
            categories[0]['dynamic_spus'].append(new)
        out = json.loads(render_collection([snapshot(1, expand)]).json_bytes)
        self.assertEqual((out['product_count'], out['sku_count'], out['category_count'], out['record_count']), (2, 4, 2, 6))

    def test_owner_change_does_not_merge_or_mutate_completed_snapshot(self):
        def change(events):
            events[1].payload['data']['food_spu_tags'][0]['dynamic_spus'][0]['id'] = 102
        original = snapshot(); before = copy.deepcopy(original)
        with self.assertRaisesRegex(P29Error, '^P29_SKU_OWNER_CHANGED$'):
            render_collection([original, snapshot(2, change)])
        self.assertEqual(original, before)

    def test_reused_or_out_of_order_observation_is_rejected(self):
        for items, code in (([snapshot(), snapshot()], 'P29_OBSERVATION_REUSED'),
                            ([snapshot(2), snapshot()], 'P29_OBSERVATION_ORDER_INVALID')):
            with self.subTest(code=code), self.assertRaisesRegex(P29Error, '^' + code + '$'):
                render_collection(items)

    def test_other_source_and_store_are_rejected(self):
        other = snapshot(2)
        # A forged type label cannot pass regeneration of its bound source.
        other['view']['source_kind'] = 'SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE'
        with self.assertRaises(P29Error): render_collection([snapshot(), other])
        def other_shop(events): events[0].payload['data']['poi_info']['poi_id_str'] = 'synthetic_other'
        with self.assertRaisesRegex(P29Error, '^P29_SOURCE_CHANGED$'):
            render_collection([snapshot(), snapshot(2, other_shop)])

    def test_category_gap_is_not_filled_by_same_product_loaded_in_another_category(self):
        s = snapshot(); loaded = s['categories'][0]['loaded_product_ids'][0]
        s['categories'].append({'category_ref': 'synthetic-b', 'category_name': 'Synthetic B',
            'source_page_number': 0, 'source_has_next_page': False, 'source_reported_product_count': 0,
            'loaded_product_ids': [], 'folded_product_ids': [loaded],
            'page_semantics': 'UNCONFIRMED', 'termination_semantics': 'UNCONFIRMED'})
        out = json.loads(render_collection([s]).json_bytes)
        self.assertEqual((out['folded_product_references_not_loaded'],
                          out['category_product_references_not_loaded']), (1, 2))
        self.assertEqual(out['termination_semantics'], 'UNCONFIRMED')

    def test_unproved_termination_and_incomplete_rows_are_rejected(self):
        s = snapshot(); s['categories'][0]['termination_semantics'] = 'COMPLETE'
        with self.assertRaisesRegex(P29Error, '^P29_TERMINATION_UNPROVEN$'): render_collection([s])
        s = snapshot(); del s['binding']['sku_records'][0]['sku_price_minor']
        with self.assertRaises(P29Error): render_collection([s])

    def test_bounds_and_invalid_ids_have_closed_errors(self):
        for limit in ('MAX_OBSERVATIONS', 'MAX_ROWS', 'MAX_COLLECTION_BYTES'):
            with self.subTest(limit=limit), patch('collection_core.p29.' + limit, 1):
                with self.assertRaisesRegex(P29Error, '^P29_COLLECTION_BUDGET$'):
                    render_collection([snapshot(), snapshot(2)])
        s = snapshot(); s['categories'][0]['folded_product_ids'] = [{}]
        with self.assertRaisesRegex(P29Error, '^P29_COVERAGE_INVALID$'): render_collection([s])

    def test_published_json_csv_manifest_are_consistent_and_no_clobber(self):
        v = render_collection([snapshot(), snapshot(2)])
        with tempfile.TemporaryDirectory() as root:
            root = os.path.realpath(root); os.chmod(root, 0o700)
            publish_result_set(root, 'synthetic_p29', v)
            p = Path(root)/'synthetic_p29'
            out = json.loads((p/'records.json').read_bytes())
            rows = list(csv.DictReader(io.StringIO((p/'records.csv').read_text())))
            manifest = json.loads((p/'manifest.json').read_bytes())
            self.assertEqual(rows, out['records'])
            for key in out:
                if key not in {'schema_version', 'records', 'category_observations'}:
                    self.assertEqual(out[key], manifest[key])
            before = {q.name: q.read_bytes() for q in p.iterdir()}
            self.assertTrue(all(q.stat().st_mode & 0o777 == 0o600 for q in p.iterdir()))
            with self.assertRaisesRegex(ResultPublishError, '^RESULT_TARGET_EXISTS$'):
                publish_result_set(root, 'synthetic_p29', v)
            self.assertEqual(before, {q.name: q.read_bytes() for q in p.iterdir()})

    def test_tampered_views_fail_before_destination_creation(self):
        v = render_collection([snapshot()])
        for changed in (replace(v, csv_bytes=b'fake'), replace(v, json_bytes=b'{}')):
            with tempfile.TemporaryDirectory() as root:
                root = os.path.realpath(root); os.chmod(root, 0o700)
                with self.assertRaisesRegex(ResultPublishError, '^RESULT_INPUT_INVALID$'):
                    publish_result_set(root, 'synthetic_p29', changed)
                self.assertEqual(list(Path(root).iterdir()), [])

    def test_closed_collection_schemas_and_extra_field_rejection(self):
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
        from collection_core.p29 import collection_manifest
        schemas = Path(__file__).parents[2]/'contracts'/'schemas'
        registry = Registry()
        for file in schemas.glob('*.schema.json'):
            registry = registry.with_resource(file.name, Resource.from_contents(json.loads(file.read_text())))
        views = render_collection([snapshot(), snapshot(2)])
        for name, value in (('p29-result-view-v1', json.loads(views.json_bytes)),
                            ('p29-result-manifest-v1', json.loads(collection_manifest(views, 'synthetic_p29')[0]))):
            schema = json.loads((schemas/(name+'.schema.json')).read_text())
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
            self.assertEqual([(list(e.path), e.validator) for e in validator.iter_errors(value)], [])
            self.assertFalse(validator.is_valid({**value, 'unexpected': 'synthetic'}))


if __name__ == '__main__': unittest.main()
