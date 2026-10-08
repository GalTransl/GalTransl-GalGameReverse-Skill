# Noesis / ArcIGA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `IGA` / `GameRes.Formats.Noesis.IgaOpener` | `iga` | `49474130` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `IgaOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `IgaOpener.ReadPackedUInt` | `val = val << 7 \| input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Noesis.IgaEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint NameOffset ;
```

### GameRes.Formats.Noesis.IgaOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    using (var input = file.CreateStream())
    {
        input.Position = 0x10;
        uint index_length = ReadPackedUInt (input);
        var dir = new List<Entry>();
        long end_pos = input.Position + index_length;
        while (input.Position < end_pos)
        {
            var entry = new IgaEntry();
            entry.NameOffset = ReadPackedUInt (input);
            entry.Offset     = ReadPackedUInt (input);
            entry.Size       = ReadPackedUInt (input);
            dir.Add (entry);
        }
        uint names_length = ReadPackedUInt (input);
        long data_offset = input.Position + names_length;
        for (int i = 0; i < dir.Count; ++i)
        {
            var entry = dir[i] as IgaEntry;
            uint name_length;
            if (i + 1 < dir.Count)
                name_length = (dir[i+1] as IgaEntry).NameOffset - entry.NameOffset;
            else
                name_length = names_length - entry.NameOffset;
            entry.Name = ReadPackedString (input, name_length);
            entry.Type = FormatCatalog.Instance.GetTypeFromName (entry.Name);
            entry.Offset += data_offset;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    int key = entry.Name.HasExtension (".s") ? 0xFF : 0;
    for (int i = 0; i < data.Length; ++i)
        data[i] ^= (byte)((i + 2) ^ key);
    return new BinMemoryStream (data, entry.Name);
}
```

#### ReadPackedUInt

```csharp
static uint ReadPackedUInt (IBinaryStream input) {
    uint val = 0;
    while ((val & 1) == 0)
    {
        val = val << 7 | input.ReadUInt8();
    }
    return val >> 1;
}
```

#### ReadPackedString

```csharp
static string ReadPackedString (IBinaryStream input, uint length) {
    var bytes = new byte[length];
    for (uint i = 0; i < length; ++i)
    {
        bytes[i] = (byte)ReadPackedUInt (input);
    }
    return Encodings.cp932.GetString (bytes);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Noesis/ArcIGA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
