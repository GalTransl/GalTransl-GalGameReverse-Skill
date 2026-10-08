# Tanaka / ArcARCG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARCG` / `GameRes.Formats.Will.ArcGOpener` | `arc`, `bmx`, `scb`, `vpk` | `41524347` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcGOpener.TryOpen` | `if (0x10000 != file.View.ReadUInt32 (4))` |
| `ArcGOpener.TryOpen` | `int index_offset = file.View.ReadInt32 (8);` |
| `ArcGOpener.TryOpen` | `int index_size   = file.View.ReadInt32 (0xC);` |
| `ArcGOpener.TryOpen` | `int dir_count = file.View.ReadUInt16 (0x10);` |
| `ArcGOpener.TryOpen` | `int count = file.View.ReadInt32 (0x12);` |
| `ArcGOpener.TryOpen` | `if (null == index \|\| !index.AsciiEqual ("ARCG") \|\| index.ToUInt32 (4) != 0x10000)` |
| `ArcGOpener.TryOpen` | `index_offset = index.ToInt32 (8);` |
| `ArcGOpener.TryOpen` | `index_size   = index.ToInt32 (0xC);` |
| `ArcGOpener.TryOpen` | `dir_count = index.ToUInt16 (0x10);` |
| `ArcGOpener.TryOpen` | `count = index.ToInt32 (0x12);` |
| `ArcGOpener.TryOpen` | `index = file.View.ReadBytes (index_offset, (uint)index_size);` |
| `ArcGOpener.TryOpen` | `int dir_offset = index.ToInt32 (index_pos) - base_offset;` |
| `ArcGOpener.TryOpen` | `int file_count = index.ToInt32 (index_pos+4);` |
| `ArcGOpener.TryOpen` | `entry.Offset = index.ToUInt32 (dir_offset);` |
| `ArcGOpener.TryOpen` | `entry.Size   = index.ToUInt32 (dir_offset+4);` |
| `ArcGOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |
| `ArcGOpener.ReadIndex` | `uint signature = index.ToUInt32 (0);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Will.ArcGOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
BmiScheme KnownSchemes = new BmiScheme() ;

internal static Lazy<ImageFormat> BcFormat = new Lazy<ImageFormat> (() => ImageFormat.FindByTag ("BC")) ;
```

#### ArcGOpener

```csharp
public ArcGOpener () {
    Extensions = new string[] { "arc", "bmx", "scb", "vpk" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (0x10000 != file.View.ReadUInt32 (4))
        return null;
    int index_offset = file.View.ReadInt32 (8);
    int index_size   = file.View.ReadInt32 (0xC);
    int dir_count = file.View.ReadUInt16 (0x10);
    int count = file.View.ReadInt32 (0x12);
    int base_offset = index_offset;
    byte[] index = null;
    if (0 == index_offset)
    {
        if (VFS.IsVirtual || !file.Name.HasExtension ("bmx"))
            return null;
        var bmi_name = Path.ChangeExtension (file.Name, "bmi");
        index = ReadIndex (bmi_name);
        if (null == index || !index.AsciiEqual ("ARCG") || index.ToUInt32 (4) != 0x10000)
            return null;
        index_offset = index.ToInt32 (8);
        index_size   = index.ToInt32 (0xC);
        dir_count = index.ToUInt16 (0x10);
        count = index.ToInt32 (0x12);
        base_offset = 0;
    }
    else
    {
        if (index_offset >= file.MaxOffset)
            return null;
        index = file.View.ReadBytes (index_offset, (uint)index_size);
    }
    if (!IsSaneCount (count) || index_size > index.Length)
        return null;
    int index_pos = index_offset - base_offset;
    var dir = new List<Entry> (count);
    for (int j = 0; j < dir_count; ++j)
    {
        int name_length = index[index_pos];
        var dir_name = Binary.GetCString (index, index_pos+1, name_length-1);
        index_pos += name_length;
        int dir_offset = index.ToInt32 (index_pos) - base_offset;
        int file_count = index.ToInt32 (index_pos+4);
        if (dir_offset < 0 || dir_offset >= index.Length || file_count < 0 || file_count > count)
            return null;
        index_pos += 8;
        for (int i = 0; i < file_count; ++i)
        {
            name_length = index[dir_offset];
            if (0 == name_length)
                return null;
            var file_name = Binary.GetCString (index, dir_offset+1, name_length-1);
            file_name = file_name.Replace ('?', '？');
            dir_offset += name_length;
            file_name = Path.Combine (dir_name, file_name);
            var entry = FormatCatalog.Instance.Create<Entry> (file_name);
            entry.Offset = index.ToUInt32 (dir_offset);
            entry.Size   = index.ToUInt32 (dir_offset+4);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir_offset += 8;
            dir.Add (entry);
        }
    }
    foreach (var entry in dir.Where (e => string.IsNullOrEmpty (e.Type)))
    {
        uint signature = file.View.ReadUInt32 (entry.Offset);
        IResource res;
        if ((signature & 0xFFFF) == 0x4342)
            res = BcFormat.Value;
        else
            res = AutoEntry.DetectFileType (signature);
        if (res != null)
            entry.Type = res.Type;
    }
    return new ArcFile (file, this, dir);
}
```

#### ReadIndex

```csharp
byte[] ReadIndex (string bmi_name) {
    var index = File.ReadAllBytes (bmi_name);
    uint signature = index.ToUInt32 (0);
    string passkey;
    if (!KnownKeys.TryGetValue (signature, out passkey))
    {
        var root = Path.GetPathRoot (bmi_name);
        if (string.IsNullOrEmpty (root))
            return null;
        uint serial;
        if (!GetVolumeInformation (root, IntPtr.Zero, 0, out serial,
                                   IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 0))
            return null;
        passkey = string.Format ("{0:x4}{1}", serial, (int)serial);
    }
    uint seed = GetSeedFromString (passkey);
    var twister = new MersenneTwister (seed);
    unsafe
    {
        fixed (byte* idx8 = index)
        {
            uint* dst = (uint*)idx8;
            for (int n = index.Length / 4; n > 0; --n)
            {
                *dst++ ^= twister.Rand();
            }
        }
    }
    return index;
}
```

#### GetSeedFromString

```csharp
uint GetSeedFromString (string passphrase) {
    if (string.IsNullOrEmpty (passphrase))
        return 0;
    var buf = Encodings.cp932.GetBytes (passphrase);
    int seed = (sbyte)buf[0];
    for (int i = 1; i < buf.Length; ++i)
        seed *= (sbyte)buf[i];
    return (uint)seed;
}
```

#### DllImport

```csharp
[DllImport("Kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
[return: MarshalAs(UnmanagedType.Bool)]
public extern static bool GetVolumeInformation(
    string rootPathName, IntPtr volumeNameBuffer, int volumeNameSize,
    out uint volumeSerialNumber, IntPtr maximumComponentLength, IntPtr fileSystemFlags,
    IntPtr fileSystemNameBuffer, int nFileSystemNameSize) ;
```

## 配套算法与外部条件

- [ArcFormats/MersenneTwister.cs](../MersenneTwister.md)：本页引用的随包算法资料。
- [ArcFormats/Tanaka/ImageBC.cs](ImageBC.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Tanaka/ArcARCG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
