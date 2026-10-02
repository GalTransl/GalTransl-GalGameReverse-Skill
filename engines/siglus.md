# Siglus：Scene.pck 解包不等于 `.ss` 文本往返

## 能力与停止点
- 独立标准库参考见 `../python/archives/siglus.py`。
- 已实现受限 Scene.pck 头与场景索引、固定 XOR key、显式游戏 key、带长度检查的 LZ 解码。
- 返回的 `.ss` 是字节码，标记为 `content_type="siglus-bytecode"`，不是译文或纯文本。
- 未实现 `.ss` 指令分析、字符串引用重定位、编译器、Scene.pck writer。
- 因此目前不能宣称 Siglus 完整提取—翻译—回填—部署闭环。
- 不依赖插件、原仓库运行时、游戏可执行程序、外部 exe 或在线密钥库。
- 解包前可确认结构与密钥需求；缺失任何必要条件时拒绝，不猜测后继续。

## 识别证据：不是靠扩展名
- Scene.pck 没有 ASCII magic；开头 LE `u32 header_length` 必须为 `0x5c`。
- 文件名 `Scene.pck` 和 `.pck` 只能作为线索，不能替代结构检查。
- GARbro 将本族实现放在 `ArcFormats/RealLive`，同目录还收录 AVG32、Flix；不能据目录名把它们与 RealLive 的剧本算法合并。
- 固定头至少 92 字节；以下字段均为 little-endian。

| 偏移 | 字段 | 参考含义 |
| --- | --- | --- |
| `0x00` | `u32` | 头长，受支持值 `0x5c` |
| `0x34` | `u32` | 名称索引表绝对偏移 |
| `0x38` | `u32` | 场景数 |
| `0x3c` | `u32` | 名称字符串区绝对偏移 |
| `0x40` | `u32` | 名称计数，必须等于场景数 |
| `0x44` | `u32` | 数据位置索引表绝对偏移 |
| `0x48` | `u32` | 位置项计数，必须等于场景数 |
| `0x4c` | `u32` | 加密成员区绝对偏移 |
| `0x50` | `u32` | 数据计数，必须等于场景数 |
| `0x54` | `u32` | 额外游戏 key 标记，本参考只接受 0 或 1 |

- 名称索引每项两个 `u32`：相对名称区的 UTF-16 code-unit 偏移、code-unit 长度。
- 因此名称字节起点为 `names_at + offset * 2`，读取 `length * 2` 字节。
- 名称按严格 UTF-16LE 解码；参考 reader 追加 `.ss` 后缀。
- 数据位置索引也是两个 `u32`：相对成员区偏移、存储长度。
- 数据起点为 `data_at + relative_offset`，存储长度不能跨越输入末尾。
- 本 Python 子集要求名称索引、名称区、位置索引、成员区按该顺序且互不跨界。
- 非标准表顺序、错误计数、重复名、NUL 名、越界及过大成员一律拒绝。
- 头部 `[0x04,0x34)` 和 `0x58` 字段未解释，不应声称已验证整个游戏元数据系统。
- 这些字段可能参与后续 writer；仅理解四个场景表不足以正确重建整包。

## 两层 XOR 与 key 限制
- 固定 key 是源码 `SceneOpener.DefaultKey` 的 256 字节常量，已附许可移植。
- 每个成员从 key 第 0 字节重新开始循环 XOR，不按包内绝对偏移取 key。
- 额外标记为 1 时，再按每个成员起点循环 XOR 调用者提供的 16 字节 `game_key`。
- 两层 XOR 都覆盖成员里的压缩头，不只覆盖压缩正文。
- 没有 game key、key 长度不对、标记不是 0/1 都拒绝。
- 标记为 0 却传入 game key 也拒绝，避免误认为所有包都要第二层 XOR。
- 未移植参考源码的 `GuessKey`、游戏查表或交互查询逻辑。
- key 只能由用户合法提供并确认用途；模块不扫描可执行文件、不下载、不暴力枚举。
- 结构检查通常能发现错误 key，但格式没有认证；“解压成功”不是密钥真实性证明。

## 明文压缩帧
- XOR 后先读 LE `u32 packed_length` 与 LE `u32 unpacked_length`。
- `packed_length` 包含这 8 字节头，必须等于传入成员长度。
- 控制字节从低位到高位消费：位 1 是一个字面字节，位 0 是一个 LE `u16` 引用。
- 引用的距离为 `word >> 4`，长度为 `(word & 15) + 2`。
- 这对应 `G00Reader.LzDecompress(input, 2, 1)`，不能套另一款引擎的通用 LZSS 参数。
- 重叠复制是合法情况，例如距离 1 可以继续复制刚生成的字节。
- 距离 0、引用早于输出起点、输出越界、输入截断、解压后剩余字节都拒绝。
- 先检查声明长度和调用者预算，再分配输出；不允许无限制解压。
- 此层没有把 `.ss` 当 UTF-8/CP932 文本解码，也没有修改字节码。

