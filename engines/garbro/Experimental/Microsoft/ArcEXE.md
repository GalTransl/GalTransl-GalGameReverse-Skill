# Microsoft / ArcEXE：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `EXE` / `GameRes.Formats.Microsoft.ExeOpener` | `exe` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ExeOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "MZ") \|\| VFS.IsVirtual)` |
| `ExeOpener.OpenVersion` | `if (input.ReadUInt16() != data.Length)` |
| `ExeOpener.OpenVersion` | `int value_length = input.ReadUInt16();` |
| `ExeOpener.OpenVersion` | `int type = input.ReadUInt16();` |
| `ExeOpener.OpenVersion` | `if (input.ReadCString (Encoding.Unicode) != "VS_VERSION_INFO")` |
| `ExeOpener.OpenVersion` | `if (input.ReadUInt32() != 0xFEEF04BDu)` |
| `ExeOpener.OpenVersion` | `info_length  = input.ReadUInt16();` |
| `ExeOpener.OpenVersion` | `value_length = input.ReadUInt16();` |
| `ExeOpener.OpenVersion` | `type         = input.ReadUInt16();` |
| `ExeOpener.OpenVersion` | `found_string_info = input.ReadCString (Encoding.Unicode) == "StringFileInfo";` |
| `ExeOpener.OpenVersion` | `info_length = input.ReadUInt16();` |
| `ExeOpener.OpenVersion` | `type = input.ReadUInt16();` |
| `ExeOpener.OpenVersion` | `string block_name = input.ReadCString (Encoding.Unicode);` |
| `ExeOpener.OpenVersion` | `string key = input.ReadCString (Encoding.Unicode);` |
| `ExeOpener.OpenVersion` | `string value = value_length != 0 ? input.ReadCString (value_length * 2, Encoding.Unicode)` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Microsoft.ExeOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Dictionary<string, string> RuntimeTypeMap = new Dictionary<string, string>() {
    { "#2",  "RT_BITMAP" },
    { "#10", "RT_RCDATA" },
    { "#16", "RT_VERSION" },
}

static readonly Dictionary<string, string> ExtensionTypeMap = new Dictionary<string, string>() {
    { "PNG",  ".PNG" },
    { "WAVE", ".WAV" },
    { "MIDS", ".MID" },
    { "SCR",  ".BIN" },
    { "#2",   ".BMP" },
    { "#10",  ".BIN" },
}

bool OpenRtVersionAsText = true ;
```

#### ExeOpener

```csharp
public ExeOpener () {
    Extensions = new[] { "exe", };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "MZ") || VFS.IsVirtual)
        return null;
    var res = new ExeFile.ResourceAccessor (file.Name);
    try
    {
        var dir = new List<Entry>();
        foreach (var type in res.EnumTypes())
        {
            string dir_name = type;
            if (type.StartsWith ("#") && !RuntimeTypeMap.TryGetValue (type, out dir_name))
                continue;
            string ext;
            if (!ExtensionTypeMap.TryGetValue (type, out ext))
                ext = "";
            foreach (var name in res.EnumNames (type))
            {
                string full_name = name;
                if (name.StartsWith ("#"))
                    full_name = IdToString (name);
                full_name = string.Join ("/", dir_name, full_name) + ext;
                var entry = Create<ResourceEntry> (full_name);
                entry.NativeName = name;
                entry.NativeType = type;
                entry.Offset = 0;
                entry.Size = res.GetResourceSize (name, type);
                dir.Add (entry);
            }
        }
        if (0 == dir.Count)
        {
            res.Dispose();
            return null;
        }
        return new ResourcesArchive (file, this, dir, res);
    }
    catch
    {
        res.Dispose();
        throw;
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var rarc = (ResourcesArchive)arc;
    var rent = (ResourceEntry)entry;
    var data = rarc.Accessor.GetResource (rent.NativeName, rent.NativeType);
    if (null == data)
        return Stream.Null;
    if (rent.NativeType == "#16" && OpenRtVersionAsText)
        return OpenVersion (data, rent.Name);
    return new BinMemoryStream (data, rent.Name);
}
```

#### IdToString

```csharp
internal static string IdToString (string id) {
    if (id.Length > 1 && id[0] == '#' && char.IsDigit (id[1]))
        id = id.Substring (1).PadLeft (5, '0');
    return id;
}
```

#### OpenVersion

```csharp
Stream OpenVersion (byte[] data, string name) {
    var input = new BinMemoryStream (data, name);
    for (;;)
    {
        if (input.ReadUInt16() != data.Length)
            break;
        int value_length = input.ReadUInt16();
        int type = input.ReadUInt16();
        if (0 == value_length || type != 0)
            break;
        if (input.ReadCString (Encoding.Unicode) != "VS_VERSION_INFO")
            break;
        long pos = (input.Position + 3) & -4L;
        input.Position = pos;
        if (input.ReadUInt32() != 0xFEEF04BDu)
            break;
        int info_length = value_length;
        bool found_string_info = false;
        do
        {
            pos += info_length;
            input.Position = pos;
            info_length  = input.ReadUInt16();
            value_length = input.ReadUInt16();
            type         = input.ReadUInt16();
            found_string_info = input.ReadCString (Encoding.Unicode) == "StringFileInfo";
        }
        while (!found_string_info && input.PeekByte() != -1);
        if (!found_string_info)
            break;
        pos = (input.Position + 3) & -4L;
        input.Position = pos;
        info_length = input.ReadUInt16();
        long end_pos = pos + info_length;
        value_length = input.ReadUInt16();
        type = input.ReadUInt16();
        if (value_length != 0)
            break;
        var output = new MemoryStream();
        using (var text = new StreamWriter (output, new UTF8Encoding (false), 512, true))
        {
            string block_name = input.ReadCString (Encoding.Unicode);
            text.WriteLine ("BLOCK \"{0}\"\r\n{{", block_name);
            long next_pos = (input.Position + 3) & -4L;
            while (next_pos < end_pos)
            {
                input.Position = next_pos;
                info_length = input.ReadUInt16();
                value_length = input.ReadUInt16();
                type = input.ReadUInt16();
                next_pos = (next_pos + info_length + 3) & -4L;
                string key = input.ReadCString (Encoding.Unicode);
                input.Position = (input.Position + 3) & -4L;
                string value = value_length != 0 ? input.ReadCString (value_length * 2, Encoding.Unicode)
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

### GameRes.Formats.Microsoft.ResourceEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public string NativeName ;

public string NativeType ;
```

### GameRes.Formats.Microsoft.ResourcesArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly ExeFile.ResourceAccessor Accessor ;

bool _acc_disposed = false ;
```

#### ResourcesArchive

```csharp
public ResourcesArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, ExeFile.ResourceAccessor acc)
    : base (arc, impl, dir) {
    Accessor = acc;
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../../ArcFormats/ExeFile.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Experimental/Microsoft/ArcEXE.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
