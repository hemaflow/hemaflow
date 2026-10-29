# HemaFlow 快速上手指南

> 目标读者：想在科室里把 HemaFlow 跑起来的医生 / 研究者 / 医院信息科同事。
> 全程不需要联网服务、不需要数据库，一台普通电脑 + Python 3.9+ 即可。

---

## 一、5 分钟跑通 Demo

```bash
# 1. 克隆仓库（或直接下载 zip 解压）
git clone https://github.com/hemaflow/hemaflow.git
cd hemaflow

# 2. 跑演示脚本
python3 demo.py

# 3. 跑单元测试（19 项，应全部通过）
python3 tests.py
```

`demo.py` 会输出：

- 一份 R-CHOP 21 天 × 6 周期的完整住院时间轴（入院 / 化疗 / 出院 / 谷值复查 / 疗效评估）；
- 一张文本版床位甘特图（含层流床标签、男女分区、同床消毒间隔）；
- 一组间隔期血象的分级预警结果（黄 / 红 / 发热急诊）。

---

## 二、三分钟理解目录结构

```
hemaflow/
├── hemaflow/            # 核心包（零第三方依赖）
│   ├── engine.py        # 周期引擎：方案模板 → 时间轴 → 剂量调整传播
│   ├── beds.py          # 反向排床：预约锁床 / 冲突检测 / 消毒间隔
│   ├── alerts.py        # 分级预警：ANC/PLT/体温 阈值判定 + 趋势摘要
│   ├── config.py        # JSON 规则配置加载（阈值、方案库）
│   └── synthetic.py     # 固定种子合成数据（演示/测试用）
├── config/
│   └── rules.example.json   # 规则配置示例（改成你们科室的口径）
├── docs/
│   ├── architecture.png     # 架构图
│   └── 发布前待办指引.md
├── demo.py              # 演示脚本
└── tests.py             # 单元测试
```

**设计原则**：核心引擎不依赖任何第三方库、不访问网络、不落库。
HIS/LIS 对接、小程序、甘特前端都在引擎之外，由你按科室情况自行接入。

---

## 三、把方案改成你们科室的口径

编辑 `config/rules.example.json`：

```json
{
  "regimens": [
    {
      "name": "R-CHOP",
      "cycles": 6,
      "cycle_length_days": 21,
      "inpatient_days": 4,
      "nadir_days": [7, 12],
      "assessment_after": [2, 4, 6]
    }
  ],
  "thresholds": {
    "anc_yellow": 1.0,
    "anc_red": 0.5,
    "plt_red": 30.0,
    "fever_celsius": 38.0
  }
}
```

- **方案库**：不同中心 R-CHOP 住院天数可能不同（3~5 天），改 `inpatient_days` 即可；
- **预警阈值**：老年耐受差的患者群体，可把黄线放宽到 `1.5`；
- 加载时 `config.py` 会校验必填字段，缺了会直接报错并指出缺哪个。

在代码中使用配置：

```python
from datetime import date
from hemaflow.config import load_regimens, load_thresholds

regimens = {r.name: r for r in load_regimens("config/rules.example.json")}
plan = TreatmentPlan(patient_id="P001", regimen=regimens["R-CHOP"],
                     start_date=date(2025, 3, 3))
for ev in plan.build_timeline():
    print(ev)
```

---

## 四、典型接入方式（供信息科参考）

| 环节 | 建议做法 | 引擎侧接口 |
|---|---|---|
| 患者方案录入 | 医生在任意表单/小程序里填方案 → 调 `TreatmentPlan` | `build_timeline()` |
| 下一周期排床 | 从 `next_admission(today)` 拿入院窗口 → 写回 HIS 排班 | `BedScheduler.book()` |
| 间隔期血象 | LIS 检验报告推送 → 逐条过预警引擎 | `alerts.evaluate()` |
| 每日待办 | 每晨跑一次批量评估 + 待出院确认 | `evaluate_batch()` |

**数据边界（务必遵守）**：

1. 患者身份信息用院内 ID 或脱敏编号，不要把姓名/身份证号放进引擎；
2. 引擎只做计算与提醒，**不做诊断结论、不做线上处方**；
3. 所有医疗决策仍由管床医生人工确认。

---

## 五、常见问题

**Q：一定要 Python 吗？**
核心逻辑就三个纯函数模块，任何语言照着规则表重写一遍都行。选 Python 只是为了让临床背景的同事也能读懂、改阈值。

**Q：能直接上生产吗？**
不建议。当前版本是「可运行的最小核心」，适合先在科室里做影子验证（系统排班 vs 实际排班对照跑 1~2 个周期），确认口径一致后再考虑接入 HIS。

**Q：想参与共建？**
见 [CONTRIBUTING.md](../CONTRIBUTING.md)——三条红线：不碰真实患者隐私数据、不做诊断结论、所有阈值改动必须走 JSON 配置而不是改代码。

---

*HemaFlow · 让每一环都有人知道球在哪。*
