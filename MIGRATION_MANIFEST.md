# 重建与迁移收据

- 日期：2026-08-11
- 旧项目：`meituan-collection-agent-owned-v2`
- 新项目：`meituan-collection-agent-owned-v3`

## 载体与 Git

- 旧仓 branch：`codex/harness-lite-cutover-20260807`
- 旧仓 HEAD：`45b32b70fca11f618065db1b93acca51266c8158`
- 旧仓 all-files status SHA-256：`245598b98bb711dc10f2eef5f002c909fc193971a9f281d03ab445bbeca18189`
- 旧仓 14-worktree expanded fingerprint：`c20d4d3c6f876788690597994bb6947e311a91ef459d75cc2ac7e35be1403abb`
- 仓外归档 receipt ID：`meituan-collection-agent-owned-v2-2026-08-11`
- 归档 artifact receipt SHA-256：`cd509f4dfc78e5181885039cb128fb367d5febd882e8f57dcc4bc30a4e472f5e`
- 产品转移 preimage tar SHA-256：`a2c028f8df33bcce79d9c2f993d9d802863cf5f1848df991cf34e010554dfb47`
- 新仓初始产品 commit：`868a1b033224691641bed7d0ce61799f0da3895b`
- 新仓初始产品 tree：`1f54f8e9aafdbaaa9a1c8a8cbaee7e676e4eda64`
- 新仓 branch：`codex/project-rebuild-20260811`
- remote / upstream：无

本收据所在提交只补充 provenance，不改变初始产品 tree 中的代码、合同、runtime 或资格结论。

## 选择结果

直接带入 52 个普通文件：当前 `autocapture/`、隔离 `parser_candidate/`（排除历史 raw projection 工具）、14 个通用合同及其 README、严格 verifier 依赖的 design 文档。

摘要后新写：README、项目协作边界、当前状态、架构、资格、证据、仓外归档边界和无值资格检查清单。

明确未带入：历史 raw/live evidence、旧 Harness runtime 与控制面、旧 leaf/stage/done/report/audit/usage、旧 authority/dispatch/task graph、H5/Wechat 实验源码、其它 worktree 内容、历史 raw projection 工具。它们只存在于仓外受控归档，且不是新仓运行依赖。

## Harness Lite 0.7

- 源码权威 commit：`90b5f8c14a71a415d87374821fff4af35ad6372e`
- runtime source bundle SHA-256：`d0b445e3362f76d93c248d639f1368ca0a3a84a3e88a828f43ea00a0e87e310b`
- 安装前 identity：`fresh`
- 安装后 identity：`current`
- package digest：`sha256:99323df550792f5dc34a33ae7e09df17fae727f5c8d20195f736e746057bafb3`
- instruction digest：`sha256:4a87ff5ab56331b588057614ab5f1c824589017088b38404ea4923bbc3fe9320`
- Hook definition digest：`sha256:9dcc3c8b3f4c028956aa42ff34ca21e807903dff9d407d947837ac39186e5054`
- installed：true
- configured：true
- trusted：false（未做真实宿主 trust 验收）
- observed：四事件均 false（未做真实宿主事件观测）
- native pre-push：未安装

机制预算保持：新增用户命令 0、持久状态 0、非 push 门禁 0、Hook 事件 0、内部命令 0、技能 0、风险模块 0、项目专属 Core 兼容 0。

## 本次直接验证

- `autocapture`：154/154 通过；
- strict verifier：`AUTOCAPTURE_STRICT_VERIFY_PASS`，16 files / 15 manifest entries；
- `parser_candidate`：41/41 通过；
- Harness Lite Core：83/83 通过，selfcheck 通过；
- raw/archive/legacy-control 负向路径检查：通过；
- symlink 检查：0；
- 初始 commit 后 working tree：clean；
- 没有真实网络、微信/浏览器 UI、系统代理、CA、keychain、管理员配置或 raw 正文读取。

## 直接带入文件

