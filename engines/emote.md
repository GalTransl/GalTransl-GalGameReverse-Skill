# Emote PSB：资源包读取与内嵌资源导出

`PSB\0` 容器有两种用法：Kirikiri 的 SCN 对象树（见 [kirikiri_psb.py](../python/engines/kirikiri_psb.py)，只处理无资源区段的可写方言），以及 Emote 的**图片资源包**。本页只覆盖后者，入口是 [emote_psb.py](../python/archives/emote_psb.py)：只读解析头部、名称表和对象树，导出内嵌载荷；不写回、不解码图像、不做图层合成。

## 识别条件

| 条件 | 说明 |
|---|---|
| 文件头 | `PSB\0`，版本 u16 = 2 或 3 |
| 载荷表 | `chunk_offsets` / `chunk_lengths` 非空，且 `chunk_data` 之后仍有数据（`chunk_data < 文件长度`） |
| 对象树 | 根节点 tag `0x21`（字典）；节点中可能出现 tag `0x19`–`0x1C` 的**载荷引用** |
| 常见扩展名 | `dpak`、`pimg`、`psb`、`psbz`、`psp`（扩展名不是判据） |

SCN 的 `chunk_data` 等于文件长度、两张表都为空，因此不会被当成本页的资源包；`kirikiri_psb.py` 也会拒绝带资源区段的输入。二者不能互相替代。

## 结构与读取

| 部位 | 字段 |
|---|---|
| 头部 | 偏移 4 起为 version(u16)、flags(u16)，其后 0x20 字节内依次为 names、strings、strings_data、chunk_offsets、chunk_lengths、chunk_data、root（u32）；v3 在偏移 40 另有头部校验字段 |
| 名称表 | 两张 packed 数组组成的前缀树，按字符回溯还原属性名；字典节点的键 id 在这里解析 |
| 对象树 | 从 `root` 起按 tag 递归：整型 `0x04`–`0x0C`、字符串 `0x15`–`0x18`、载荷 `0x19`–`0x1C`、浮点 `0x1D`–`0x1F`、列表 `0x20`、字典 `0x21` |
| 载荷表 | `chunk_offsets` 与 `chunk_lengths` 按下标一一对应，绝对偏移为 `chunk_data + 相对偏移` |

载荷名按容器约定取：根字典中值为载荷引用的键（对应 `GetChunks`）、`<layer_id>.tlg` 这类同名键（对应 `GetLayers`）、以及 `source` 下 `texture`/`icon` 的 `pixel`（对应 `GetTextures`）。取不到名的条目按序号加识别出的扩展名落盘。

```text
python -m python.archives.emote_psb list "entry.dpak"
python -m python.archives.emote_psb extract "entry.dpak" "新的输出目录"
```

`extract` 用不覆盖写入，容器名先经安全校验，非法或重名时退回 `resource_<序号><扩展名>`，实际写出的名字在报告中列出。载荷按内层魔数分类（PNG / TLG / WebP / BMP，其余记 `unknown`）；只导出字节，不转换格式。

同族的**引用文本**（`.dref`）是另一层：成员正文可能是 SimpleCrypt 包装的 UTF-16LE 文本，内容为若干行 `psb://<包名>/<内层名>`。包装层沿用 [kirikiri_simple_crypt.py](../python/engines/kirikiri_simple_crypt.py) 的解包/回写，本页不另做实现。

## 边界与限制

- 只读。没有 writer，不重建载荷表、名称表或对象树。
- 拒绝加密包：flags 的 bit 0 / bit 1 表示头部/正文加密，本包不猜密钥，直接报错，不半解析。
- 只接受版本 2 与 3。更高版本的头部扩展字段（extra offsets/lengths/data）和 tag `0x22`–`0x25` 未实现，遇到即拒绝。
- 不导出纹理、图层、图标等合成结果，也不解码 TLG；需要图片时先按上述命令取原始载荷。
- 单文件预算 128 MiB，节点数、深度、名称长度、载荷数与载荷范围都有上限，越界即报错而不是截断。

## 验证

合成回归：[test_emote_psb.py](../tests/test_emote_psb.py) 覆盖具名载荷与两字节载荷下标、未知载荷类型、v2 头部、脚本对象树不被误判、头部/区段/载荷范围的拒绝，以及 CLI 的不覆盖写入。

解析通过只说明容器读对了，不代表已解码图像、已合成图层或游戏能加载；这些阶段各自单独验证，实际状态写在本次运行的结果目录。

## 出处与许可

布局参考 GARbro-Mod `ArcFormats/Emote/ArcPSB.cs`（MIT，morkt），完整 MIT 原文在 [xp3.py](../python/archives/xp3.py) 头部；本页算法范围与来源另见 [Kirikiri 来源](../provenance/kirikiri-sources.json)。路径是出处，使用时不需要访问外部仓库。
