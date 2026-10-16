"""A public projection of the observed store-detail route, separate from products.

This copy records the current selected page response. It does not infer store
identity, field meanings, or a verified product/store association.
"""

from uuid import uuid4

from .observation_time import observation_time
from .p26_identification import IdentificationError
from .p26_structure_budget import record_failure
from .p28_business_batch import analyze_public_body
from .p29_category_render import response_code_status


DETAIL_ROUTE = '/weapp/shop/v1/poi/detail'


class StoreDetailCopies:
    def __init__(self, window):
        self.window = window
        self.saved = self.rejected = 0
        self.rejected_at_least = False
        self.last_result = 'UNOBSERVED'

    def _reject(self, result):
        self.rejected_at_least |= self.rejected >= 128
        self.rejected = min(self.rejected + 1, 128)
        self.last_result = result

    def consume(self, route, body):
        window = self.window
        if not window.active() or not window.is_store_detail_route(route):
            return
        try:
            document = {
                'schema_version': 'p29-store-detail-public-copy/v1',
                'window_ref': window.window_ref, 'route': DETAIL_ROUTE,
                'route_slot': route, 'observed_at': observation_time(),
                'page_scope': 'CURRENT_USER_SELECTED_STORE_PAGE',
                'store_identity_verified': False, 'business_record_count': 0,
                'response_code_status': response_code_status(body),
                'public_analysis': analyze_public_body(body),
                'raw_payload_persisted': False, 'sensitive_values_processed': False,
            }
            size = window._check_budget(document)
            from .p26_identification_host import _write_new
            _write_new(window.root, 'store_detail_' + uuid4().hex + '-public-fields.json', document)
            self.saved += 1
            window._public_bytes += size
            window.last_body_route = route
            for category, count in document['public_analysis']['sensitive_rejections'].items():
                window.sensitive_rejections[category] = min(
                    128, window.sensitive_rejections[category] + count)
            self.last_result = 'PUBLIC_FIELDS_SAVED'
        except IdentificationError as error:
            record_failure(window, error)
            self._reject({'P26_STRUCTURE_INVALID': 'INVALID_JSON',
                'P26_STRUCTURE_BUDGET': 'STRUCTURE_LIMIT',
                'P26_TOTAL_SIZE_LIMIT': 'OUTPUT_LIMIT'}.get(error.code, 'COPY_REJECTED'))
        except Exception:
            self._reject('SAVE_FAILED')

    def diagnostic(self):
        return {'enabled': True, 'saved_responses': self.saved,
                'rejected_responses': self.rejected,
                'rejections_at_least': self.rejected_at_least,
                'last_result': self.last_result}
