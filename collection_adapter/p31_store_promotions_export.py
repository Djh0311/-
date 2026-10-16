"""Export only own FOOD store tags; never infer customer coupon eligibility."""

import argparse
import json
import os
import re
from uuid import uuid4

from parser_candidate.p31_store_promotions import parse_store_promotions, SOURCE_PATH
from . import p31_business_export as base
from .p29_store_inventory import _initial, _validate
from collection_core.result_publisher import (
    ResultPublishError, _DIRECTORY_FLAGS, _write_file, precheck_result_destination,
)

SCHEMA = 'p31-store-promotions-v1.schema.json'
MANIFEST_SCHEMA = 'p31-store-promotions-manifest-v1.schema.json'
FILES = ('records.json', 'records.csv', 'manifest.json')
COLUMNS = ('store_id', 'scope', 'group_index', 'tag_index', 'display_text', 'state',
           'endpoint_id', 'source_path', 'source_file', 'source_request_ref',
           'observed_at', 'window_ref')
_NAME = re.compile(r'p31_store_promotions_[a-f0-9]{32}')


def promotion_view(root, observation_name):
    root = base._root(root)
    public, _, _, _ = _initial(root, observation_name)
    food = next(o for o in public['observations'] if o['endpoint_id'] == 'FOOD')
    store_id = next(v['value'] for v in food['public_values']
                    if v['coordinates'] == ['data', 'poi_info', 'poi_id_str'])
    rows = [{**row, 'store_id': store_id, 'scope': 'STORE_DISPLAY',
             'endpoint_id': 'FOOD', 'source_path': SOURCE_PATH,
             'source_file': observation_name + '-public-fields.json',
             'source_request_ref': food['source_request_ref'],
             'observed_at': food['observed_at'], 'window_ref': public['window_ref']}
            for row in parse_store_promotions(food)]
    doc = {'schema_version': 'p31-store-promotions/v1', 'window_ref': public['window_ref'],
           'record_count': len(rows), 'records': rows,
           'customer_eligibility_confirmed': False, 'stacking_confirmed': False,
           'validity_confirmed': False, 'copied_into_product_rows': False}
    _validate(doc, SCHEMA)
    return doc


def publish_store_promotions(root, observation_name, result_name=None):
    root = base._root(root)
    name = result_name if result_name is not None else 'p31_store_promotions_' + uuid4().hex
    if type(name) is not str or _NAME.fullmatch(name) is None:
        base._fail('P31_EXPORT_NAME_INVALID')
    precheck_result_destination(str(root), name)
    doc = promotion_view(root, observation_name)
    manifest = {'schema_version': 'p31-store-promotions-manifest/v1',
                'result_name': name, 'window_ref': doc['window_ref'],
                'record_count': doc['record_count'], 'files': list(FILES),
                'source_kind': 'OWN_INITIAL_FOOD_PUBLIC_PROJECTION',
                'scope': 'STORE_DISPLAY', 'customer_eligibility_confirmed': False,
                'stacking_confirmed': False, 'validity_confirmed': False,
                'screenshot_values_used': False, 'live_attempts_consumed': 0}
    _validate(manifest, MANIFEST_SCHEMA)
    contents = (base._bytes(doc), base._csv_bytes(doc['records'], COLUMNS), base._bytes(manifest))
    if sum(map(len, contents)) > 16 * 1024 * 1024:
        base._fail('P31_EXPORT_BUDGET')
    root_fd = result_fd = None
    created = success = False
    try:
        root_fd = os.open(root, _DIRECTORY_FLAGS)
        os.mkdir(name, 0o700, dir_fd=root_fd); created = True
        result_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        for filename, content in zip(FILES, contents):
            _write_file(result_fd, filename, content)
        os.fsync(result_fd); os.fsync(root_fd); success = True
    except FileExistsError:
        raise ResultPublishError('RESULT_TARGET_EXISTS') from None
    except OSError:
        raise ResultPublishError('RESULT_PUBLISH_FAILED') from None
    finally:
        if created and not success:
            if result_fd is not None:
                for filename in FILES:
                    try: os.unlink(filename, dir_fd=result_fd)
                    except OSError: pass
            if root_fd is not None:
                try: os.rmdir(name, dir_fd=root_fd)
                except OSError: pass
        for fd in (result_fd, root_fd):
            if fd is not None:
                os.close(fd)
    return {'result_name': name, 'record_count': doc['record_count'], 'live_attempts_consumed': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--observation-name', required=True)
    args = parser.parse_args()
    from pathlib import Path
    from .p29_receiver_control import ReceiverControlError
    from parser_candidate.p29_category_profile import CategoryCandidateError
    try:
        print(json.dumps(publish_store_promotions(Path(args.output_root), args.observation_name)))
        return 0
    except (ResultPublishError, ReceiverControlError, CategoryCandidateError) as error:
        print(json.dumps({'code': error.code}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
