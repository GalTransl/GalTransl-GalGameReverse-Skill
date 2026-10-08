# Broccoli / BroccoliPak：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/BROCCOLI` / `GameRes.Formats.Broccoli.PakOpener` | `pak` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `var buffer = file.View.ReadBytes(0, (uint)bufferSize);` |
| `PakOpener.TryOpen` | `int count = file.View.ReadInt32(countOffset);` |
| `PakOpener.TryOpen` | `var nameBytes = file.View.ReadBytes(entryPos, 48);` |
| `PakOpener.TryOpen` | `uint offset = file.View.ReadUInt32(entryPos + 48);` |
| `PakOpener.TryOpen` | `uint size   = file.View.ReadUInt32(entryPos + 56);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Broccoli.PakOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
private static readonly byte[] FirstFileSignature = {
    0x73, 0x65, 0x5F, 0x63, 0x31, 0x31, 0x2E, 0x77, 0x61, 0x76
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    int bufferSize = 2048;
    if (file.MaxOffset < bufferSize)
        bufferSize = (int)file.MaxOffset;

    var buffer = file.View.ReadBytes(0, (uint)bufferSize);

    int signaturePos = FindSignature(buffer, FirstFileSignature);

    if (signaturePos == -1)
        return null;

    if (signaturePos < 8)
        return null;

    long countOffset = signaturePos - 8;
    int count = file.View.ReadInt32(countOffset);

    if (!IsSaneCount(count))
        return null;

    long tableStart = signaturePos;
    long entrySize = 64;
    long tableByteSize = count * entrySize;

    long dataBlobStart = tableStart + tableByteSize;

    if (dataBlobStart > file.MaxOffset)
        return null;

    var dir = new List<Entry>(count);

    for (int i = 0; i < count; i++)
    {
        long entryPos = tableStart + (i * entrySize);

        var nameBytes = file.View.ReadBytes(entryPos, 48);

        if (nameBytes.Length >= 4 &&
           (System.Text.Encoding.ASCII.GetString(nameBytes, 0, 4) == "RIFF" ||
            System.Text.Encoding.ASCII.GetString(nameBytes, 0, 4) == "OggS"))
        {
            break;
        }

        string name = Binary.GetCString(nameBytes, 0, nameBytes.Length, Encodings.cp932);

        if (string.IsNullOrWhiteSpace(name))
            continue;

        name = name.TrimEnd('\0');

        uint offset = file.View.ReadUInt32(entryPos + 48);
        uint size   = file.View.ReadUInt32(entryPos + 56);

        if (size == 0)
            continue;

        var entry = FormatCatalog.Instance.Create<Entry>(name);

        entry.Offset = dataBlobStart + offset;
        entry.Size = size;

        if (!entry.CheckPlacement(file.MaxOffset))
            return null;

        dir.Add(entry);
    }

    return new ArcFile(file, this, dir);
}
```

#### FindSignature

```csharp
private int FindSignature(byte[] buffer, byte[] signature) {
    if (buffer.Length < signature.Length) return -1;

    for (int i = 0; i <= buffer.Length - signature.Length; i++)
    {
        bool found = true;
        for (int j = 0; j < signature.Length; j++)
        {
            if (buffer[i + j] != signature[j])
            {
                found = false;
                break;
            }
        }
        if (found) return i;
    }
    return -1;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Broccoli/BroccoliPak.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
