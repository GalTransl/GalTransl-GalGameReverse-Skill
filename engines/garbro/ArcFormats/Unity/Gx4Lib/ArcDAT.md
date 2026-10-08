# Gx4Lib / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/GX4LIB` / `GameRes.Formats.Unity.Gx4Lib.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (0);` |
| `DatOpener.TryOpen` | `if (file.View.ReadInt32 (5) != 1 \|\| file.View.ReadInt32 (9) != -1)` |
| `DatOpener.OpenEntry` | `if (arc.File.View.AsciiEqual (entry.Offset, "UnityRaw"))` |
| `DatOpener.OpenEntry` | `byte id = arc.File.View.ReadByte (entry.Offset);` |
| `DatOpener.OpenEntry` | `uint packed_size = arc.File.View.ReadUInt32 (entry.Offset+1);` |
| `DatOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+5);` |
| `DatOpener.OpenUnityRaw` | `var signature = input.ReadCString();` |
| `DatOpener.OpenUnityRaw` | `int format = input.ReadInt32();` |
| `DatOpener.OpenUnityRaw` | `input.ReadCString();` |
| `DatOpener.OpenUnityRaw` | `uint file_size = input.ReadUInt32();` |
| `DatOpener.OpenUnityRaw` | `uint header_size = input.ReadUInt32();` |
| `DatOpener.OpenUnityRaw` | `int entry_count = input.ReadInt32();` |
| `DatOpener.OpenUnityRaw` | `int bundle_count = input.ReadInt32();` |
| `DatOpener.OpenUnityRaw` | `int count = input.ReadInt32();` |
| `DatOpener.OpenUnityRaw` | `header_size = input.ReadUInt32();` |
| `DatOpener.OpenUnityRaw` | `uint asset_size = input.ReadUInt32();` |
| `DatOpener.QlzUnpack` | `bits = input.ReadUInt32();` |
| `DatOpener.QlzUnpack` | `offset = input.ReadUInt8() >> 2;` |
| `DatOpener.QlzUnpack` | `offset = input.ReadUInt16() >> 2;` |
| `DatOpener.QlzUnpack` | `offset = input.ReadUInt16() >> 6;` |
| `DatOpener.QlzUnpack` | `offset = (input.ReadInt24() >> 7) & 0x1FFFF;` |
| `DatOpener.QlzUnpack` | `uint v = input.ReadUInt32();` |
| `DatOpener.QlzUnpack` | `output[dst++] = input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Unity.Gx4Lib.VisualDiffData

#### 状态与常量

```csharp
public string   BaseFileName ;

public int      PosX ;

public int      PosY ;
```

### GameRes.Formats.Unity.Gx4Lib.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
Lazy<Dictionary<string, VisualDiffData>>  DefaultVisualMap = new Lazy<Dictionary<string, VisualDiffData>> (ReadVisualData) ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_size = file.View.ReadUInt32 (0);
    if (index_size <= 12 || index_size >= file.MaxOffset)
        return null;
    if (file.View.ReadInt32 (5) != 1 || file.View.ReadInt32 (9) != -1)
        return null;
    using (var hstream = file.CreateStream (4, index_size))
    {
        var pf = new PackageFile();
        var index = pf.Deserialize (hstream);
        if (null == index)
            return null;
        string type = "";
        if (index is PFAudioHeaders)
            type = "audio";
        else if (index is PFImageHeaders)
            type = "image";
        uint data_offset = index_size + 4;
        var dir = index.headers.Select (h => new PackedEntry {
            Name = h.FileName,
            Type = type,
            Offset = h.readStartBytePos + data_offset,
            Size = (uint)h.ByteLength
        } as Entry).ToList();
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (arc.File.View.AsciiEqual (entry.Offset, "UnityRaw"))
        return OpenUnityRaw (arc, entry);
    var pent = (PackedEntry)entry;
    if (!pent.IsPacked)
    {
        byte id = arc.File.View.ReadByte (entry.Offset);
        uint packed_size = arc.File.View.ReadUInt32 (entry.Offset+1);
        if ((id & ~1) != 0x5E || packed_size != entry.Size)
            return base.OpenEntry (arc, entry);
        pent.IsPacked = 0 != (id & 1);
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+5);
    }
    if (!pent.IsPacked)
        return arc.File.CreateStream (pent.Offset+9, pent.UnpackedSize);
    var data = new byte[pent.UnpackedSize];
    using (var input = arc.File.CreateStream (pent.Offset+9, pent.Size))
        QlzUnpack (input, data);
    return new BinMemoryStream (data, entry.Name);
}
```

