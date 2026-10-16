"""Offline-only orchestration from a registered fake Adapter to P0 readable JSON."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import sys
from typing import Any, Callable, Mapping

from collection_core import (
    P0Context,
    P0Error,
    P1AssemblyError,
    P1ResultViewError,
    P0ResultViewError,
    ResultPublishError,
    build_p1_batch,
    build_p0_batch,
    publish_result_set,
    render_p1_result,
    render_p0_result,
)
from parser_candidate import Binding, FoodParserConfig, ParserConfig, ParserRegistry, synthetic_p1_registry

from .contract import Adapter, AdapterError, CollectionRunConfig, CollectionTarget
from .fake import (
    FakeAdapter,
    cross_observation_fixture,
    empty_fixture,
    format_error_fixture,
    p1_success_fixture,
    success_fixture,
)
from .request import (
    OfflineOutputIntent,
    OfflineRequestError,
    OfflineRunOptions,
    OfflineRunRequest,
    OfflineTargetRegistry,
)


class OfflineRunError(ValueError):
    """Closed-code runner failure; never contains source or filesystem values."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class OfflineP0Run:
    """One fully assembled, in-memory P0 result from an explicit offline request."""

    request: OfflineRunRequest
    target: CollectionTarget
    config: CollectionRunConfig
    p0_result: dict[str, Any]


def run_offline(
    adapters: Mapping[str, Adapter],
    target: CollectionTarget,
    config: CollectionRunConfig,
    parser_registry: ParserRegistry,
    p0_context: P0Context,
) -> dict[str, Any]:
    """Run one explicit fake Adapter in memory and return complete readable JSON data.

    This function has no publisher or output-path parameter. It either returns a
    fully assembled result or raises a closed error before any caller-visible
    output is produced.
    """

    if (
        type(adapters) is not dict
        or type(target) is not CollectionTarget
        or type(config) is not CollectionRunConfig
        or type(parser_registry) is not ParserRegistry
        or type(p0_context) is not P0Context
    ):
        raise OfflineRunError("RUNNER_CONFIG_INVALID")
    adapter = adapters.get(config.adapter_id)
    if adapter is None or not hasattr(adapter, "collect"):
        raise OfflineRunError("RUNNER_ADAPTER_NOT_REGISTERED")
    p0_result = _build_p0_result(adapter, target, config, parser_registry, p0_context)
    return {
        "schema_version": "offline-collection-run/v1",
        "adapter_id": config.adapter_id,
        "target_ref": target.target_ref,
        "run_ref": config.run_ref,
        "observation_scope": config.observation_scope,
        "source_kind": p0_context.source_kind,
        "readable_records": _readable_records(p0_result),
    }


def run_request(
    request: OfflineRunRequest,
    target_registry: OfflineTargetRegistry,
    adapters: Mapping[str, Adapter],
    parser_registry: ParserRegistry,
    *,
    p0_context_factory: Callable[[CollectionRunConfig], P0Context] | None = None,
) -> OfflineP0Run:
    """Resolve an explicit request into exactly one in-memory P0 run.

    This function never selects a default target, publishes files, or merges
    values between observations.
    """

    if type(request) is not OfflineRunRequest or type(target_registry) is not OfflineTargetRegistry:
        raise OfflineRunError("RUNNER_REQUEST_INVALID")
    if type(adapters) is not dict or type(parser_registry) is not ParserRegistry:
        raise OfflineRunError("RUNNER_CONFIG_INVALID")
    try:
        target, config = request.to_collection_inputs(target_registry)
    except OfflineRequestError:
        raise OfflineRunError("RUNNER_REQUEST_FAILED") from None
    adapter = adapters.get(config.adapter_id)
    if adapter is None or not hasattr(adapter, "collect"):
        raise OfflineRunError("RUNNER_ADAPTER_NOT_REGISTERED")
    factory = default_p0_context if p0_context_factory is None else p0_context_factory
    if not callable(factory):
        raise OfflineRunError("RUNNER_CONFIG_INVALID")
    try:
        p0_context = factory(config)
    except (OfflineRunError, P0Error, TypeError):
        raise OfflineRunError("RUNNER_P0_REJECTED") from None
    if type(p0_context) is not P0Context:
        raise OfflineRunError("RUNNER_P0_REJECTED")
    return OfflineP0Run(
        request=request,
        target=target,
        config=config,
        p0_result=_build_p0_result(adapter, target, config, parser_registry, p0_context),
    )


def publish_request(
    request: OfflineRunRequest,
    target_registry: OfflineTargetRegistry,
    adapters: Mapping[str, Adapter],
    parser_registry: ParserRegistry,
) -> dict[str, object]:
    """Build and publish one explicit offline request without fallback behavior."""

    run = run_request(request, target_registry, adapters, parser_registry)
    try:
        views = render_p0_result(run.p0_result)
    except P0ResultViewError:
        raise OfflineRunError("RUNNER_P0_REJECTED") from None
    try:
        return publish_result_set(
            request.output_intent.output_root,
            request.output_intent.result_name,
            views,
        )
    except ResultPublishError as error:
        if error.code == "RESULT_TARGET_EXISTS":
            raise OfflineRunError("RUNNER_PUBLISH_TARGET_EXISTS") from None
        raise OfflineRunError("RUNNER_PUBLISH_FAILED") from None


