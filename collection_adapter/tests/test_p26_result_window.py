"""Synthetic counterexamples for the rules discovered in current P26 input."""
import copy
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from collection_adapter.p26_identification import IdentificationError
from collection_adapter.p26_identification_host import _update_state
from collection_adapter.p26_public_projection import FOOD_ROUTE,PRODUCT_ROUTE,PUBLIC_PATHS
from collection_adapter.p26_request_metadata import RequestBudget,begin_form_metadata
from collection_adapter.p26_request_metadata import inspect_current_store_parameter
from collection_adapter.p26_result_window import P26ResultWindow,validate_profile


def profile():
    return {"schema_version":"p26-real-result-profile/v1","profile_ref":"profile:"+"a"*32,
      "runtime_target_ref":"target:"+"1"*32,"target_binding_ref":"target-binding:"+"2"*32,
      "target_confirmation_ref":"target-confirmation:"+"3"*32,"capability_ref":"capability:"+"4"*32,
      "source_identification_window_ref":"identification:"+"5"*32,
      "payload_family":"meituan_wechat_miniprogram","payload_version":"p26-observed-shop-v1",
      "routing_parameter_key":"wm_poi_id","currency":"CNY","amount_unit":"YUAN",
      "unit_evidence":"CURRENT_USER_PUBLIC_PAGE_CONFIRMATION_WITH_PRICE_MATCH",
      "source_identity_evidence":"CURRENT_STORE_NAME_AND_BOTH_FORM_ID_MATCHES",
      "price_relation":"SPU_MIN_EQUALS_RENDER_AND_MIN_SKU",
      "same_observation_rule":"FRESH_WINDOW_FIRST_PAIR_SAME_PUBLIC_STORE_WITHIN_10_SECONDS",
      "formal_qualification":False}


def bodies():
    food={"code":0,"data":{"poi_base_info":{"poi_id_str":"synthetic-store-id","name":"合成门店"},
        "discount_info":{"scopeToken":"SYNTHETIC_PRIVATE_VALUE"}}}
    product={"code":0,"data":{"food_spu_tags":[{"tag":"synthetic-category","name":"合成分类",
        "current_page":0,"has_next_page":False,"dynamic_spus":[{"id":501,"name":"合成商品",
        "min_price":7.42,"skus":[{"id":601,"spec":"合成规格","price":7.42,"status":0}],
        "render_info":{"price_info":{"min_price":7.42,"min_price_tail":"起"}}}]}],
        "container_template":{"show_shop_header":1}}}
    return food,product


def profile_v2():
    return {**profile(), "schema_version":"p26-real-result-profile/v2",
        "payload_version":"p26-observed-shop-v2", "routing_parameter_key":"poi_id_str",
        "source_identity_evidence":"CURRENT_STORE_NAME_BOTH_STRING_AND_NUMERIC_FORM_MATCHES",
        "merchant_container":"$.data.poi_info", "secondary_routing_parameter_key":"wm_poi_id",
        "secondary_response_id_path":"$.data.poi_info.id"}


class ResultWindowTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.root=Path(self.directory.name).resolve()
        os.chmod(self.root,0o700)
        self.time=[100.0]
        self.window=P26ResultWindow("合成门店",self.root,profile(),clock=lambda:self.time[0],duration_seconds=None)
    def tearDown(self):self.directory.cleanup()

    def start(self):
        self.window.start_once()
        slot=self.window.domain("wx.waimai.meituan.com");self.window.allow_domain(slot)
        self.routes=[]
        for route in [FOOD_ROUTE,PRODUCT_ROUTE]:
            r=self.window.route("POST","192.0.2.1",route,tls_domain="wx.waimai.meituan.com")
            self.window.select_route(r);self.routes.append(r)
        return self.routes

    def request(self,index,store="synthetic-store-id"):
        ref="request:"+("b" if index==0 else "c")*32
        c=begin_form_metadata(self.window,RequestBudget(self.window),ref,self.routes[index],[])
        c.feed(("userToken=SYNTHETIC_PRIVATE_VALUE&wm_poi_id="+store).encode());c.feed(b"")
        return ref

    def response(self,index,payload,ref):
        c=self.window.begin_response(self.routes[index],"identity",source_request_ref=ref)
        if c:c.feed(json.dumps(payload,ensure_ascii=False).encode());c.feed(b"")

    def run_pair(self,food=None,product=None,other_store=False):
        self.start();f,p=bodies()
        refs=[self.request(0),self.request(1,"other-synthetic-id" if other_store else "synthetic-store-id")]
        self.response(0,food or f,refs[0]);self.time[0]+=0.5
        self.response(1,product or p,refs[1])

    def test_prepare_never_calls_clock_or_consumes_attempt(self):
        with patch.object(self.window,"clock",side_effect=AssertionError):
            d=self.window.diagnostic()
        self.assertEqual((d["result_attempts"],d["identification_attempts"]),(0,0))
        self.assertEqual(d["execution_latch"],"CLOSED")
        self.assertFalse((self.root/"first_result").exists())

    def test_missing_unit_and_changed_target_do_not_become_ready(self):
        p=profile();state={k:p[k] for k in ("runtime_target_ref","target_binding_ref","target_confirmation_ref","capability_ref")}
        self.assertEqual(validate_profile(p,state),p)
        for key,value in [("amount_unit","UNKNOWN"),("runtime_target_ref","target:"+"f"*32),
                          ("payload_version","synthetic_p1"),("formal_qualification",True)]:
            wrong={**p,key:value}
            with self.assertRaises(IdentificationError):validate_profile(wrong,state)
        self.assertEqual(self.window.attempts,0)

    def test_fresh_result_is_consistent_and_private_values_are_not_decoded(self):
        original=json.loads
        def safe_loads(value,*args,**kwargs):
            if type(value) in (str,bytes):self.assertNotIn("SYNTHETIC_PRIVATE_VALUE",value.decode() if type(value)is bytes else value)
            return original(value,*args,**kwargs)
        with patch("collection_adapter.p26_identification.json.loads",side_effect=safe_loads):self.run_pair()
        d=self.window.diagnostic();self.assertEqual(d["code"],"P26_RESULT_PUBLISHED")
        self.assertEqual((d["result_attempts"],d["identification_attempts"],d["qualified_business_events"],d["parsed_records"],d["published_records"]),(1,0,2,1,1))
        root=self.root/"first_result";data=json.loads((root/"records.json").read_text())
        rows=list(csv.DictReader(io.StringIO((root/"records.csv").read_text())))
        manifest=json.loads((root/"manifest.json").read_text())
        self.assertEqual(rows,data["records"])
        self.assertEqual(manifest["source_proof"],data["source_proof"])
        self.assertEqual(rows[0]["price_yuan"],"7.42")
        self.assertEqual(rows[0]["price_description_state"],"SOURCE_NOT_PROVIDED")
        self.assertEqual(manifest["coverage_status"],"PARTIAL")
        self.assertFalse(self.window.request_leases or self.window.projected_observations or self.window.collectors)
        self.assertEqual(d["live_capture_latch"],d["execution_latch"])
        self.assertEqual(d["live_capture_latch"],"CLOSED")

    def test_other_store_parameter_cannot_form_complete_event(self):
        self.run_pair(other_store=True)
        self.assertEqual(self.window.code,"P26_RESULT_SOURCE_ASSOCIATION_INVALID")
        self.assertEqual(self.window.diagnostic()["qualified_business_events"],0)
        self.assertFalse((self.root/"first_result").exists())

    def test_placeholder_probe_match_is_named_and_cannot_publish_identity(self):
        self.start();food,products=bodies();food["data"]["poi_base_info"]["id"]=-1
        a=self.request(0,store="-1");b=self.request(1,store="-1")
        self.response(0,food,a)
        probe=inspect_current_store_parameter(self.window,a,"wm_poi_id")
        self.assertTrue(probe["matches_current_public_store_id"])
        self.assertEqual(probe["matched_public_id_paths"],["$.data.poi_base_info.id"])
        self.response(1,products,b)
        self.assertEqual(self.window.code,"P26_RESULT_SOURCE_ASSOCIATION_INVALID")
        check=self.window.association_check
        self.assertTrue(check["food_wm_poi_id_matches_numeric_id"])
        self.assertFalse(check["food_wm_poi_id_matches_public_string_id"])
        self.assertTrue(check["wm_poi_id_equal_between_requests"])
        self.assertIsNone(check["poi_id_str_equal_between_requests"])
        self.assertFalse((self.root/"first_result").exists())

    def test_newly_observed_container_is_identified_without_silent_result_fallback(self):
        self.start();food,products=bodies()
        food["data"]["poi_info"]=food["data"].pop("poi_base_info")
        food["data"]["poi_info"]["id"]=-123
        self.window.public_projection_paths[FOOD_ROUTE]=PUBLIC_PATHS[FOOD_ROUTE]
        a=self.request(0);b=self.request(1)
        self.response(0,food,a)
        probe=inspect_current_store_parameter(self.window,a,"wm_poi_id")
        self.assertEqual(probe["matched_public_id_paths"],["$.data.poi_info.poi_id_str"])
        self.response(1,products,b)
        self.assertEqual(self.window.association_check["merchant_container"],"$.data.poi_info")
        self.assertTrue(self.window.association_check["store_name_match"])
        self.assertTrue(self.window.association_check["food_wm_poi_id_matches_public_string_id"])
        self.assertEqual(self.window.code,"P26_RESULT_MAPPING_INVALID")
        self.assertFalse((self.root/"first_result").exists())

    def test_two_merchant_containers_are_ambiguous_even_when_names_match(self):
        self.start();food,products=bodies()
        food["data"]["poi_info"]=copy.deepcopy(food["data"]["poi_base_info"])
        self.window.public_projection_paths[FOOD_ROUTE]=PUBLIC_PATHS[FOOD_ROUTE]
        a=self.request(0);b=self.request(1)
        self.response(0,food,a);self.response(1,products,b)
        check=self.window.association_check
        self.assertEqual(check["merchant_container"],"AMBIGUOUS")
        self.assertFalse(check["store_name_match"])
        self.assertIsNone(check["food_wm_poi_id_matches_public_string_id"])
        self.assertFalse((self.root/"first_result").exists())

    def test_other_store_name_stops(self):
        food,_=bodies();food["data"]["poi_base_info"]["name"]="别的合成门店"
        self.run_pair(food=food)
        self.assertEqual(self.window.code,"P26_RESULT_SOURCE_ASSOCIATION_INVALID")

    def test_render_and_sku_price_difference_is_not_silently_adapted(self):
        _,p=bodies();p["data"]["food_spu_tags"][0]["dynamic_spus"][0]["render_info"]["price_info"]["min_price"]=3.14
        self.run_pair(product=p);self.assertEqual(self.window.code,"P26_RESULT_PRICE_RULE_CHANGED")
        self.assertFalse((self.root/"first_result").exists())

    def test_required_sku_status_is_not_filled_with_zero(self):
        _,p=bodies();del p["data"]["food_spu_tags"][0]["dynamic_spus"][0]["skus"][0]["status"]
        self.run_pair(product=p);self.assertEqual(self.window.code,"P26_RESULT_PARSE_FAILED")
        self.assertEqual(self.window.diagnostic()["qualified_business_events"],0)

    def test_observed_numeric_status_is_required_without_enum_guessing(self):
        _,p=bodies();p["data"]["food_spu_tags"][0]["dynamic_spus"][0]["skus"][0]["status"]=2.0
        self.run_pair(product=p);self.assertEqual(self.window.code,"P26_RESULT_PUBLISHED")

    def test_cross_time_pair_rejected(self):
        self.start();f,p=bodies();a=self.request(0);b=self.request(1)
        self.response(0,f,a);self.time[0]+=11;self.response(1,p,b)
        self.assertEqual(self.window.code,"P26_RESULT_SOURCE_ASSOCIATION_INVALID")

    def test_single_event_expires_without_reusing_next_group(self):
        self.start();f,_=bodies();self.response(0,f,self.request(0));self.time[0]+=60
        self.assertFalse(self.window.active());self.assertEqual(self.window.code,"P26_RESULT_EVENT_SET_EXPIRED")
        self.assertFalse(self.window.request_leases or self.window.projected_observations)

    def test_duplicate_endpoint_does_not_become_complete_pair(self):
        self.start();f,_=bodies();r=self.request(0);self.response(0,f,r);self.response(0,f,r)
        self.assertEqual(self.window.code,"P26_RESULT_EVENT_SET_INVALID")

    def test_existing_result_is_not_overwritten(self):
        target=self.root/"first_result";target.mkdir();(target/"records.json").write_text("OWNED_EXISTING_SENTINEL")
        self.run_pair();self.assertEqual(self.window.code,"P26_RESULT_PUBLISH_FAILED")
        self.assertEqual((target/"records.json").read_text(),"OWNED_EXISTING_SENTINEL")

    def test_result_counter_is_separate_and_close_does_not_double_count(self):
        state={"identification_attempts":19,"result_attempts":0}
        _update_state(self.root,state,self.window)
        self.start();_update_state(self.root,state,self.window);self.window.close();_update_state(self.root,state,self.window)
        saved=json.loads((self.root/"transport-state.json").read_text())
        self.assertEqual((saved["identification_attempts"],saved["result_attempts"]),(19,1))
        self.assertEqual(saved["execution_latch"],"CLOSED")


