# Adobe / ArcAIR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/AIR` / `GameRes.Formats.Adobe.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `uint index_pos = Binary.BigEndian (file.View.ReadUInt32 (0));` |
| `DatOpener.TryOpen` | `if (0x0A != index.ReadUInt8() \|\|` |
| `DatOpener.TryOpen` | `0x0B != index.ReadUInt8() \|\|` |
| `DatOpener.TryOpen` | `0x01 != index.ReadUInt8())` |
| `DatOpener.TryOpen` | `int length = index.ReadUInt8();` |
| `DatOpener.TryOpen` | `if (0x09 != index.ReadUInt8() \|\|` |
| `DatOpener.TryOpen` | `0x05 != index.ReadUInt8() \|\|` |
| `DatOpener.TryOpen` | `if (0x04 != index.ReadUInt8())` |
| `DatOpener.ReadInteger` | `uint u = input.ReadUInt8();` |
| `DatOpener.ReadInteger` | `uint b = input.ReadUInt8();` |
| `DatOpener.ReadInteger` | `b = input.ReadUInt8();` |
| `DatOpener.ReadInteger` | `return u \| input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Adobe.DatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_pos = Binary.BigEndian (file.View.ReadUInt32 (0));
    if (index_pos >= file.MaxOffset || 0 == index_pos || file.MaxOffset > 0x40000000)
        return null;
    uint index_size = (uint)(file.MaxOffset - index_pos);
    if (index_size > 0x100000)
        return null;
    using (var input = file.CreateStream (index_pos, index_size))
    using (var unpacked = new DeflateStream (input, CompressionMode.Decompress))
    using (var index = new BinaryStream (unpacked, file.Name))
    {
        if (0x0A != index.ReadUInt8() ||
            0x0B != index.ReadUInt8() ||
            0x01 != index.ReadUInt8())
            return null;
        var name_buffer = new byte[0x80];
        var dir = new List<Entry>();
        while (index.PeekByte() != -1)
        {
            int length = index.ReadUInt8();
            if (0 == (length & 1))
                return null;
            length >>= 1;
            if (0 == length)
                break;
            index.Read (name_buffer, 0, length);
            var name = Encoding.UTF8.GetString (name_buffer, 0, length);
            if (0x09 != index.ReadUInt8() ||
                0x05 != index.ReadUInt8() ||
                0x01 != index.ReadUInt8())
                return null;
            if (0x04 != index.ReadUInt8())
                return null;
            uint offset = ReadInteger (index);
            if (0x04 != index.ReadUInt8())
                return null;
            uint size = ReadInteger (index);
            var entry = Create<PackedEntry> (name);
            entry.Offset = offset;
            entry.Size   = size;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (0 == entry.Size)
        return Stream.Null;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new DeflateStream (input, CompressionMode.Decompress);
}
```

#### ReadInteger

```csharp
internal static uint ReadInteger (IBinaryStream input) {
    uint u = input.ReadUInt8();
    if (u < 0x80)
        return u;
    u = (u & 0x7F) << 7;
    uint b = input.ReadUInt8();
    if (b < 0x80)
        return u | b;
    u = (u | b & 0x7F) << 7;
    b = input.ReadUInt8();
    if (b < 0x80)
        return u | b;
    u = (u | b & 0x7F) << 8;
    return u | input.ReadUInt8();
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Adobe/ArcAIR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
