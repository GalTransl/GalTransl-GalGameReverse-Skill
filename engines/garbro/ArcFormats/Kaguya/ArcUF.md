# Kaguya / ArcUF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/UF01` / `GameRes.Formats.Kaguya.UfOpener` | `arc` | `55463031` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `UfOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (4);` |
| `UfOpener.TryOpen` | `int name_length = index.ReadInt32();` |
| `UfOpener.TryOpen` | `int flags = index.ReadInt16();` |
| `UfOpener.TryOpen` | `entry.Size   = index.ReadUInt32();` |
| `UfOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kaguya.UfOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
const int MaxFileNameLength = 0x100 ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_offset = file.View.ReadUInt32 (4);
    if (index_offset >= file.MaxOffset - 4)
        return null;
    using (var index = file.CreateStream (index_offset+4))
    {
        long data_offset = 8;
        var name_buffer = new byte[MaxFileNameLength];
        var dir = new List<Entry>();
        while (index.PeekByte() != -1)
        {
            int name_length = index.ReadInt32();
            if (name_length <= 0 || name_length > name_buffer.Length)
                return null;
            if (name_length != index.Read (name_buffer, 0, name_length))
                return null;
            var name = DecryptString (name_buffer, name_length);
            name = name.TrimStart ('\\', '/');
            var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
            int flags = index.ReadInt16();
            data_offset += 4 + name_length + 6;
            entry.Offset = data_offset;
            entry.Size   = index.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            entry.IsPacked = 1 == flags;
            dir.Add (entry);
            data_offset += entry.Size;
            if (entry.IsPacked)
                data_offset += 4;
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    if (0 == pent.UnpackedSize)
    {
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);
        if (0 == pent.UnpackedSize)
            return Stream.Null;
    }
    using (var input = arc.File.CreateStream (entry.Offset+4, entry.Size))
    {
        var output = new byte[pent.UnpackedSize];
        LzUnpack (input, output);
        return new BinMemoryStream (output);
    }
}
```

#### DecryptString

```csharp
string DecryptString (byte[] name, int length) {
    for (int i = 0; i < length; ++i)
        name[i] ^= 0xFF;
    return Encodings.cp932.GetString (name, 0, length);
}
```

#### LzUnpack

```csharp
void LzUnpack (Stream input, byte[] output) {
    var frame = new byte[0x1000];
    int frame_pos = 1;
    int dst = 0;
    using (var bits = new MsbBitStream (input))
    {
        while (dst < output.Length)
        {
            if (0 != bits.GetNextBit())
            {
                byte b = (byte)bits.GetBits (8);
                output[dst++] = b;
                frame[frame_pos++ & 0xFFF] = b;
            }
            else
            {
                int offset = bits.GetBits (12);
                int count = bits.GetBits (4) + 2;
                for (int i = 0; i < count; ++i)
                {
                    byte b = frame[(offset + i) & 0xFFF];
                    output[dst++] = b;
                    frame[frame_pos++ & 0xFFF] = b;
                }
            }
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Kaguya/ArcUF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