| path | mode | bytes | sha256 |
| --- | ---: | ---: | --- |
| `autocapture/__init__.py` | `0644` | 68 | `95c974a1b5b0171a6029bdb30c4d4e65c3d28846bfabaeb6a1f8c8325cbcdd24` |
| `autocapture/addon.py` | `0644` | 12906 | `bdf2e5a77b84f277dae0d0c28894463d6f151672506805698b2f74a8f7c0a74e` |
| `autocapture/build-manifest.json` | `0644` | 2584 | `191e41a534f354fc7b9e1229512251b3ab47f965b57d042eae1dd8051c7d7315` |
| `autocapture/lease.py` | `0644` | 5849 | `a13d4e92e963e190e46f567fc29d9fd3f3be18d072f40dd762d0fa89cf86f63d` |
| `autocapture/policy.py` | `0644` | 10760 | `7e2f2206a0d1e23780eb5ede20dc55bb1081f37c1253b69030a28e8545604e44` |
| `autocapture/publisher.py` | `0644` | 26593 | `dd3d318053882df14e961508d7d05f54eee1fe841a9c5d3ad4a12543cf5bf32c` |
| `autocapture/shape.py` | `0644` | 32664 | `1b987f0349608ea08ed92ff22914c9810cfd233b0f79fb8456ef61507b689e75` |
| `autocapture/tests/__init__.py` | `0644` | 67 | `0a18cd520a066693c3786c2744334489e00370b05f4c40ef14f09be30436a5a8` |
| `autocapture/tests/fakes.py` | `0644` | 9152 | `444be0f5d6a930898428c0e518be1683550038c8756ecf8273e1b5a33ed96658` |
| `autocapture/tests/test_addon.py` | `0644` | 29320 | `8f07d5e517ead1ec4dfe25447cdd140ec875d9ead6514806fe598fdef7b75f06` |
| `autocapture/tests/test_policy_and_lease.py` | `0644` | 17988 | `187178bf797bdcab2d99db59ffa18b8e83189b9bea929454fbdd111f019a79f3` |
| `autocapture/tests/test_publisher.py` | `0644` | 25252 | `c8d9e966d1b68f664c502fa81905d8b1d06075c69d93bf246a4a5ffad26d6151` |
| `autocapture/tests/test_shape.py` | `0644` | 19886 | `43db307d32d8b569b87f4cf39514877cdac4821831c9b88d6f0b04c53f8854e4` |
| `autocapture/tests/test_verifier.py` | `0644` | 52661 | `1e8e23ef3715f4e09cd5cfe4542d37be2803a163b02347274e0c443591ee8af6` |
| `autocapture/tools/verify_autocapture_build.py` | `0644` | 134676 | `901a55b3b74247abd9a4ee4917d687e258cac0a69e7ad2d354070e38e0d9de3a` |
| `contracts/README.md` | `0644` | 5410 | `848251880a0f1e16393321bbe8e890bbadc6f042deeef37912627f3aea415422` |
| `contracts/schemas/adapter-checkpoint.schema.json` | `0644` | 8524 | `57c0ca033699fcce094c78d3e54a5eb29e625479464d56ef6e9b0cf14c67f1ea` |
| `contracts/schemas/business-record-v2.schema.json` | `0644` | 3908 | `60fab61beb5afde53b26110de72f21ab4afd47361244643a6fafbff3caa81190` |
| `contracts/schemas/capability-ledger.schema.json` | `0644` | 26352 | `526ed8a5a8ab910859433e2db974bad38699f5f832b8550297e68741fcc42e8a` |
| `contracts/schemas/coverage-receipt.schema.json` | `0644` | 3376 | `5c7c8d3e81356da475312ba139ba8543cea056a40ac14e2389df2781397740c1` |
| `contracts/schemas/error-status-code.schema.json` | `0644` | 2819 | `8c2898e7f9e3054c46ab40dba097c26c48618da88d9e736f1dc33c4224d4d0af` |
| `contracts/schemas/evidence-manifest.schema.json` | `0644` | 8237 | `1de4af93a0d8d658dc632a19baf2962fa7497ba27a69f4a4c3e2af6410cb8142` |
| `contracts/schemas/field-observation-v2.schema.json` | `0644` | 13657 | `124b3bc974202c5d188f8088f82db3b3bcbfb3191effc55dc4b62d9cdea264f6` |
| `contracts/schemas/observation-batch.schema.json` | `0644` | 5395 | `8c7fe1bcf9dd1033bf38bda40dffccea39d7ee03c2855b9694995e912eec8661` |
| `contracts/schemas/observation-envelope.schema.json` | `0644` | 4088 | `e4c328b1a743433aa8e5417119ac54e47ce9730cbe5bac02333bc519e68f95e9` |
| `contracts/schemas/provider-contract.schema.json` | `0644` | 6516 | `cc2694b093bda9a3275d52b7577ce2d2650113a8145ac28e5b5f6edcc774d9e8` |
| `contracts/schemas/provider-qualification-summary.schema.json` | `0644` | 8469 | `65f921c550cfde4601112429c786ab6d058cbdfb79bbc3bb8cb058b041e6a880` |
| `contracts/schemas/provider-qualification.schema.json` | `0644` | 16223 | `fd83d4b166166550e27c79c7afd5a096e02ac1a36352587dd0eabe514a300474` |
| `contracts/schemas/source-integrity-receipt.schema.json` | `0644` | 8525 | `e37f270ccfdba9b6cd505b2e5a0a0b6ced6238b9542e0e996d639174af87cdb1` |
| `contracts/schemas/value-free-sensitive-stop.schema.json` | `0644` | 2644 | `9b3c704565353d681aa18d591c6896bf347326779b2b8a9a0e869546407e702d` |
| `docs/design/autocapture-shape-discovery-v1.md` | `0644` | 16927 | `6747f44a62113461b727d29687c4644177f1a511cf191ba791b00602308147d6` |
| `parser_candidate/__init__.py` | `0644` | 1259 | `6c0a1bc118d975b42e2429ca1f89bb4cf2f41c3c47816243f31b7bb00e607383` |
| `parser_candidate/capture_contract.py` | `0644` | 9690 | `dfe27ab16cd47b87e743267f174f8578732c01975c1045a61b8bb771813368a1` |
| `parser_candidate/envelope.py` | `0644` | 4716 | `68f976d170be70bac501d03d24645bba1bcbd3b40b001c076ededc9b4b62ce17` |
| `parser_candidate/fixtures/h34/manifest.json` | `0644` | 6947 | `2cc424cb853d2c6463b4867744b78b69d9df92841bcb7b28ef414e10e4559103` |
| `parser_candidate/fixtures/h34/read_01/events/event_01.json` | `0644` | 106959 | `79a2f484769f6f29b230ae0b301545f02b2d4261754fae6b0a4acfb91d70869e` |
| `parser_candidate/fixtures/h34/read_01/events/event_02.json` | `0644` | 767668 | `2a5bf58e05d5d517a5749ca29b9c8ace3f75c749006248ffcd91b671e6433705` |
| `parser_candidate/fixtures/h34/read_02/events/event_01.json` | `0644` | 79427 | `379dd69213baa5981f5c6b85fe9e84caffc4af42da1214cbdfb3ae356ccb05a2` |
| `parser_candidate/fixtures/h34/read_02/events/event_02.json` | `0644` | 677449 | `c80118fb6e959bade17ba733e02a6b4eda2b779af8c93a13c3ab2aeffee5153e` |
| `parser_candidate/fixtures/h34/read_03/events/event_01.json` | `0644` | 79427 | `c662b12388b6c0c1a4c072402002613ee5aef15662359b916ac0bb20a34608f4` |
| `parser_candidate/fixtures/h34/read_03/events/event_02.json` | `0644` | 679917 | `638b645453d17b3f6caeeea0d14ef0d72094aab5a3e09e84d77d6206c9183b90` |
| `parser_candidate/fixtures/h34/read_03/events/event_03.json` | `0644` | 79427 | `3619b5aa132cb0e3f5991c2f0bbe928766c46d704f44b2ad57413a366349b9ee` |
| `parser_candidate/fixtures/h34/read_03/events/event_04.json` | `0644` | 679917 | `4f1d0deb1517c09e13cdc4116d33d318ecb1bf7d570a0b1387d172bc4420ff0f` |
| `parser_candidate/parser.py` | `0644` | 16959 | `fe720b2f07af3825833b708c1dd1a8656ce1490677f93969d2fe95d193d27a5b` |
| `parser_candidate/profiles.py` | `0644` | 8027 | `66a95f1bbd90fde73a69e11df3d58985b93294aaae0b553a89700c8756cb9c00` |
| `parser_candidate/registry.py` | `0644` | 3421 | `34d272a51ab871745e20aa8349e61b85c1b9442cd85fda9254f3774196f54175` |
| `parser_candidate/tests/__init__.py` | `0644` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `parser_candidate/tests/test_capture_contract.py` | `0644` | 13847 | `9703cb4b7ed45ff93fce014a1503d890c094e496e39a331a08851102b523f0c0` |
| `parser_candidate/tests/test_food_profile.py` | `0644` | 2460 | `0bab83889f9239cea89acc2bfbb8878fd7719cc3095ff8051a4c11ab49304cf8` |
| `parser_candidate/tests/test_h34_sanitized_fixtures.py` | `0644` | 17793 | `63f6aab71e8cbdee301c46f3d2e93b4557a1f526e51db00ffd4fb335fa9237e4` |
| `parser_candidate/tests/test_parser.py` | `0644` | 16298 | `21433bcb33b3ca313b25c4f21f98bcea1143ac190256ab8a76422d344534f91c` |
| `parser_candidate/tests/test_profiles.py` | `0644` | 5631 | `09f3bd383acbe452dcf12bb13e47274e4b84f1d61dd6ea1bbdf44dc1a9aae34d` |
