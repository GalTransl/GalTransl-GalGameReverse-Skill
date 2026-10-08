# Nekopack / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/NEKOPACK` / `GameRes.Formats.Neko.DatOpener` | `dat` | `4e454b4f` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "PACK"))` |
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (0x10);` |
| `DatOpener.TryOpen` | `byte extra = file.View.ReadByte (index_offset);` |
| `DatOpener.TryOpen` | `uint name_length = file.View.ReadByte (index_offset + 1);` |
| `DatOpener.TryOpen` | `var name_buffer = file.View.ReadBytes (index_offset + 2, name_length);` |
| `DatOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset);` |
| `DatOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset + 4);` |
| `DatOpener.OpenEntry` | `var input = arc.File.View.ReadBytes (nent.Offset, nent.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Neko.NekoItaEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public byte ExtraKey ;
```

### GameRes.Formats.Neko.DatOpener

继承/接口：`ArchiveFormat`。

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "PACK"))
        return null;

    int count = file.View.ReadInt32 (0x10);
    if (!IsSaneCount (count))
        return null;

    var table = new uint[0x270];
    int pos = 0;
    InitTable (table, 0x9999);

    var dir = new List<Entry> (count);
    uint index_offset = 0x14;
    for (int i = 0; i < count; ++i)
    {
        byte extra = file.View.ReadByte (index_offset);
        uint name_length = file.View.ReadByte (index_offset + 1);
        var name_buffer = file.View.ReadBytes (index_offset + 2, name_length);
        pos = Decrypt (name_buffer, 0, (int)name_length, table, pos);
        var name = Binary.GetCString (name_buffer, 0, (int)name_length);
        var entry = Create<NekoItaEntry> (name);
        index_offset += name_length + 2;
        entry.Offset = file.View.ReadUInt32 (index_offset);
        entry.Size = file.View.ReadUInt32 (index_offset + 4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (entry.Name.HasExtension (".img"))
            entry.Type = "";
        entry.ExtraKey = extra;
        dir.Add (entry);
        index_offset += 8;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var nent = (NekoItaEntry)entry;
    var input = arc.File.View.ReadBytes (nent.Offset, nent.Size);
    if (nent.ExtraKey != 0)
    {
        var table = new uint[0x270];
        InitTable (table, (uint)(0x9999 + nent.ExtraKey));
        Decrypt (input, 0, (int)nent.Size, table, 0);
    }
    return new BinMemoryStream (input);
}
```

#### InitTable

```csharp
void InitTable (uint[] table, uint key) {
    for (int i = 0; i < table.Length; i++)
    {
        key *= 0x10dcd;
        table[i] = key;
    }
}
```

#### Decrypt

```csharp
int Decrypt (byte[] data, int pos, int length, uint[] table, int table_pos) {
    for (int i = pos; i < pos + length; i++)
    {
        if (table_pos == table.Length)
        {
            InitTable (table, table[table.Length - 1]);
            table_pos = 0;
        }
        uint key = table[table_pos++];
        key ^= key >> 11;
        key ^= (key << 7) & 0x31518a63;
        key ^= (key << 15) & 0x17f1ca43;
        key ^= key >> 18;
        data[i] ^= (byte)key;
    }
    return table_pos;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Nekopack/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
