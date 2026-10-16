"""Bounded public category/root codes; source flags are not eligibility."""

from . import p31_public_fields as base

_OP = ('data','container_operation_source')
_CAT = ('data','food_spu_tags',None)
FOOD_SPECS = (
    ('operation_activity_type_code',_OP+('operation_source_list',None,'activity_type'),'integer','运营活动来源类型码'),
    ('operation_sequence_number',_OP+('operation_source_list',None,'sequence'),'integer','运营项来源顺序数字（非排名证明）'),
    ('operation_type_code',_OP+('operation_source_list',None,'type'),'integer','运营项来源类型码'),
    ('operation_tag_reference',_OP+('tag',),'text','运营标签来源引用'),
    ('operation_tag_sequence_number',_OP+('tag_sequence',),'integer','运营标签来源顺序数字'),
    ('food_has_hotsale_tag_flag',('data','has_hotsale_tag'),'boolean','FOOD热销标签来源标记'),
    ('delivery_activity_info_type_code',('data','pick_goods_tab_info','delivery','activity_info_type'),'integer','配送页签活动信息来源类型码'),
    ('shop_type_code',('data','shop_type'),'integer','店铺来源类型码'),
)
CATEGORY_SPECS = (
    ('category_business_type_code',_CAT+('buzType',),'integer','分类buzType来源码'),
    ('category_health_tag_flag',_CAT+('health_tag',),'boolean','分类health_tag来源标记（非健康认证）'),
    ('category_sequence_number',_CAT+('sequence',),'integer','分类来源顺序数字（非排名证明）'),
    ('category_type_code',_CAT+('type',),'integer','分类来源类型码'),
)
LIST_SPECS = (
    ('list_has_hotsale_tag_flag',('data','has_hotsale_tag'),'boolean','PRODUCTLIST热销标签来源标记'),
    ('box_price_type_code',('data','poi_box_price_detail','box_price_type'),'integer','包装费来源类型码（非费用金额）'),
    ('has_required_tag_flag',('data','required_tag_info','has_required_tag'),'boolean','必选分类来源标记（非个人购物车状态）'),
    ('required_tag_reference',('data','required_tag_info','required_tag_id'),'text','必选分类来源引用（匹配关系未推定）'),
    ('support_preorder_flag',('data','supportPreOrder'),'boolean','预订能力来源标记（非本次订单资格）'),
    ('support_cake_upgrade_flag',('data','support_cake_product_upgrade'),'boolean','蛋糕升级能力来源标记（非本次订单资格）'),
)
SPECS = FOOD_SPECS + CATEGORY_SPECS + LIST_SPECS


def _row(spec, coords, selected, scope, category_ref=None, category_index=None, entry_index=None):
    field,path,kind,label=spec
    value,state=base._fact(selected.get(coords,base._MISSING),kind)
    return {'scope':scope,'category_ref':category_ref,'category_index':category_index,
            'entry_index':entry_index,'field':field,'field_label_zh':label,
            'source_path':base._canonical(path),'value_type':kind,'value':value,'state':state}


def parse_context_codes(analysis, endpoint_id):
    if endpoint_id not in ('FOOD','PRODUCTLIST'):
        base._fail()
    specs=FOOD_SPECS if endpoint_id=='FOOD' else CATEGORY_SPECS+LIST_SPECS
    patterns={base._canonical(path):path for _,path,_,_ in specs}
    selected=base._select(analysis,patterns)
    kinds={base._canonical(path):{'integer':'number','boolean':'boolean','text':'string'}[kind]
           for _,path,kind,_ in specs}
    metadata=analysis.get('fields')
    if type(metadata) is not list or len(metadata)>8000:
        base._fail()
    for item in metadata:
        if type(item) is not dict or type(item.get('path')) is not str:
            base._fail()
        path=item['path']
        if any(path==p or path.startswith(p+'.') or path.startswith(p+'[') for p in patterns):
            if path not in patterns or item.get('type') not in (kinds[path],'null'):
                base._fail()
    rows=[]
    if endpoint_id=='FOOD':
        for spec in specs:
            path=spec[1]
            if None in path:
                coords=sorted(c for c in selected if len(c)==len(path) and all(p is None or p==v for p,v in zip(path,c)))
                rows.extend(_row(spec,c,selected,'FOOD_ROOT',entry_index=c[3]) for c in coords)
                if not coords:
                    rows.append(_row(spec,path,selected,'FOOD_ROOT'))
            else:
                rows.append(_row(spec,path,selected,'FOOD_ROOT'))
    else:
        tag=_CAT+('tag',)
        ids=base._select(analysis,{base._canonical(tag):tag})
        categories={}
        for coords,value in sorted(ids.items()):
            value,state=base._fact(value,'text')
            if state!='PRESENT_UNCONFIRMED' or value in categories.values():
                base._fail()
            categories[coords[2]]=value
        if any(c[:2]==('data','food_spu_tags') and c[2] not in categories for c in selected):
            base._fail()
        for index,ref in categories.items():
            for spec in CATEGORY_SPECS:
                path=spec[1][:2]+(index,)+spec[1][3:]
                rows.append(_row(spec,path,selected,'CATEGORY',ref,index))
        rows.extend(_row(spec,spec[1],selected,'PRODUCTLIST_ROOT') for spec in LIST_SPECS)
    return rows
