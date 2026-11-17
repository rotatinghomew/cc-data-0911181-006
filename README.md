# 多重归属课程服务

统计服务支持单课程报名人数、出勤课次、符合条件报名项的完成率，以及按单课程保存的周材料。
此外提供统一口径（learner-scope-v1）的多维范围查询：方向、校区、学期任意组合下，参与/资格/完成人数按学员去重，课次参与按课次累加，学员完成率以结课资格学员为分母、至少完成一门者为分子，并对多方向与跨校归属给出重叠说明。

## 运行环境

使用 Python 3.11，仅依赖标准库，无外部服务、账号或网络数据。
示例数据使用虚构标识和本地合成记录，不涉及真实学员。

```bash
python3 -m app check
python3 -m app summary
python3 -m app serve --host 127.0.0.1 --port 8080
```

服务提供只读 JSON 查询：`/api/statistics`, `/api/subscriptions`, `/api/metrics`, `/api/saved_views`。
多维查询示例：`/api/metrics?directions=photo,digital&campuses=east&group_by=direction&detail=true`。
`/health` 显示存活及表计数，`/api/records?table=表名` 可查看已知数据表。
详细字段语义、计数单位和当前能力见 `docs/数据契约.md`。

## 验证

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q app tests smoke.py
python3 smoke.py
```

测试从实际数据装载进入领域计算、报告与真实 HTTP 服务，并用临时副本验证错误输入。
冒烟程序动态分配本地端口，启动服务后读取全部业务查询并原样输出 JSON，随后正常关闭。
查询不写回数据，因此可以直接重复运行；验证不会访问项目外文件。

## 容器

```bash
docker build -t metric-lens:local .
docker run --rm --network none metric-lens:local
docker run --rm --network none metric-lens:local python3 smoke.py
```

镜像只封装本应用，测试使用回环网络，不依赖宿主端口。
无第三方包依赖，`requirements.lock` 记录此状态。

## 业务办理

单课程流程 targets.evaluate 按单课程统计判结课目标，followups.assign 分派校区跟进并保留办结，deliveries.prepare 汇集原口径与对应工单。

范围流程与 `/api/metrics` 共用同一口径：views.save 保存订阅定义（临时展开不入库），targets.evaluate_scope 按范围判定，followups.assign_scope 按校区分担共有责任且换分组不重复催办，deliveries.prepare_scope 在周材料中区分冻结依据与当前依据，只发出当前仍成立的待办。

业务操作以 JSON 对象 POST 到 `/api/workflow/操作名`，下列操作保留现有函数入参和行为。

- `targets.evaluate`
- `targets.evaluate_scope`
- `followups.assign`
- `followups.assign_scope`
- `followups.close`
- `deliveries.prepare`
- `deliveries.prepare_scope`
- `views.save`

业务贯通用例见 `tests/test_workflows.py` 与 `tests/test_scope_workflows.py`，其中为可直接运行的本地调用。默认状态存于内存；需要重启后保留时，可运行 `python3 -m app serve --state /tmp/learning-service.sqlite3`。状态库只保留本机操作，不向外部发送数据。
