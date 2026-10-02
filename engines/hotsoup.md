# HotSoup / HSP DPMX

> 能力层级：`container-zero-key-roundtrip`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/archives/hotsoup.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- DPMX魔数，16字节头；+4为data_base、+8为count。
- 每索引项32字节，前16字节cp932名字。
- +0x14为key、+0x18为相对data_base偏移、+0x1C为大小。

## 从容器到脚本

- DPMX → 零key资源成员 → AX等脚本仍需反编译。
- 此参考明确只支持key=0分支，不携带游戏测试密钥。
- 外部EXE附加档和DPM其它版本需另行识别。

## 对白与 name / message 映射

- .ax只是脚本候选，不代表可以按普通文本行翻译。
- DPM名字是成员路径，不是角色name。
- 语义层缺失时不输出虚假的name/message列表。

## 回填、偏移与控制码

- 包头data_base等于头长加索引总长，成员offset只记录数据区内位置。
- 每项+0x10保留常用FFFFFFFF占位，本packer固定零key。
- 严格名字长度检查，避免上游越长写入扩展记录的隐患。

## 部署先决条件

- 读取非零key项立即拒绝，而不是宣称解密。
- 重新生成的零key档是否允许替代加密原档需加载器证明。

## 诚实边界

- 没有AX文本反编译/组装，也没有加密DPMX支持。
- 不可因扩展名DAT就套用该格式。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.archives import hotsoup
archive = hotsoup.pack([('test.ax', b'synthetic')])
entries = hotsoup.unpack(archive)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/HotSoup/dpm_pack.py`。
- 源码符号：`pack`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/HSP/ArcDPM.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 双成员合成测试核对data_base与第二项相对offset。
- 零key往返通过，非零key显式拒绝。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
