# Lazycrew / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/LAZYCREW` / `GameRes.Formats.Lazycrew.DatOpener` | `dat`, `` | `02000000` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.ReadIndex` | `int dir_count = index.View.ReadInt32 (0);` |
| `DatOpener.ReadIndex` | `Name   = index.View.ReadString (dir_offset, 8),` |
| `DatOpener.ReadIndex` | `Offset = index.View.ReadInt32 (dir_offset+8),` |
| `DatOpener.ReadIndex` | `Count  = index.View.ReadInt32 (dir_offset+12),` |
| `DatOpener.ReadIndex` | `int id = index.View.ReadUInt16 (dir_offset);` |
| `DatOpener.ReadIndex` | `Offset = index.View.ReadUInt32 (dir_offset+2),` |
| `DatOpener.ReadIndex` | `Size   = index.View.ReadUInt32 (dir_offset+6),` |
| `DatOpener.OpenEntry` | `uint signature = arc.File.View.ReadUInt32 (entry.Offset);` |
| `DatOpener.OpenAudio` | `uint data_size = arc.File.View.ReadUInt32 (entry.Offset+0x16);` |
| `DatOpener.OpenAudio` | `var pcm = arc.File.View.ReadBytes (entry.Offset+0x1A, data_size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Lazycrew.DirEntry

#### 状态与常量

```csharp
public string   Name ;

public int      Offset ;

public int      Count ;
```

### GameRes.Formats.Lazycrew.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Regex NamePattern = new Regex (@"^(?:(?<num>0\d\d\d)\.dat|data(?<num>\d+)?)$", RegexOptions.IgnoreCase) ;

const uint DefaultPcmKey = 0x4B5AB4A5 ;
```

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat", "" };
    Signatures = new uint[] { 2, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var name = Path.GetFileName (file.Name);
    if (!NamePattern.IsMatch (name))
        return null;
    var match = NamePattern.Match (name);
    int name_id = 1;
    var num_str = match.Groups["num"].Value;
    if (!string.IsNullOrEmpty (num_str))
        name_id = Int32.Parse (num_str);
    if (name_id < 1)
        return null;
    ArcView index = file;
    try
    {
        if (name_id != 1)
        {
            string index_name;
            if (file.Name.HasExtension (".dat"))
                index_name = VFS.ChangeFileName (file.Name, "0001.dat");
            else
                index_name = VFS.ChangeFileName (file.Name, "data");
            if (!VFS.FileExists (index_name))
                return null;
            index = VFS.OpenView (index_name);
        }
        var dir = ReadIndex (index, name_id, file.MaxOffset);
        if (null == dir || 0 == dir.Count)
            return null;
        return new ArcFile (file, this, dir);
    }
    finally
    {
        if (index != file)
            index.Dispose();
    }
}
```

#### ReadIndex

```csharp
List<Entry> ReadIndex (ArcView index, int arc_id, long arc_length) {
    int dir_count = index.View.ReadInt32 (0);
    if (dir_count <= 0 || dir_count > 20)
        return null;
    var dir_list = new List<DirEntry> (dir_count);
    int dir_offset = 4;
    int first_offset = dir_count * 0x10 + 4;
    for (int i = 0; i < dir_count; ++i)
    {
        var dir_entry = new DirEntry {
            Name   = index.View.ReadString (dir_offset, 8),
            Offset = index.View.ReadInt32 (dir_offset+8),
            Count  = index.View.ReadInt32 (dir_offset+12),
        };
        if (dir_entry.Offset < first_offset || dir_entry.Offset >= index.MaxOffset
            || !IsSaneCount (dir_entry.Count))
            return null;
        dir_list.Add (dir_entry);
        dir_offset += 16;
    }
    var file_list = new List<Entry>();
    foreach (var dir in dir_list)
    {
        dir_offset = dir.Offset;
        string type = "";
        if (dir.Name.Equals ("image", StringComparison.OrdinalIgnoreCase))
            type = "image";
        else if (dir.Name.Equals ("sound", StringComparison.OrdinalIgnoreCase))
            type = "audio";
        for (int i = 0; i < dir.Count; ++i)
        {
            int id = index.View.ReadUInt16 (dir_offset);
            if (id == arc_id)
            {
                var entry = new Entry {
                    Name = Path.Combine (dir.Name, i.ToString ("D5")),
                    Type = type,
                    Offset = index.View.ReadUInt32 (dir_offset+2),
                    Size   = index.View.ReadUInt32 (dir_offset+6),
                };
                if (!entry.CheckPlacement (arc_length))
                    return null;
                file_list.Add (entry);
            }
            dir_offset += 10;
        }
    }
    return file_list;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Type == "audio")
    {
        uint signature = arc.File.View.ReadUInt32 (entry.Offset);
        if (signature == 0x10000 || signature == 0)
            return OpenAudio (arc, entry);
        else if (signature == 1 || signature == 0x10001)
            return arc.File.CreateStream (entry.Offset+4, entry.Size-4);
    }
    return base.OpenEntry (arc, entry);
}
```

#### OpenAudio

```csharp
Stream OpenAudio (ArcFile arc, Entry entry) {
    var riff_header = new byte[0x2C];
    LittleEndian.Pack (AudioFormat.Wav.Signature, riff_header, 0);
    LittleEndian.Pack (0x45564157, riff_header, 8);
    LittleEndian.Pack (0x20746d66, riff_header, 12);
    LittleEndian.Pack (0x10, riff_header, 16);
    arc.File.View.Read (entry.Offset+4, riff_header, 20, 0x10);
    LittleEndian.Pack (0x61746164, riff_header, 0x24);
    uint data_size = arc.File.View.ReadUInt32 (entry.Offset+0x16);
    LittleEndian.Pack (data_size + 0x24u, riff_header, 4);
    LittleEndian.Pack (data_size, riff_header, 0x28);
    var pcm = arc.File.View.ReadBytes (entry.Offset+0x1A, data_size);
    DecryptData (pcm, DefaultPcmKey);
    var riff_data = new MemoryStream (pcm);
    return new PrefixStream (riff_header, riff_data);
}
```

#### DecryptData

```csharp
void DecryptData (byte[] data, uint key) {
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] ^= (byte)key;
        key = data[i] ^ ((key << 9) | (key >> 23) & 0x1F0);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Lazycrew/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
