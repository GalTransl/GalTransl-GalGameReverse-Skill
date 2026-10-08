# Tmr-Hiro / ArcPAC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAC/TMR-HIRO` / `GameRes.Formats.TmrHiro.PacOpener` | `pac` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PacOpener.TryOpen` | `int count = file.View.ReadInt16 (0);` |
| `PacOpener.TryOpen` | `uint name_length = file.View.ReadByte (2);` |
| `PacOpener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (3);` |
| `PacOpener.TryOpen` | `var name = file.View.ReadString (index_offset, name_length);` |
| `PacOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset) + data_offset;` |
| `PacOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+4);` |
| `PacOpener.TryOpen` | `entry.Offset = file.View.ReadInt64 (index_offset) + data_offset;` |
| `PacOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+8);` |
| `PacOpener.TryOpen` | `var signature = file.View.ReadUInt32 (entry.Offset);` |
| `PacOpener.TryOpen` | `else if (0x44 == (signature & 0xFF) && entry.Size-9 == file.View.ReadUInt32 (entry.Offset+5))` |
| `PacOpener.OpenEntry` | `int record_count = arc.File.View.ReadInt32 (entry.Offset);` |
| `PacOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `PacOpener.OpenEntry` | `int chunk_size = LittleEndian.ToUInt16 (data, pos) - 4;` |
| `PacOpener.IsSrp` | `return 0x030010 == file.View.ReadUInt32 (entry.Offset+entry.Size-4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.TmrHiro.PacOpener

继承/接口：`ArchiveFormat`。

#### PacOpener

```csharp
public PacOpener () {
    Extensions = new string[] { "pac" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt16 (0);
    if (!IsSaneCount (count))
        return null;
    uint name_length = file.View.ReadByte (2);
    if (0 == name_length)
        return null;
    uint data_offset = file.View.ReadUInt32 (3);
    if (data_offset >= file.MaxOffset)
        return null;
    int version;
    uint index_size = 7 + (name_length + 8) * (uint)count;
    if (data_offset == index_size)
        version = 1;
    else if (data_offset == index_size + 4 * (uint)count)
        version = 2;
    else
        return null;

    var dir = new List<Entry> (count);
    uint index_offset = 7;
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, name_length);
        index_offset += name_length;
        var entry = new Entry { Name = name };
        if (1 == version)
        {
            entry.Offset = file.View.ReadUInt32 (index_offset) + data_offset;
            entry.Size   = file.View.ReadUInt32 (index_offset+4);
            index_offset += 8;
        }
        else
        {
            entry.Offset = file.View.ReadInt64 (index_offset) + data_offset;
            entry.Size   = file.View.ReadUInt32 (index_offset+8);
            index_offset += 12;
        }
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    var arc_name = Path.GetFileNameWithoutExtension (file.Name).ToLower();
    foreach (var entry in dir)
    {
        var signature = file.View.ReadUInt32 (entry.Offset);
        if (0x5367674F == signature)
        {
            entry.Name = Path.ChangeExtension (entry.Name, "ogg");
            entry.Type = "audio";
        }
        else if ((((signature & 0xFF) == 1 || (signature & 0xFF) == 2)) && arc_name.Contains ("grd"))
        {
            entry.Name = Path.ChangeExtension (entry.Name, "grd");
            entry.Type = "image";
        }
        else if (0x44 == (signature & 0xFF) && entry.Size-9 == file.View.ReadUInt32 (entry.Offset+5))
        {
            entry.Type = "audio";
        }
        else if (IsSrp (file, entry))
        {
            entry.Type = "script";
            if ("srp" == arc_name)
                entry.Name = Path.ChangeExtension (entry.Name, "srp");
        }
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if ("script" != entry.Type
        || !IsSrp (arc.File, entry))
        return base.OpenEntry (arc, entry);
    int record_count = arc.File.View.ReadInt32 (entry.Offset);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    int pos = 4;
    for (int i = 0; i < record_count && pos + 2 <= data.Length; ++i)
    {
        int chunk_size = LittleEndian.ToUInt16 (data, pos) - 4;
        pos += 6;
        if (pos + chunk_size > data.Length)
            return base.OpenEntry (arc, entry);
        for (int j = 0; j < chunk_size; ++j)
        {
            data[pos] = Binary.RotByteR (data[pos], 4);
            ++pos;
        }
    }
    return new BinMemoryStream (data, entry.Name);
}
```

#### IsSrp

```csharp
bool IsSrp (ArcView file, Entry entry) {
    return 0x030010 == file.View.ReadUInt32 (entry.Offset+entry.Size-4);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Tmr-Hiro/ArcPAC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
