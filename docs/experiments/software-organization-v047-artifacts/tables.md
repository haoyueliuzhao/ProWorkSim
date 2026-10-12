这些表使用冻结计划分母；null 保持未知。识别区间不是置信区间。首次固定提交不等于首次正确解；提交费用切点不再次加进完整回合费用。

## 250,000 token：逐 root 结果

| root | 配置 | 状态 | R_joint | R_token | Q_joint | 完整实际token | 首次提交token | 最终提交token | 出生/调用/峰存活 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LA | S1 | submitted_acceptance_failed | 0 | 0 | 0.667 | 95,528 | 79,481 | 79,481 | 1/1/1 |
| LA | D2 | normal_no_submission | 0 | 0 | 0.000 | 241,420 | null | null | 1/1/1 |
| LA | D4 | normal_no_submission | 0 | 0 | 0.000 | 245,562 | null | null | 1/1/1 |
| LA | I2 | accepted_complete_delivery | 1 | 1 | 1.000 | 241,353 | 241,353 | 241,353 | 2/2/2 |
| LA | I4 | normal_no_submission | 0 | 0 | 0.000 | 240,710 | null | null | 4/4/4 |
| LA | P2 | accepted_complete_delivery | 1 | 1 | 1.000 | 197,562 | 183,134 | 183,134 | 2/2/2 |
| LA | P4 | normal_no_submission | 0 | 0 | 0.000 | 220,402 | null | null | 4/4/4 |
| HA | S1 | normal_no_submission | 0 | 0 | 0.000 | 234,750 | null | null | 1/1/1 |
| HA | D2 | normal_no_submission | 0 | 0 | 0.000 | 233,921 | null | null | 1/1/1 |
| HA | D4 | normal_no_submission | 0 | 0 | 0.000 | 243,504 | null | null | 1/1/1 |
| HA | I2 | normal_no_submission | 0 | 0 | 0.000 | 241,983 | null | null | 2/2/2 |
| HA | I4 | normal_no_submission | 0 | 0 | 0.000 | 243,265 | null | null | 4/4/4 |
| HA | P2 | normal_no_submission | 0 | 0 | 0.000 | 232,172 | null | null | 2/2/2 |
| HA | P4 | normal_no_submission | 0 | 0 | 0.000 | 224,502 | null | null | 4/4/4 |
| LB | S1 | accepted_complete_delivery | 1 | 1 | 1.000 | 113,205 | 96,719 | 96,719 | 1/1/1 |
| LB | D2 | accepted_complete_delivery | 1 | 1 | 1.000 | 185,306 | 94,277 | 154,841 | 1/1/1 |
| LB | D4 | accepted_complete_delivery | 1 | 1 | 1.000 | 114,223 | 81,905 | 81,905 | 1/1/1 |
| LB | I2 | normal_no_submission | 0 | 0 | 0.000 | 240,081 | null | null | 2/2/2 |
| LB | I4 | normal_no_submission | 0 | 0 | 0.000 | 247,795 | null | null | 4/4/4 |
| LB | P2 | normal_no_submission | 0 | 0 | 0.000 | 239,815 | null | null | 2/2/2 |
| LB | P4 | normal_no_submission | 0 | 0 | 0.000 | 246,682 | null | null | 4/4/4 |
| HB | S1 | normal_no_submission | 0 | 0 | 0.000 | 245,174 | null | null | 1/1/1 |
| HB | D2 | normal_no_submission | 0 | 0 | 0.000 | 245,022 | null | null | 1/1/1 |
| HB | D4 | normal_no_submission | 0 | 0 | 0.000 | 234,448 | null | null | 1/1/1 |
| HB | I2 | normal_no_submission | 0 | 0 | 0.000 | 243,545 | null | null | 2/2/2 |
| HB | I4 | normal_no_submission | 0 | 0 | 0.000 | 244,708 | null | null | 4/4/4 |
| HB | P2 | normal_no_submission | 0 | 0 | 0.000 | 232,756 | null | null | 2/2/2 |
| HB | P4 | normal_no_submission | 0 | 0 | 0.000 | 245,065 | null | null | 4/4/4 |

## 500,000 token：逐 root 结果

