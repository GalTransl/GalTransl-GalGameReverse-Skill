# NekoNovel / ArcNKPACK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NKPACK/NekoNovel` / `GameRes.Formats.NekoNovel.NkpackOpener` | `nkpack` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `NkpackOpener.TryOpen` | `uint entryOffset = ~stream.ReadUInt32();` |
| `NkpackOpener.TryOpen` | `string signature = ReadString(stream);` |
| `NkpackOpener.TryOpen` | `int count = stream.ReadInt32();` |
| `NkpackOpener.TryOpen` | `string name = ReadString(stream);` |
| `NkpackOpener.TryOpen` | `entry.Offset = ~stream.ReadUInt32();` |
| `NkpackOpener.TryOpen` | `entry.UnpackedSize = stream.ReadUInt32();` |
| `NkpackOpener.TryOpen` | `entry.Size = ~stream.ReadUInt32();` |
| `NkpackOpener.ReadString` | `private unsafe static string ReadString(Stream stream) {` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.NekoNovel.NkpackOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
private static readonly byte[] s_mHeader = new byte[] {
    0x0F, 0x00, 0x00, 0x00, 0x4E, 0x4B, 0x4E, 0x4F, 0x45, 0x56, 0x4C, 0x20, 0x50, 0x41, 0x43, 0x4B,
    0x41, 0x47, 0x45
}
```

#### NkpackOpener

```csharp
public NkpackOpener() {
    Extensions = new string[] { "nkpack" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    if (!file.View.BytesEqual(0L, s_mHeader))
    {
        return null;
    }
    using (ArcViewStream stream = file.CreateStream())
    {
        stream.Seek(-4L, SeekOrigin.End);
        uint entryOffset = ~stream.ReadUInt32();

        stream.Seek(entryOffset, SeekOrigin.Begin);
        string signature = ReadString(stream);

        int count = stream.ReadInt32();
        List<Entry> entries = new List<Entry>(count);
        for (int i = 0; i < count; ++i)
        {
            string name = ReadString(stream);

            PackedEntry entry = Create<PackedEntry>(name);
            entry.Offset = ~stream.ReadUInt32();
            entry.UnpackedSize = stream.ReadUInt32();
            entry.Size = ~stream.ReadUInt32();
            entry.IsPacked = true;

            if (!entry.CheckPlacement(file.MaxOffset))
            {
                return null;
            }

            entries.Add(entry);
        }

        return new ArcFile(file, this, entries);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    if (!(entry is PackedEntry e))
    {
        return arc.File.CreateStream(entry.Offset, entry.Size);
    }
    return new ZLibStream(arc.File.CreateStream(e.Offset, e.Size), CompressionMode.Decompress);
}
```

#### ReadString

```csharp
private unsafe static string ReadString(Stream stream) {
    uint length = 0u;
    stream.Read(new Span<byte>(&length, 4));

    if (length == 0u)
    {
        return string.Empty;
    }

    byte[] data = new byte[length];
    stream.Read(data, 0, data.Length);

    return Encoding.UTF8.GetString(data);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/NekoNovel/ArcNKPACK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
