# elf / ArcHED：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BIN/HED` / `GameRes.Formats.Elf.PakOpener` | `bin` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `if (0x00646568 != pak.View.ReadUInt32 (0))` |
| `PakOpener.TryOpen` | `int count = pak.View.ReadInt32 (4);` |
| `PakOpener.ReadCgPak` | `entry.Offset = pak.View.ReadUInt32 (index_offset);` |
| `PakOpener.ReadCgPak` | `entry.Size   = pak.View.ReadUInt32 (index_offset + 4);` |
| `PakOpener.ReadVoicePak` | `entry.Offset = pak.View.ReadUInt32 (index_offset);` |
| `PakOpener.ReadVoicePak` | `entry.Size   = pak.View.ReadUInt32 (index_offset + 4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Elf.PakOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
private List<string>    CgMap { get; set; }

private List<string> VoiceMap { get; set; }

private string CurrentMapName { get; set; }

static readonly Regex FilesTypeRe = new Regex (@"^//([A-Z]+) FILES = (\d+)") ;
```

#### PakOpener

```csharp
public PakOpener () {
    Extensions = new string[] { "bin" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    string pak_name = Path.ChangeExtension (file.Name, "pak");
    if (pak_name == file.Name || !VFS.FileExists (pak_name))
        return null;
    var file_map = GetFileMap (pak_name);
    if (null == file_map)
        return null;
    string base_name = Path.GetFileNameWithoutExtension (pak_name);

    using (var pak = VFS.OpenView (pak_name))
    {
        if (0x00646568 != pak.View.ReadUInt32 (0))
            return null;
        int count = pak.View.ReadInt32 (4);
        if (count != file_map.Count)
            return null;
        List<Entry> dir;
        if ("cg" == base_name)
            dir = ReadCgPak (pak, file, file_map);
        else
            dir = ReadVoicePak (pak, file, file_map);
        if (null == dir)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

#### ReadCgPak

```csharp
List<Entry> ReadCgPak (ArcView pak, ArcView bin, List<string> file_map) {
    uint index_offset = 8;
    uint index_size = (uint)file_map.Count * 8u;
    if (index_size > pak.View.Reserve (index_offset, index_size))
        return null;
    var dir = new List<Entry> (file_map.Count);
    for (int i = 0; i < file_map.Count; ++i)
    {
        var entry = FormatCatalog.Instance.Create<Entry> (file_map[i]);
        entry.Offset = pak.View.ReadUInt32 (index_offset);
        entry.Size   = pak.View.ReadUInt32 (index_offset + 4);
        if (!entry.CheckPlacement (bin.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 8;
    }
    return dir;
}
```

#### ReadVoicePak

```csharp
List<Entry> ReadVoicePak (ArcView pak, ArcView bin, List<string> file_map) {
    uint index_offset = 8;
    uint index_size = (uint)file_map.Count * 0x18u;
    if (index_size > pak.View.Reserve (index_offset, index_size))
        return null;
    var dir = new List<Entry> (file_map.Count);
    for (int i = 0; i < file_map.Count; ++i)
    {
        var entry = FormatCatalog.Instance.Create<Entry> (file_map[i]);
        entry.Offset = pak.View.ReadUInt32 (index_offset);
        entry.Size   = pak.View.ReadUInt32 (index_offset + 4);
        if (!entry.CheckPlacement (bin.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x18;
    }
    return dir;
}
```

#### GetFileMap

```csharp
private List<string> GetFileMap (string pak_name, string map_name = "avking.map") {
    string base_name = Path.GetFileNameWithoutExtension (pak_name);
    List<string> map;
    if ("cg" == base_name)
        map = CgMap;
    else if ("voice" == base_name)
        map = VoiceMap;
    else
        return null;
    if (null != map && File.Exists (CurrentMapName))
        return map;
    CgMap = null;
    VoiceMap = null;
    string dir_name = Path.GetDirectoryName (pak_name);
    if (string.IsNullOrEmpty (dir_name))
        dir_name = ".";
    while (!string.IsNullOrEmpty (dir_name))
    {
        string map_file = Path.Combine (dir_name, map_name);
        if (File.Exists (map_file))
        {
            if (!ReadMap (map_file))
                return null;
            CurrentMapName = map_file;
            if ("cg" == base_name)
                return CgMap;
            if ("voice" == base_name)
                return VoiceMap;
        }
        dir_name = Path.GetDirectoryName (dir_name);
    }
    return null;
}
```

#### ReadMap

```csharp
private bool ReadMap (string map_file) {
    try
    {
        using (var map = File.OpenRead (map_file))
        using (var input = new StreamReader (map, Encoding.ASCII))
        {
            var cg = new List<string>();
            var voice = new List<string>();
            List<string> current_list = null;
            for (;;)
            {
                string line = input.ReadLine();
                if (null == line)
                    break;
                var match = FilesTypeRe.Match (line);
                if (!match.Success)
                    return false;
                string type = match.Groups[1].Value;
                if ("BG" == type || "CHR" == type)
                    current_list = cg;
                else if ("VOICE" == type)
                    current_list = voice;
                else
                    current_list = null;
                int count = UInt16.Parse (match.Groups[2].Value);
                for (int i = 0; i < count; ++i)
                {
                    line = input.ReadLine();
                    if (null == line)
                        break;
                    if (null != current_list)
                        current_list.Add (line.TrimEnd ('\0'));
                }
            }
            CgMap = cg;
            VoiceMap = voice;
            return cg.Count > 0 || voice.Count > 0;
        }
    }
    catch
    {
        return false;
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/elf/ArcHED.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
