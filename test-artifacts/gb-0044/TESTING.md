# 炉序失准监控测试说明

## 独立 oracle（本目录，仅标准库可跑）

```bash
python3 test-artifacts/gb-0044/test_monitor_sprt.py
```

覆盖：似然比口径（失准率三成对一成）、报警界限=炉数÷误报上限、失准阈值判定、
乱序补报缓冲、缺号只等该炉、首次报警锁定、重试不重复计入、中断后从持久化状态续跑、
已计入更正留痕且报警仍按当时读数。被测 `backend/src/services/monitor_sprt.py`
为纯标准库模块，服务层（SQLAlchemy）只做持久化与行锁，不含第二份判定逻辑。

## HTTP 全流程（compose 环境）

```bash
cp .env.example .env && docker compose up -d --build
# 种子自动创建“十一月炉序失准监控”：1#炉正常、2#炉第4件首次报警且缺第5件、3#炉带更正留痕
```

1. 登录 `analyst@drying-forest.demo` / `Research2026!`，进入“炉序监控”页。
2. 上报实测：乱序号（如先报第8件再报第6件）验证缺号等待；重复提交同号同
   读数返回 `duplicate` 不重复计入；已计入序号的不同读数返回 `correction_logged` 留痕。
3. 页面核对各炉“核对到”与“首次报警试件”，报警横幅与当时读数保持不变。
4. API：`GET/POST /api/monitor/plans`、`POST /api/monitor/plans/{id}/readings`、
   `POST/GET /api/monitor/plans/{id}/corrections`，匿名 401、viewer 写 403。
