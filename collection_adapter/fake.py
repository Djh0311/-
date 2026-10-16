"""Controlled in-memory Adapter and synthetic Stage 01 fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple

from .contract import (
    AdapterError,
    CollectionEvent,
    CollectionEventBatch,
    CollectionRunConfig,
    CollectionTarget,
)


_FIXTURE_FAILURES = frozenset({"ADAPTER_EMPTY_RESULT", "ADAPTER_FORMAT_INVALID"})


@dataclass(frozen=True)
class FakeFixture:
    """A fully in-memory success event tuple or one predeclared closed failure."""

    events: Tuple[CollectionEvent, ...] = ()
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if self.failure_code is not None:
            if self.events or self.failure_code not in _FIXTURE_FAILURES:
                raise AdapterError("ADAPTER_FIXTURE_INVALID")
            return
        if not self.events or any(type(event) is not CollectionEvent for event in self.events):
            raise AdapterError("ADAPTER_FIXTURE_INVALID")


class FakeAdapter:
    """A replaceable Adapter whose complete fixture set is supplied by the caller."""

    adapter_id = "offline_fake"

    def __init__(self, fixtures: Mapping[str, FakeFixture]) -> None:
        if type(fixtures) is not dict or any(
            type(target_ref) is not str or type(fixture) is not FakeFixture
            for target_ref, fixture in fixtures.items()
        ):
            raise AdapterError("ADAPTER_FIXTURE_INVALID")
        self._fixtures = dict(fixtures)

    def collect(self, target: CollectionTarget, config: CollectionRunConfig) -> CollectionEventBatch:
        if type(target) is not CollectionTarget:
            raise AdapterError("ADAPTER_TARGET_INVALID")
        if type(config) is not CollectionRunConfig:
            raise AdapterError("ADAPTER_CONFIG_INVALID")
        if config.adapter_id != self.adapter_id:
            raise AdapterError("ADAPTER_NOT_REGISTERED")
        try:
            fixture = self._fixtures[target.target_ref]
        except KeyError:
            raise AdapterError("ADAPTER_TARGET_UNAVAILABLE") from None
        if fixture.failure_code is not None:
            raise AdapterError(fixture.failure_code)
        return CollectionEventBatch.from_events(fixture.events, config)


def success_fixture(config: CollectionRunConfig) -> FakeFixture:
    """Return one synthetic FOOD + PRODUCTLIST observation for offline-only tests."""

    if type(config) is not CollectionRunConfig:
        raise AdapterError("ADAPTER_CONFIG_INVALID")
    common = {
        "read_scope": config.read_scope,
        "observation_scope": config.observation_scope,
        "payload_family": "synthetic_productlist",
        "payload_version": "v1",
    }
    return FakeFixture(
        events=(
            CollectionEvent(
                **common,
                event_index=1,
                endpoint_id="FOOD",
                payload={
                    "data": {
                        "poi_info": {
                            "poi_id_str": "store-demo-01",
                            "name": "Demo Store",
                        }
                    }
                },
            ),
            CollectionEvent(
                **common,
                event_index=2,
                endpoint_id="PRODUCTLIST",
                payload={
                    "data": {
                        "food_spu_tags": [
                            {
                                "tag": "category-demo-01",
                                "current_page": 1,
                                "has_next_page": False,
                                "dynamic_spus": [
                                    {
                                        "id": 101,
                                        "name": "Demo Product",
                                        "min_price": 12.5,
                                        "skus": [
                                            {
                                                "id": 1001,
                                                "spec": "regular",
                                                "price": 12.5,
                                                "status": 1,
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                },
            ),
        )
    )


def empty_fixture() -> FakeFixture:
    return FakeFixture(failure_code="ADAPTER_EMPTY_RESULT")


def format_error_fixture() -> FakeFixture:
    return FakeFixture(failure_code="ADAPTER_FORMAT_INVALID")


def cross_observation_fixture(config: CollectionRunConfig) -> FakeFixture:
    """Return an intentionally mixed observation which the shared contract rejects."""

    if type(config) is not CollectionRunConfig:
        raise AdapterError("ADAPTER_CONFIG_INVALID")
    valid = success_fixture(config).events
    product = valid[1]
    return FakeFixture(
        events=(
            valid[0],
            CollectionEvent(
                read_scope=product.read_scope,
                observation_scope="OBS_OTHER_01",
                event_index=product.event_index,
                endpoint_id=product.endpoint_id,
                payload_family=product.payload_family,
                payload_version=product.payload_version,
                payload=product.payload,
            ),
        )
    )


def p1_success_fixture(config: CollectionRunConfig) -> FakeFixture:
    """Return a complete Stage 03 fixture created solely in Python memory."""

    if type(config) is not CollectionRunConfig:
        raise AdapterError("ADAPTER_CONFIG_INVALID")
    common = {
        "read_scope": config.read_scope,
        "observation_scope": config.observation_scope,
        "payload_family": "synthetic_p1_productlist",
        "payload_version": "v1",
    }
    return FakeFixture(
        events=(
            CollectionEvent(
                **common,
                event_index=1,
                endpoint_id="FOOD",
                payload={
                    "data": {
                        "poi_info": {
                            "poi_id_str": "store-demo-01",
                            "name": "Demo Store",
                            "delivery_fee": 3.0,
                            "min_order": 20.0,
                            "delivery_status": "AVAILABLE",
                        }
                    }
                },
            ),
            CollectionEvent(
                **common,
                event_index=2,
                endpoint_id="PRODUCTLIST",
                payload={
                    "data": {
                        "food_spu_tags": [
                            {
                                "tag": "category-demo-01",
                                "name": "Demo Category",
                                "current_page": 1,
                                "has_next_page": False,
                                "dynamic_spus": [
                                    {
                                        "id": 101,
                                        "name": "Demo Product",
                                        "min_price": 12.5,
                                        "skus": [
                                            {
                                                "id": 1001,
                                                "spec": "regular",
                                                "price": 12.5,
                                                "status": 1,
                                                "origin_price": 15.0,
                                                "activity_price": 12.5,
                                                "promotion": {
                                                    "type": "DIRECT_REDUCTION",
                                                    "discount": 2.5,
                                                    "scope": "SKU",
                                                },
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                },
            ),
        )
    )


def p1_cross_observation_fixture(config: CollectionRunConfig) -> FakeFixture:
    """Return a mixed Stage 03 fixture which the Adapter contract rejects."""

    if type(config) is not CollectionRunConfig:
        raise AdapterError("ADAPTER_CONFIG_INVALID")
    valid = p1_success_fixture(config).events
    product = valid[1]
    return FakeFixture(
        events=(
            valid[0],
            CollectionEvent(
                read_scope=product.read_scope,
                observation_scope="OBS_OTHER_01",
                event_index=product.event_index,
                endpoint_id=product.endpoint_id,
                payload_family=product.payload_family,
                payload_version=product.payload_version,
                payload=product.payload,
            ),
        )
    )
