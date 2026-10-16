"""Prove shop scope from the current pair's numeric IDs, without ID rewriting."""

from collection_core.p29_source_association import (
    NUMERIC_MARKERS, NUMERIC_REQUIRED, NUMERIC_VERSION, p29_association_ready,
)
from .p26_identification import IdentificationError
from .p26_public_projection import FOOD_ROUTE, PRODUCT_ROUTE, is_business_origin
from .p26_result_mapping import current_routing_id


def numeric_store_association(window, check):
    # Validate cheap, value-free scope before revisiting approved public IDs.
    if (not window.active() or type(check) is not dict
            or check.get('schema_version') != 'p26-result-association-check/v1'
            or check.get('window_ref') != window.window_ref
            or check.get('merchant_container') != '$.data.poi_info'
            or not all(check.get(k) is True for k in NUMERIC_REQUIRED)
            or any(check.get(k) is not False for k in (
                'food_poi_id_str_matches_public_string_id',
                'product_poi_id_str_matches_public_string_id'))):
        return None
    rows = {window.routes[r['route_slot']][2]: r for r in window.projected_observations}
    if set(rows) != {FOOD_ROUTE, PRODUCT_ROUTE} or any(
            window.routes[r['route_slot']][0] != 'POST'
            or not is_business_origin(window.route_origins[r['route_slot']])
            for r in rows.values()):
        return None
    values = {tuple(v['coordinates']): v['value'] for v in rows[FOOD_ROUTE]['values']}
    numeric = values.get(('data', 'poi_info', 'id'))
    public = values.get(('data', 'poi_info', 'poi_id_str'))
    if type(numeric) is not int or type(public) is not str or not 1 <= len(public) <= 256:
        return None
    try:
        selectors = [current_routing_id(window, rows[r], 'poi_id_str')
                     for r in (FOOD_ROUTE, PRODUCT_ROUTE)]
        if (selectors[0] != selectors[1] or selectors[0] == public
                or any(current_routing_id(window, rows[r], 'wm_poi_id') != str(numeric)
                       for r in (FOOD_ROUTE, PRODUCT_ROUTE))):
            return None
    except IdentificationError:
        return None
    proof = {**check, 'schema_version': NUMERIC_VERSION, **NUMERIC_MARKERS}
    return proof if p29_association_ready(proof, window.window_ref) else None