def publish_p1_request(
    request: OfflineRunRequest,
    target_registry: OfflineTargetRegistry,
    adapters: Mapping[str, Adapter],
    parser_registry: ParserRegistry,
) -> dict[str, object]:
    """Build and publish one explicit synthetic P1 request without fallback behavior."""

    if type(request) is not OfflineRunRequest or type(target_registry) is not OfflineTargetRegistry:
        raise OfflineRunError("RUNNER_REQUEST_INVALID")
    if type(adapters) is not dict or type(parser_registry) is not ParserRegistry:
        raise OfflineRunError("RUNNER_CONFIG_INVALID")
    try:
        target, config = request.to_collection_inputs(target_registry)
    except OfflineRequestError:
        raise OfflineRunError("RUNNER_REQUEST_FAILED") from None
    adapter = adapters.get(config.adapter_id)
    if adapter is None or not hasattr(adapter, "collect"):
        raise OfflineRunError("RUNNER_ADAPTER_NOT_REGISTERED")
    try:
        parser_events = adapter.collect(target, config).to_parser_events()
    except AdapterError:
        raise OfflineRunError("RUNNER_ADAPTER_FAILED") from None
    try:
        p1_result = build_p1_batch(parser_events, parser_registry, default_p0_context(config))
    except (OfflineRunError, P0Error, P1AssemblyError, TypeError):
        raise OfflineRunError("RUNNER_P1_REJECTED") from None
    try:
        views = render_p1_result(p1_result)
    except P1ResultViewError:
        raise OfflineRunError("RUNNER_P1_REJECTED") from None
    try:
        return publish_result_set(
            request.output_intent.output_root,
            request.output_intent.result_name,
            views,
        )
    except ResultPublishError as error:
        if error.code == "RESULT_TARGET_EXISTS":
            raise OfflineRunError("RUNNER_PUBLISH_TARGET_EXISTS") from None
        raise OfflineRunError("RUNNER_P1_PUBLISH_FAILED") from None


def default_parser_registry() -> ParserRegistry:
    """Return the explicit profile used only by the built-in synthetic fixture."""

    return ParserRegistry(
        (
            ParserConfig(
                payload_family="synthetic_productlist",
                payload_version="v1",
                category_id=Binding("category_id", "$.data.food_spu_tags[*].tag", ("string",), "category"),
                product_price=Binding(
                    "product_price",
                    "$.data.food_spu_tags[*].dynamic_spus[*].min_price",
                    ("number",),
                    "product",
                ),
                sku_price=Binding(
                    "sku_price",
                    "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].price",
                    ("number",),
                    "sku",
                ),
            ),
        ),
        (
            FoodParserConfig(
                payload_family="synthetic_productlist",
                payload_version="v1",
                merchant_id=Binding("merchant_id", "$.data.poi_info.poi_id_str", ("string",), "merchant"),
                merchant_name=Binding("merchant_name", "$.data.poi_info.name", ("string",), "merchant"),
            ),
        ),
    )


def default_p0_context(config: CollectionRunConfig) -> P0Context:
    """Build the explicit, synthetic-only context required by the current P0 Core."""

    if type(config) is not CollectionRunConfig:
        raise OfflineRunError("RUNNER_CONFIG_INVALID")
    run_suffix = config.run_ref[4:]
    observation_suffix = config.observation_scope
    return P0Context(
        run_ref=config.run_ref,
        batch_ref=f"batch:{run_suffix}",
        source_ref=f"source:{run_suffix}",
        source_kind="SYNTHETIC_OFFLINE_FIXTURE",
        provider_contract_ref=f"provider-contract:{run_suffix}",
        authorization_ref=f"authorization:{run_suffix}",
        attempt_ref=f"attempt:{run_suffix}",
        envelope_ref=f"envelope:{run_suffix}",
        observation_ref=f"observation:{observation_suffix}",
        binding_context_ref=f"context:{observation_suffix}",
        evidence_ref=f"evidence:{run_suffix}",
        source_integrity_ref=f"source-integrity:{run_suffix}",
        coverage_ref=f"coverage:{run_suffix}",
        coverage_scope_ref=f"scope:{observation_suffix}",
        evidence_manifest_ref=f"evidence-manifest:{run_suffix}",
        observed_at=config.observed_at,
    )


