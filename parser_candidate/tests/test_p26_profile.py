import unittest
from dataclasses import replace
from parser_candidate.p26_profile import FAMILY,VERSION,VERSION_V2,p26_registry
from parser_candidate.parser import Binding,FoodParserConfig,ParserError,parse_food


class P26ProfileTests(unittest.TestCase):
    def config(self,container):
        return FoodParserConfig(FAMILY,VERSION,
          Binding("merchant_id",container+".poi_id_str",("string",),"merchant"),
          Binding("merchant_name",container+".name",("string",),"merchant"),merchant_container=container)
    def test_actual_container_shape_uses_explicit_mapping(self):
        config=self.config("$.data.poi_base_info")
        parsed=parse_food({"data":{"poi_base_info":{"poi_id_str":"synthetic-store","name":"合成门店"}}},config)
        self.assertEqual(parsed["merchant"]["id"],"synthetic-store")
    def test_old_container_remains_compatible(self):
        config=self.config("$.data.poi_info")
        self.assertEqual(parse_food({"data":{"poi_info":{"poi_id_str":"old-synthetic","name":"合成旧店"}}},config)["merchant"]["id"],"old-synthetic")
    def test_cross_container_bindings_are_rejected(self):
        config=replace(self.config("$.data.poi_info"),merchant_container="$.data.poi_base_info")
        with self.assertRaises(ParserError):config.validate()
    def test_observed_v2_container_is_registered_explicitly_without_v1_fallback(self):
        registry=p26_registry(VERSION_V2)
        food=registry.resolve_food(FAMILY,VERSION_V2)
        self.assertEqual(food.merchant_container,"$.data.poi_info")
        with self.assertRaises(ParserError):registry.resolve_food(FAMILY,VERSION)
        with self.assertRaises(ParserError):p26_registry("unknown")


if __name__=="__main__":unittest.main()