class ResultV2Tests(unittest.TestCase):
    def run_pair(self, change=None):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();root.chmod(0o700)
            window=P26ResultWindow("合成门店",root,profile_v2(),duration_seconds=None)
            window.inspect_current_domain("wx.waimai.meituan.com");window.start_once()
            food,products=bodies();food["data"]["poi_info"]=food["data"].pop("poi_base_info")
            food["data"]["poi_info"]["id"]=-123
            forms=["wm_poi_id=-123&poi_id_str=synthetic-store-id&userToken=SYNTHETIC_PRIVATE_VALUE"]*2
            if change:change(food,products,forms)
            for index,(route,body) in enumerate([(FOOD_ROUTE,food),(PRODUCT_ROUTE,products)]):
                r=window.route("POST","192.0.2.1",route,tls_domain="wx.waimai.meituan.com");window.select_route(r)
                ref="request:"+("b" if index==0 else "c")*32
                request=begin_form_metadata(window,RequestBudget(window),ref,r,[])
                request.feed(forms[index].encode());request.feed(b"")
                response=window.begin_response(r,"identity",source_request_ref=ref)
                response.feed(json.dumps(body,ensure_ascii=False).encode());response.feed(b"")
            result={"diagnostic":window.diagnostic(),"proof":window.source_proof,
                "association":window.association_check,"files":{}}
            target=root/"first_result"
            if target.exists():
                for name in ("records.json","records.csv","manifest.json"):
                    result["files"][name]=(target/name).read_text()
            self.assertFalse(window.request_leases or window.projected_observations)
            return result

    def test_exact_dual_id_relationship_publishes_consistent_v2_without_private_scalars(self):
        original=json.loads
        def safe_loads(value,*args,**kwargs):
            if type(value) in (str,bytes):self.assertNotIn("SYNTHETIC_PRIVATE_VALUE",value.decode() if type(value)is bytes else value)
            return original(value,*args,**kwargs)
        with patch("collection_adapter.p26_identification.json.loads",side_effect=safe_loads):result=self.run_pair()
        self.assertEqual(result["diagnostic"]["code"],"P26_RESULT_PUBLISHED")
        payload=json.loads(result["files"]["records.json"]);manifest=json.loads(result["files"]["manifest.json"])
        self.assertEqual(payload["records"],list(csv.DictReader(io.StringIO(result["files"]["records.csv"]))))
        self.assertEqual(payload["payload_version"],"p26-observed-shop-v2")
        self.assertEqual(payload["source_proof"],manifest["source_proof"])
        self.assertTrue(payload["source_proof"]["food_secondary_parameter_match"])
        self.assertEqual(result["association"]["merchant_container"],"$.data.poi_info")
        from jsonschema import Draft202012Validator
        schemas=Path(__file__).resolve().parents[2]/"contracts/schemas"
        for name,doc in [("p26-result-view-v1.schema.json",payload),("p26-result-manifest-v1.schema.json",manifest),
                         ("p26-source-observation-proof-v2.schema.json",payload["source_proof"])]:
            Draft202012Validator(json.loads((schemas/name).read_text())).validate(doc)

    def test_either_request_id_mismatch_is_rejected(self):
        for old,new in (("wm_poi_id=-123","wm_poi_id=-456"),("poi_id_str=synthetic-store-id","poi_id_str=other-synthetic-store")):
            def change(_food,_products,forms):forms[1]=forms[1].replace(old,new)
            result=self.run_pair(change)
            self.assertEqual(result["diagnostic"]["code"],"P26_RESULT_SOURCE_ASSOCIATION_INVALID")
            self.assertEqual(result["files"],{})

    def test_old_or_ambiguous_container_is_not_silently_selected(self):
        for ambiguous in (False,True):
            def change(food,_products,_forms):
                food["data"]["poi_base_info"]=copy.deepcopy(food["data"]["poi_info"])
                if not ambiguous:del food["data"]["poi_info"]
            result=self.run_pair(change)
            self.assertNotEqual(result["diagnostic"]["code"],"P26_RESULT_PUBLISHED")
            self.assertEqual(result["files"],{})

    def test_v2_profile_cannot_drop_secondary_or_change_declared_path(self):
        valid=profile_v2();state={k:valid[k] for k in ("runtime_target_ref","target_binding_ref","target_confirmation_ref","capability_ref")}
        self.assertEqual(validate_profile(valid,state),valid)
        for key,value in (("secondary_response_id_path","$.data.poi_info.other_id"),
                          ("routing_parameter_key","wm_poi_id"),("merchant_container","$.data.poi_base_info")):
            with self.assertRaises(IdentificationError):validate_profile({**valid,key:value},state)
        missing={**valid};del missing["secondary_routing_parameter_key"]
        with self.assertRaises(IdentificationError):validate_profile(missing,state)

    def test_repeated_product_across_categories_preserves_both_source_memberships(self):
        def change(_food,products,_forms):
            category=copy.deepcopy(products["data"]["food_spu_tags"][0]);category["tag"]="synthetic-second-category"
            products["data"]["food_spu_tags"].append(category)
        result=self.run_pair(change);payload=json.loads(result["files"]["records.json"])
        self.assertEqual(payload["record_count"],2)
        rows=payload["records"]
        self.assertEqual(rows[0]["product_id"],rows[1]["product_id"])
        self.assertNotEqual(rows[0]["category_ref"],rows[1]["category_ref"])
        self.assertNotEqual(rows[0]["business_record_ref"],rows[1]["business_record_ref"])
        self.assertEqual(rows[0]["observation_ref"],rows[1]["observation_ref"])


if __name__=="__main__":unittest.main()
