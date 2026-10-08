# Sviu / ArcPKZ：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PKZ` / `GameRes.Formats.Sviu.PkzOpener` | `pkz` | `504b5a30` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PkzOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `PkzOpener.TryOpen` | `var index = file.View.ReadBytes (8, data_offset - 8);` |
| `PkzOpener.TryOpen` | `entry.Size   = index.ToUInt32 (index_offset+0x20);` |
| `PkzOpener.TryOpen` | `entry.Offset = index.ToUInt32 (index_offset+0x24) + data_offset;` |
| `PkzOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `PkzOpener.OpenEntry` | `if (data.AsciiEqual (0, "SVS1"))` |
| `PkzOpener.UnpackScript` | `if (data.ToInt32 (0x10) == 0)` |
| `PkzOpener.UnpackScript` | `int unpacked_size = data.ToInt32 (0xC);` |
| `PkzOpener.UnpackScript` | `int header_size = data.ToInt32 (0x14);` |
| `PkzOpener.UnpackScript` | `int packed_size = data.ToInt32 (0x1C);` |
| `PkzOpener.LzUnpack` | `ctl = input.ReadByte();` |
| `PkzOpener.LzUnpack` | `byte b = input.ReadUInt8();` |
| `PkzOpener.LzUnpack` | `byte lo = input.ReadUInt8();` |
| `PkzOpener.LzUnpack` | `byte hi = input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Sviu.PkzArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### PkzArchive

```csharp
public PkzArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Sviu.PkzOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
PkzScheme DefaultScheme = new PkzScheme { KnownSchemes = new Dictionary<string, byte[]>() }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;
    var key = QueryKey();
    if (null == key)
        return null;
    uint data_offset = (uint)count * 0x2Cu + 0x14u;
    var index = file.View.ReadBytes (8, data_offset - 8);
    DecryptData (index, key);
    var dir = new List<Entry> (count);
    int index_offset = 0xC;
    for (int i = 0; i < count; ++i)
    {
        var name = Binary.GetCString (index, index_offset, 0x20);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Size   = index.ToUInt32 (index_offset+0x20);
        entry.Offset = index.ToUInt32 (index_offset+0x24) + data_offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x2C;
    }
    return new PkzArchive (file, this, dir, key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var parc = (PkzArchive)arc;
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    DecryptData (data, parc.Key);
    if (data.AsciiEqual (0, "SVS1"))
        data = UnpackScript (data);
    return new BinMemoryStream (data, entry.Name);
}
```

#### UnpackScript

```csharp
public static byte[] UnpackScript (byte[] data) {
    if (data.ToInt32 (0x10) == 0)
        return data;
    int unpacked_size = data.ToInt32 (0xC);
    int header_size = data.ToInt32 (0x14);
    int packed_size = data.ToInt32 (0x1C);
    var output = new byte[unpacked_size];
    Buffer.BlockCopy (data, 0, output, 0, header_size);
    LittleEndian.Pack (0, output, 0x10);
    using (var input = new BinMemoryStream (data, header_size, packed_size))
        LzUnpack (input, output, header_size);
    return output;
}
```

#### LzUnpack

```csharp
public static void LzUnpack (IBinaryStream input, byte[] output, int dst) {
    var frame = new byte[0x800];
    int frame_pos = 0x7E8;
    int ctl = 1;
    while (dst < output.Length)
    {
        if (1 == ctl)
        {
            ctl = input.ReadByte();
            if (-1 == ctl)
                break;
            ctl |= 0x100;
        }
        if (0 != (ctl & 1))
        {
            byte b = input.ReadUInt8();
            output[dst++] = b;
            frame[frame_pos++ & 0x7FF] = b;
        }
        else
        {
            byte lo = input.ReadUInt8();
            byte hi = input.ReadUInt8();
            int offset = lo | (hi & 0xE0) << 3;
            int count = (hi & 0x1F) + 2;
            for (int i = 0; i < count; ++i)
            {
                byte b = frame[(offset + i) & 0x7FF];
                output[dst++] = b;
                frame[frame_pos++ & 0x7FF] = b;
            }
        }
        ctl >>= 1;
    }
}
```

#### CreateKey

```csharp
public static byte[] CreateKey (string key) {
    var bkey = Encodings.cp932.GetBytes (key);
    for (int i = 0; i < bkey.Length; ++i)
    {
        bkey[i] += 6;
    }
    return bkey;
}
```

#### DecryptData

```csharp
void DecryptData (byte[] data, byte[] key) {
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] ^= key[i % key.Length];
        data[i] += 0x80;
    }
}
```

#### QueryKey

```csharp
byte[] QueryKey () {
    if (DefaultScheme.KnownSchemes.Count == 0)
        return null;
    return DefaultScheme.KnownSchemes.Values.First();
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Sviu/ArcPKZ.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
