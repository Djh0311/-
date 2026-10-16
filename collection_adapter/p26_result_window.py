"""One fresh real-result attempt using the existing bounded P26 receiver."""
from pathlib import Path
from uuid import uuid4

from collection_core.p0 import P0Context, P0Error, build_p0_batch
from collection_core.result_publisher import ResultPublishError, publish_result_set
from collection_core.p26_result_views import render_p26_result
from parser_candidate.p26_profile import FAMILY, VERSION, VERSION_V2, p26_registry
from .p26_identification import IdentificationError, IdentificationWindow
from .p26_public_projection import RESULT_PATHS_BY_VERSION
from .p26_result_mapping import map_current_observation, check_current_association

PROFILE_KEYS=frozenset({"schema_version","profile_ref","runtime_target_ref","target_binding_ref",
 "target_confirmation_ref","capability_ref","source_identification_window_ref","payload_family",
 "payload_version","routing_parameter_key","currency","amount_unit","unit_evidence",
 "source_identity_evidence","price_relation","same_observation_rule","formal_qualification"})
PROFILE_KEYS_V2 = PROFILE_KEYS | {"merchant_container", "secondary_routing_parameter_key",
                                 "secondary_response_id_path"}


def validate_profile(profile,state):
    v2 = type(profile) is dict and profile.get("schema_version") == "p26-real-result-profile/v2"
    if (type(profile) is not dict or set(profile)!=(PROFILE_KEYS_V2 if v2 else PROFILE_KEYS)
        or profile["schema_version"]!=("p26-real-result-profile/v2" if v2 else "p26-real-result-profile/v1")
        or profile["payload_family"]!=FAMILY or profile["payload_version"]!=(VERSION_V2 if v2 else VERSION)
        or profile["routing_parameter_key"]!=("poi_id_str" if v2 else "wm_poi_id") or profile["currency"]!="CNY"
        or profile["amount_unit"]!="YUAN" or profile["formal_qualification"] is not False
        or profile["unit_evidence"]!="CURRENT_USER_PUBLIC_PAGE_CONFIRMATION_WITH_PRICE_MATCH"
        or profile["source_identity_evidence"]!=("CURRENT_STORE_NAME_BOTH_STRING_AND_NUMERIC_FORM_MATCHES" if v2 else "CURRENT_STORE_NAME_AND_BOTH_FORM_ID_MATCHES")
        or (v2 and (profile["merchant_container"]!="$.data.poi_info"
                    or profile["secondary_routing_parameter_key"]!="wm_poi_id"
                    or profile["secondary_response_id_path"]!="$.data.poi_info.id"))
        or profile["price_relation"]!="SPU_MIN_EQUALS_RENDER_AND_MIN_SKU"
        or profile["same_observation_rule"]!="FRESH_WINDOW_FIRST_PAIR_SAME_PUBLIC_STORE_WITHIN_10_SECONDS"
        or any(profile[k]!=state[k] for k in ("runtime_target_ref","target_binding_ref","target_confirmation_ref","capability_ref"))
        or type(profile["profile_ref"]) is not str or not profile["profile_ref"].startswith("profile:")
        or len(profile["profile_ref"])!=40
        or type(profile["source_identification_window_ref"]) is not str
        or not profile["source_identification_window_ref"].startswith("identification:")
        or len(profile["source_identification_window_ref"])!=47):
        raise IdentificationError("P26_RESULT_PROFILE_INVALID")
    return profile


class P26ResultWindow(IdentificationWindow):
    phase="RESULT"

    def __init__(self,expected_store,root,profile,**kwargs):
        if type(profile) is not dict:
            raise IdentificationError("P26_RESULT_PROFILE_INVALID")
        validate_profile(profile, profile)
        super().__init__(expected_store,**kwargs)
        self.window_ref="result:"+uuid4().hex
        self.root,self.profile=Path(root),profile
        self.read_scope="READ_"+uuid4().hex
        self.observation_scope="OBS_"+uuid4().hex
        self.key_layout_only=self.sensitive_key_layout_authorized=self.public_projection_enabled=True
        self.public_projection_paths=dict(RESULT_PATHS_BY_VERSION[profile["payload_version"]])
        self.qualified=self.parsed=self.published=0
        self.first_body_at=None
        self.source_proof=None
        self.association_check=None
        self.result_summary=None
        self.context=None
        self.code="P26_RESULT_NOT_STARTED"

    def start_once(self):
        super().start_once()
        self.code="P26_RESULT_RECEIVING"

    def _consume(self,route,body,*,source_request_ref=None):
        if self.first_body_at is None: self.first_body_at=self.last_clock
        super()._consume(route,body,source_request_ref=source_request_ref)
        if not self.active() or len(self.projected_observations)<2: return
        try:
            self.association_check=check_current_association(self)
            events,details,proof=map_current_observation(self,self.profile["profile_ref"],
                                                        self.read_scope,self.observation_scope,profile=self.profile)
            self.target_matches=2
            refs={key:key.removesuffix("_ref").replace("binding_context","context").replace("coverage_scope","scope")
                  .replace("_","-")+":"+uuid4().hex for key in P0Context.__dataclass_fields__
                  if key.endswith("_ref")}
            refs.update(run_ref="run:"+self.window_ref.split(":")[1],
                        attempt_ref="attempt:"+self.window_ref.split(":")[1],
                        observation_ref="observation:"+self.observation_scope.removeprefix("OBS_"))
            self.context=P0Context(**refs,source_kind="SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE",
                                   observed_at=proof["product_observed_at"],currency="CNY",coverage_status="PARTIAL")
            proof.update(run_ref=self.context.run_ref,observation_ref=self.context.observation_ref,
                         authorization_ref=self.context.authorization_ref,
                         capability_ref=self.profile["capability_ref"])
            batch=build_p0_batch(events,p26_registry(self.profile["payload_version"]),self.context)
            self.qualified=2
            self.parsed=len(batch["business_records"])
            views=render_p26_result(batch,details,proof)
            self.result_summary=publish_result_set(str(self.root),"first_result",views)
            self.published=self.result_summary["record_count"]
            self.source_proof=proof
            self.close("P26_RESULT_PUBLISHED")
        except IdentificationError as error:
            self.close(error.code)
        except P0Error:
            self.close("P26_RESULT_PARSE_FAILED")
        except ResultPublishError:
            self.close("P26_RESULT_PUBLISH_FAILED")
        except Exception:
            self.close("P26_RESULT_ASSEMBLY_FAILED")

    def active(self):
        active=super().active()
        if active and self.first_body_at is not None and self.last_clock-self.first_body_at>=60:
            self.close("P26_RESULT_EVENT_SET_EXPIRED")
            return False
        return active

    def close(self,code="P26_RESULT_CLOSED"):
        super().close(code)

    def diagnostic(self):
        result=super().diagnostic()
        result.update(schema_version="p26-result-diagnostic/v1",identification_attempts=0,
            result_attempts=self.attempts,qualified_business_events=self.qualified,
            parsed_records=self.parsed,published_records=self.published,
            execution_latch="OPEN" if self.state=="ACTIVE" else "CLOSED",
            product_result="complete" if self.published else "incomplete")
        return result
