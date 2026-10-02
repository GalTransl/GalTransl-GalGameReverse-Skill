# Mirai / ACV1 script.dat

> 能力层级：`keyed-script-container-roundtrip`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/archives/mirai.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- 必须为ACV1字面魔数；+4的count需XOR 8B6A4E5F。
- 索引从8开始，每项21字节：lo、hi、flag、offset、packed_size、capacity。
- offset额外XOR 8B6A4E5F；NonColor旧分支没有这个额外因子。

## 从容器到脚本

- ACV1 → 反混淆索引 → DWORD XOR → zlib → script bytes。
- 正文DWORD key=调用方crc_low XOR entry.key_lo，末1..3字节不XOR。
- title_key接受调用方提供的标题编码bytes，无默认商业标题或测试key。

## 对白与 name / message 映射

- 解封脚本常含星号标签；标签用于定位，不是要翻译的name。
- 容器只有key/hash没有角色信息，不能从key_hi猜name。
- 对白与$name变量需脚本文法；该参考不把解出的全部行直接当message。

## 回填、偏移与控制码

- 保留entry次序、lo/hi、flag及索引到首payload之间的header gap。
- 压缩后重新DWORD XOR，重算offset/packed_size，capacity至少容纳新明文。
- 密钥来源必须正确；错误key或不完整zlib流拒绝，不输出乱码假成功。
- CRC多项式为42F0E1EBA9EA3693，MSB-first，初末值全1，不是零初值ECMA常见变种。

## 部署先决条件

- 解压默认累计输出限制64MiB，并限制声明capacity。
- 当前是源码中script.dat分支，不把所有ACV资源flags解释为同一解码路线。

## 诚实边界

- 回封会规范化成员间隙/压缩流，不承诺整个原包byte-exact。
- 不提供脚本文本语法回填或游戏加载验证。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.archives import mirai
key = mirai.title_key(title_text.encode('cp932'))
scripts = mirai.unpack(dat_bytes, crc_low=key)
new_dat = mirai.rebuild(dat_bytes, scripts, crc_low=key)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/Mirai/acv1_dat_tool.py`。
- 源码符号：`crc64_ecma_msb`, `parse_index`, `build_index`, `xor_payload_dwords`, `pack_entry`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/NonColor/ArcACV.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- ACV1合成key、gap、变长回封及错误key测试通过。
- CRC标准输入123456789低32位向量和DWORD尾余数独立测试。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
