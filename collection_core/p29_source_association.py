"""Closed P29 identity evidence; distinct string fields are never aliases."""

import re

LEGACY_VERSION = 'p26-result-association-check/v1'
NUMERIC_VERSION = 'p29-numeric-store-association/v1'
NUMERIC_BASIS = 'CURRENT_RESPONSE_NUMERIC_ID_MATCHES_BOTH_REQUESTS'
LEGACY_REQUIRED = (
    'store_name_match', 'food_success_code', 'product_success_code',
    'same_observation_gap_valid', 'public_string_id_ready',
    'food_poi_id_str_matches_public_string_id', 'product_poi_id_str_matches_public_string_id',
    'poi_id_str_equal_between_requests', 'food_wm_poi_id_matches_numeric_id',
    'product_wm_poi_id_matches_numeric_id', 'wm_poi_id_equal_between_requests',
)
NUMERIC_REQUIRED = tuple(k for k in LEGACY_REQUIRED
                        if not k.endswith('_poi_id_str_matches_public_string_id')) + (
    'food_wm_poi_id_ready', 'product_wm_poi_id_ready',
    'food_poi_id_str_ready', 'product_poi_id_str_ready',
)
LEGACY_KEYS = frozenset({
    'schema_version', 'window_ref', 'store_name_match', 'merchant_container',
    'public_string_id_ready', 'numeric_id_is_negative', 'public_id_fields_equal_as_text',
    'food_success_code', 'product_success_code', 'same_observation_gap_valid',
    'raw_payload_persisted', 'sensitive_values_processed',
} | {label + '_' + key + suffix for label in ('food', 'product')
     for key in ('wm_poi_id', 'poi_id_str')
     for suffix in ('_ready', '_matches_public_string_id', '_matches_numeric_id')}
  | {key + '_equal_between_requests' for key in ('wm_poi_id', 'poi_id_str')})
NUMERIC_MARKERS = {
    'identity_basis': NUMERIC_BASIS,
    'numeric_id_type': 'INTEGER',
    'string_id_relation': 'DISTINCT_FIELDS',
    'string_id_role': 'UNCONFIRMED',
}


def p29_association_ready(check, window_ref=None):
    if type(check) is not dict:
        return False
    numeric = check.get('schema_version') == NUMERIC_VERSION
    markers = set(NUMERIC_MARKERS) if numeric else set()
    if (set(check) != LEGACY_KEYS | markers
            or check.get('schema_version') not in (LEGACY_VERSION, NUMERIC_VERSION)
            or type(check.get('window_ref')) is not str
            or re.fullmatch(r'result:[a-f0-9]{32}', check['window_ref']) is None
            or window_ref is not None and check['window_ref'] != window_ref
            or check.get('merchant_container') != '$.data.poi_info'
            or check.get('raw_payload_persisted') is not False
            or check.get('sensitive_values_processed') is not False
            or any(type(v) is not bool and v is not None for k, v in check.items()
                   if k not in {'schema_version', 'window_ref', 'merchant_container'} | markers)
            or not all(check.get(k) is True for k in (NUMERIC_REQUIRED if numeric else LEGACY_REQUIRED))):
        return False
    if numeric:
        return (all(check.get(k) == v for k, v in NUMERIC_MARKERS.items())
                and all(check.get(k) is False for k in (
                    'food_poi_id_str_matches_public_string_id',
                    'product_poi_id_str_matches_public_string_id')))
    return True
