# WildBug / ArcWBP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `WBP` / `GameRes.Formats.WildBug.WbpOpener` | `wbp` | `41524346` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `WbpOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "ARCFORM") \|\|` |
| `WbpOpener.TryOpen` | `!file.View.AsciiEqual (8, " WBUG "))` |
| `WbpOpener.TryOpen` | `int version = file.View.ReadByte (7) - '0';` |
| `WbpOpener.TryOpen` | `int count = file.View.ReadInt32 (0x10);` |
| `WbpOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0x14);` |
| `WbpOpener.TryOpen` | `uint index_size   = file.View.ReadUInt32 (0x18);` |
| `WbpOpener.TryOpen` | `uint data_offset  = file.View.ReadUInt32 (0x1C);` |
| `WbpOpener.OpenV3` | `uint name_length = file.View.ReadByte (index_offset+9);` |
| `WbpOpener.OpenV3` | `string name = file.View.ReadString (index_offset+0x14, name_length);` |
| `WbpOpener.OpenV3` | `entry.Offset = file.View.ReadUInt32 (index_offset);` |
| `WbpOpener.OpenV3` | `entry.Size   = file.View.ReadUInt32 (index_offset+4);` |
| `WbpOpener.OpenV4` | `byte hash = file.View.ReadByte (dir_offset);` |
| `WbpOpener.OpenV4` | `byte name_length = file.View.ReadByte (dir_offset+1);` |
| `WbpOpener.OpenV4` | `int dir_id = file.View.ReadUInt16 (dir_offset+2);` |
| `WbpOpener.OpenV4` | `byte hash = file.View.ReadByte (res_offset);` |
| `WbpOpener.OpenV4` | `byte name_length = file.View.ReadByte (res_offset+1);` |
| `WbpOpener.OpenV4` | `int dir_id  = file.View.ReadUInt16 (res_offset+2);` |
| `WbpOpener.OpenV4` | `entry.Offset = file.View.ReadUInt32 (res_offset+4);` |
| `WbpOpener.OpenV4` | `entry.Size   = file.View.ReadUInt32 (res_offset+8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.WildBug.WbpOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "ARCFORM") ||
        !file.View.AsciiEqual (8, " WBUG "))
        return null;
    int version = file.View.ReadByte (7) - '0';
    if (version < 2 || version > 4)
        return null;
    int count = file.View.ReadInt32 (0x10);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = file.View.ReadUInt32 (0x14);
    uint index_size   = file.View.ReadUInt32 (0x18);
    uint data_offset  = file.View.ReadUInt32 (0x1C);
    if (data_offset < index_offset || data_offset > file.MaxOffset)
        return null;
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;

    if (4 == version)
        return OpenV4 (file, count, index_offset, index_size);
    else
        return OpenV3 (file, count, index_offset);
}
```

#### OpenV3

```csharp
ArcFile OpenV3 (ArcView file, int count, uint index_offset) {
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint name_length = file.View.ReadByte (index_offset+9);
        string name = file.View.ReadString (index_offset+0x14, name_length);
        if (0 == name.Length)
            return null;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset);
        entry.Size   = file.View.ReadUInt32 (index_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += name_length + 0x14;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenV4

```csharp
ArcFile OpenV4 (ArcView file, int count, uint index_offset, uint index_size) {
    var buffer = new byte[0x400];
    var dir_names = new uint[0x100];
    file.View.Read (0x24, buffer, 0, 0x400);
    Buffer.BlockCopy (buffer, 0, dir_names, 0, 0x400);
    var res_names = new uint[0x100];
    file.View.Read (0x424, buffer, 0, 0x400);
    Buffer.BlockCopy (buffer, 0, res_names, 0, 0x400);

    var dir_table = new Dictionary<int, string>();
    for (int i = 0; i < 0x100; ++i)
    {
        if (0 == dir_names[i])
            continue;
        uint dir_offset = dir_names[i];
        for (;;)
        {
            byte hash = file.View.ReadByte (dir_offset);
            if (hash != i)
                break;
            byte name_length = file.View.ReadByte (dir_offset+1);
            int dir_id = file.View.ReadUInt16 (dir_offset+2);
            file.View.Read (dir_offset + 4, buffer, 0, name_length);
            byte checksum = 0;
            for (int j = 0; j < name_length; ++j)
                checksum += buffer[j];
            if (hash != checksum)
                return null;
            dir_table[dir_id] = Encodings.cp932.GetString (buffer, 0, name_length).TrimStart ('\\');
            dir_offset += 5u + name_length;
        }
    }
    uint index_end = index_offset + index_size;
    var dir = new List<Entry> (count);
    for (int i = 0; i < 0x100; ++i)
    {
        if (0 == res_names[i])
            continue;
        uint res_offset = res_names[i];
        while (res_offset < index_end)
        {
            byte hash = file.View.ReadByte (res_offset);
            if (hash != i)
                break;
            byte name_length = file.View.ReadByte (res_offset+1);
            int dir_id  = file.View.ReadUInt16 (res_offset+2);
            file.View.Read (res_offset+0x14, buffer, 0, name_length);
            byte checksum = 0;
            for (int j = 0; j < name_length; ++j)
                checksum += buffer[j];
            if (hash != checksum)
                return null;
            var dir_name = dir_table[dir_id];
            var name = dir_table[dir_id] + Encodings.cp932.GetString (buffer, 0, name_length);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = file.View.ReadUInt32 (res_offset+4);
            entry.Size   = file.View.ReadUInt32 (res_offset+8);
            res_offset += (0x18u + name_length) & ~3u;
            dir.Add (entry);
        }
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/WildBug/ArcWBP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
