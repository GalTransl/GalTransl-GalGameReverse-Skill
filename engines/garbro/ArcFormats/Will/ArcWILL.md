# Will / ArcWILL：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/Will` / `GameRes.Formats.Will.ArcOpener` | `arc` | `01000000`, `05000000`, `06000000` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `int ext_count = file.View.ReadInt32 (0);` |
| `ArcOpener.TryOpen` | `string ext = file.View.ReadString (dir_offset, 4).ToLowerInvariant();` |
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (dir_offset+4);` |
| `ArcOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (dir_offset+8);` |
| `ArcOpener.ReadFileList` | `string name = file.View.ReadString (dir_offset, name_size);` |
| `ArcOpener.ReadFileList` | `entry.Size = file.View.ReadUInt32 (dir_offset+name_size);` |
| `ArcOpener.ReadFileList` | `entry.Offset = file.View.ReadUInt32 (dir_offset+name_size+4);` |
| `ArcOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Will.ExtRecord

#### 状态与常量

```csharp
public string   Extension ;

public int      FileCount ;

public uint     DirOffset ;
```

### GameRes.Formats.Will.ArcOpener

继承/接口：`ArchiveFormat`。

#### ArcOpener

```csharp
ArcOpener () {
    Extensions = new string[] { "arc" };
    Signatures = new uint[] { 1, 0, 5, 6 };
    ContainedFormats = new[] { "WIP", "PNA", "OGG", "SCR" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int ext_count = file.View.ReadInt32 (0);
    if (ext_count <= 0 || ext_count > 0xff)
        return null;

    uint dir_offset = 4;
    var ext_list = new List<ExtRecord> (ext_count);
    for (int i = 0; i < ext_count; ++i)
    {
        string ext = file.View.ReadString (dir_offset, 4).ToLowerInvariant();
        int count = file.View.ReadInt32 (dir_offset+4);
        uint offset = file.View.ReadUInt32 (dir_offset+8);
        if (count <= 0 || count > 0xffff || offset <= dir_offset || offset > file.MaxOffset)
            return null;
        ext_list.Add (new ExtRecord { Extension = ext, FileCount = count, DirOffset = offset });
        dir_offset += 12;
    }
    List<Entry> dir = null;
    try
    {
        dir = ReadFileList (file, ext_list, 9);
    }
    catch {  }
    if (null == dir)
        dir = ReadFileList (file, ext_list, 13);
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### ReadFileList

```csharp
List<Entry> ReadFileList (ArcView file, IEnumerable<ExtRecord> ext_list, uint name_size) {
    var dir = new List<Entry> (ext_list.Sum (ext => ext.FileCount));
    foreach (var ext in ext_list)
    {
        uint dir_offset = ext.DirOffset;
        for (int i = 0; i < ext.FileCount; ++i)
        {
            string name = file.View.ReadString (dir_offset, name_size);
            if (string.IsNullOrEmpty (name))
                return null;
            name = name.ToLowerInvariant();
            if (ext.Extension.Length > 0)
                name = Path.ChangeExtension (name, ext.Extension);
            var entry = Create<Entry> (name);
            entry.Size = file.View.ReadUInt32 (dir_offset+name_size);
            entry.Offset = file.View.ReadUInt32 (dir_offset+name_size+4);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            dir_offset += name_size+8;
        }
    }
    return dir;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (!IsScriptFile (entry.Name))
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    DecodeScript (data);
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecodeScript

```csharp
private static void DecodeScript (byte[] data) {
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] = Binary.RotByteR (data[i], 2);
    }
}
```

#### EncodeScript

```csharp
private static void EncodeScript (byte[] data) {
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] = Binary.RotByteL (data[i], 2);
    }
}
```

#### WriteEntry

```csharp
private uint WriteEntry (string filename, Stream output) {
    if (!IsScriptFile (filename))
    {
        using (var input = File.OpenRead (filename))
        {
            var size = input.Length;
            if (size > uint.MaxValue)
                throw new FileSizeException();
            input.CopyTo (output);
            return (uint)size;
        }
    }
    else
    {
        var input = File.ReadAllBytes (filename);
        EncodeScript (input);
        output.Write (input, 0, input.Length);
        return (uint)input.Length;
    }
}
```

#### IsScriptFile

```csharp
private static bool IsScriptFile (string filename) {
    return filename.HasAnyOfExtensions ("scr", "wsc");
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Will/ArcWILL.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