#### OpenUnityRaw

```csharp
Stream OpenUnityRaw (ArcFile arc, Entry entry) {
    using (var stream = arc.File.CreateStream (entry.Offset, entry.Size))
    using (var input = new AssetReader (stream))
    {
        var signature = input.ReadCString();
        if (signature != "UnityRaw")
            return base.OpenEntry (arc, entry);
        int format = input.ReadInt32();
        input.ReadCString();
        input.ReadCString();
        uint file_size = input.ReadUInt32();
        if (file_size != entry.Size)
            return base.OpenEntry (arc, entry);
        uint header_size = input.ReadUInt32();
        int entry_count = input.ReadInt32();
        int bundle_count = input.ReadInt32();
        if (entry_count != 1 || bundle_count != 1)
            return base.OpenEntry (arc, entry);

        input.Position = header_size;
        int count = input.ReadInt32();
        long asset_pos = input.Position;
        input.ReadCString();
        header_size = input.ReadUInt32();
        uint asset_size = input.ReadUInt32();
        long base_pos = asset_pos + header_size - 4;

        input.Position = base_pos;
        var index = new ResourcesAssetsDeserializer (arc.File.Name);
        var dir = index.Parse (input, base_pos);
        if (null == dir || 0 == dir.Count)
            return base.OpenEntry (arc, entry);;
        return arc.File.CreateStream (entry.Offset + dir[0].Offset, dir[0].Size);
    }
}
```

#### QlzUnpack

```csharp
void QlzUnpack (IBinaryStream input, byte[] output) {
    int dst = 0;
    uint bits = 1;
    int output_last = output.Length - 11;
    while (dst < output.Length)
    {
        if (1 == bits)
        {
            bits = input.ReadUInt32();
        }
        if ((bits & 1) == 1)
        {
            int ctl = input.PeekByte();
            int offset, count = 3;
            if ((ctl & 3) == 0)
            {
                offset = input.ReadUInt8() >> 2;
            }
            else if ((ctl & 2) == 0)
            {
                offset = input.ReadUInt16() >> 2;
            }
            else if ((ctl & 1) == 0)
            {
                offset = input.ReadUInt16() >> 6;
                count += ((ctl >> 2) & 0xF);
            }
            else if ((ctl & 0x7F) != 3)
            {
                offset = (input.ReadInt24() >> 7) & 0x1FFFF;
                count += ((ctl >> 2) & 0x1F) - 1;
            }
            else
            {
                uint v = input.ReadUInt32();
                offset = (int)(v >> 15);
                count += (int)((v >> 7) & 0xFF);
            }
            Binary.CopyOverlapped (output, dst-offset, dst, count);
            dst += count;
        }
        else
        {
            if (dst > output_last)
                break;
            output[dst++] = input.ReadUInt8();
        }
        bits >>= 1;
    }
    while (dst < output.Length)
    {
        if (1 == bits)
        {
            input.Seek (4, SeekOrigin.Current);
            bits = 0x80000000u;
        }
        output[dst++] = input.ReadUInt8();
        bits >>= 1;
    }
}
```

#### ReadVisualData

```csharp
internal static Dictionary<string, VisualDiffData> ReadVisualData () {
    var map = new Dictionary<string, VisualDiffData>();
    try
    {
        FormatCatalog.Instance.ReadFileList (name_list_parameter, (line) => {
            var parts = line.Split (':', ',');
            if (parts.Length > 3)
            {
                var diff = new VisualDiffData { BaseFileName = parts[1] };
                if (int.TryParse (parts[2], out diff.PosX) && int.TryParse (parts[3], out diff.PosY))
                    map[parts[0]] = diff;
            }
        });
    }
    catch {  }
    return map;
}
```

## 配套算法与外部条件

- [ArcFormats/Unity/AssetReader.cs](../AssetReader.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/ResourcesAssets.cs](../ResourcesAssets.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Unity/Gx4Lib/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