def run_default_scenario(scenario: str) -> dict[str, Any]:
    """Execute a named built-in synthetic scenario without reading external input."""

    config = CollectionRunConfig(
        adapter_id="offline_fake",
        run_ref="run:offline_demo_01",
        read_scope="READ_DEMO_01",
        observation_scope="OBS_DEMO_01",
        observed_at="2026-08-11T10:00:00Z",
    )
    fixture = {
        "success": success_fixture(config),
        "empty": empty_fixture(),
        "format-error": format_error_fixture(),
        "cross-observation": cross_observation_fixture(config),
    }[scenario]
    return run_offline(
        {"offline_fake": FakeAdapter({"target:offline_demo_01": fixture})},
        CollectionTarget(target_ref="target:offline_demo_01"),
        config,
        default_parser_registry(),
        default_p0_context(config),
    )


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an explicit synthetic offline collection request.")
    parser.add_argument(
        "--scenario",
        choices=("success", "empty", "format-error", "cross-observation"),
        default=None,
    )
    parser.add_argument("--target")
    parser.add_argument("--adapter-id")
    parser.add_argument("--run-ref")
    parser.add_argument("--read-scope")
    parser.add_argument("--observation-scope")
    parser.add_argument("--observed-at")
    parser.add_argument("--output-root")
    parser.add_argument("--result-name")
    parser.add_argument("--formats", choices=("JSON_CSV",))
    parser.add_argument("--p1", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.scenario is not None:
            if any(
                value is not None
                for value in (
                    args.target,
                    args.adapter_id,
                    args.run_ref,
                    args.read_scope,
                    args.observation_scope,
                    args.observed_at,
                    args.output_root,
                    args.result_name,
                    args.formats,
                )
            ) or args.p1:
                raise OfflineRunError("RUNNER_REQUEST_FAILED")
            result = run_default_scenario(args.scenario)
        else:
            result = _publish_explicit_cli_request(args)
    except OfflineRunError as error:
        json.dump({"error": error.code}, sys.stdout, ensure_ascii=True, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump(result, sys.stdout, ensure_ascii=True, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _publish_explicit_cli_request(args: argparse.Namespace) -> dict[str, object]:
    required = (
        args.target,
        args.adapter_id,
        args.run_ref,
        args.read_scope,
        args.observation_scope,
        args.observed_at,
        args.output_root,
        args.result_name,
        args.formats,
    )
    if any(value is None for value in required):
        raise OfflineRunError("RUNNER_REQUEST_FAILED")
    try:
        request = OfflineRunRequest(
            target_ref=args.target,
            options=OfflineRunOptions(
                adapter_id=args.adapter_id,
                run_ref=args.run_ref,
                read_scope=args.read_scope,
                observation_scope=args.observation_scope,
                observed_at=args.observed_at,
            ),
            output_intent=OfflineOutputIntent(
                output_root=args.output_root,
                result_name=args.result_name,
                formats=("JSON", "CSV"),
            ),
        )
        target_registry = OfflineTargetRegistry((CollectionTarget(target_ref="target:offline_demo_01"),))
        config = request.options.to_collection_config()
    except OfflineRequestError:
        raise OfflineRunError("RUNNER_REQUEST_FAILED") from None
    if args.p1:
        return publish_p1_request(
            request,
            target_registry,
            {"offline_fake": FakeAdapter({"target:offline_demo_01": p1_success_fixture(config)})},
            synthetic_p1_registry(),
        )
    return publish_request(
        request,
        target_registry,
        {"offline_fake": FakeAdapter({"target:offline_demo_01": success_fixture(config)})},
        default_parser_registry(),
    )


def _readable_records(p0_result: Mapping[str, Any]) -> list[dict[str, str]]:
    records = p0_result.get("business_records")
    if type(records) is not list:
        raise OfflineRunError("RUNNER_P0_REJECTED")
    readable: list[dict[str, str]] = []
    for record in records:
        if type(record) is not dict or type(record.get("field_observations")) is not list:
            raise OfflineRunError("RUNNER_P0_REJECTED")
        fields = {
            field.get("field_name"): field
            for field in record["field_observations"]
            if type(field) is dict
        }
        try:
            store = fields["store_name"]["public_value_raw"]
            product = fields["product_name"]["public_value_raw"]
            price_minor = fields["display_price_minor"]["normalized_value"]
            currency = fields["currency"]["normalized_value"]
        except (KeyError, TypeError):
            raise OfflineRunError("RUNNER_P0_REJECTED") from None
        if (
            type(store) is not str
            or type(product) is not str
            or type(price_minor) is not int
            or type(currency) is not str
        ):
            raise OfflineRunError("RUNNER_P0_REJECTED")
        readable.append(
            {
                "store": store,
                "product": product,
                "price_yuan": f"{price_minor // 100}.{price_minor % 100:02d}",
                "currency": currency,
            }
        )
    if not readable:
        raise OfflineRunError("RUNNER_P0_REJECTED")
    return readable


def _build_p0_result(
    adapter: Adapter,
    target: CollectionTarget,
    config: CollectionRunConfig,
    parser_registry: ParserRegistry,
    p0_context: P0Context,
) -> dict[str, Any]:
    try:
        batch = adapter.collect(target, config)
        parser_events = batch.to_parser_events()
    except AdapterError:
        raise OfflineRunError("RUNNER_ADAPTER_FAILED") from None
    try:
        return build_p0_batch(parser_events, parser_registry, p0_context)
    except P0Error as error:
        if error.code == "P0_PARSE_FAILED":
            raise OfflineRunError("RUNNER_PARSER_FAILED") from None
        raise OfflineRunError("RUNNER_P0_REJECTED") from None


if __name__ == "__main__":
    raise SystemExit(main())