| root | 配置 | 状态 | R_joint | R_token | Q_joint | 完整实际token | 首次提交token | 最终提交token | 出生/调用/峰存活 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LA | S1 | submitted_acceptance_failed | 0 | 0 | 0.667 | 110,941 | 79,371 | 79,371 | 1/1/1 |
| LA | D4 | accepted_complete_delivery | 1 | 1 | 1.000 | 112,169 | 96,149 | 96,149 | 1/1/1 |
| LA | I4 | normal_no_submission | 0 | 0 | 0.000 | 495,331 | null | null | 4/4/4 |
| LA | P4 | normal_no_submission | 0 | 0 | 0.000 | 371,082 | null | null | 4/4/4 |
| HA | S1 | normal_no_submission | 0 | 0 | 0.000 | 190,189 | null | null | 1/1/1 |
| HA | D4 | normal_no_submission | 0 | 0 | 0.000 | 497,846 | null | null | 1/1/1 |
| HA | I4 | normal_no_submission | 0 | 0 | 0.000 | 487,690 | null | null | 4/4/4 |
| HA | P4 | normal_no_submission | 0 | 0 | 0.000 | 490,599 | null | null | 4/4/4 |
| LB | S1 | accepted_complete_delivery | 1 | 1 | 1.000 | 236,962 | 171,702 | 171,702 | 1/1/1 |
| LB | D4 | accepted_complete_delivery | 1 | 1 | 1.000 | 164,578 | 69,272 | 148,937 | 1/1/1 |
| LB | I4 | accepted_complete_delivery | 1 | 1 | 1.000 | 457,112 | 442,754 | 442,754 | 4/4/4 |
| LB | P4 | normal_no_submission | 0 | 0 | 0.000 | 428,925 | null | null | 4/4/4 |
| HB | S1 | normal_no_submission | 0 | 0 | 0.000 | 497,094 | null | null | 1/1/1 |
| HB | D4 | normal_no_submission | 0 | 0 | 0.000 | 495,988 | null | null | 1/1/1 |
| HB | I4 | normal_no_submission | 0 | 0 | 0.000 | 497,392 | null | null | 4/4/4 |
| HB | P4 | normal_no_submission | 0 | 0 | 0.000 | 491,546 | null | null | 4/4/4 |

## 四 root 等权汇总

| 预算 | 配置 | R_token均值 | R_token识别区间 | Q_token均值 | 全部4槽完整实际token | 平均实际token |
| --- | --- | --- | --- | --- | --- | --- |
| 250,000 | S1 | 0.250 | [0.25, 0.25] | 0.417 | 688,657 | 172164.250 |
| 250,000 | D2 | 0.250 | [0.25, 0.25] | 0.250 | 905,669 | 226417.250 |
| 250,000 | D4 | 0.250 | [0.25, 0.25] | 0.250 | 837,737 | 209434.250 |
| 250,000 | I2 | 0.250 | [0.25, 0.25] | 0.250 | 966,962 | 241740.500 |
| 250,000 | I4 | 0.000 | [0.0, 0.0] | 0.000 | 976,478 | 244119.500 |
| 250,000 | P2 | 0.250 | [0.25, 0.25] | 0.250 | 902,305 | 225576.250 |
| 250,000 | P4 | 0.000 | [0.0, 0.0] | 0.000 | 936,651 | 234162.750 |
| 500,000 | S1 | 0.250 | [0.25, 0.25] | 0.417 | 1,035,186 | 258796.500 |
| 500,000 | D4 | 0.500 | [0.5, 0.5] | 0.500 | 1,270,581 | 317645.250 |
| 500,000 | I4 | 0.250 | [0.25, 0.25] | 0.250 | 1,937,525 | 484381.250 |
| 500,000 | P4 | 0.000 | [0.0, 0.0] | 0.000 | 1,782,152 | 445538.000 |

## 真实 250k→500k 配对响应

| 配置 | ΔR_joint | ΔR_token | ΔR_token识别区间 | ΔQ_token | 平均完整实际token差 |
| --- | --- | --- | --- | --- | --- |
| S1 | 0.000 | 0.000 | [0.0, 0.0] | 0.000 | 86632.250 |
| D4 | 0.250 | 0.250 | [0.25, 0.25] | 0.250 | 108211.000 |
| I4 | 0.250 | 0.250 | [0.25, 0.25] | 0.250 | 240261.750 |
| P4 | 0.000 | 0.000 | [0.0, 0.0] | 0.000 | 211375.250 |