## Python 函数示例
```python
from hashlib import sha256
from python.archives.siglus import extract, lz_decompress

def scene_manifest(blob: bytes, game_key: bytes | None = None) -> list[dict]:
    records = extract(blob, game_key=game_key, max_file_size=16 << 20)
    return [
        {
            "id": "Scene.pck:" + item.name,
            "member": item.name,
            "kind": item.content_type,
            "decoded_size": len(item.data),
            "decoded_sha256": sha256(item.data).hexdigest(),
            "translation_status": "blocked/no-ss-parser",
        }
        for item in records
    ]
```
- `extract(bytes, game_key=...) -> list[Entry]` 返回名称、字节码、偏移、存储长度和类型。
- `lz_decompress(bytes) -> bytes` 仅处理已经解除 XOR 的完整压缩帧。
- 示例不落盘；若要保存 `.ss`，必须通过调用者的安全输出器并使用新目录。
- 输出器仍须拒绝穿越路径、盘符、归一化重名和符号链接绕过。

## JSON 映射：当前只能记录字节码制品
```json
{
  "id": "Scene.pck:start.ss",
  "member": "start.ss",
  "kind": "siglus-bytecode",
  "decoded_size": 1234,
  "decoded_sha256": "<实际字节码 SHA256>",
  "translation_status": "blocked/no-ss-parser"
}
```
- 此处 `decoded_size` 为示例值；实际值由函数产生，不把压缩长度当文本长度。
- 不应为这一记录填写“译文”，也不能把二进制扫描出的可打印串直接替换回去。
- 后续文本记录至少需要 scene ID、指令/字符串表索引、原字节区间、源哈希、引用信息。
- 姓名、对白、选项、系统文本、资源路径必须按调用位置和指令语义区分。
- 同一字符串可能被多个指令共享，重复字符串也可能是独立条目；不能按字面值合并。

## 下一步缺失：`.ss` 字节码与回填
1. 为目标版本确认 `.ss` 头、区段、字符串表和指令边界，建立独立人工最小样本。
2. 只在确认编码后解读字符串；名称索引为 UTF-16LE 不能证明所有字节码字符串同编码。
3. 建立操作码长度和引用关系，分离对白/选项与脚本标识符、资源参数。
4. 为每个可翻译项建立可逆 JSON 映射，保护控制串、变量和占位符。
5. 确认替换策略：固定槽位、字符串表重排还是完整重编译，不能默认允许变长原地覆盖。
6. 若变长影响偏移、跳转、字符串索引或区段长度，重建全部相关引用并验证范围。
7. 再设计压缩编码、两层 XOR、场景索引和未知头字段保留策略，才谈 Scene.pck writer。
8. 最后验证加载顺序、字体、编码和运行时表现；目前这些步骤均未交付。

## 部署与验证证据
- 不能把解得 `.ss` 直接当 loose override 部署；运行时是否支持以及优先级均需实测。
- 不覆盖原 Scene.pck；保留原始哈希、原包和合法 key 的来源记录。
- `../tests/test_archives.py` 的 `SiglusTests` 仅使用手造场景表和 LZ 帧。
- 覆盖 0x5c 头、四处计数一致、名称 code-unit 边界、位置越界和重复场景名。
- 覆盖固定 key 首尾常量、256/16 周期与成员起点重置、缺 key、错误 key、错误标记。
- 覆盖字面量、多控制字节、合法重叠引用、非法距离、长短不符和超限压缩头。
- 未运行真实游戏，未证明 `.ss` 编译器一致性，未进行付费 API 或密码恢复操作。
- 合成测试证明这里的受限算法能按预期读写内存，不证明任何完整游戏汉化兼容性。

## 相对源码出处与许可
- GARbro-Mod `ArcFormats/RealLive/ArcSCENE.cs`：`SceneOpener.TryOpen/OpenEntry/DefaultKey`。
- GARbro-Mod `ArcFormats/RealLive/ImageG00.cs`：`G00Reader.LzDecompress`，参数 `2, 1`。
- 均核对提交 `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`，文件头 MIT 许可。
- 参考代码中缺少本任务所需的 `.ss` 文本重编译链，不虚构其已经存在。
- Python 模块保留许可和源码符号，验证矩阵见 `../provenance/archives.json`。
