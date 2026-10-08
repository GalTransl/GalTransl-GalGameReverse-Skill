# Entergram / ArcPacV1：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PacV1/Entergram` / `GameRes.Formats.Entergram.PacOpenerV1` | `pacv1` | `50414320` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PacOpenerV1.OpenEntry` | `byte[] data = s.ReadBytes(int.MaxValue);` |
| `PacOpenerV1.ParseEntry` | `string name = ReadString(stream);` |
| `PacOpenerV1.ParseEntry` | `long offset = stream.ReadInt64() + 0x10L;` |
| `PacOpenerV1.ParseEntry` | `long length = stream.ReadInt64();` |
| `PacOpenerV1.ParseEntry` | `long offset = stream.ReadInt64() + 0x14L;` |
| `PacOpenerV1.ReadString` | `private static string ReadString(ArcViewStream stream) {` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Entergram.PacOpenerV1

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
private static readonly byte[] smHeader = new byte[] {
    0x50, 0x41, 0x43, 0x20, 0x56, 0x45, 0x52, 0x2D, 0x31, 0x2E, 0x30, 0x30, 0x00, 0x00, 0x00, 0x00
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    if (!file.View.BytesEqual(0L, smHeader))
    {
        return null;
    }

    List<Entry> entries = this.ParseEntry(file);
    if(entries == null)
    {
        return null;
    }

    return new ArcFile(file, this, entries);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    if(!(entry is PackedEntry e))
    {
        return base.OpenEntry(arc, entry);
    }

    if (e.IsPacked)
    {
        using(ArcViewStream s = arc.File.CreateStream(e.Offset, e.Size))
        {
            byte[] data = s.ReadBytes(int.MaxValue);
            data = QLZCompressor.Decompress(data);
            return new MemoryStream(data, false);
        }
    }
    else
    {
        return base.OpenEntry(arc, entry);
    }
}
```

#### ParseEntry

```csharp
private List<Entry> ParseEntry(ArcView file) {
    bool compressed = Path.GetFileNameWithoutExtension(file.Name).EndsWith("_c");
    using(ArcViewStream stream = file.CreateStream(smHeader.LongLength))
    {
        List<PackedEntry> entries = new List<PackedEntry>();

        {
            stream.Position = 0L;
            while (stream.Position < stream.Length)
            {
                string name = ReadString(stream);

                long offset = stream.ReadInt64() + 0x10L;
                long length = stream.ReadInt64();
                if (!CheckEntry(offset, length, file.MaxOffset))
                {
                    entries.Clear();
                    break;
                }

                PackedEntry entry = Create<PackedEntry>(name);
                entry.Offset = offset;
                entry.Size = (uint)length;
                entry.IsPacked = compressed;
                entries.Add(entry);

                stream.Seek(length, SeekOrigin.Current);
            }
        }

        if (!entries.Any())
        {
            stream.Position = 0L;
            while (stream.Position < stream.Length)
            {
                string name = ReadString(stream);

                long offset = stream.ReadInt64() + 0x14L;
                stream.Position += 2L;
                long length = stream.ReadInt64();
                stream.Position += 2L;
                if (!CheckEntry(offset, length, file.MaxOffset))
                {
                    entries.Clear();
                    break;
                }

                PackedEntry entry = Create<PackedEntry>(name);
                entry.Offset = offset;
                entry.Size = (uint)length;
                entry.IsPacked = compressed;
                entries.Add(entry);

                stream.Seek(length, SeekOrigin.Current);
            }
        }

        return entries.Cast<Entry>().ToList();
    }
}
```

#### ReadString

```csharp
private static string ReadString(ArcViewStream stream) {
    byte[] buf = new byte[0x20];
    if (stream.Read(buf, 0, buf.Length) != buf.Length)
    {
        return string.Empty;
    }

    int len = Array.IndexOf<byte>(buf, 0);
    if (len <= 0)
    {
        return string.Empty;
    }

    return Encoding.UTF8.GetString(buf, 0, len);
}
```

#### CheckEntry

```csharp
private static bool CheckEntry(long offset, long length, long max) {
    return offset >= 0L &&
           length >= 0L &&
           offset < max &&
           length <= max &&
           length <= uint.MaxValue &&
           offset <= max - length;
}
```

## 配套算法与外部条件

- [ArcFormats/Entergram/QuickLZ.cs](QuickLZ.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Entergram/ArcPacV1.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
