# Patisserie / ArcBIN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BIN/OZ` / `GameRes.Formats.Patisserie.BinOpener` | `bin` | `4f5a0001` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BinOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "OFST"))` |
| `BinOpener.TryOpen` | `int index_size = file.View.ReadInt32 (8);` |
| `BinOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (index_offset);` |
| `BinOpener.TryOpen` | `next_offset = i+1 < count ? file.View.ReadUInt32 (index_offset) : (uint)file.MaxOffset;` |
| `BinOpener.TryOpen` | `entry.IsPacked = file.View.AsciiEqual (entry.Offset, "DFLT");` |
| `BinOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (entry.Offset+4);` |
| `BinOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (entry.Offset+8);` |
| `BinOpener.TryOpen` | `else if (file.View.AsciiEqual (entry.Offset, "DATA"))` |
| `BinOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |
| `BinOpener.ReadFileNames` | `if (index.View.ReadUInt32 (0) != Signature)` |
| `BinOpener.ReadFileNames` | `if (!index.View.AsciiEqual (4, "OFST"))` |
| `BinOpener.ReadFileNames` | `int index_size = index.View.ReadInt32 (8);` |
| `BinOpener.ReadFileNames` | `uint index_offset = index.View.ReadUInt32 (0xC + arc_no * 4);` |
| `BinOpener.ReadFileNames` | `if (index.View.AsciiEqual (index_offset, "DFLT"))` |
| `BinOpener.ReadFileNames` | `uint packed_size = index.View.ReadUInt32 (index_offset+4);` |
| `BinOpener.ReadFileNames` | `else if (index.View.AsciiEqual (index_offset, "DATA"))` |
| `BinOpener.ReadFileNames` | `uint data_size = index.View.ReadUInt32 (index_offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Patisserie.BinOpener

继承/接口：`ArchiveFormat`。

#### BinOpener

```csharp
public BinOpener () {
    Extensions = new string[] { "bin" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "OFST"))
        return null;
    int index_size = file.View.ReadInt32 (8);
    int count = index_size / 4;
    if (!IsSaneCount (count))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    string content_ext = "", content_type = "";
    if (base_name.EndsWith ("flac", StringComparison.OrdinalIgnoreCase))
    {
        content_ext = "flac";
        content_type = "audio";
        base_name = base_name.Substring (0, base_name.Length-4);
    }
    else if (base_name.EndsWith ("ogg", StringComparison.OrdinalIgnoreCase))
    {
        content_ext = "ogg";
        content_type = "audio";
        base_name = base_name.Substring (0, base_name.Length-3);
    }

    var filenames = GetFileNames (file.Name);
    if (null == filenames)
        filenames = new List<string> (count);
    for (int i = filenames.Count; i < count; ++i)
        filenames.Add (string.Format ("{0}#{1:D5}", base_name, i));

    uint index_offset = 0xC;
    var dir = new List<Entry> (count);
    uint next_offset = file.View.ReadUInt32 (index_offset);
    for (int i = 0; i < count; ++i)
    {
        index_offset += 4;
        var entry = new PackedEntry { Name = filenames[i] };
        entry.Offset = next_offset;
        next_offset = i+1 < count ? file.View.ReadUInt32 (index_offset) : (uint)file.MaxOffset;
        entry.Size = next_offset - (uint)entry.Offset;
        if (entry.Size > 0 && !entry.CheckPlacement (file.MaxOffset))
            return null;
        if (!string.IsNullOrEmpty (content_type))
        {
            entry.Type = content_type;
            entry.Name = Path.ChangeExtension (entry.Name, content_ext);
        }
        dir.Add (entry);
    }
    foreach (PackedEntry entry in dir.Where (e => e.Size > 4))
    {
        entry.IsPacked = file.View.AsciiEqual (entry.Offset, "DFLT");
        if (entry.IsPacked)
        {
            entry.Size = file.View.ReadUInt32 (entry.Offset+4);
            entry.UnpackedSize = file.View.ReadUInt32 (entry.Offset+8);
            entry.Offset += 12;
        }
        else if (file.View.AsciiEqual (entry.Offset, "DATA"))
        {
            entry.Size = file.View.ReadUInt32 (entry.Offset+4);
            entry.UnpackedSize = entry.Size;
            entry.Offset += 8;
            if (string.IsNullOrEmpty (entry.Type))
            {
                uint signature = file.View.ReadUInt32 (entry.Offset);
                if (0x43614C66 == signature)
                {
                    entry.Type = "audio";
                    entry.Name = Path.ChangeExtension (entry.Name, "flac");
                }
                else
                {
                    var res = AutoEntry.DetectFileType (signature);
                    if (null != res)
                        entry.ChangeType (res);
                }
            }
        }
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    return new ZLibStream (input, CompressionMode.Decompress);
}
```

#### ReadListFile

```csharp
IList<string> ReadListFile (string lst_name) {
    return File.ReadAllLines (lst_name, Encodings.cp932);
}
```

#### GetFileNames

```csharp
IList<string> GetFileNames (string arc_name) {
    var dir_name = VFS.GetDirectoryName (arc_name);
    var lst_name = Path.ChangeExtension (arc_name, ".lst");
    if (VFS.FileExists (lst_name))
        return ReadListFile (lst_name);

    var lists_lst_name = VFS.CombinePath (dir_name, name_list_parameter);
    if (!VFS.FileExists (lists_lst_name))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (arc_name);
    var arcs = ReadListFile (lists_lst_name);
    var arc_no = arcs.IndexOf (base_name);
    if (-1 == arc_no)
        return null;
    var lists_bin_name = VFS.CombinePath (dir_name, "lists.bin");
    using (var lists_bin = VFS.OpenView (lists_bin_name))
        return ReadFileNames (lists_bin, arc_no);
}
```

#### ReadFileNames

```csharp
IList<string> ReadFileNames (ArcView index, int arc_no) {
    if (index.View.ReadUInt32 (0) != Signature)
        return null;
    if (!index.View.AsciiEqual (4, "OFST"))
        return null;
    int index_size = index.View.ReadInt32 (8);
    int arc_count = index_size / 4;
    if (arc_no >= arc_count)
        return null;
    uint index_offset = index.View.ReadUInt32 (0xC + arc_no * 4);
    if (index_offset >= index.MaxOffset)
        return null;
    Stream input;
    if (index.View.AsciiEqual (index_offset, "DFLT"))
    {
        uint packed_size = index.View.ReadUInt32 (index_offset+4);
        input = index.CreateStream (index_offset+12, packed_size);
        input = new ZLibStream (input, CompressionMode.Decompress);
    }
    else if (index.View.AsciiEqual (index_offset, "DATA"))
    {
        uint data_size = index.View.ReadUInt32 (index_offset+4);
        input = index.CreateStream (index_offset+8, data_size);
    }
    else
        return null;
    using (input)
    using (var reader = new StreamReader (input, Encodings.cp932))
    {
        var list = new List<string>();
        string line;
        while ((line = reader.ReadLine()) != null)
            list.Add (line.Trim());
        return list;
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Patisserie/ArcBIN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
