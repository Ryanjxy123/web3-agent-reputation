# 后续会话继续提示词

```text
继续当前Web3 Agent项目。先读有效AGENTS.md、PLAN.md、docs/implementation/STATUS.md，再核对git status/branch/log与上次记录，不根据聊天记忆猜进度。
找出BACKLOG第一张依赖已满足且未验收的任务卡；先复跑上一轮相关最小测试，再继续实现。
M1未验收先修M1，不扩公网/页面/LLM；M1通过后按负责人本次指定的下一个里程碑执行。
保留用户未提交改动、原有规则/许可证；复用既有接口和版本。任务更改Schema/policy/合约/安全边界必须更新spec、测试和ADR；不得用修改阈值让失败消失。
每个逻辑任务附实际测试结果并小提交。正常push工作分支需remote正确、认证有效和diff审查通过；不得强推/直接改main。
结束更新STATUS：已完成、真实测试、阻塞、分支commit/push结果、下一个task_id和命令。
```

例：M1确认通过后，在提示词末尾加“本轮只执行M2-01与M2-02，不实施P1”，让边界保持清晰。
