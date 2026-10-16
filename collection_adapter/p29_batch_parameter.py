"""Inspect one observed batch key after the request's shop scope is verified.

The key is observed; its grammar and role are still unknown. JSON containers
are described lexically, with private branches opaque. Comparisons refer only
to public IDs in this response. They never establish pagination or price units.
No selected or unmatched parameter value is returned or persisted.
"""

from collections import Counter
import re
from urllib.parse import unquote_to_bytes

from .p26_identification import IdentificationError, MAX_BODY, key_only_layout
from .p26_result_mapping import current_routing_id

KEY = 'tag_spu_ids'
MAX_PARAMETER_BYTES = 16 * 1024
MAX_PARAMETER_PATHS = 128
MAX_PARAMETER_SCALARS = 4096
_BAD_PERCENT = re.compile(rb'%(?![0-9a-fA-F]{2})')
_PRODUCT_ID_PATH = '$.data.food_spu_tags[].dynamic_spus[].id'
_CATEGORY_PATH = '$.data.food_spu_tags[].tag'
ARRAY_PROFILE = 'p29-observed-batch-array-v1'
_ARRAY_FIELDS = {('$', 'array'), ('$[]', 'object'),
    ('$[].spuId', 'number'), ('$[].tagId', 'string'),
    ('$[].childTagId', 'string'), ('$[].tagType', 'number')}


def _empty_array_relation():
    return {'profile_version': ARRAY_PROFILE, 'status': 'PROFILE_NOT_OBSERVED',
        'item_count': 0, 'request_membership_count': 0,
        'matching_tag_membership_count': 0, 'matching_child_tag_membership_count': 0,
        'request_memberships_not_in_response': 0,
        'response_memberships_not_in_request': 0, 'duplicate_request_memberships': 0,
        'tag_type_semantics': 'UNCONFIRMED', 'child_tag_semantics': 'UNCONFIRMED'}


def _array_length(parameter):
    """Count an already validated array without decoding any value.

    Scalar coordinates omit empty objects. Count outer items separately so a
    trailing empty item cannot silently pass. Private strings remain bytes.
    """
    depth, quoted, escaped, commas, nonempty = 0, False, False, 0, False
    for byte in parameter.strip(b' \r\n\t')[1:-1]:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
            continue
        if byte not in b' \r\n\t':
            nonempty = True
        if byte == 34:
            quoted = True
        elif byte in (123, 91):
            depth += 1
        elif byte in (125, 93):
            depth -= 1
        elif byte == 44 and depth == 0:
            commas += 1
    return commas + 1 if nonempty else 0


def _array_relation(parameter, values, memberships, fields):
    report = _empty_array_relation()
    if not parameter.startswith(b'['):
        return report
    count = _array_length(parameter)
    if count > MAX_PARAMETER_SCALARS:
        raise IdentificationError('P26_STRUCTURE_BUDGET')
    report['item_count'] = count
    if not count:
        report.update(status='EMPTY_ARRAY', response_memberships_not_in_request=len(memberships))
        return report
    # Names/types were observed in window 6. Names alone do not prove roles.
    if {(r['path'], r['type']) for r in fields} != _ARRAY_FIELDS:
        return report
    items = {}
    for row in values:
        coordinates = row['coordinates']
        if (len(coordinates) != 3 or coordinates[0] != 'p29_parameter'
                or type(coordinates[1]) is not int or not 0 <= coordinates[1] < count
                or coordinates[2] not in {'spuId', 'tagId', 'childTagId', 'tagType'}):
            report['status'] = 'ARRAY_ITEMS_INVALID'
            return report
        item = items.setdefault(coordinates[1], {})
        if coordinates[2] in item:
            report['status'] = 'ARRAY_ITEMS_INVALID'
            return report
        item[coordinates[2]] = row['value']
    if (set(items) != set(range(count)) or any(
            set(item) != {'spuId', 'tagId', 'childTagId', 'tagType'}
            or type(item['spuId']) is not int or len(str(item['spuId'])) > 64
            or type(item['tagId']) is not str or type(item['childTagId']) is not str
            or type(item['tagType']) not in (int, float) for item in items.values())):
        report['status'] = 'ARRAY_ITEMS_INVALID'
        return report
    requested = {(r['tagId'], str(r['spuId'])) for r in items.values()}
    child_requested = {(r['childTagId'], str(r['spuId'])) for r in items.values()}
    duplicates = count - len(requested)
    report.update(request_membership_count=len(requested),
        matching_tag_membership_count=len(requested & memberships),
        matching_child_tag_membership_count=len(child_requested & memberships),
        request_memberships_not_in_response=len(requested - memberships),
        response_memberships_not_in_request=len(memberships - requested),
        duplicate_request_memberships=duplicates,
        status='MATCHED_CURRENT_RESPONSE' if requested == memberships and not duplicates
               else 'MEMBERSHIPS_DIFFER')
    return report


