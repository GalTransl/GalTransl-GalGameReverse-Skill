# NonColor / legacy ACV

> 能力层级：`keyed-legacy-script-container-roundtrip`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/archives/noncolor.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- 此参考专门处理无ACV1字面魔数的legacy分支。
- 首u32=count XOR 26ACA46E，索引从4开始，每项仍21字节。
- offset仅XOR key_lo；不可带入Mirai ACV1的8B6A4E5F额外XOR。

## 从容器到脚本

- legacy DAT → 索引 → DWORD XOR → zlib → script bytes。
- 标题CRC低32位由调用方给定；不复制上游DEFAULT_GAME_TITLE。
- 本模块只复用同知识库mirai中的纯CRC/XOR/zlib函数，没有运行时上游依赖。

## 对白与 name / message 映射

- key_lo/key_hi不代表角色name，标签和变量也不自动变台词。
- 仍需脚本文法来识别name/message/选择/控制命令。
- 保留$str20一类变量原样，上层翻译不可擅自实化。

## 回填、偏移与控制码

- 索引末尾到首payload的gap长度不固定，按原字节完整保留。
- 只XOR完整DWORD，末1..3字节保持原样；压缩使用标准库zlib。
- 按原次序保留entry keys、flag，重新计算offset/packed_size并确保capacity足够。
- ACV1输入显式拒绝，避免把近似结构当成相同格式。

## 部署先决条件

- 必须取得合法crc_low或正确标题编码；缺key不猜测、不联网查找。
- zlib解压检查EOF、尾随数据、capacity及累计输出预算。

## 诚实边界

- 上游工具能读两分支，本参考拆为两个显式模块以避免误路由。
- 成员间隙和压缩结果规范化，未承诺全档byte-exact或完整VM文本往返。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.archives import noncolor
scripts = noncolor.unpack(dat_bytes, crc_low=supplied_key)
new_dat = noncolor.rebuild(dat_bytes, scripts, crc_low=supplied_key)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/NonColor/dat_tool.py`。
- 源码符号：`parse_header`, `build_header`, `xor_payload_dwords`, `unpack_entry`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/NonColor/ArcDAT.cs`，不作为运行时导入。
- 补充结构来源：`ArcFormats/NonColor/ArcACV.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 合成legacy档验证无魔数count、无extra-XOR及8字节gap保持。
- 和Mirai互相拒绝错误分支，错误key/预算限制及变长重建已测试。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
