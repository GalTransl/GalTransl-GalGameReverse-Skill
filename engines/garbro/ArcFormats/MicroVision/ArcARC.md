# MicroVision / ArcARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/MICROVISION` / `GameRes.Formats.MicroVision.ArcOpener` | `arc` | `41524331` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `int count = (int)arc.ReadHeader (0xD);` |
| `ArcOpener.TryOpen` | `uint names_offset = arc.ReadHeader (8);` |
| `ArcOpener.TryOpen` | `names_length = arc.ReadHeader (9);` |
| `ArcOpener.TryOpen` | `names_offset = arc.ReadHeader (7);` |
| `ArcOpener.TryOpen` | `names_length = arc.ReadHeader (6);` |
| `ArcOpener.TryOpen` | `uint index_offset = arc.ReadHeader (4);` |
| `ArcOpener.TryOpen` | `var name = file.View.ReadString (name_offset, name_length);` |
| `ArcOpener.LzUnpack` | `ctl = input.ReadByte();` |
| `ArcOpener.LzUnpack` | `byte b = (byte)input.ReadByte();` |
| `ArcOpener.LzUnpack` | `int lo = input.ReadByte();` |
| `ArcOpener.LzUnpack` | `int hi = input.ReadByte();` |
| `ArcReader.ReadHeader` | `public uint ReadHeader (uint offset) {` |
| `ArcReader.ReadHeader` | `return ReadUInt32 (offset, HeaderObfuscationStep);` |
| `ArcReader.ReadIndex` | `return ReadUInt32 (offset, IndexObfuscationStep);` |
| `ArcReader.ReadUInt32` | `uint ReadUInt32 (uint offset, uint step) {` |
| `ArcReader.ReadUInt32` | `uint v = m_file.View.ReadByte (offset);` |
| `ArcReader.ReadUInt32` | `v \|= (uint)m_file.View.ReadByte (offset) << 8;` |
| `ArcReader.ReadUInt32` | `v \|= (uint)m_file.View.ReadByte (offset) << 16;` |
| `ArcReader.ReadUInt32` | `v \|= (uint)m_file.View.ReadByte (offset) << 24;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.MicroVision.ArcOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var arc = new ArcReader (file);
    int count = (int)arc.ReadHeader (0xD);
    if (!IsSaneCount (count))
        return null;
    uint names_length;
    uint names_offset = arc.ReadHeader (8);
    if (names_offset != 0)
    {
        names_length = arc.ReadHeader (9);
    }
    else
    {
        names_offset = arc.ReadHeader (7);
        names_length = arc.ReadHeader (6);
    }
    uint index_size = names_offset + names_length;
    index_size = (index_size + 0x7Fu) & ~0x7Fu;
    if (index_size < 0x40 || index_size >= file.MaxOffset)
        return null;
    file.View.Reserve (0, index_size);
    uint index_offset = arc.ReadHeader (4);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name_offset = arc.ReadIndex (index_offset+2);
        var name_length = arc.ReadIndex (index_offset+3);
        var name = file.View.ReadString (name_offset, name_length);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset = arc.ReadIndex (index_offset+4);
        entry.Size   = arc.ReadIndex (index_offset+5);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.UnpackedSize = arc.ReadIndex (index_offset+6);
        entry.IsPacked = entry.UnpackedSize != entry.Size;
        dir.Add (entry);
        index_offset += 0x20;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return base.OpenEntry (arc, entry);
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var data = new byte[pent.UnpackedSize];
    LzUnpack (input, data);
    return new BinMemoryStream (data);
}
```

#### LzUnpack

```csharp
void LzUnpack (Stream input, byte[] output) {
    var frame = new byte[0x1000];
    int frame_pos = 1;
    const int frame_mask = 0xFFF;
    int dst = 0;
    int bit = 0;
    int ctl = 0;
    while (dst < output.Length)
    {
        if (0 == bit)
        {
            ctl = input.ReadByte();
            if (-1 == ctl)
                break;
            bit = 0x80;
        }
        if (0 != (ctl & bit))
        {
            byte b = (byte)input.ReadByte();
            frame[frame_pos++ & frame_mask] = b;
            output[dst++] = b;
        }
        else
        {
            int lo = input.ReadByte();
            int hi = input.ReadByte();
            if (-1 == lo || -1 == hi)
                break;
            int offset = hi >> 4 | lo << 4;
            for (int count = 2 + (hi & 0xF); count > 0 && dst < output.Length; --count)
            {
                byte v = frame[offset++ & frame_mask];
                frame[frame_pos++ & frame_mask] = v;
                output[dst++] = v;
            }
        }
        bit >>= 1;
    }
}
```

### GameRes.Formats.MicroVision.ArcReader

#### 状态与常量

```csharp
ArcView     m_file ;

const uint HeaderObfuscationStep = 0xC ;

const uint IndexObfuscationStep = 7 ;
```

#### ArcReader

```csharp
public ArcReader (ArcView file) {
    m_file = file;
}
```

#### ReadHeader

```csharp
public uint ReadHeader (uint offset) {
    return ReadUInt32 (offset, HeaderObfuscationStep);
}
```

#### ReadIndex

```csharp
public uint ReadIndex (uint offset) {
    return ReadUInt32 (offset, IndexObfuscationStep);
}
```

#### ReadUInt32

```csharp
uint ReadUInt32 (uint offset, uint step) {
    uint v = m_file.View.ReadByte (offset);
    offset += step;
    v |= (uint)m_file.View.ReadByte (offset) << 8;
    offset += step;
    v |= (uint)m_file.View.ReadByte (offset) << 16;
    offset += step;
    v |= (uint)m_file.View.ReadByte (offset) << 24;
    return v;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/MicroVision/ArcARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
