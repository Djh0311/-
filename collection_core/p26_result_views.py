"""Basic real-result view with explicit list-price meaning and source linkage."""
from dataclasses import dataclass
import csv
import io
import json
from .result_views import render_p0_result

P26_CSV_FIELDS=("store","store_id","product","product_id","category_ref","category_name",
 "price_yuan","currency","price_unit","price_meaning","price_source_path","price_suffix",
 "price_suffix_state","price_description","price_description_state","run_ref","batch_ref",
 "observation_ref","business_record_ref","observed_at")


@dataclass(frozen=True)
class P26ResultViews:
    json_bytes: bytes
    csv_bytes: bytes


def render_p26_result(batch, details, proof):
    payload=json.loads(render_p0_result(batch).json_bytes)
    if len(details)!=payload["record_count"]:
        raise ValueError("P26_RESULT_VIEW_INVALID")
    rows=[]
    for record,detail,source_record in zip(payload["records"],details,batch["business_records"]):
        fields={f["field_name"]:f["normalized_value"] for f in source_record["field_observations"]}
        if detail["store_id"]!=fields["store_ref"] or detail["product_id"]!=fields["product_ref"]:
            raise ValueError("P26_RESULT_VIEW_INVALID")
        row={**record,"store_id":detail["store_id"],"product_id":detail["product_id"],
            "category_ref":detail["category_ref"],"category_name":detail["category_name"],
            "price_unit":"YUAN","price_meaning":"PRODUCT_LIST_MINIMUM_SKU_PRICE",
            "price_source_path":"$.data.food_spu_tags[].dynamic_spus[].min_price",
            "observed_at":payload["observed_at"]}
        for name in ("price_suffix","price_description"):
            value=detail[name]
            row[name]="" if value is None else value
            row[name+"_state"]="SOURCE_NOT_PROVIDED" if value is None else "PRESENT"
        if set(row)!=set(P26_CSV_FIELDS) or any(type(v) is not str for v in row.values()):
            raise ValueError("P26_RESULT_VIEW_INVALID")
        rows.append(row)
    payload.update(schema_version="collection-p26-result-view/v1",records=rows,
        payload_family="meituan_wechat_miniprogram",payload_version=proof.get("payload_version","p26-observed-shop-v1"),
        coverage_status="PARTIAL",coverage_scope="CURRENT_LIST_RESPONSE_ONLY",
        unit_evidence="CURRENT_USER_PUBLIC_PAGE_CONFIRMATION_WITH_PRICE_MATCH",
        source_proof=proof)
    stream=io.StringIO(newline="")
    writer=csv.DictWriter(stream,fieldnames=P26_CSV_FIELDS,lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    return P26ResultViews((json.dumps(payload,ensure_ascii=True,sort_keys=True,indent=2)+"\n").encode(),
                          stream.getvalue().encode("utf-8"))
