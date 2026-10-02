# AdvSys3 / arc*.dat

> 能力层级：`container-roundtrip`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/archives/advsys3.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- 无固定魔数，目录证据是arc开头的.dat文件与顺序记录布局。
- 记录头为u32 payload_size、u32 counter、u16 name_length。
- name_length范围1..256；随后名字字节与payload，size=0可终止。

## 从容器到脚本

- arc*.dat → 有序成员及counter → 各成员自己的脚本/图像/音频格式。
- 上游改版把counter缓存到arc.json以便封包，本参考直接在返回tuple中保留。
- 参考使用tools明确的UTF-8名字规则；不悄悄忽略解码错误。

## 对白与 name / message 映射

- 容器成员名字不是角色name，counter也不是对白ID。
- 上游会探测GWD/WAVE；这不能证明每个成员都是脚本。
- 需先定位实际文本成员，再建立脚本内name/message映射；此模块不猜测。

## 回填、偏移与控制码

- 重建按输入成员顺序生成长度头，counter原样保留。
- 零size终止后的字节作为trailer原样返回/写回。
- 不允许把空payload写成普通成员，避免被解释为全档终止。
- 不复制上游按类型改后缀行为，真实资源名必须稳定。

## 部署先决条件

- 没有仅凭扩展名自动执行；调用方需核对容器布局。
- 这是无压缩顺序容器重建，不要求任何外部exe。

## 诚实边界

- 不提供成员脚本指令编译和游戏加载验证。
- UTF-8名字规则来自该tools版本，其他码页需新证据而不是errors=ignore。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.archives import advsys3
entries, trailer = advsys3.unpack(archive_bytes)
rebuilt = advsys3.pack(entries, trailer)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/AdvSys3/ExAdvsys3.py`。
- 直接依据：`tools/AdvSys3/README.md`。
- 源码符号：`try_open_arc`, `extract_arc`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/AdvSys/ArcAdvSys3.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 合成容器逐字节往返，保留counter和带不透明尾部的终止块。
- 变长成员重建及空成员拒绝已测试。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
