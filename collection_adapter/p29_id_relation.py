"""Describe a current routing-ID mismatch without changing qualification.

Only already-approved public IDs are compared after this pair's store name,
numeric IDs, success codes and observation interval have passed. No identifier,
request body, hash or decoded private parameter becomes an output value.
"""

import re
import unicodedata
from urllib.parse import unquote

from .p26_identification import IdentificationError
from .p26_public_projection import FOOD_ROUTE, PRODUCT_ROUTE, is_business_origin
from .p26_result_mapping import current_routing_id

_GUARDS = (
    'store_name_match', 'food_success_code', 'product_success_code',
    'same_observation_gap_valid', 'public_string_id_ready',
    'food_wm_poi_id_ready', 'product_wm_poi_id_ready',
    'food_wm_poi_id_matches_numeric_id', 'product_wm_poi_id_matches_numeric_id',
    'wm_poi_id_equal_between_requests', 'food_poi_id_str_ready',
    'product_poi_id_str_ready', 'poi_id_str_equal_between_requests',
)
_ESCAPE = re.compile(r'%[0-9a-fA-F]{2}')


def _kind(value):
    if not value.isascii():
        return 'NON_ASCII'
    if value.isdecimal():
        return 'ASCII_DECIMAL'
    if value[:1] in ('-', '+') and value[1:].isdecimal():
        return 'ASCII_SIGNED_DECIMAL'
    return 'ASCII_OTHER'


def _url_equal(value, other):
    try:
        return unquote(value, errors='strict') == other
    except UnicodeError:
        return None


def inspect_current_id_relation(window, check):
    """Return fixed markers/counts, or None before reading an unverified scope.

    Encoding comparisons are diagnostic observations. They never provide an
    alternate ID, activate a mapping rule or make a business record qualified.
    """
    if (not window.active() or type(check) is not dict
            or check.get('window_ref') != window.window_ref
            or check.get('merchant_container') != '$.data.poi_info'
            or not all(check.get(key) is True for key in _GUARDS)
            or any(check.get(key) is not False for key in (
                'food_poi_id_str_matches_public_string_id',
                'product_poi_id_str_matches_public_string_id'))):
        return None
    rows = {window.routes[row['route_slot']][2]: row
            for row in window.projected_observations}
    if set(rows) != {FOOD_ROUTE, PRODUCT_ROUTE}:
        return None
    if any(window.routes[row['route_slot']][0] != 'POST'
           or not is_business_origin(window.route_origins[row['route_slot']])
           for row in rows.values()):
        return None
    source = [v['value'] for v in rows[FOOD_ROUTE]['values']
              if v['path'] == '$.data.poi_info.poi_id_str'
              and v['coordinates'] == ['data', 'poi_info', 'poi_id_str']]
    if len(source) != 1 or type(source[0]) is not str or not 1 <= len(source[0]) <= 256:
        return None
    response = source[0]
    try:
        request = current_routing_id(window, rows[FOOD_ROUTE], 'poi_id_str')
        other = current_routing_id(window, rows[PRODUCT_ROUTE], 'poi_id_str')
    except IdentificationError:
        return None
    if request != other or request == response:
        return None
    normalize = lambda value: unicodedata.normalize('NFKC', value).replace(' ', '')
    return {
        'schema_version': 'p29-routing-id-relation/v1',
        'window_ref': window.window_ref,
        'food_request_ref': rows[FOOD_ROUTE]['source_request_ref'],
        'product_request_ref': rows[PRODUCT_ROUTE]['source_request_ref'],
        'food_observed_at': rows[FOOD_ROUTE]['observed_at'],
        'product_observed_at': rows[PRODUCT_ROUTE]['observed_at'],
        'scope_basis': 'CURRENT_PAIR_NAME_NUMERIC_IDS_SUCCESS_AND_WITHIN_10_SECONDS',
        'request_pair_equal': True, 'request_equals_response': False,
        'request_string_kind': _kind(request), 'response_string_kind': _kind(response),
        'request_string_length': len(request), 'response_string_length': len(response),
        'request_contains_url_escape': bool(_ESCAPE.search(request)),
        'response_contains_url_escape': bool(_ESCAPE.search(response)),
        'one_more_request_url_decode_equals_response': _url_equal(request, response),
        'one_response_url_decode_equals_request': _url_equal(response, request),
        'nfkc_space_free_strings_equal': normalize(request) == normalize(response),
        'field_role_relation': 'UNCONFIRMED', 'mapping_rule_qualified': False,
        'business_record_count': 0, 'parameter_values_returned': False,
        'raw_payload_persisted': False, 'sensitive_values_processed': False,
    }
