# BlueGale：BDT 与 indexwww.dat 联动

## 识别与目录线索
- 对应 SExtractor `Engine_BlueGale_bdt`，剧本后缀 `.bdt`。
- 本页不是 BlueGale 图像、视频或所有资源容器的转换器。
- BDT 源读取器没有固定 magic 校验，只提供按字节 XOR 的解密。
- 识别需结合目录来源、解密后的 CRLF 行及标签/台词语法。
- `indexwww.dat` 是源 writer 生成的伴随索引，不是可以忽略的缓存。
- 若目录中有 `.snn` 与同名 `.Inx`，它们是另一层资源包线索。
- GARbro-Mod `BlueGale/ArcSNN.cs` 要求这对文件同时存在。
- SNN 的 Inx 每条 `0x48` 字节：`0x40` 名称、offset、size。
- 它与 BDT 的 16 字节标签索引完全不同，不能混用。

## 容器 → BDT
- 先按实测容器版本提取 BDT，保留原名字和相对位置。
- 本 leaf 不读取 SNN/Inx，也不实现它们的 writer。
- 不能只因扩展名为 DAT 就把 indexwww.dat 当作文本解密。
- 记录 BDT 原始加密状态；源设置 `decrypt=1` 是用户明确选择。
- [xor_bdt](../python/engines/bluegale.py#L7) 逐字节 `XOR FF`。
- 同一函数用于加密与解密；不修改输入 bytes。
- 解密后所有偏移均以明文 BDT 开头为基准。
- XOR 不改变长度，因此同一 offset 也可定位密文对应字节。

## 行语法与提取
- 源预设按精确 CRLF 拆分，不按操作系统默认换行处理。
- 以可选空白后 `(`、`$`、`%`、`#` 开始的行先跳过。
- `$` 和 `%` 是标签相关行，不能作为台词翻译。
- `V` 加数字/大写字母可作为台词前置声频标识。
- `!名字` 后接空白和双引号，再跟 message。
- 没有 `!名字` 时，以双引号开始的是旁白/message。
- 源规则捕获从开引号之后直到行末，不要求额外闭引号。
- `QP` 后的二项或三项逗号字段在预设中作为选项候选。
- [dialogue_spans](../python/engines/bluegale.py#L43) 给出角色与字符跨度。
- 它只支持核实过的这组语法，不是 BDT 全语言解析器。
- 其中 span 是 str 的字符位置；标签索引却必须按编码后 bytes 计算。
- 不能拿字符位置直接写回二进制标签 offset。
- 译文中的换行、逗号和引号须按具体命令语法检查。

## indexwww.dat 算法
- [build_index](../python/engines/bluegale.py#L11) 从翻译后的明文重建索引。
- 标签行匹配 `^\t*[$%](.*)$`，前导只允许 TAB，遵循源 writer。
- 标签名是 `$`/`%` 之后的原始字节，不包含标签符号。
- offset 指向该行的 `$`/`%`，不是行首 TAB，也不是标签名首字节。
- 每条索引用 little-endian `<8sII`。
- 第一个字段为最多八字节的原标签名，短者补零。
- 第二字段是标签 offset。
- 第三字段是下一标签 offset 减去本标签 offset。
- 最后一个标签 length 必须为零，不能擅自改为至文件末尾。
- 默认容量 `0xFA0 = 4000`，总索引大小 `64000` 字节。
- 未使用的槽位全零填充，标签保持源文件出现顺序。
- 全部计数包括 CRLF 的两个字节和前导 TAB。
- 名称超八字节、重名、空标签或超过容量时明确拒绝。
- 这比原 `struct.pack('8s')` 静默截短更保守，避免标签歧义。

## 回填部署
- 先严格编码全部修改行，再用原 CRLF 组合完整明文。
- name 与 message 的替换不得修改声频 ID、QP 语法或标签。
- [package_script](../python/engines/bluegale.py#L59) 返回两个 bytes 结果。
- 第一个是 XOR 后 BDT，第二个是匹配它的新 indexwww.dat。
- 必须将二者作为一组事务交给公共层写出。
- 若只覆盖 BDT，变长后的跳转很可能读取错误位置。
- 目录中多个 BDT 如何共享索引由实际游戏决定，不能循环覆盖同一索引。
- 本函数只针对单个已确认拥有该索引的剧本数据流。
- 外层封包、免封包覆盖优先级和字体支持仍需单独验证。

## 调用示意
```python
from python.engines import bluegale
plain = bluegale.xor_bdt(encrypted_bdt)
# modified_plain 是已保留标签、语法、CRLF 的编码后完整明文。
new_bdt, new_index = bluegale.package_script(modified_plain)
assert bluegale.xor_bdt(new_bdt) == modified_plain
```
- 不要在 leaf 内猜测磁盘目录或自行创建 indexwww.dat。
- 公共层决定输出位置、备份和两个文件的原子部署策略。

## 验证与边界
- 合成测试确认标签前 TAB 参与 offset、标签符号本身为指向位置。
- 验证下一标签差值、最后零长度以及 4000 槽填充。
- 验证 name/message/QP 字段、XOR 互逆和所有截断拒绝条件。
- 尚无商业游戏资源实测，也未验证其他 BDT 方言。
- 未实现 SNN/Inx 容器、完整语法校验和跨 BDT 合并索引。
- 遇到不符合规则的标签必须停止并检查版本，不能修改游戏 ID 凑八字节。

## 来源与许可
- SExtractor commit：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 主要来源：`src/extract_BlueGale_bdt.py` 的 `decrypt`、`replaceEndImp`。
- 语法来源：`src/engine.ini` 的 `Engine_BlueGale_bdt`。
- [固定源码](https://github.com/satan53x/SExtractor/blob/8d8d976fd04ae54e7c677705af937273d04a376a/src/extract_BlueGale_bdt.py)。
- 容器补充只参考 GARbro-Mod `ArcFormats/BlueGale/ArcSNN.cs`。
- GARbro-Mod 固定提交 `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`，文件含 MIT 许可头。
- Python 改编来源为 SExtractor GPLv3，模块按 GPL-3.0-only 标注。
- 验证范围与来源链见 [provenance](../provenance/sextractor-core.json)。
