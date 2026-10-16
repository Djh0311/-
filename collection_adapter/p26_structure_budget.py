"""Closed, value-free reasons for the existing structure rejection."""

LIMITS = {'NODES': 40000, 'DEPTH': 32, 'FIELD_DEFINITIONS': 4096,
          'RESTRICTED_DEFINITIONS': 4096, 'PUBLIC_VALUES': 8000,
          'CATALOG_DEFINITIONS': 4096}
STAGES = {'LEXICAL_SCAN', 'STRICT_SCAN', 'PUBLIC_PROJECTION', 'FIELD_CATALOG'}


def validate_detail(detail):
    if type(detail) is not dict or set(detail) != {'dimension', 'stage', 'limit', 'observed'}:
        return None
    dimension, stage = detail['dimension'], detail['stage']
    if type(dimension) is not str or dimension not in LIMITS or type(stage) is not str or stage not in STAGES:
        return None
    limit, observed = detail['limit'], detail['observed']
    if (type(limit) is not int or limit != LIMITS[dimension]
            or type(observed) is not int or not limit < observed <= 40001):
        return None
    return dict(detail)


def make_detail(dimension, observed, stage):
    return validate_detail({'dimension': dimension, 'stage': stage,
                            'limit': LIMITS.get(dimension), 'observed': observed})


def record_failure(window, error):
    if getattr(error, 'code', None) != 'P26_STRUCTURE_BUDGET' or window.state == 'CLOSED':
        return
    detail = validate_detail(getattr(error, 'structure_budget', None))
    if detail is not None and getattr(window, 'structure_budget_failure', None) is None:
        window.structure_budget_failure = detail
