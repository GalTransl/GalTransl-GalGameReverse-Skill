# Palette / ArcCHR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CHR/Palette` / `GameRes.Formats.Palette.ChrOpener` | `chr` | `63686172` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ChrOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (4);` |
| `ChrOpener.TryOpen` | `int count = file.View.ReadInt32 (index_offset)+1;` |
| `ChrOpener.TryOpen` | `uint name_length = file.View.ReadByte (index_offset++);` |
| `ChrOpener.TryOpen` | `var name = file.View.ReadString (index_offset, name_length);` |
| `ChrOpener.TryOpen` | `uint size = file.View.ReadUInt32 (index_offset+name_length);` |
| `ChrOpener.TryOpen` | `OffsetX = file.View.ReadInt16 (index_offset),` |
| `ChrOpener.TryOpen` | `OffsetY = file.View.ReadInt16 (index_offset+2),` |
| `ChrOpener.OpenEntry` | `var ihdr_size = reader.ReadInt32();` |
| `ChrOpener.OpenEntry` | `writer.Write (reader.ReadBytes (ihdr_size+8));` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Palette.CharEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int  OffsetX ;

public int  OffsetY ;
```

### GameRes.Formats.Palette.VirtualCharEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public CharEntry    Source ;
```

### GameRes.Formats.Palette.ChrOpener

继承/接口：`ArchiveFormat`。

#### ChrOpener

```csharp
public ChrOpener () {
    Extensions = new string[] { "chr" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_offset = file.View.ReadUInt32 (4);
    int count = file.View.ReadInt32 (index_offset)+1;
    if (!IsSaneCount (count))
        return null;

    string base_name = Path.GetFileNameWithoutExtension (file.Name);

    var dir = new List<Entry> (count);
    dir.Add (new Entry {
        Name = string.Format ("{0}#0.png", base_name),
        Type = "image", Offset = 8, Size = index_offset-8
    });
    index_offset += 4;
    for (int i = 1; i < count; ++i)
    {
        uint name_length = file.View.ReadByte (index_offset++);
        var name = file.View.ReadString (index_offset, name_length);
        uint size = file.View.ReadUInt32 (index_offset+name_length);
        index_offset += name_length + 4;
        if (size > 8)
        {
            var entry = new CharEntry
            {
                Name = string.Format ("{0}#{1}.png", base_name, name),
                Type = "image",
                Offset = index_offset+8,
                Size = size-8,
                OffsetX = file.View.ReadInt16 (index_offset),
                OffsetY = file.View.ReadInt16 (index_offset+2),

            };
            dir.Add (entry);
            var virt_entry = new VirtualCharEntry {
                Name = string.Format ("{0}#blend#{1}.png", base_name, name),
                Type = "image",
                Source = entry,
                Offset = 0,
            };
            dir.Add (virt_entry);
        }
        index_offset += size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry is VirtualCharEntry)
        return Stream.Null;
    int extra_length = PgaFormat.PngHeader.Length + PgaFormat.PngFooter.Length;
    var png = new MemoryStream ((int)entry.Size + extra_length + 17);
    var cent = entry as CharEntry;
    png.Write (PgaFormat.PngHeader, 0, PgaFormat.PngHeader.Length);
    using (var body = arc.File.CreateStream (entry.Offset, entry.Size))
    {
        if (cent != null && cent != arc.Dir.First()
            && (cent.OffsetX != 0 || cent.OffsetY != 0))
        {

            using (var reader = new BinaryReader (body, Encoding.ASCII, true))
            using (var writer = new BinaryWriter (png, Encoding.ASCII, true))
            {
                var ihdr_size = reader.ReadInt32();
                writer.Write (ihdr_size);
                ihdr_size = Binary.BigEndian (ihdr_size);
                writer.Write (reader.ReadBytes (ihdr_size+8));

                writer.Write (Binary.BigEndian ((int)9));
                int position = (int)writer.BaseStream.Position;
                char[] tag = { 'o', 'F', 'F', 's' };
                writer.Write (tag);
                writer.Write (Binary.BigEndian (cent.OffsetX));
                writer.Write (Binary.BigEndian (cent.OffsetY));
                writer.Write ((byte)0);
                uint crc = Crc32.Compute (png.GetBuffer(), position, 13);
                writer.Write (Binary.BigEndian (crc));
            }
        }
        body.CopyTo (png);
    }
    png.Write (PgaFormat.PngFooter, 0, PgaFormat.PngFooter.Length);
    png.Position = 0;
    return png;
}
```

## 配套算法与外部条件

- [ArcFormats/Palette/ImagePGA.cs](ImagePGA.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Palette/ArcCHR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
