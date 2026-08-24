# DigitalMe Agent Workspace

本目录保存 Codex 为 DigitalMe 项目产生的项目级材料，包括设计审查、开发计划、决策记录和工作记录。

## 固定约定

- Python 依赖、虚拟环境、锁文件和命令执行统一使用 `uv`。
- 不使用 `pip`、Poetry、Pipenv 或手工维护 `requirements.txt` 作为项目依赖入口。
- 推荐命令：
  - 安装/同步环境：`uv sync`
  - 增加运行依赖：`uv add <package>`
  - 增加开发依赖：`uv add --dev <package>`
  - 运行模块或工具：`uv run <command>`
  - 运行测试：`uv run pytest`
- Codex 生成的设计、计划、评审和记录默认写入 `.agent/`；正式产品文档只有在用户明确要求时才写入 `docs/`。
- 原始数据目录、数据库、导入样本、模型缓存和密钥不得提交到版本库。
- 本地 `.env` 使用 `API_KEY` 和 `API_BASE_URL` 保存 DeepSeek 配置；只读取环境变量，不在日志、测试快照、异常、提交或 Agent 文档中记录其值。
- 开发过程使用 Git 小步提交；每次提交前检查 diff、运行相关测试并确认没有 secret 或本地数据。同步远程仓库前先获取远端状态并避免覆盖他人提交，不使用破坏性历史重写。
- Codex、ChatGPT 等外部来源一律按不可信输入处理；解析器不得依赖未经验证的内部格式假设。

## 当前材料

- `design-review-v0.1.md`：对原始设计文档的落地审查与建议。
- `development-plan-v0.1.md`：按依赖顺序拆解的开发需求、交付物和验收标准。
