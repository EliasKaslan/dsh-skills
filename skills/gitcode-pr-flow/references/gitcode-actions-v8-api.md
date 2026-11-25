# GitCode/AtomGit Actions v8 API 与「初始化步骤」

主人：`gitcode-pr-flow`。v5 没有流水线这条线，查 run/job 必须用 v8。

## 端点（实测 200，Bearer 鉴权与 v5 同一个令牌）

```bash
TOK=$(python -c "import io;print(io.open(r'/path/to/token.txt',encoding='ascii').read().strip())")
R=https://api.gitcode.com/api/v8/repos/Ascend/MindSpeed-Ops/actions
curl -s -H "Authorization: Bearer $TOK" "$R/runs?per_page=100"           # 运行列表
curl -s -H "Authorization: Bearer $TOK" "$R/runs/<run_id>"               # run 详情
curl -s -H "Authorization: Bearer $TOK" "$R/runs/<run_id>/jobs/<job_id>" # job 详情
curl -s -H "Authorization: Bearer $TOK" "$R/workflows"                   # 工作流列表
```

- 403 `UN_KNOW` = 私有仓或无权限；404 `NOT_PATH` = 路径/对象不存在，**和「没权限」同形**，别据此断言流水线不存在。
- `/jobs/{id}/logs` 是 405（GET 不支持），日志正文拿不到，只能靠 `message` + `steps[]` 判读。

## run 对象

`workflow_run_id`(32 hex)、`workflow_name`、`file_path`、`status`(COMPLETED/FAILED/CANCELED/RUNNING)、`event`(`Note` = 评论触发)、`run_number`、`head_branch`、`head_sha`、`pull_request_id`、`start_time`/`end_time`(毫秒 epoch)、`stages[].jobs[]`。

## job 对象（判「卡在哪一步」靠它）

| 字段 | 用途 |
| --- | --- |
| `exec_id` = `last_dispatch_id` | `<32hex>_<19位雪花>`；平台日志 `Job(...)` 里就是它 |
| `apply_time` | 派发/排队时刻，与初始化步骤首行日志同秒 |
| `start_time` | `null` = 从未轮到执行 |
| `execute_cost_time` | 负数 = 排队时间被记成负时长 |
| `message` | 失败归因；`步骤初始化步骤执行失败…点击任务查看详情` = 派发/容器没起来，`步骤run X执行失败` = 脚本真跑过 |
| `resource` | JSON 串：`name`=自托管池名、`labels`(如 `npu=1`)、`container.image` |
| `steps[]` | 每步 `name`/`task`/`status`/`start_time`/`end_time` |

## 初始化步骤

每个 job 的首步固定是 `{"name":"初始化步骤","task":"official_pre_step"}`，末步 `后处理步骤`(`official_post_step`)，YAML 里的 step 夹在中间。

```text
[<时间> GMT+08:00] [INFO] Job(<exec_id 的 32hex 段>_<19 位雪花>) duration check: true
```

`duration check: true` 只表示时长校验通过，**不是报错**；看到它说明该 job 被送进排队，离「真的开始跑」还差一次调度。

## 判读顺序

1. 先看 `start_time`：`null` → 池没给机器（同窗口多仓同症状即可判池级故障）。
2. 有 `start_time` → 看 `message` 定位到具体 step，再回 YAML 找对应 script。
3. 要反证「同镜像能不能跑」：找同一天更早一个用同一 `container.image` 的 run，比它的耗时。
