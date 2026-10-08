# JamCreation / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/JAM` / `GameRes.Formats.JamCreation.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.OpenEntry` | `var data = input.ReadBytes ((int)entry.Size);` |
| `DatOpener.ReadIndex` | `if (file.View.ReadUInt32 (0x14) != 1)` |
| `DatOpener.ReadIndex` | `Offset = file.View.ReadUInt32 (table_pos),` |
| `DatOpener.ReadIndex` | `Size   = file.View.ReadUInt32 (table_pos+4),` |
| `DatOpener.ReadIndex` | `int count = file.View.ReadInt32 (indexDir[0].Offset);` |
| `DatOpener.ReadIndex` | `var index = file.View.ReadBytes (indexDir[0].Offset+4, indexDir[0].Size-4);` |
| `DatOpener.ReadIndex` | `int name_count = file.View.ReadInt32 (indexDir[1].Offset);` |
| `DatOpener.ReadIndex` | `var names_index = file.View.ReadBytes (indexDir[1].Offset+4, indexDir[1].Size-4);` |
| `DatOpener.ReadIndex` | `var names = file.View.ReadBytes (indexDir[2].Offset, indexDir[2].Size);` |
| `DatOpener.ReadIndex` | `int arc_count = file.View.ReadInt32 (indexDir[3].Offset);` |
| `DatOpener.ReadIndex` | `var arc_names_index = file.View.ReadBytes (indexDir[3].Offset+4, indexDir[3].Size-4);` |
| `DatOpener.ReadIndex` | `var arc_names_data = file.View.ReadBytes (indexDir[4].Offset, indexDir[4].Size);` |
| `DatOpener.ReadIndex` | `int pos = arc_names_index.ToInt32 (i * 4);` |
| `DatOpener.ReadIndex` | `uint flags = index.ToUInt32 (index_pos+0x10);` |
| `DatOpener.ReadIndex` | `int name_pos = names_index.ToInt32 (i * 4);` |
| `DatOpener.ReadIndex` | `int subdir_count = index.ToInt32 (index_pos+0x14);` |
| `DatOpener.ReadIndex` | `int id = index.ToInt32 (index_pos);` |
| `DatOpener.ReadIndex` | `entry.Offset = index.ToUInt32 (index_pos+4);` |
| `DatOpener.ReadIndex` | `entry.Size = index.ToUInt32 (index_pos+8);` |
| `DatOpener.ReadIndex` | `entry.UnpackedSize = index.ToUInt32 (index_pos+12);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.JamCreation.AinosEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public bool IsEncrypted ;
```

### GameRes.Formats.JamCreation.DatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat") || VFS.IsPathEqualsToFileName (file.Name, "00000000.dat"))
        return null;
    var index_name = VFS.ChangeFileName (file.Name, "00000000.dat");
    if (!VFS.FileExists (index_name))
        return null;
    var arc_name = Path.GetFileName (file.Name);
    using (var index = VFS.OpenView (index_name))
    {
        var dir = ReadIndex (index, arc_name, file.MaxOffset);
        if (null == dir)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as AinosEntry;
    if (null == pent)
        return input;
    if (pent.IsPacked)
        return new ZLibStream (input, CompressionMode.Decompress);
    if (!pent.IsEncrypted)
        return input;
    using (input)
    {
        var data = input.ReadBytes ((int)entry.Size);
        Decrypt (data, data.Length);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### ReadIndex

```csharp
List<Entry> ReadIndex (ArcView file, string arc_name, long arc_length) {
    if (file.View.ReadUInt32 (0x14) != 1)
        return null;
    uint table_pos = 0x18;
    var indexDir = new List<Entry> (5);
    for (int i = 0; i < 5; ++i)
    {
        var entry = new Entry {
            Offset = file.View.ReadUInt32 (table_pos),
            Size   = file.View.ReadUInt32 (table_pos+4),
        };
        if (entry.Size < 4 || !entry.CheckPlacement (file.MaxOffset))
            return null;
        indexDir.Add (entry);
        table_pos += 8;
    }
    int count = file.View.ReadInt32 (indexDir[0].Offset);
    if (!IsSaneCount (count) || 24 * count > indexDir[0].Size - 4)
        return null;
    var index = file.View.ReadBytes (indexDir[0].Offset+4, indexDir[0].Size-4);
    Decrypt (index, 24 * count);

    int name_count = file.View.ReadInt32 (indexDir[1].Offset);
    if (4 * name_count > indexDir[1].Size - 4)
        return null;
    var names_index = file.View.ReadBytes (indexDir[1].Offset+4, indexDir[1].Size-4);
    Decrypt (names_index, 4 * name_count);

    var names = file.View.ReadBytes (indexDir[2].Offset, indexDir[2].Size);
    Decrypt (names, (int)indexDir[2].Size);

    int arc_count = file.View.ReadInt32 (indexDir[3].Offset);
    if (4 * arc_count > indexDir[3].Size - 4)
        return null;
    var arc_names_index = file.View.ReadBytes (indexDir[3].Offset+4, indexDir[3].Size-4);
    Decrypt (arc_names_index, 4 * arc_count);

    var arc_names_data = file.View.ReadBytes (indexDir[4].Offset, indexDir[4].Size);
    Decrypt (arc_names_data, (int)indexDir[4].Size);
    var arc_names = new Dictionary<string, int> (arc_count);
    for (int i = 0; i < arc_count; ++i)
    {
        int pos = arc_names_index.ToInt32 (i * 4);
        var name = Binary.GetCString (arc_names_data, pos);
        arc_names[name] = i;
    }
    if (!arc_names.ContainsKey (arc_name))
        return null;

    int arc_id = arc_names[arc_name];
    var dir = new List<Entry>();
    string subdir_name = "";
    int index_pos = 0;
    for (int i = 0; i < count; ++i)
    {
        uint flags = index.ToUInt32 (index_pos+0x10);
        if (flags == 0x80000000)
        {
            int name_pos = names_index.ToInt32 (i * 4);
            subdir_name = Binary.GetCString (names, name_pos);
            int subdir_count = index.ToInt32 (index_pos+0x14);
        }
        else
        {
            int id = index.ToInt32 (index_pos);
            if (id == arc_id)
            {
                int name_pos = names_index.ToInt32 (i * 4);
                var name = Path.Combine (subdir_name, Binary.GetCString (names, name_pos));
                var entry = Create<AinosEntry> (name);
                entry.Offset = index.ToUInt32 (index_pos+4);
                entry.Size = index.ToUInt32 (index_pos+8);
                entry.UnpackedSize = index.ToUInt32 (index_pos+12);
                entry.IsPacked = (flags & 0x100) != 0;
                entry.IsEncrypted = (flags & 0x200) != 0;
                if (entry.CheckPlacement (arc_length))
                    dir.Add (entry);
            }
        }
        index_pos += 24;
    }
    if (0 == dir.Count)
        return null;
    return dir;
}
```

#### Decrypt

```csharp
void Decrypt (byte[] data, int length) {
    byte prev = data[0];
    for (int i = 1; i < length; ++i)
    {
        data[i] -= (byte)(i + prev);
        prev = data[i];
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/JamCreation/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
