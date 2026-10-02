# FlyingShine / PD2

## 模块分工

| 层 | 模块与接口 |
|---|---|
| 归档 | [archives/flyingshine.py](../python/archives/flyingshine.py)：`index`、`rebuild` |
| 脚本 | [engines/flyingshine.py](../python/engines/flyingshine.py)：`script_decode`、`script_encode` |

按下述版本与阶段限制调用；成员 codec 或索引子集不等于完整解包器。

> 能力层级：`container-script-shell-roundtrip`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/engines/flyingshine.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- 魔数FlyingShinePDFile加NUL共18字节；头长0x20。
- +0x14是索引XOR key，+0x1C为成员数；每项0x30字节。
- .def/.dsf是上游确认的脚本候选；不能泛化到全部.pd版本。

## 从容器到脚本

- PD2 → 逐项索引XOR → 取stored → 脚本尾部CRLF推导正文XOR key。
- 索引名字字段0x24字节；其后的shift加在offset和size上。
- 正文key=末字节XOR 0A，并要求倒数第二字节XOR key为0D。

## 对白与 name / message 映射

- 解除XOR后仍需脚本文法；本参考不切分台词或认定某个命令是name。
- 归档文件名与shift均不是角色信息。
- 应在语法确认后提取对白，保留资源命令、标签、控制码和CRLF。

## 回填、偏移与控制码

- script_encode要求终端CRLF；不替调用方追加换行来掩盖异常。
- rebuild接收已经加壳的stored列表，按原次序保留header、name field与shift。
- 新的offset和size写回前加shift，检查u32溢出。
- 本模块不修复OGG、不自动改变音频，避免与文本改动混杂。

## 部署先决条件

- CRLF校验失败必须停止；不能把猜不到key的数据当成功解密。
- 尾部推导是格式启发，不是密码学认证；仍需内容及脚本语法复核。

## 诚实边界

- 不重算未知头部校验字段，也不保证存储间隙原样；需要部署前验证。
- 不是旧Pack/PD版本通用解析器。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.engines import flyingshine
from python.archives import flyingshine as flyingshine_archive
plain, key = flyingshine.script_decode(stored_bytes)
stored_new = flyingshine.script_encode(plain, key)
new_pd = flyingshine_archive.rebuild(pd_bytes, stored_payloads)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/FlyingShine/flytool.py`。
- 源码符号：`parse_header`, `read_entries`, `decrypt_script_payload`, `encrypt_script_payload`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/FlyingShine/ArcPD.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 独立合成索引验证XOR与shift减法、空回封字节一致。
- 正文XOR往返、CRLF拒绝、变长payload长度更新已测试。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
