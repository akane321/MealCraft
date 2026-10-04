## 完成内容

<!-- 简要说明本 PR 改变了什么。 -->

## 用户价值或问题

<!-- 说明它解决的 Issue、用户问题或技术问题。 -->

## 范围与非目标

<!-- 列出本 PR 包含的内容，以及明确不包含的内容。 -->

## 安全与租户边界

- [ ] 不涉及认证、授权、租户隔离或敏感数据
- [ ] 涉及上述边界，已说明威胁、权限规则、拒绝行为与测试证据
- [ ] 私有资源查询在 Repository 层包含 `household_id`
- [ ] 未记录密码、原始 Token、Cookie、密钥或真实健康数据

## 迁移、兼容性与回滚

<!-- 说明数据库/API/数据格式兼容性、升级/降级步骤与安全回滚；不涉及则写“不涉及”。 -->

## 验证方式

- [ ] 后端 Ruff 与 Pytest 通过，或本 PR 不涉及后端
- [ ] 前端 ESLint、Vitest、typecheck 与 build 通过，或本 PR 不涉及前端
- [ ] 涉及用户流程时 Playwright（`pnpm test:e2e`）通过
- [ ] 涉及评价时运行 `python -m app.evaluation.workbench`，并提交重新生成的报告
- [ ] `python scripts/check_docs_integrity.py`、`scripts/check_heldout_episodes.py` 与 `scripts/report_catalog_reality.py --check` 通过
- [ ] 涉及 `data-engineering/` 时其单元测试（`python -m unittest discover -s tests`）通过
- [ ] Docker Compose 配置检查通过
- [ ] 已在最低 1280×720 桌面视口检查相关页面，或本 PR 不涉及页面
- [ ] 已更新相关 API、架构或使用文档
- [ ] 未提交密码、Token、个人数据或本地 .env

## 验证证据

<!-- 给出命令与结果摘要；UI 修改请附截图和视口，非 UI 修改附测试输出或检查报告。 -->

## 风险与后续工作

<!-- 列出已知风险、观测方式和不应被本 PR 宣称为完成的后续工作。 -->

## 关联任务

Closes #

## 知识库记录（必填，最高优先级）

<!-- 与本 PR 同时在 MealCraft-Knowledge 开配对 PR，在下一行写出它的完整链接。没有链接，CI 的 knowledge-record 检查会失败。只有 Dependabot 和原样回退豁免。 -->

知识库 PR：

- [ ] 配对的知识库 PR 与本 PR 同时开出，两边互相链接
- [ ] 任务记录写了思路（Approach and reasoning）：做法、理由、没采用的其他做法
- [ ] 任务记录写了方向核对（Direction check）：约束这次工作的 ADR、需求和 owner 决定，以及是否一致
- [ ] 发现的冲突已交给 owner 或写进 `OPEN_QUESTIONS.md`；新的 owner 决定已在同一个知识库 PR 里写成 ADR
- [ ] 评审改动了本 PR 的实质内容时，知识库 PR 已同步更新
- [ ] 未把私有知识库内容、真实健康数据或课程原始文件复制到公开仓库
