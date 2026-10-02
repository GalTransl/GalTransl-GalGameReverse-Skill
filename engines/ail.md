# Ail / SNL

> 能力层级：`container-literal-pack`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/archives/ail.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- 无固定魔数：u32槽位数及count×u32存储长度表；扩展名可为.dat/.snl。
- 0或FFFFFFFF大小项为缺失槽，不能压缩掉其编号。
- 压缩成员头为u16=1及u32解压长度，之后才是压缩流。

## 从容器到脚本

- 脚本成员明文字节 → literal_block → 大小表容器。
- 源码按sall#数字保留槽位；参考用list[bytes|None]明确传递空槽。
- stored_entries只分割磁盘成员，不承诺解压/识别对白。

## 对白与 name / message 映射

- 脚本内文本类型不在此目录的packer中；须另有脚本解析依据。
- 稳定定位应使用槽号和脚本内ID，不从生成的sall#文件名推断角色名。
- 不可把Ogg资源内容当message。

## 回填、偏移与控制码

- 本格式literal标志位为0，与常见LZSS的1为literal相反。
- 每8个原始字节前写控制字节00；这是合法字面量编码，不是通用byte替换。
- 参考仅生成全字面量流，没有匹配压缩优化；文件会变大。

## 部署先决条件

- 生成前需评估游戏加载缓冲区与体积上限。
- 不实现上游Ogg特判的无压缩分支；当前所有非空槽按压缩头封装。

## 诚实边界

- 不提供通用Ail LZSS解码与脚本语义回填。
- 返回stored含6字节压缩头，不能直接视为文本。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.archives import ail
archive = ail.pack([None, b'synthetic'])
slots = ail.stored_entries(archive)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/Ail/dat_pack_fake_compress.py`。
- 源码符号：`AilArchivePacker.pack_archive`, `AilArchivePacker.lzss_compress`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/Ail/ArcAil.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 独立期望字节验证6字节头、零控制字节、跨8字节组。
- 测试缺失槽不移动及大小表等于存储块大小。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
