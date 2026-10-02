# NSystem：BIN 预设的地址表和独立消息记录

## 能力边界
- 状态：`partial / preset-record-only`。
- Python：`python/engines/nsystem.py`。
- 这是 `_BIN_NSystem` 规则的有界算法提炼，不是完整 NSystem VM。
- 只实现确定格式的地址表解析和已隔离消息记录回填。
- 不提供整个二进制文件的通用变长替换。

## 识别线索
- 预设使用 `DA 07` 或 `D8 07` 作为分段线索。
- 这些短字节序列本身不能证明文件属于该引擎。
- 记录格式和地址表范围应同时经过独立样本核实。
- 地址区从 `0x458` 开始。
- 表项数是 `u32@0x14 + u32@0x18`。
- 字节码地址基址是 `0x458 + 表项数 * 4`。
- 表中每项相对该基址，解析时检查文件范围。

## 不执行配置表达式
- 上游 reg.yaml 把地址边界写成求值表达式。
- 本模块使用固定算术与 `struct`，没有 `eval`。
- 表项数上限十万，过大的计数在读取之前失败。
- `address_table` 返回基址和 `(字段位置, 绝对目标)`。
- 这些结果只是已知表项，不保证涵盖所有内联地址。

## 消息记录结构
- API 输入的是分隔符之后、已独立确定边界的一条记录。
- 消息开始前有十八字节头部，最后一字节为 03。
- 记录头两字节是原始 u16 长度。
- 来源 `preLenAdd=-27` 表示有效正文长度等于存储长度减 27。
- 正文后为 NUL，且必须符合来源指定的字节范围。
- 第二个长度字节必须位于 00..01 范围。
- 不在任意二进制位置搜索“可能是汉字”的片段。

## name / message
- `parse_message_record` 返回严格解码的 message。
- 另一规则中的名字形态是大写字母加编号，如 `TEST_123`。
- `name_identifier` 返回 name_id 和 number，不解释成显示人名。
- 无名字映射表时，不凭声线或剧情内容补名字。
- 资源、命令和非匹配分段不属于可自动翻译范围。

## 回填算法
- `rewrite_message_record` 重编码正文并计算 `len(bytes)+27`。
- 更新 u16 存储长度，十八字节头其余部分保持不变。
- 保留末尾 NUL，拒绝内部控制字节越界。
- 新长度离开第二字节 00..01 的已知方言时拒绝。
- 这不是通用字节替换：它重算具体记录的长度字段。
- 但它也不是全文件 writer：外部地址表尚未被自动重定位。

## Python 示例
```python
from python.engines.nsystem import address_table, rewrite_message_record
addresses = address_table(script_bytes)
new_record = rewrite_message_record(isolated_record, "合成試験")
```
- `isolated_record` 的边界不能只靠在任意数据中找短分隔符猜测。
- 变长记录不可直接粘回原文件；必须补完整重布局和地址修正。

## 部署条件与缺口
- 缺少容器层、解密、全 VM 指令边界与名字映射。
- 缺少整文件记录目录以及所有地址来源的完整清单。
- 缺少内联控制码和分支/选择项语义。
- 只有确认完整 relocation 后才可考虑实际部署。
- 没有真实游戏或译文编码兼容性验证。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 主要证据：`src/reg.yaml` 的 `_BIN_NSystem`。
- 长度语义：`src/extract_TXT.py`、`src/extract_BIN.py`。
- 来源仓库 GPL-3.0；保留 satan53x / SExtractor 贡献者归属。
- 测试算术地址基址、长度加 27、头部保留、名字编号及溢出。
- 测试文件 `tests/test_engines_tools_b.py`，全部合成记录。
