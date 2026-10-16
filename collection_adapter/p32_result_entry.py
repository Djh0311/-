"""Read-only entry for the existing, bounded local delivery."""

import argparse
import json
import os
from pathlib import Path
import re
import stat

from .p29_store_inventory import _read_owned, _validate
from .p29_receiver_control import _root
from .p31_context_codes_export import FILES


REPO = Path(__file__).resolve().parents[1]
CURRENT_ROOT = REPO / 'runtime-output/p29_pages_003b896bb92941eb9115e3c9202e26e5'
CURRENT_RESULT = 'p31_confirmed_units_f73fc5498c734905b23afa6c9442453d'
RESULT_NAME = re.compile(r'p31_confirmed_units_[a-f0-9]{32}')
COUNT_FIELDS = ('record_count', 'product_count', 'sku_count', 'category_count',
                'store_record_count', 'public_text_record_count', 'public_code_record_count')
LABELS = {'records.csv': '商品和 SKU 表', 'stores.csv': '门店表',
          'public_texts.csv': '公开说明表', 'public_codes.csv': '来源码表',
          'field_dictionary.json': '逐列字段说明', 'coverage.json': '字段状态和缺失清单'}
RECOVERY = {
    'P32_ROOT_UNAVAILABLE': '当前受控结果目录不可用，请核对本地目录位置；不会自动采集。',
    'P32_RESULT_NAME_INVALID': '结果名称不符合当前支持的版本，请使用已交付结果。',
    'P32_RESULT_NOT_FOUND': '已交付结果目录不存在，请核对原交付位置或从备份恢复。',
    'P32_RESULT_FILE_MISSING': '结果文件缺失，请从同一交付包的备份恢复；不要混用不同批次。',
    'P32_RESULT_FILE_UNSAFE': '结果路径或权限不符合受控文件要求，请核对目录及文件权限；不会自动修改。',
    'P32_MANIFEST_INVALID': '结果清单损坏或版本不匹配，请从同一交付包的备份恢复。',
}


def _failure(code):
    return {'status': 'RESULT_UNAVAILABLE', 'code': code, 'next_action_zh': RECOVERY[code]}


def _owned(path, directory=False):
    info = path.lstat()
    return (info.st_uid == os.getuid()
            and (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600))


def inspect_result(root=None, result_name=None):
    """Check metadata and file presence; never read business table contents."""
    name = CURRENT_RESULT if result_name is None else result_name
    if type(name) is not str or RESULT_NAME.fullmatch(name) is None:
        return _failure('P32_RESULT_NAME_INVALID')
    try:
        root = _root(CURRENT_ROOT if root is None else root)
    except (OSError, ValueError):
        return _failure('P32_ROOT_UNAVAILABLE')
    bundle = root / name
    try:
        if not _owned(bundle, directory=True):
            return _failure('P32_RESULT_FILE_UNSAFE')
    except FileNotFoundError:
        return _failure('P32_RESULT_NOT_FOUND')
    except OSError:
        return _failure('P32_RESULT_FILE_UNSAFE')
    try:
        for filename in FILES:
            if not _owned(bundle / filename):
                return _failure('P32_RESULT_FILE_UNSAFE')
    except FileNotFoundError:
        return _failure('P32_RESULT_FILE_MISSING')
    except OSError:
        return _failure('P32_RESULT_FILE_UNSAFE')
    try:
        manifest = _read_owned(bundle / 'manifest.json', 64 * 1024)
        _validate(manifest, 'p31-business-manifest-v7.schema.json')
        if manifest['result_name'] != name:
            return _failure('P32_MANIFEST_INVALID')
    except (OSError, ValueError, KeyError):
        return _failure('P32_MANIFEST_INVALID')
    return {
        'status': 'LOCAL_FILES_PRESENT', 'result_name': name,
        'declared_counts': {key: manifest[key] for key in COUNT_FIELDS},
        'count_basis': 'EXISTING_MANIFEST_NOT_RECOUNTED',
        'files': {filename: str(bundle / filename) for filename in FILES},
        'guide': str(REPO / 'docs/harness/p32-local-results.md'),
        'coverage_status': manifest['coverage_status'],
        'business_data_revalidated': False, 'all_store_products_complete': False,
        'images': 'EXCLUDED_BY_USER', 'target_system_import_validation_required': False,
        'inspection_scope': 'MANIFEST_CONTRACT_AND_LOCAL_FILE_METADATA_ONLY',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='查看当前已交付结果；只读，不采集、不导入。')
    parser.add_argument('--json', action='store_true', help='输出无业务值的结构化状态')
    args = parser.parse_args(argv)
    result = inspect_result()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result['status'] == 'RESULT_UNAVAILABLE':
        print('结果暂不可用：' + result['code'])
        print(result['next_action_zh'])
    else:
        counts = result['declared_counts']
        print('当前已交付文件可用（清单和文件状态检查通过）。')
        print(f"交付清单记载：{counts['record_count']} 行，{counts['product_count']} 个商品，"
              f"{counts['sku_count']} 个 SKU，{counts['category_count']} 个分类。")
        print('覆盖为 PARTIAL；本命令不重算业务数据，不证明全店收齐。')
        print('图片已排除；不执行目标系统导入验证。')
        for filename, label in LABELS.items():
            print(f"{label}：{result['files'][filename]}")
        print('使用说明：' + result['guide'])
    return 0 if result['status'] == 'LOCAL_FILES_PRESENT' else 1


if __name__ == '__main__':
    raise SystemExit(main())
