# Musica：SC 消息、选择与文本转义

## 能力边界
- 引擎 ID：`musica`。
- 参考模块：[python/engines/musica.py](../python/engines/musica.py)。
- 实现 `.message` 与 `.select` 的有限文本区间解析和保留分隔符回填。
- 输入输出为已经解码的 `str`，没有资源解密或磁盘写入。
- 不把未识别命令的参数作为普通文字导出。

## 识别证据
- `.sc` 配合 `.message`、`.select` 等行命令可作为语法证据。
- PAZ/PAK 资源与 Musica 引擎痕迹可加强判断，但不是 SC 的编码证明。
- `.message` 的常见参数布局是 id、voice、name、text。
- `.select` 的选项带 `文本:目标`，目标部分不能翻译。
- 必须检查多条正常句、旁白和选择，不能只凭第一行判断参数位置。
- 可读的 `.sc` 不代表所有命令参数均是玩家可见文本。

## 格式方言
- VN 按空格或制表符逐个分隔参数，连续分隔符可产生空参数。
- 不能用普通 `split()` 折叠空白，否则空名字的参数位置会漂移。
- 第三个参数是名字；名字可有 `@` 前缀。
- 第四个参数起至行尾为正文范围，而非只取最后一个 token。
- `.select` 每个参数在第一个冒号前的部分才是选项文本。
- `\n` 代表换行，`\$HH` 代表两位十六进制字符码。
- 全角空格在正文显示层可表示半角空格。
- 本参考保留名字中的全角空格，不继承 VN 的自动删名内空格策略。

## 容器到剧本路线
1. 先辨别 PAZ/PAK/DAT 是否真是 Musica 容器及对应版本。
2. GARbro-Mod `ArcFormats/Musica/ArcPAZ.cs`、`ArcPAK.cs` 提供格式线索。
3. 资源版本、压缩、密钥和文件名处理必须先得到证据。
4. 提取 SC 成员后严格解码，并保留编码/换行/BOM 元数据。
5. 文本回填再编码后进入已验证的归档或外置部署流程。
- 本页不提供 PAZ 密钥数据库，不下载资源，不调用工具包装器。

## 源码与算法对应
- 主来源：`VNTextPatch-net8`，MIT。
- 提交：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 路径：`VNTextPatch.Shared/Scripts/MusicaScript.cs`。
- `GetMessageRanges` 对应第三参数名字及后续整段正文。
- `GetSelectRanges` 对应选项冒号左侧区间。
- `GetTextForRead/GetTextForWrite` 对应全角空格、`\n`、`\$HH`。
- 对照：`msg-tool/src/scripts/musica/sc.rs` 的 extract/import_messages。
- 该 Rust 提交 `f72716cee88554d40c1cdface2812493b14ca653`，GPL-3.0-or-later。
- msg-tool 目前只处理 `.message`，并取末两个参数；不能声称它覆盖 `.select`。

## Python 接口与示例
```python
from python.engines.musica import musica_fields, patch_musica
src = '.message 1 voice @Alice Hello\\nworld\r\n.select Yes:go No:stop\r\n'
fields = musica_fields(src)
assert [f.kind for f in fields] == ['name', 'message', 'choice', 'choice']
out = patch_musica(src, {1: 'New line\nnext', 2: 'Accept'})
assert '.select Accept:go No:stop' in out
```
- `musica_fields(str) -> tuple[Field, ...]`：字符区间和显示文本。
- `decode_text(str, name=False) -> str`：只处理有证据的转义。
- `patch_musica(str, {字段原序号: str}) -> str`。
- 字符区间属于 Unicode 字符串，不等于 SC 文件字节偏移。

## name / message 映射
- 名字参数前 `@` 保留为原语法，不导出到显示名中。
- 空名字不创建伪 name，正文序号仍由原结构确定。
- 以 `$` 开头的姓名变量保留且 `writable=False`。
- 选择作为独立 choice，不能丢进普通正文集合后失去目标关联。
- 多条 name 字段按顺序保存；模块不自动压成全局最后一个姓名。
- voice、id 与选择目标没有成为译文字段。

## 回填、长度与控制码
- 原始行命令、分隔空白、voice、id、目标及行尾保持不变。
- 替换采用原字符区间逆序处理。
- 普通译文空格转成全角空格，避免产生新的参数。
- 显示换行转成字面 `\n`。
- NUL、制表符、自由反斜线和选项中的冒号注入被拒绝。
- 未识别的原转义也拒绝，不能靠删除反斜线“清洗”输入。
- 回填后比较字段角色序列，结构发生变化时拒绝输出。
- 文本层不需要 VM 地址修复，容器层的长度/索引另行更新。

## 部署条件
- 参数布局可能随游戏脚本方言变化，需要从实际行证明确认。
- 输出编码必须由部署环境决定，本模块不会偷偷选择 UTF-8。
- 全角空格和实际字体宽度需要运行时检查。
- 验证选项显示以及选中后去向，不能只看文本变了。
- 路径约束、原包保护、manifest 和最终写出由父 Skill 统一负责。

## 验证与缺口
- 合成测试覆盖 `.message`、`@name`、空名字、多个 `.select` 选项。
- 覆盖 `\n`、`\$21`、空格转义与目标不变。
- 覆盖姓名变量、未知转义和冒号注入拒绝。
- 测试位置：`tests/test_engines_primary.py` 中 `TextDialectTests`。
- 未覆盖所有 Musica 命令、自定义嵌套脚本、资源密钥或 PAZ writer。
- 未采用 VN 的自动换行器，也未把 msg-tool 的不足隐藏在统一接口后。
- 没有商业素材、外部工具或游戏运行时验证。
