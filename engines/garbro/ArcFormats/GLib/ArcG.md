# GLib / ArcG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `G/GML` / `GameRes.Formats.GLib.GOpener` | `g`, `xp` | `474d4c5f` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `GOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "ARC\0"))` |
| `GOpener.TryOpen` | `uint data_offset   = file.View.ReadUInt32 (8);` |
| `GOpener.TryOpen` | `uint unpacked_size = file.View.ReadUInt32 (0xC);` |
| `GOpener.TryOpen` | `uint packed_size   = file.View.ReadUInt32 (0x10);` |
| `GOpener.TryOpen` | `var key = index.ReadBytes (256);` |
| `GOpener.TryOpen` | `int count = index.ReadInt32();` |
| `GOpener.TryOpen` | `int name_length = index.ReadInt32();` |
| `GOpener.TryOpen` | `var name = index.ReadCString (name_length);` |
| `GOpener.TryOpen` | `entry.Offset = index.ReadUInt32() + data_offset;` |
| `GOpener.TryOpen` | `entry.Size   = index.ReadUInt32();` |
| `GOpener.TryOpen` | `entry.Header = index.ReadBytes (4);` |
| `GOpener.OpenEntry` | `var data = garc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `GOpener.LzssUnpack` | `ctl = input.ReadByte();` |
| `GOpener.LzssUnpack` | `int b = input.ReadByte();` |
| `GOpener.LzssUnpack` | `int lo = input.ReadByte();` |
| `GOpener.LzssUnpack` | `int hi = input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.GLib.GmlArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### GmlArchive

```csharp
public GmlArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.GLib.GmlEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public byte[] Header ;
```

### GameRes.Formats.GLib.GOpener

继承/接口：`ArchiveFormat`。

#### GOpener

```csharp
public GOpener () {
    Extensions = new string[] { "g", "xp" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "ARC\0"))
        return null;
    uint data_offset   = file.View.ReadUInt32 (8);
    uint unpacked_size = file.View.ReadUInt32 (0xC);
    uint packed_size   = file.View.ReadUInt32 (0x10);
    byte[] unpacked = new byte[unpacked_size];
    using (var packed = file.CreateStream (0x14, packed_size))
    using (var input = new XoredStream (packed, 0xFF))
    {
        LzssUnpack (input, unpacked);
    }
    using (var index = new BinMemoryStream (unpacked))
    {
        var key = index.ReadBytes (256);
        int count = index.ReadInt32();
        if (!IsSaneCount (count))
            return null;
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            int name_length = index.ReadInt32();
            var name = index.ReadCString (name_length);
            var entry = FormatCatalog.Instance.Create<GmlEntry> (name);
            entry.Offset = index.ReadUInt32() + data_offset;
            entry.Size   = index.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            entry.Header = index.ReadBytes (4);
        }
        return new GmlArchive (file, this, dir, key);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var garc = arc as GmlArchive;
    var gent = entry as GmlEntry;
    if (null == garc || null == gent)
        return base.OpenEntry (arc, entry);
    var data = garc.File.View.ReadBytes (entry.Offset, entry.Size);
    for (int i = gent.Header.Length; i < data.Length; ++i)
        data[i] = garc.Key[data[i]];
    Buffer.BlockCopy (gent.Header, 0, data, 0, gent.Header.Length);
    return new BinMemoryStream (data, entry.Name);
}
```

#### LzssUnpack

```csharp
internal static void LzssUnpack (Stream input, byte[] output) {
    const int frame_mask = 0xFFF;
    byte[] frame = new byte[0x1000];
    int frame_pos = 0xFEE;
    int dst = 0;
    int ctl = 2;
    while (dst < output.Length)
    {
        ctl >>= 1;
        if (1 == ctl)
        {
            ctl = input.ReadByte();
            if (-1 == ctl)
                break;
            ctl |= 0x100;
        }
        if (0 != (ctl & 1))
        {
            int b = input.ReadByte();
            if (-1 == b)
                break;
            output[dst++] = frame[frame_pos++ & frame_mask] = (byte)b;
        }
        else
        {
            int lo = input.ReadByte();
            if (-1 == lo)
                break;
            int hi = input.ReadByte();
            if (-1 == hi)
                break;
            int offset = (hi & 0xf0) << 4 | lo;
            int count = Math.Min ((~hi & 0xF) + 3, output.Length-dst);
            while (count --> 0)
            {
                byte v = frame[offset++ & frame_mask];
                frame[frame_pos++ & frame_mask] = v;
                output[dst++] = v;
            }
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/GLib/ArcG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