def _empty(status):
    return {'key': KEY, 'status': status, 'root_kind': 'UNOBSERVED',
        'fields': [], 'public_scalar_count': 0,
        'response_category_count': 0, 'response_product_count': 0,
        'response_category_product_membership_count': 0,
        'matching_category_id_count': 0, 'matching_product_id_count': 0,
        'matching_memberships_by_ancestor_key_count': 0,
        'array_item_relation': _empty_array_relation(),
        'unmatched_public_scalar_count': 0,
        'private_key_category_counts': {k: 0 for k in (
            'CREDENTIAL_KEY', 'SESSION_KEY', 'PERSONAL_KEY',
            'TRANSPORT_KEY', 'UNCLASSIFIED_KEY')},
        'parameter_role': 'UNKNOWN', 'grammar_qualified': False,
        'termination_semantics': 'UNCONFIRMED',
        'same_observation_record_ready': False,
        'can_publish_complete_result': False,
        'parameter_values_persisted': False, 'business_values_in_report': False,
        'sensitive_values_processed': False, 'raw_payload_persisted': False}


def _response_memberships(analysis):
    """Use only the already approved response's exact public coordinates."""
    tags, products = {}, {}
    for row in analysis['public_values']:
        c, value = row['coordinates'], row['value']
        if (row['path'] == _CATEGORY_PATH and len(c) == 4
                and c[:2] == ['data', 'food_spu_tags'] and type(c[2]) is int
                and 0 <= c[2] < 256 and c[3] == 'tag' and type(value) is str):
            tags[c[2]] = value
        elif (row['path'] == _PRODUCT_ID_PATH and len(c) == 6
                and c[:2] == ['data', 'food_spu_tags'] and type(c[2]) is int
                and 0 <= c[2] < 256 and c[3] == 'dynamic_spus'
                and type(c[4]) is int and 0 <= c[4] < 8000
                and c[5] == 'id' and type(value) is int and len(str(value)) <= 64):
            products[c[2], c[4]] = str(value)
    return {(tags[index], value) for (index, _), value in products.items() if index in tags}


