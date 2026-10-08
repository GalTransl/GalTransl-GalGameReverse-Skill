# Kid / ArcP2T：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `P2T` / `GameRes.Formats.KID.P2tOpener` | `p2t` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `P2tOpener.TryOpen` | `uint headerEnd = file.View.ReadUInt32(0x08);` |
| `P2tOpener.TryOpen` | `uint numFiles = file.View.ReadUInt32(0x0C);` |
| `P2tOpener.TryOpen` | `uint dataStartBase = file.View.ReadUInt32(0x10);` |
| `P2tOpener.TryOpen` | `uint checkFF = file.View.ReadUInt32(headerEnd + 48);` |
| `P2tOpener.TryOpen` | `uint rawOffset = file.View.ReadUInt32(currentEntryPtr + 52);` |
| `P2tOpener.TryOpen` | `uint compressedLen = file.View.ReadUInt32(currentEntryPtr + 60);` |
| `P2tOpener.TryOpen` | `uint realUncompressedSize = file.View.ReadUInt32(sizeInfoOffset);` |
| `P2tOpener.TryOpen` | `byte[] timHeaderChunk = file.View.ReadBytes(currentEntryPtr, 48);` |
| `P2tOpener.OpenEntry` | `var compressedData = arc.File.View.ReadBytes(entry.Offset, p2tEntry.CompressedSize);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.KID.P2tEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public byte[] TimHeaderChunk { get; set; }

public int RealUncompressedSize { get; set; }

public uint CompressedSize { get; set; }
```

### GameRes.Formats.KID.P2tOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
private static readonly byte[] Tim2Magic = new byte[] {
    0x54, 0x49, 0x4D, 0x32, 0x04, 0x00, 0x01, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    if (file.MaxOffset < 0x20) return null;

    uint headerEnd = file.View.ReadUInt32(0x08);
    uint numFiles = file.View.ReadUInt32(0x0C);
    uint dataStartBase = file.View.ReadUInt32(0x10);

    if (numFiles == 0 || numFiles > 0xFFFF || headerEnd >= file.MaxOffset) return null;

    uint checkFF = file.View.ReadUInt32(headerEnd + 48);
    if (checkFF != 0xFFFFFFFF) return null;

    var dir = new List<Entry>((int)numFiles);
    long currentEntryPtr = headerEnd;
    const int EntrySize = 64;

    for (int i = 0; i < numFiles; i++)
    {

        uint rawOffset = file.View.ReadUInt32(currentEntryPtr + 52);
        uint compressedLen = file.View.ReadUInt32(currentEntryPtr + 60);

        long sizeInfoOffset = dataStartBase + rawOffset;
        if (sizeInfoOffset + 4 > file.MaxOffset) break;

        uint realUncompressedSize = file.View.ReadUInt32(sizeInfoOffset);
        byte[] timHeaderChunk = file.View.ReadBytes(currentEntryPtr, 48);

        var entry = new P2tEntry
        {
            Name = string.Format("{0:D4}.tm2", i),
            Type = "image",
            Offset = sizeInfoOffset + 4,
            Size = realUncompressedSize,
            RealUncompressedSize = (int)realUncompressedSize,
            CompressedSize = compressedLen,
            TimHeaderChunk = timHeaderChunk
        };

        dir.Add(entry);
        currentEntryPtr += EntrySize;
    }

    return new ArcFile(file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    var p2tEntry = entry as P2tEntry;
    if (p2tEntry == null) return base.OpenEntry(arc, entry);

    var compressedData = arc.File.View.ReadBytes(entry.Offset, p2tEntry.CompressedSize);

    var decompressedBody = LzssDecompress(compressedData);

    if (decompressedBody.Length != p2tEntry.RealUncompressedSize)
        Array.Resize(ref decompressedBody, p2tEntry.RealUncompressedSize);

    int finalSize = Tim2Magic.Length + p2tEntry.TimHeaderChunk.Length + decompressedBody.Length;
    var outputData = new byte[finalSize];

    Buffer.BlockCopy(Tim2Magic, 0, outputData, 0, Tim2Magic.Length);
    Buffer.BlockCopy(p2tEntry.TimHeaderChunk, 0, outputData, Tim2Magic.Length, p2tEntry.TimHeaderChunk.Length);
    Buffer.BlockCopy(decompressedBody, 0, outputData, Tim2Magic.Length + p2tEntry.TimHeaderChunk.Length, decompressedBody.Length);

    return new MemoryStream(outputData);
}
```

#### LzssDecompress

```csharp
private byte[] LzssDecompress(byte[] input) {
    var output = new List<byte>(input.Length * 2);
    const int n = 4096;
    const int threshold = 2;
    int r = n - 18;
    var textBuf = new byte[n + 18 - 1];
    Array.Clear(textBuf, 0, textBuf.Length);

    int flags = 0;
    int srcPos = 0;

    while (srcPos < input.Length)
    {
        flags >>= 1;
        if ((flags & 0x100) == 0)
        {
            if (srcPos >= input.Length) break;
            flags = input[srcPos++] | 0xFF00;
        }

        if ((flags & 1) != 0)
        {
            if (srcPos >= input.Length) break;
            byte c = input[srcPos++];
            output.Add(c);
            textBuf[r] = c;
            r = (r + 1) & (n - 1);
        }
        else
        {
            if (srcPos + 1 >= input.Length) break;
            int i = input[srcPos++];
            int j = input[srcPos++];
            int offset = i | ((j & 0xF0) << 4);
            int len = (j & 0x0F) + threshold;
            for (int k = 0; k <= len; k++)
            {
                byte c = textBuf[(offset + k) & (n - 1)];
                output.Add(c);
                textBuf[r] = c;
                r = (r + 1) & (n - 1);
            }
        }
    }
    return output.ToArray();
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Kid/ArcP2T.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
