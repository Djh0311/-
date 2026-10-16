"""Initial-pair numeric relation and product-unit role, from the same source."""

import re
import sys

from . import p31_context_export as previous
from .p29_store_inventory import _initial, _align_initial_rows, _INITIAL_BASE_FIELDS, _validate
from .p29_receiver_control import ReceiverControlError
from parser_candidate.p29_category_price import parse_category_price
from parser_candidate.p29_category_profile import CategoryCandidateError

base = previous.base
PRODUCT_SCHEMA = 'p31-business-products-v4.schema.json'
MANIFEST_SCHEMA = 'p31-business-manifest-v5.schema.json'
MANIFEST_VERSION = 'p31-business-manifest/v5'
RESULT_PREFIX = 'p31_initial_relation_'
RESULT_CODE = 'P31_INITIAL_RELATION_EXPORTED'
_NAME = re.compile(r'p31_initial_relation_[a-f0-9]{32}')
DICTIONARY_SCHEMA = previous.DICTIONARY_SCHEMA
COVERAGE_SCHEMA = previous.COVERAGE_SCHEMA
FILES = previous.FILES
MAX_COLLECTION_BYTES = previous.MAX_COLLECTION_BYTES
_write_file = previous._write_file
field_dictionary = previous.field_dictionary
coverage_view = previous.coverage_view


def business_view(root, observation_name, input_names):
    try:
        products, stores, texts = previous.business_view(root, observation_name, input_names)
        _, product, _, source_rows = _initial(base._root(root), observation_name)
        parsed = _align_initial_rows(source_rows, parse_category_price(product).rows)
        located = {}
        for source, price in zip(source_rows, parsed):
            if (any(getattr(source, key) != getattr(price, key) for key in _INITIAL_BASE_FIELDS)
                    or price.numeric_relation_proves_currency or price.numeric_relation_proves_amount_unit):
                base._fail('P29_INVENTORY_INITIAL_ROW_MISMATCH')
            located[source.category_ref, source.product_id, source.sku_id] = price
        for row in products['records']:
            if row['source_kind'] != 'CHECKED_INITIAL_PAIR':
                continue
            price = located.get((row['category_ref'],row['product_id'],row['sku_id']))
            if (price is None or row['source_file'] != observation_name + '-public-fields.json'
                    or row['source_request_ref'] != product['source_request_ref']
                    or row['observed_at'] != product['observed_at']
                    or any(row[key] != getattr(price, key) for key in _INITIAL_BASE_FIELDS)):
                base._fail('P29_INVENTORY_INITIAL_ROW_MISMATCH')
            row['numeric_min_relation'] = price.numeric_min_relation
            row['product_unit_role'] = price.product_unit_role
        products['schema_version'] = 'p31-business-products/v4'
        products['initial_pair_relation_and_unit_role_reparsed'] = True
        _validate(products, PRODUCT_SCHEMA)
        return products, stores, texts
    except (CategoryCandidateError, ReceiverControlError):
        raise
    except (OSError, ValueError, KeyError, TypeError):
        base._fail()


def publish_business_fields(root, observation_name, input_names, result_name=None):
    return previous.publish_business_fields(root, observation_name, input_names, result_name,
                                           _profile=sys.modules[__name__])


def main():
    return previous.previous.previous.main(_profile=sys.modules[__name__])


if __name__ == '__main__':
    raise SystemExit(main())
