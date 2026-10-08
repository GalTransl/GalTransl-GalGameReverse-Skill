# Peach / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/KARTE` / `GameRes.Formats.Peach.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `uint ofs_encrypted = file.View.ReadUInt32 (offset);` |
| `DatOpener.TryOpen` | `Size = file.View.ReadUInt32 (offset + 4) - ofs_encrypted + 0x24b7935b` |
| `DatOpener.TryOpen` | `uint unpacked_size = file.View.ReadUInt32 (entry.Offset);` |
| `DatOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (entry.Offset + 8);` |
| `DatOpener.LzUnpack` | `int ctl = input.ReadByte();` |
| `DatOpener.LzUnpack` | `output[dst++] = (byte)(input.ReadByte() - delta);` |
| `DatOpener.LzUnpack` | `ushort v = input.ReadUInt16();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Peach.DatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat"))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);

    uint offset = 0;
    uint i = 1;
    var dir = new List<Entry> ();
    do
    {
        uint ofs_encrypted = file.View.ReadUInt32 (offset);
        var entry = new PackedEntry {
            Name = string.Format ("{0}#{1:D4}", base_name, i - 1),
            Offset = ofs_encrypted + 0x24b7935b * i,
            Size = file.View.ReadUInt32 (offset + 4) - ofs_encrypted + 0x24b7935b
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        uint unpacked_size = file.View.ReadUInt32 (entry.Offset);
        if ((unpacked_size & 0xffffff) == 0x1ff)
        {
            entry.UnpackedSize = file.View.ReadUInt32 (entry.Offset + 8);
            entry.Type = "image";
        }
        else
        {
            entry.UnpackedSize = unpacked_size;
            entry.Type = "script";
        }
        dir.Add (entry);
        offset += 4;
        i++;
    }
    while (offset < dir[0].Offset - 4);

    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (pent.Type != "script")
        return base.OpenEntry (arc, entry);

    var input = arc.File.CreateStream (pent.Offset + 4, pent.Size - 4);
    var output = new byte[pent.UnpackedSize];

    LzUnpack (input, output, 0x37);
    return new BinMemoryStream (output);
}
```

#### LzUnpack

```csharp
void LzUnpack (IBinaryStream input, byte[] output, byte delta) {
    int dst = 0;
    while (dst < output.Length)
    {
        int ctl = input.ReadByte();
        for (int bit = 1; bit != 0x100 && dst < output.Length; bit <<= 1)
        {
            if (0 != (ctl & bit))
            {
                output[dst++] = (byte)(input.ReadByte() - delta);
            }
            else
            {
                ushort v = input.ReadUInt16();
                int offset = v >> 4;
                for (int count = 3 + (v & 0xF); count != 0; --count)
                {
                    int src = dst - offset;
                    if (src < 0)
                        output[dst++] = 0;
                    else
                        output[dst++] = output[src];
                }
            }
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Peach/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
