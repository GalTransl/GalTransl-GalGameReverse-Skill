# Circus：按游戏配置解释 MES token

## 识别与适用范围
- 剧本候选扩展名为 `.mes`，扩展名本身不能证明格式。
- 本页覆盖 msg-tool 的 Circus MES 分支，不宣称覆盖所有 Circus 作品。
- 头部前两个字段是小端 i32。
- 第二字段为 3 时采用新头部推导方式。
- 旧式版本位置为 `count * 4 + 4`。
- 新式版本位置为 `count * 6 + 4`。
- 版本之后的代码偏移分别再加 2 或 3。
- 版本号只是证据之一；必须显式指定已核实的游戏 profile。

## 容器与剧本分工
- `src/scripts/circus/archive/` 是来源仓库中的容器分支。
- 容器层和本页 MES token 层不是一个输入格式。
- 应先取得容器内原始 MES 字节，再调用本模块。
- 本模块不解析 DAT/PCK/CRM，不调用外部可执行文件。
- 输出 token 也不是可直接替代归档的成品文件。

## 源码依据
- 仓库：msg-tool。
- 固定版本：`f72716cee88554d40c1cdface2812493b14ca653`。
- 许可：GPL-3.0-or-later；分发派生算法须遵守相应许可。
- 文件：`src/scripts/circus/script.rs`。
- 符号：`CircusMesScript::new`、`extract_messages`、`import_messages`。
- 配置来源：`src/scripts/circus/info.rs` 的 `ScriptInfo`。
- 表中不同作品具有不同 opcode 区间、明文 opcode、姓名 opcode 与密钥。
- 不得把示例的 `0x20` 解密增量当作全引擎通用常量。

## Python 模块与实际能力
- 模块：[circus.py](../python/engines/circus.py)。
- `Profile(...)` 明确描述版本与五类 opcode 区间。
- `read_header(data, profile=...)` 验证头部并返回代码位置。
- `read_token(data, offset, profile=...)` 读取已知边界上的一条指令。
- 返回字段为 `offset/end/opcode/text/role`；`end` 是排他偏移。
- `write_text_token(text, opcode, profile=...)` 构造单个姓名/对白 token。
- 没有整份 MES writer，没有全局地址修补器。

## 使用示例
```python
from python.engines.circus import Profile, write_text_token, read_token
# 来源表中的 ffexa 配置，仅作此 profile 的测试示例。
p = Profile(0x7B69, (0, 0x28), (0x29, 0x2E), (0x2F, 0x49),
            (0x4A, 0x4D), (0x4E, 0xFF), 0x43, 0x20, 0x4B)
token = write_text_token("名前", 0x4B, profile=p)
record = read_token(token, 0, profile=p)
assert record["role"] == "name"
```

## 输入与输出边界
- 函数输入是内存 `bytes/str` 和显式参数，无文件路径读取。
- `read_token` 的 offset 必须来自已建立的指令边界，不能来自字节搜索。
- 固定指令分别消费 opcode 加两个 u8，或 opcode 加四个 u16。
- 字符串类以 NUL 结束；带 u8 参数的字符串类另跳过该参数。
- 未识别 opcode、缺终止符、短指令、越界头部均拒绝。
- `Profile` 中 `(255,255)` 继承来源的“区间不存在”语义。
- 不导入 GalTransl、插件、缓存或来源 Rust 项目。

## name/message 与姓名
- 只有 profile 中的加密字符串及指定明文对白 opcode 被当作文本。
- 其中姓名 opcode 返回 `role="name"`。
- 来源提取器把姓名暂存到下一条对白，再清空。
- 本局部接口不自动合并跨 token 的姓名与 message。
- 公共 sidecar 层需要保存原 token 顺序、opcode、原始边界和角色。
- 连续姓名、缺对白等异常应交由上层显式判定，不应猜配对。

## 回填、编码与控制码
- 默认编码 CP932，使用严格编码错误策略。
- 解密为每字节加 `decode_key`，回填为减该值，均模 256。
- opcode 与结尾 NUL 不参与该文本变换。
- 译文编码后若产生 NUL，或加密后碰到 NUL，立即拒绝。
- 例如示例密钥下 ASCII 空格会产生加密终止符，不能静默写入。
- 原作 ruby 标记与全角符号需保留；模块不做跨编码隧道替换。
- 文本变长以后，块表与跳转地址必须由另一个完整结构阶段更新。

## 部署限制与缺口
- 这里只完成“profile 校验、单指令读取、单文本 token 组装”。
- 未完成全部作品 profile 数据移植，也不自动猜作品。
- 未完成块偏移重算、控制流重定位、容器重打包。
- 不允许把本 token builder 标注成完整 MES writer。
- 中文不在 CP932 内时会失败；字体和编码补丁属于另一授权阶段。

## 验证状态
- 合成测试覆盖真实示例 profile、姓名角色与密钥的正反向变换。
- 覆盖旧/新头部偏移、固定指令边界与坏头部。
- 覆盖截断、非法 opcode 用途和加密 NUL 碰撞。
- 测试文件：[test_engines_secondary.py](../tests/test_engines_secondary.py)。
- 未使用游戏资产做运行验证，未运行付费接口。
- 模块成功返回只证明局部字节契约成立，不证明游戏能加载。
