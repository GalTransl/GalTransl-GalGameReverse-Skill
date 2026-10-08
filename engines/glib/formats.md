# GLib / GML_ARC、BCS、GMS 与 FDT2

格式资料，无随包 Python reader/writer、真实解包/回填/重封包或显示验证。GML_ARC 与 LZSS 已按[随包 GARbro 算法](../garbro/ArcFormats/GLib/ArcG.md)交叉核对；BCS/GMS/FDT2 来自[工程备忘录](../../provenance/translation-engineering-notes.json)，仍须确认目标加载器。不同 GLib 版本不可只按名称套用。整数默认小端。

## 三层读取

`GML_ARC -> BCS 解压体 -> GMS 解码字符串池`，各层分别校验大小与预算。媒体成员不因在同包中就按 BCS 解码。

| GML_ARC 偏移 | 字段 |
|---|---|
| `0` | 8 字节 `GML_ARC\0` |
| `8` | u32 data_offset |
| `0x0C` | u32 index_unpacked |
| `0x10` | u32 index_packed |
| `0x14` | index_packed 字节，先 XOR FF，再 LZSS |

索引解压体为 256 字节置换表、i32 count，再逐项 i32 name_length、该长度内 CP932/NUL 名称、u32 relative_offset、u32 size、4 字节原始成员头。成员绝对位置为 data_offset+relative_offset；从第 4 字节起用 `key[stored_byte]` 还原，前 4 字节由索引头恢复。原存储前 4 字节也应保留用于保真重建。

读取时核对每个跨度、短成员及名称边界；置换表可能满足解码但非一一对应，writer 必须确认全部 256 值唯一再生成逆表。索引明确存压缩大小，不把下面的 BCS 读取预算套到此层。

## BCS 行表与字段语义

| 偏移 | 字段 |
|---|---|
| `0` | `BCS\0` |
| `4` | u32 dec_size，body 解压后长度 |
| `8` | u32 n1，table1 条目数 |
| `0x0C` | u32 n_label，原样保留，完整语义待核 |
| `0x10` | u32 n2，table2 条目数 |
| `0x14` | u32 str_size，GMS 解码池大小 |
| `0x18` | body 的 LZSS 流，不 XOR |

解压体依次为 `8*n1` 字节 table1、`8*n2` 字节 table2、GMS 块。table1 项是 `(u32 count, u32 start)`，start 为 table2 **条目下标**，行跨度需在 n2 内；table2 项是 `(u32 type, u32 payload)`，type3 为字符串池字节偏移、type1 为整数。其他 type 的语义不充分，不默认当空槽可删除。

首行可定义 `%line/%seq/%name/%voice/%text` 等字段；按字段定义建立映射，不硬编码每行恰好 14 列。`%text` 为正文候选，`%name` 为显示名候选，`%truename` 等内部身份不混作译名。`%seq` 中 `$menu 显示文本,目标` 的拆分、转义及目标类型需独立核对；`#` 标记是否为调试行也须结构验证，不能按前缀一律丢弃。

仅改池内容时 table1 下标通常不动，重定位所有已证明的 type3 字节偏移；共享的资源/正文引用不能全局覆盖。保持原池项身份、顺序、NUL 和尾部填充，未经证明不按内容去重。

## GMS 换位头与校验

GMS 块的头长 `0x10`。对磁盘头交换 `(9,13)、(11,15)、(4,8)、(6,10)` 后，四个 u32 依次为 `GMS\0`、checksum、保留、pool_size。该交换自身可逆，写回使用相同交换；保留字段原样。

头后 LZSS 解压到 pool_size，再逐字节 XOR FF 得 CP932/NUL 字符串池。BCS.str_size、GMS.pool_size 与实际池长度应一致，所有引用指向有效字符串起点。

备忘录给出的校验为 `sum(pool[i] + i%253) mod 2^32`，作用于 XOR 后的明文池。设 `q,r=divmod(len(pool),253)`，则 `checksum=(sum(pool)+q*253*252//2+r*(r-1)//2)&0xFFFFFFFF`。修改后重算并写入换位前的 checksum 字段，不能只修长度；保留该公式为已记录方言，部署前与加载器核对。

## LZSS 与压缩读取预算

4096 字节零窗口，写指针 `0xFEE`；控制字节低位优先，1 为 literal，0 读 lo/hi：窗口位置 `lo|((hi&0xF0)<<4)`，长度 `(~hi&0x0F)+3`，允许逐字节重叠复制。此反向长度 nibble 与普通 `(hi&15)+3` LZSS 不同。严格实现拒绝截断和输出越界，不继承 GARbro 提前结束/截断匹配的宽松行为。

备忘录记录的 BCS 加载器最多读取 dec_size 字节作为压缩输入，因此该方言要求 **packed_body_size <= dec_size**。全 literal 流可能增大约 1/8，不能凭能解压就认定可加载。GMS 的加载输入范围另行确认，不泛化这一不等式到所有引擎；压缩需使用匹配变体并按实际读取范围回读验证。

## FDT2 位图字库

记录布局为：`0 FDT2`、`+8 u16 width`、`+0x0A u16 height`、`+0x0C u32 bpp`、`+0x14 u32 glyph_count`、`+0x1C u32 code_table_size`、`+0x20 u32 bitmap_size`，`+0x24` 后 glyph_count 个 u16 码表，再接字形数据。其他头字段含义未完整给出，必须保留；先验证头、表、实际跨度及乘法预算。

记录方言为 4bpp，左像素在低 nibble，右像素在高 nibble；24x24 对应每字 288 字节，仅当头部尺寸匹配时适用。码表记录 SJIS 双字节码取反后的值；取反会反转数值排序，不能照搬“取反后仍升序”描述，应核对加载器比较器、字节组合、表序和别名。单字节字与缺字处理未完整定义。

字库容量、系统字体回退和动态扩容依赖实际渲染实现，不能由 FDT2 头部推断。如重绘，采用本批公共 JIS 映射，保留未改字形与非字形区域，验证像素方向、灰度及标点位置。换系统字体未必影响正在使用的位图字库；没有加载器/字库样本时不生成可部署字体。
