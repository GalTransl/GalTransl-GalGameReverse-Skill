# Ail / ArcAil：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/Ail` / `GameRes.Formats.Ail.DatOpener` | `dat`, `snl` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `DatOpener.ReadIndex` | `uint size = file.View.ReadUInt32 (index_offset);` |
| `DatOpener.DetectFileTypes` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |
| `DatOpener.DetectFileTypes` | `entry.UnpackedSize = file.View.ReadUInt32 (entry.Offset+2);` |
| `DatOpener.DetectFileTypes` | `else if (0 == signature \|\| file.View.AsciiEqual (entry.Offset+4, "OggS"))` |
| `DatOpener.DetectFileTypes` | `signature = LittleEndian.ToUInt32 (sign_buf, 0);` |
| `DatOpener.DetectFileTypes` | `signature = file.View.ReadUInt32 (entry.Offset);` |
| `DatOpener.LzssUnpack` | `ctl = input.ReadByte();` |
| `DatOpener.LzssUnpack` | `int v = input.ReadByte();` |
| `DatOpener.LzssUnpack` | `int offset = input.ReadByte();` |
| `DatOpener.LzssUnpack` | `int count = input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Ail.DatOpener

继承/接口：`ArchiveFormat`。

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat", "snl" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    var dir = ReadIndex (file, 4, count);
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pentry = entry as PackedEntry;
    if (null == pentry || !pentry.IsPacked)
        return input;
    using (input)
    {
        byte[] data = new byte[pentry.UnpackedSize];
        LzssUnpack (input, data);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### ReadIndex

```csharp
internal List<Entry> ReadIndex (ArcView file, uint index_offset, int count) {
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    long offset = index_offset + count*4;
    if (offset >= file.MaxOffset)
        return null;
    var dir = new List<Entry> (count/2);
    for (int i = 0; i < count; ++i)
    {
        uint size = file.View.ReadUInt32 (index_offset);
        if (size != 0 && size != uint.MaxValue)
        {
            var entry = new PackedEntry
            {
                Name = string.Format ("{0}#{1:D5}", base_name, i),
                Offset = offset,
                Size = size,
                IsPacked = false,
            };
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            offset += size;
        }
        index_offset += 4;
    }
    if (0 == dir.Count || (file.MaxOffset - offset) > 0x80000)
        return null;
    DetectFileTypes (file, dir);
    return dir;
}
```

#### DetectFileTypes

```csharp
internal void DetectFileTypes (ArcView file, List<Entry> dir) {
    byte[] preview = new byte[16];
    byte[] sign_buf = new byte[4];
    foreach (PackedEntry entry in dir)
    {
        uint extra = 6;
        if (extra > entry.Size)
            continue;
        uint signature = file.View.ReadUInt32 (entry.Offset);
        if (1 == (signature & 0xFFFF))
        {
            entry.IsPacked = true;
            entry.UnpackedSize = file.View.ReadUInt32 (entry.Offset+2);
        }
        else if (0 == signature || file.View.AsciiEqual (entry.Offset+4, "OggS"))
        {
            extra = 4;
        }
        entry.Offset += extra;
        entry.Size   -= extra;
        if (entry.IsPacked)
        {
            file.View.Read (entry.Offset, preview, 0, (uint)preview.Length);
            using (var input = new MemoryStream (preview))
            {
                LzssUnpack (input, sign_buf);
                signature = LittleEndian.ToUInt32 (sign_buf, 0);
            }
        }
        else
        {
            signature = file.View.ReadUInt32 (entry.Offset);
        }
        if (0 != signature)
            SetEntryType (entry, signature);
    }
}
```

#### SetEntryType

```csharp
static void SetEntryType (Entry entry, uint signature) {
    if (0xBA010000 == signature)
    {
        entry.Type = "video";
        entry.Name = Path.ChangeExtension (entry.Name, "mpg");
    }
    else
    {
        var res = AutoEntry.DetectFileType (signature);
        if (null != res)
            entry.ChangeType (res);
    }
}
```

#### LzssUnpack

```csharp
static void LzssUnpack (Stream input, byte[] output) {
    int frame_pos = 0xfee;
    byte[] frame = new byte[0x1000];
    for (int i = 0; i < frame_pos; ++i)
        frame[i] = 0x20;
    int dst = 0;
    int ctl = 0;

    while (dst < output.Length)
    {
        ctl >>= 1;
        if (0 == (ctl & 0x100))
        {
            ctl = input.ReadByte();
            if (-1 == ctl)
                break;
            ctl |= 0xff00;
        }
        if (0 == (ctl & 1))
        {
            int v = input.ReadByte();
            if (-1 == v)
                break;
            output[dst++] = (byte)v;
            frame[frame_pos++] = (byte)v;
            frame_pos &= 0xfff;
        }
        else
        {
            int offset = input.ReadByte();
            if (-1 == offset)
                break;
            int count = input.ReadByte();
            if (-1 == count)
                break;
            offset |= (count & 0xf0) << 4;
            count   = (count & 0x0f) + 3;

            for (int i = 0; i < count; i++)
            {
                if (dst >= output.Length)
                    break;
                byte v = frame[offset++];
                offset &= 0xfff;
                frame[frame_pos++] = v;
                frame_pos &= 0xfff;
                output[dst++] = v;
            }
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Ail/ArcAil.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
