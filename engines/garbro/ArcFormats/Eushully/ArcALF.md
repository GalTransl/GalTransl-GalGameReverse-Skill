# Eushully / ArcALF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ALF` / `GameRes.Formats.Eushully.AlfOpener` | `alf` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AlfOpener.GetAGEArcInfo` | `byte[] sig = view.View.ReadBytes(0, 8);` |
| `AlfOpener.ReadIndex` | `index = new BinaryStream(new LzssStream(ini.CreateStream(info.offset + 4, (uint)ini.View.ReadInt32(info.offset))), ini_file);` |
| `AlfOpener.ReadSysIni` | `int arc_count = index.ReadInt32();` |
| `AlfOpener.ReadSysIni` | `string name = info.isNameUnicode ? index.ReadCString(0x200, Encoding.Unicode) : index.ReadCString(0x100);` |
| `AlfOpener.ReadSysIni` | `int file_count = index.ReadInt32();` |
| `AlfOpener.ReadSysIni` | `string name = info.isNameUnicode ? index.ReadCString(0x80, Encoding.Unicode) : index.ReadCString(0x40);` |
| `AlfOpener.ReadSysIni` | `int arc_id = index.ReadInt32();` |
| `AlfOpener.ReadSysIni` | `index.ReadInt32();` |
| `AlfOpener.ReadSysIni` | `uint offset = index.ReadUInt32();` |
| `AlfOpener.ReadSysIni` | `uint size = index.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Eushully.AlfOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
Tuple<string, Dictionary<string, List<Entry>>> LastAccessedIndex ;

static AGEArchiveInfo[] infos = {
    new AGEArchiveInfo(Encoding.ASCII.GetBytes("S3IN"), 0x12C, false, false),
    new AGEArchiveInfo(Encoding.ASCII.GetBytes("S3IC"), 0x134, false, true),
    new AGEArchiveInfo(Encoding.ASCII.GetBytes("S3AC"), 0x114, false, true),
    new AGEArchiveInfo(Encoding.ASCII.GetBytes("S4IC"), 0x134, false, true),
    new AGEArchiveInfo(Encoding.ASCII.GetBytes("S4AC"), 0x114, false, true),
    new AGEArchiveInfo(Encoding.Unicode.GetBytes("S5IC"), 0x224, true, true),
    new AGEArchiveInfo(Encoding.Unicode.GetBytes("S5AC"), 0x21C, true, true)
}
```

#### AlfOpener

```csharp
public AlfOpener () {
    ContainedFormats = new[] { "AGF", "WAV", "AOG/SYS3", "SCR" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    string dir_name = Path.GetDirectoryName (file.Name);
    string file_name = Path.GetFileName (file.Name);
    foreach (var ini_name in GetIndexNames (file_name))
    {
        string ini_path = VFS.CombinePath (dir_name, ini_name);
        if (VFS.FileExists (ini_path))
        {
            var dir = ReadIndex (ini_path, file_name);
            if (null != dir)
                return new ArcFile (file, this, dir);
        }
    }
    return null;
}
```

#### GetAAIName

```csharp
static internal string GetAAIName(string alf_name) {
    const string pattern = @"^(APPEND(?:[0-9]+)?)(?:_[0-9]+)?\.ALF$";
    var match = Regex.Match(alf_name, pattern);
    if (match.Success)
        return match.Groups[1].Value;
    return alf_name;
}
```

#### GetIndexNames

```csharp
internal IEnumerable<string> GetIndexNames (string alf_name) {
    yield return "sys5ini.bin";
    yield return "sys4ini.bin";
    yield return "sys3ini.bin";
    yield return Path.ChangeExtension (GetAAIName(alf_name), "AAI");
}
```

#### GetAGEArcInfo

```csharp
static internal AGEArchiveInfo GetAGEArcInfo(ArcView view) {
    byte[] sig = view.View.ReadBytes(0, 8);
    var siglow = sig.Take(4);
    var res = infos.Where(i => Enumerable.SequenceEqual(i.signature, siglow));
    if (res.Any()) return res.First();
    res = infos.Where(i => Enumerable.SequenceEqual(i.signature, sig));
    if (res.Any()) return res.First();
    return null;
}
```

#### ReadIndex

```csharp
List<Entry> ReadIndex (string ini_file, string arc_name) {
    if (null == LastAccessedIndex
        || !LastAccessedIndex.Item1.Equals (ini_file, StringComparison.OrdinalIgnoreCase))
    {
        LastAccessedIndex = null;
        using (var ini = VFS.OpenView (ini_file))
        {
            IBinaryStream index;

            AGEArchiveInfo info = GetAGEArcInfo (ini);
            if (info == null) return null;

            if (info.isLZSSCompressed)
            {
                index = new BinaryStream(new LzssStream(ini.CreateStream(info.offset + 4, (uint)ini.View.ReadInt32(info.offset))), ini_file);
            }
            else
            {
                index = ini.CreateStream(info.offset);
            }
            using (index)
            {
                var file_table = ReadSysIni (index, info);
                if (null == file_table)
                    return null;
                LastAccessedIndex = Tuple.Create (ini_file, file_table);
            }
        }
    }
    List<Entry> dir = null;
    LastAccessedIndex.Item2.TryGetValue (arc_name, out dir);
    return dir;
}
```

#### ReadSysIni

```csharp
internal Dictionary<string, List<Entry>> ReadSysIni (IBinaryStream index, AGEArchiveInfo info) {
    int arc_count = index.ReadInt32();
    if (!IsSaneCount (arc_count))
        return null;
    var file_table = new Dictionary<string, List<Entry>> (arc_count, StringComparer.OrdinalIgnoreCase);
    var arc_list = new List<Entry>[arc_count];
    for (int i = 0; i < arc_count; ++i)
    {
        string name = info.isNameUnicode ? index.ReadCString(0x200, Encoding.Unicode) : index.ReadCString(0x100);

        var file_list = new List<Entry>();
        file_table.Add (name, file_list);
        arc_list[i] = file_list;
    }
    int file_count = index.ReadInt32();
    if (!IsSaneCount (file_count))
        return null;

    for (int i = 0; i < file_count; ++i)
    {
        string name = info.isNameUnicode ? index.ReadCString(0x80, Encoding.Unicode) : index.ReadCString(0x40);
        int arc_id = index.ReadInt32();
        if (arc_id < 0 || arc_id >= arc_list.Length)
            return null;
        index.ReadInt32();
        uint offset = index.ReadUInt32();
        uint size = index.ReadUInt32();
        if ("@" == name)
            continue;
        var entry = Create<Entry> (name);
        entry.Offset = offset;
        entry.Size = size;
        arc_list[arc_id].Add (entry);
    }
    return file_table;
}
```

### GameRes.Formats.Eushully.AlfOpener.AGEArchiveInfo

#### 状态与常量

```csharp
public readonly byte[] signature ;

public readonly int offset ;

public readonly bool isNameUnicode ;

public readonly bool isLZSSCompressed ;
```

#### AGEArchiveInfo

```csharp
public AGEArchiveInfo(byte[] Signature, int Offset, bool IsNameUnicode, bool IsLZSSCompressed) {
    signature = Signature;
    offset = Offset;
    isNameUnicode = IsNameUnicode;
    isLZSSCompressed = IsLZSSCompressed;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Eushully/ArcALF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
