# Microsoft / ArcNE：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `EXE/NE` / `GameRes.Formats.Microsoft.NeExeOpener` | `exe` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `NeExeOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "MZ") \|\| file.MaxOffset < 0x40)` |
| `NeExeOpener.TryOpen` | `uint ne_offset = file.View.ReadUInt32 (0x3C);` |
| `NeExeOpener.TryOpen` | `if (ne_offset > file.MaxOffset-2 \|\| !file.View.AsciiEqual (ne_offset, "NE"))` |
| `NeExeOpener.TryOpen` | `uint res_table_offset = file.View.ReadUInt16 (ne_offset+0x24) + ne_offset;` |
| `NeExeOpener.TryOpen` | `int shift = file.View.ReadUInt16 (res_table_offset);` |
| `NeExeOpener.TryOpen` | `int type_id = file.View.ReadUInt16 (res_table_offset);` |
| `NeExeOpener.TryOpen` | `int count = file.View.ReadUInt16 (res_table_offset+2);` |
| `NeExeOpener.TryOpen` | `int offset = file.View.ReadUInt16 (res_table_offset) << shift;` |
| `NeExeOpener.TryOpen` | `uint size = (uint)file.View.ReadUInt16 (res_table_offset+2) << shift;` |
| `NeExeOpener.TryOpen` | `int res_id = file.View.ReadUInt16 (res_table_offset+6);` |
| `NeExeOpener.OpenVersion` | `uint data_length = arc.File.View.ReadUInt16 (entry.Offset);` |
| `NeExeOpener.OpenVersion` | `input.ReadUInt16();` |
| `NeExeOpener.OpenVersion` | `int value_length = input.ReadUInt16();` |
| `NeExeOpener.OpenVersion` | `if (input.ReadCString (DefaultEncoding) != "VS_VERSION_INFO")` |
| `NeExeOpener.OpenVersion` | `if (input.ReadUInt32() != 0xFEEF04BDu)` |
| `NeExeOpener.OpenVersion` | `int str_info_length = input.ReadUInt16();` |
| `NeExeOpener.OpenVersion` | `value_length = input.ReadUInt16();` |
| `NeExeOpener.OpenVersion` | `if (input.ReadCString (DefaultEncoding) != "StringFileInfo")` |
| `NeExeOpener.OpenVersion` | `int info_length = input.ReadUInt16();` |
| `NeExeOpener.OpenVersion` | `string block_name = input.ReadCString (DefaultEncoding);` |
| `NeExeOpener.OpenVersion` | `info_length = input.ReadUInt16();` |
| `NeExeOpener.OpenVersion` | `string key = input.ReadCString (DefaultEncoding);` |
| `NeExeOpener.OpenVersion` | `string value = value_length != 0 ? input.ReadCString (value_length, DefaultEncoding)` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Microsoft.NeExeOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Dictionary<int, string> TypeMap = new Dictionary<int, string> {
    { 1, "RT_CURSOR" },
    { 2, "RT_BITMAP" },
    { 3, "RT_ICON" },
    { 4, "RT_MENU" },
    { 5, "RT_DIALOG" },
    { 6, "RT_STRING" },
    { 10, "RT_DATA" },
    { 11, "RT_MESSAGETABLE" },
    { 16, "RT_VERSION" },
}

Encoding DefaultEncoding = Encodings.cp932 ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "MZ") || file.MaxOffset < 0x40)
        return null;
    uint ne_offset = file.View.ReadUInt32 (0x3C);
    if (ne_offset > file.MaxOffset-2 || !file.View.AsciiEqual (ne_offset, "NE"))
        return null;
    uint res_table_offset = file.View.ReadUInt16 (ne_offset+0x24) + ne_offset;
    if (res_table_offset <= ne_offset || res_table_offset >= file.MaxOffset)
        return null;
    int shift = file.View.ReadUInt16 (res_table_offset);
    res_table_offset += 2;
    var dir = new List<Entry>();
    while (res_table_offset + 1 < file.MaxOffset)
    {
        int type_id = file.View.ReadUInt16 (res_table_offset);
        if (0 == type_id)
            break;
        string dir_name = null;
        if ((type_id & 0x8000) != 0)
        {
            type_id &= 0x7FFF;
            TypeMap.TryGetValue (type_id, out dir_name);
        }
        int count = file.View.ReadUInt16 (res_table_offset+2);
        res_table_offset += 8;
        if (null == dir_name)
            dir_name = string.Format ("#{0}", type_id);
        for (int i = 0; i < count; ++i)
        {
            int offset = file.View.ReadUInt16 (res_table_offset) << shift;
            uint size = (uint)file.View.ReadUInt16 (res_table_offset+2) << shift;
            int res_id = file.View.ReadUInt16 (res_table_offset+6);
            if ((res_id & 0x8000) != 0)
                res_id &= 0x7FFF;
            res_table_offset += 12;
            string name = res_id.ToString ("D5");
            name = string.Join ("/", dir_name, name);
            var entry = new NeResourceEntry {
                Name = name,
                Offset = offset,
                Size = size,
                NativeName = res_id,
                NativeType = type_id,
            };
            dir.Add (entry);
        }
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var rent = (NeResourceEntry)entry;
    if (rent.NativeType == 16)
        return OpenVersion (arc, rent);
    return base.OpenEntry (arc, entry);
}
```

#### OpenVersion

```csharp
Stream OpenVersion (ArcFile arc, NeResourceEntry entry) {
    uint data_length = arc.File.View.ReadUInt16 (entry.Offset);
    var input = arc.File.CreateStream (entry.Offset, data_length);
    for (;;)
    {
        input.ReadUInt16();
        int value_length = input.ReadUInt16();
        if (0 == value_length)
            break;
        if (input.ReadCString (DefaultEncoding) != "VS_VERSION_INFO")
            break;
        long pos = (input.Position + 3) & -4L;
        input.Position = pos;
        if (input.ReadUInt32() != 0xFEEF04BDu)
            break;
        input.Position = pos + value_length;
        int str_info_length = input.ReadUInt16();
        value_length = input.ReadUInt16();
        if (value_length != 0)
            break;
        if (input.ReadCString (DefaultEncoding) != "StringFileInfo")
            break;
        pos = (input.Position + 3) & -4L;
        input.Position = pos;
        int info_length = input.ReadUInt16();
        long end_pos = pos + info_length;
        value_length = input.ReadUInt16();
        if (value_length != 0)
            break;
        var output = new MemoryStream();
        using (var text = new StreamWriter (output, DefaultEncoding, 512, true))
        {
            string block_name = input.ReadCString (DefaultEncoding);
            text.WriteLine ("BLOCK \"{0}\"\n{{", block_name);
            long next_pos = (input.Position + 3) & -4L;
            while (next_pos < end_pos)
            {
                input.Position = next_pos;
                info_length = input.ReadUInt16();
                value_length = input.ReadUInt16();
                next_pos = (next_pos + info_length + 3) & -4L;
                string key = input.ReadCString (DefaultEncoding);
                input.Position = (input.Position + 3) & -4L;
                string value = value_length != 0 ? input.ReadCString (value_length, DefaultEncoding)
                                                 : String.Empty;
                text.WriteLine ("\tVALUE \"{0}\", \"{1}\"", key, value);
            }
            text.WriteLine ("}");
        }
        input.Dispose();
        output.Position = 0;
        return output;
    }
    input.Position = 0;
    return input;
}
```

### GameRes.Formats.Microsoft.NeResourceEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int NativeType ;

public int NativeName ;
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Experimental/Microsoft/ArcNE.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
