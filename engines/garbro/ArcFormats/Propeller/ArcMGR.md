# Propeller / ArcMGR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MGR` / `GameRes.Formats.Propeller.MgrOpener` | `mgr` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MgrOpener.TryOpen` | `int count = file.View.ReadInt16 (0);` |
| `MgrOpener.TryOpen` | `first_offset = file.View.ReadUInt32 (current);` |
| `MgrOpener.TryOpen` | `if (!file.View.AsciiEqual (first_offset+9, "BM"))` |
| `MgrOpener.TryOpen` | `Offset = file.View.ReadUInt32 (current),` |
| `MgrOpener.TryOpen` | `entry.UnpackedSize  = file.View.ReadUInt32 (entry.Offset);` |
| `MgrOpener.TryOpen` | `entry.Size          = file.View.ReadUInt32 (entry.Offset+4);` |
| `MgrOpener.Decompress` | `int count = input.ReadByte();` |
| `MgrOpener.Decompress` | `count += input.ReadByte();` |
| `MgrOpener.Decompress` | `offset += input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Propeller.MgrOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".mgr"))
        return null;
    int count = file.View.ReadInt16 (0);
    if (count <= 0 || count >= 0x100)
        return null;
    uint current = 2;
    uint first_offset = current;
    if (count > 1)
    {
        first_offset = file.View.ReadUInt32 (current);
        if (first_offset != 2 + count * 4)
            return null;
    }
    if (!file.View.AsciiEqual (first_offset+9, "BM"))
        return null;
    string base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry> (count);
    if (count > 1)
    {
        for (int i = 0; i < count; ++i)
        {
            var entry = new PackedEntry {
                Name = string.Format ("{0}#{1:D4}.bmp", base_name, i),
                Type = "image",
                Offset = file.View.ReadUInt32 (current),
            };
            if (entry.Offset < first_offset || entry.Offset >= file.MaxOffset)
                return null;
            dir.Add (entry);
            current += 4;
        }
    }
    else
    {
        dir.Add (new PackedEntry { Name = base_name+".bmp", Type = "image", Offset = current });
    }
    foreach (PackedEntry entry in dir)
    {
        entry.UnpackedSize  = file.View.ReadUInt32 (entry.Offset);
        entry.Size          = file.View.ReadUInt32 (entry.Offset+4);
        entry.IsPacked      = true;
        if (entry.UnpackedSize < 0x36 || entry.Size > file.MaxOffset-entry.Offset)
            return null;
        entry.Offset += 8;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
    {
        var bmp = new byte[(entry as PackedEntry).UnpackedSize];
        Decompress (input, bmp);
        return new BinMemoryStream (bmp, entry.Name);
    }
}
```

#### Decompress

```csharp
static public int Decompress (Stream input, byte[] output) {
    int dst = 0;
    while (dst < output.Length)
    {
        int count = input.ReadByte();
        if (-1 == count)
            break;
        if (count < 0x20)
        {
            count = Math.Min (count+1, output.Length-dst);
            int read = input.Read (output, dst, count);
            dst += read;
            if (read < count)
                break;
        }
        else
        {
            int offset = ((count & 0x1F) << 8) + 1;
            count >>= 5;
            if (7 == count)
                count += input.ReadByte();
            offset += input.ReadByte();
            if (offset >= dst)
                throw new InvalidFormatException();
            count = Math.Min (count+2, output.Length-dst);
            Binary.CopyOverlapped (output, dst - offset, dst, count);
            dst += count;
        }
    }
    return dst;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Propeller/ArcMGR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
