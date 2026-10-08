# Kid / ArcDATRAW：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/KID` / `GameRes.Formats.Kid.DATRAWOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DATRAWOpener.TryOpen` | `uint offset = file.View.ReadUInt32(i * 8);` |
| `DATRAWOpener.TryOpen` | `uint size = file.View.ReadUInt32(i * 8 + 4);` |
| `DATRAWOpener.UnpackCps` | `var header = input.ReadHeader(0x10);` |
| `DATRAWOpener.UnpackCps` | `int packed_size = header.ToInt32(4);` |
| `DATRAWOpener.UnpackCps` | `int compression = header.ToUInt16(0xA);` |
| `DATRAWOpener.UnpackCps` | `int unpacked_size = header.ToInt32(0xC);` |
| `DATRAWOpener.UnpackCps` | `uint key_offset = input.ReadUInt32() - 0x7534682;` |
| `DATRAWOpener.UnpackCps` | `uint key = input.ReadUInt32() + key_offset + 0x3786425;` |
| `DATRAWOpener.UnpackCps` | `cps.ReadInt32();` |
| `DATRAWOpener.UnpackLnd` | `int ctl = input.ReadByte();` |
| `DATRAWOpener.UnpackLnd` | `count += input.ReadUInt8() << 5;` |
| `DATRAWOpener.UnpackLnd` | `byte v = input.ReadUInt8();` |
| `DATRAWOpener.UnpackLnd` | `int offset = ((ctl & 3) << 8) + input.ReadUInt8() + 1;` |
| `DATRAWOpener.UnpackLnd` | `int count = input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kid.DATRAWOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
private static readonly uint dataEntryCount = 4096 ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    var archivename = Path.GetFileNameWithoutExtension(file.Name);
    var dir = new List<Entry>();
    for (int i = 0; i < dataEntryCount; i++)
    {
        uint offset = file.View.ReadUInt32(i * 8);
        uint size = file.View.ReadUInt32(i * 8 + 4);
        offset = offset * 2048 + 0x8000;
        size *= 1024;
        if (offset > file.MaxOffset || size > file.MaxOffset)
        {
            throw new InvalidFormatException();
        }
        if (size == 0) continue;

        var entry = Create<Entry>(archivename + i.ToString("D5"));
        entry.Offset = offset;
        entry.Size = size;
        dir.Add(entry);
    }
    if (dir.Count == 0)
        return null;
    return new ArcFile(file, this, dir);
}
```

#### UnpackCps

```csharp
Stream UnpackCps(IBinaryStream input) {
    var header = input.ReadHeader(0x10);
    int packed_size = header.ToInt32(4);
    int compression = header.ToUInt16(0xA);
    int unpacked_size = header.ToInt32(0xC);

    input.Seek(packed_size - 4, SeekOrigin.Begin);
    uint key_offset = input.ReadUInt32() - 0x7534682;
    input.Position = key_offset;
    uint key = input.ReadUInt32() + key_offset + 0x3786425;

    var decryptor = new CpsTransform(packed_size, (int)key_offset, key);
    using (var decoded = new InputCryptoStream(input.AsStream, decryptor))
    using (var cps = new BinaryStream(decoded, input.Name))
    {
        var output = new byte[unpacked_size];
        if ((compression & 1) != 0)
        {
            cps.ReadInt32();
            UnpackLnd(cps, output);
        }
        else if ((compression & 2) != 0)
        {
            UnpackLnd16(cps, output);
        }
        else
        {
            cps.ReadInt32();
            cps.Read(output, 0, unpacked_size);
        }
        return new BinMemoryStream(output);
    }
}
```

#### UnpackLnd

```csharp
internal static void UnpackLnd(IBinaryStream input, byte[] output) {
    int unpacked_size = output.Length;
    int dst = 0;
    while (dst < unpacked_size)
    {
        int ctl = input.ReadByte();
        if (-1 == ctl)
            break;
        if ((ctl & 0x80) != 0)
        {
            if ((ctl & 0x40) != 0)
            {
                int count = (ctl & 0x1F) + 2;
                if ((ctl & 0x20) != 0)
                    count += input.ReadUInt8() << 5;
                count = Math.Min(count, unpacked_size - dst);
                byte v = input.ReadUInt8();
                for (int i = 0; i < count; ++i)
                    output[dst++] = v;
            }
            else
            {
                int count = ((ctl >> 2) & 0xF) + 2;
                int offset = ((ctl & 3) << 8) + input.ReadUInt8() + 1;
                count = Math.Min(count, unpacked_size - dst);
                Binary.CopyOverlapped(output, dst - offset, dst, count);
                dst += count;
            }
        }
        else if ((ctl & 0x40) != 0)
        {
            int length = Math.Min((ctl & 0x3F) + 2, unpacked_size - dst);
            int count = input.ReadUInt8();
            input.Read(output, dst, length);
            dst += length;
            count = Math.Min(count * length, unpacked_size - dst);
            if (count > 0)
            {
                Binary.CopyOverlapped(output, dst - length, dst, count);
                dst += count;
            }
        }
        else
        {
            int count = (ctl & 0x1F) + 1;
            if ((ctl & 0x20) != 0)
                count += input.ReadUInt8() << 5;
            count = Math.Min(count, unpacked_size - dst);
            input.Read(output, dst, count);
            dst += count;
        }
    }
}
```

#### UnpackLnd16

```csharp
static void UnpackLnd16(IBinaryStream input, byte[] output) {
    throw new NotImplementedException("KID Lnd16 compression not implemented.");
}
```

## 配套算法与外部条件

- [ArcFormats/Kid/ArcDAT.cs](ArcDAT.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Kid/ArcDATRAW.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
