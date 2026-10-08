# Tactics / ArcLST：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `LST` / `GameRes.Formats.Nexton.LstOpener` | `` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LstOpener.OpenMoon` | `int count = (int)(lst.View.ReadUInt32 (0) ^ 0xcccccccc);` |
| `LstOpener.OpenMoon` | `entry.Offset = lst.View.ReadUInt32 (index_offset) ^ 0xcccccccc;` |
| `LstOpener.OpenMoon` | `entry.Size   = lst.View.ReadUInt32 (index_offset+4) ^ 0xcccccccc;` |
| `LstOpener.OpenNexton` | `uint key = lst.View.ReadByte (3);` |
| `LstOpener.OpenNexton` | `int count = (int)(lst.View.ReadUInt32 (0) ^ key);` |
| `LstOpener.OpenNexton` | `Offset = lst.View.ReadUInt32 (index_offset) ^ key,` |
| `LstOpener.OpenNexton` | `Size   = lst.View.ReadUInt32 (index_offset+4) ^ key,` |
| `LstOpener.OpenNexton` | `int type = lst.View.ReadInt32 (index_offset+0x48);` |
| `LstOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `LstOpener.ReadName` | `byte b = view.View.ReadByte (offset+n);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Nexton.NextonEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public byte Key ;
```

### GameRes.Formats.Nexton.LstOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static string[] TypeExt = new string[] { "LST", "SNX", "BMP", "PNG", "WAV", "OGG" }
```

#### LstOpener

```csharp
public LstOpener () {
    Extensions = new string[] { "" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    string lstname = file.Name + ".lst";
    if (!VFS.FileExists (lstname))
        return null;
    using (var lst = VFS.OpenView (lstname))
    {
        List<Entry> dir = null;
        try
        {
            dir = OpenMoon (lst, file.MaxOffset);
        }
        catch {  }
        if (null == dir)
            dir = OpenNexton (lst, file.MaxOffset);
        if (null == dir)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenMoon

```csharp
private List<Entry> OpenMoon (ArcView lst, long max_offset) {
    int count = (int)(lst.View.ReadUInt32 (0) ^ 0xcccccccc);
    if (count <= 0 || (4 + count*0x2c) > lst.MaxOffset)
        return null;
    var cp932 = Encodings.cp932.WithFatalFallback();
    var dir = new List<Entry> (count);
    uint index_offset = 4;
    for (int i = 0; i < count; ++i)
    {
        string name = ReadName (lst, index_offset+8, 0x24, 0xcc, cp932);
        if (0 == name.Length)
            return null;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = lst.View.ReadUInt32 (index_offset) ^ 0xcccccccc;
        entry.Size   = lst.View.ReadUInt32 (index_offset+4) ^ 0xcccccccc;
        if (!entry.CheckPlacement (max_offset))
            return null;
        dir.Add (entry);
        index_offset += 0x2c;
    }
    return dir;
}
```

#### OpenNexton

```csharp
private List<Entry> OpenNexton (ArcView lst, long max_offset) {
    uint key = lst.View.ReadByte (3);
    if (0 == key)
        return null;
    key |= key << 8;
    key |= key << 16;
    int count = (int)(lst.View.ReadUInt32 (0) ^ key);
    if (count <= 0 || (4 + count*0x4c) > lst.MaxOffset)
        return null;
    var cp932 = Encodings.cp932.WithFatalFallback();
    var dir = new List<Entry> (count);
    uint index_offset = 4;
    for (int i = 0; i < count; ++i)
    {
        string name = ReadName (lst, index_offset+8, 0x40, (byte)key, cp932);
        if (0 == name.Length)
            return null;
        var entry = new NextonEntry {
            Name = name,
            Offset = lst.View.ReadUInt32 (index_offset) ^ key,
            Size   = lst.View.ReadUInt32 (index_offset+4) ^ key,
        };
        if (!entry.CheckPlacement (max_offset))
            return null;
        int type = lst.View.ReadInt32 (index_offset+0x48);
        if (type >= 0 && type < TypeExt.Length)
        {
            entry.Name = Path.ChangeExtension (name, TypeExt[type]);
            if (2 == type || 3 == type)
                entry.Type = "image";
            else if (4 == type || 5 == type)
                entry.Type = "audio";
            else if (1 == type)
            {
                entry.Type = "script";
                entry.Key = (byte)(key + 1);
            }
        }
        dir.Add (entry);
        index_offset += 0x4c;
    }
    return dir;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var nxent = entry as NextonEntry;
    if (null == nxent || 0 == nxent.Key)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    for (int i = 0; i != data.Length; ++i)
        data[i] ^= nxent.Key;
    return new BinMemoryStream (data, entry.Name);
}
```

#### ReadName

```csharp
private static string ReadName (ArcView view, long offset, uint size, byte key, Encoding enc) {
    byte[] buffer = new byte[size];
    uint n;
    for (n = 0; n < size; ++n)
    {
        byte b = view.View.ReadByte (offset+n);
        if (0 == b)
            break;
        if (b != key)
            b ^= key;
        buffer[n] = b;
    }
    return enc.GetString (buffer, 0, (int)n);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Tactics/ArcLST.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
