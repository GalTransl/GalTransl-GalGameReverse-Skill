# UMeSoft / ArcPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PK` / `GameRes.Formats.UMeSoft.PkOpener` | `pk`, `gpk`, `tpk`, `wpk`, `mpk`, `pk0`, `pka`, `pkb`, `pkc`, `pkd`, `pke`, `pkf` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PkOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (index_end);` |
| `PkOpener.TryOpen` | `uint name_len = file.View.ReadByte (index_offset++);` |
| `PkOpener.TryOpen` | `string name = file.View.ReadString (index_offset, name_len);` |
| `PkOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset);` |
| `PkOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+4);` |
| `PkOpener.OpenEntry` | `int output_size = arc.File.View.ReadInt32 (entry.Offset);` |
| `PkOpener.LzUnpack` | `ctl = input.ReadByte();` |
| `PkOpener.LzUnpack` | `output[dst++] = (byte)input.ReadByte();` |
| `PkOpener.LzUnpack` | `int lo = input.ReadByte();` |
| `PkOpener.LzUnpack` | `int hi = input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.UMeSoft.PkOpener

继承/接口：`ArchiveFormat`。

#### PkOpener

```csharp
public PkOpener () {
    Extensions = new string[] { "pk", "gpk", "tpk", "wpk", "mpk", "pk0", "pka", "pkb", "pkc", "pkd", "pke", "pkf" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    long index_end = file.MaxOffset - 4;
    uint index_size = file.View.ReadUInt32 (index_end);
    if (0 == index_size || index_size >= index_end)
        return null;

    long index_offset = index_end - index_size;
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;

    var dir = new List<Entry>();
    while (index_offset < index_end)
    {
        uint name_len = file.View.ReadByte (index_offset++);
        if (0 == name_len)
            break;
        if (name_len+14 > index_end-index_offset)
            return null;
        string name = file.View.ReadString (index_offset, name_len);
        if (name.Length < (int)name_len / 2 + 1)
            return null;
        index_offset += name_len+6;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Size = file.View.ReadUInt32 (index_offset);
        entry.Offset = file.View.ReadUInt32 (index_offset+4);
        if (!entry.CheckPlacement (index_offset))
            return null;
        dir.Add (entry);
        index_offset += 8;
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (!entry.Name.HasAnyOfExtensions ("scr", "tbl"))
        return base.OpenEntry (arc, entry);
    int output_size = arc.File.View.ReadInt32 (entry.Offset);
    if (output_size <= 0)
        return base.OpenEntry (arc, entry);
    using (var input = arc.File.CreateStream (entry.Offset+4, entry.Size-4))
    {
        var data = LzUnpack (input, output_size);
        for (int i = 0; i < data.Length; ++i)
            data[i] ^= 0x42;
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### LzUnpack

```csharp
byte[] LzUnpack (Stream input, int output_size) {
    var output = new byte[output_size];
    int ctl = 0;
    int mask = 0;
    int dst = 0;
    while (dst < output_size)
    {
        mask >>= 1;
        if (0 == mask)
        {
            ctl = input.ReadByte();
            if (-1 == ctl)
                break;
            mask = 0x80;
        }
        if (0 == (ctl & mask))
        {
            output[dst++] = (byte)input.ReadByte();
        }
        else
        {
            int lo = input.ReadByte();
            int hi = input.ReadByte();
            if (-1 == lo || -1 == hi)
                break;
            int offset = hi << 4 | lo >> 4;
            if (0 == offset)
                break;
            int count  = (lo & 0xF) + 3;
            Binary.CopyOverlapped (output, dst - offset, dst, count);
            dst += count;
        }
    }
    return output;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/UMeSoft/ArcPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