def inspect_current_batch_parameter(window, route, request_ref, analysis):
    """Read the chosen key only under this request's current authorization.

    Expired, reused and other-shop inputs are refused before chosen-value URL
    decoding. Other FORM values are never decoded, including malformed private
    bytes. Scope proof is not a complete-record or source-version qualification.
    """
    inspector = getattr(window, 'render_inspector', None)
    if (not window.active() or inspector is None or inspector.target is None
            or request_ref not in inspector.authorized
            or request_ref in inspector.consumed or not window.is_category_route(route)):
        return _empty('SCOPE_UNAVAILABLE')
    lease = window.request_leases.get(request_ref)
    if (not lease or lease.get('route_slot') != route
            or lease.get('expires_at', 0) <= window.last_clock):
        return _empty('REQUEST_LEASE_UNAVAILABLE')
    try:
        row = {'route_slot': route, 'source_request_ref': request_ref}
        # Recheck the category route's two current response IDs, just as the
        # body authorization does. The initial-pair selector is diagnostic only.
        if (current_routing_id(window, row, 'poi_id_str') != inspector.target['response_public_string']
                or current_routing_id(window, row, 'wm_poi_id') != inspector.target['wm_poi_id']):
            return _empty('SCOPE_UNAVAILABLE')
    except IdentificationError:
        return _empty('SCOPE_UNAVAILABLE')
    if KEY not in lease.get('keys', []):
        return _empty('ABSENT')
    body = lease.get('body')
    if type(body) is not bytes or len(body) > MAX_BODY:
        raise IdentificationError('P26_STRUCTURE_BUDGET')
    selected = []
    for pair in body.split(b'&'):
        encoded_key, _, encoded_value = pair.partition(b'=')
        if unquote_to_bytes(encoded_key.replace(b'+', b' ')) == KEY.encode('ascii'):
            selected.append(encoded_value)
    if len(selected) != 1:
        return _empty('INVALID_ENCODING')
    if len(selected[0]) > MAX_PARAMETER_BYTES * 3:
        raise IdentificationError('P26_STRUCTURE_BUDGET')
    if _BAD_PERCENT.search(selected[0]):
        return _empty('INVALID_ENCODING')
    parameter = unquote_to_bytes(selected[0].replace(b'+', b' '))
    if len(parameter) > MAX_PARAMETER_BYTES:
        raise IdentificationError('P26_STRUCTURE_BUDGET')
    stripped = parameter.lstrip(b' \r\n\t')
    if not stripped.startswith((b'{', b'[')):
        return _empty('NOT_A_JSON_CONTAINER')
    # This artificial lexical root permits both object and array parameters.
    # Strip it from every reported source path and every comparison coordinate.
    wrapped = b'{"p29_parameter":' + parameter + b'}'
    try:
        definitions, _ = key_only_layout(wrapped)
        if len(definitions) > MAX_PARAMETER_PATHS:
            raise IdentificationError('P26_STRUCTURE_BUDGET')
        paths = frozenset(r['path'] for r in definitions
            if r['type'] in {'string', 'number', 'boolean', 'null'})
        values, unavailable = [], []
        definitions, categories = key_only_layout(wrapped, public_paths=paths,
            public_values=values, public_failures=unavailable,
            max_public_paths=MAX_PARAMETER_PATHS)
        if len(values) > MAX_PARAMETER_SCALARS:
            raise IdentificationError('P26_STRUCTURE_BUDGET')
    except IdentificationError as error:
        if error.code in ('P26_STRUCTURE_BUDGET', 'P26_RESPONSE_SIZE_LIMIT'):
            raise
        return _empty('MALFORMED_STRUCTURE')
    except (ValueError, UnicodeError, OverflowError):
        return _empty('MALFORMED_STRUCTURE')
    # Unsafe/unavailable scalar values do not qualify an ID grammar. Keep a
    # fixed failure marker rather than exporting such values or partial proof.
    if unavailable:
        return _empty('UNAVAILABLE_PUBLIC_SCALAR')
    memberships = _response_memberships(analysis)
    category_ids = {c for c, _ in memberships}
    product_ids = {p for _, p in memberships}
    matched_categories, matched_products, matched_memberships = set(), set(), set()
    unmatched = 0
    counts = Counter()
    for value in values:
        scalar = value['value']
        counts[value['path'], {str: 'string', int: 'number', float: 'number',
            bool: 'boolean', type(None): 'null'}[type(scalar)]] += 1
        comparable = str(scalar) if type(scalar) is int else scalar if type(scalar) is str else None
        ancestor_tags = {c for c in value['coordinates'][1:-1]
                         if type(c) is str and c in category_ids}
        matched_categories.update(ancestor_tags)
        matched = False
        if comparable in category_ids:
            matched_categories.add(comparable); matched = True
        if comparable in product_ids:
            matched_products.add(comparable); matched = True
            matched_memberships.update((c, comparable) for c in ancestor_tags
                                      if (c, comparable) in memberships)
        unmatched += not matched
    report = _empty('STRUCTURE_OBSERVED')
    report.update(root_kind='OBJECT' if stripped.startswith(b'{') else 'ARRAY',
        fields=[{'path': '$' + r['path'].removeprefix('$.p29_parameter'),
                 'type': r['type'], 'public_scalar_count': counts[r['path'], r['type']]}
                for r in definitions if r['path'] != '$'], public_scalar_count=len(values),
        private_key_category_counts=categories,
        response_category_count=len(category_ids), response_product_count=len(product_ids),
        response_category_product_membership_count=len(memberships),
        matching_category_id_count=len(matched_categories),
        matching_product_id_count=len(matched_products),
        matching_memberships_by_ancestor_key_count=len(matched_memberships),
        unmatched_public_scalar_count=unmatched)
    report['array_item_relation'] = _array_relation(stripped, values, memberships, report['fields'])
    return report
