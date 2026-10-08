# Valkyria / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/VALKYRIA` / `GameRes.Formats.Valkyria.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (0);` |
| `DatOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x104);` |
| `DatOpener.TryOpen` | `entry.Offset = base_offset + file.View.ReadUInt32 (index_offset);` |
| `DatOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+4);` |
| `DatOpener.TryOpenV1` | `var index_encrypted = file.View.ReadUInt32 (0) == 1;` |
| `DatOpener.TryOpenV1` | `var index_size = file.View.ReadUInt32 (4);` |
| `DatOpener.TryOpenV1` | `var index = file.View.ReadBytes (8, index_size);` |
| `DatOpener.TryOpenV1` | `entry.Offset = LittleEndian.ToUInt32 (buffer, 0);` |
| `DatOpener.TryOpenV1` | `entry.Size = LittleEndian.ToUInt32 (buffer, 4);` |
| `DatOpener.GetEntryKey` | `return BitConverter.ToUInt32 (key, 0);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Valkyria.DatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_size = file.View.ReadUInt32 (0);
    if (0 == index_size || 1 == index_size)
        return TryOpenV1 (file);
    if (index_size >= file.MaxOffset)
        return null;
    int count = (int)index_size / 0x10C;
    if (index_size != (uint)count * 0x10Cu || !IsSaneCount (count))
        return null;
    uint index_offset = 4;
    long base_offset = index_offset + index_size;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x104);
        index_offset += 0x104;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = base_offset + file.View.ReadUInt32 (index_offset);
        entry.Size   = file.View.ReadUInt32 (index_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        index_offset += 8;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### TryOpenV1

```csharp
private ArcFile TryOpenV1 (ArcView file) {
    var index_encrypted = file.View.ReadUInt32 (0) == 1;
    var index_size = file.View.ReadUInt32 (4);
    if (0 == index_size || index_size >= file.MaxOffset)
        return null;
    int count = (int)index_size / 0x10C;
    if (index_size != (uint)count * 0x10Cu || !IsSaneCount (count))
        return null;
    var dir_path = Path.GetDirectoryName (file.Name);
    if (null == dir_path)
        return null;
    var arc_key = ReadArcKey (dir_path);
    if (null == arc_key)
        return null;
    uint index_offset = 0;
    long base_offset = 8 + index_size;
    var index = file.View.ReadBytes (8, index_size);
    if (index_encrypted)
    {
        var scheme = new EncryptionScheme
        {
            OddKey1 = 0x627e907b,
            OddKey2 = 7,
            EvenKey1 = 0xe1da85e3,
            EvenKey2 = 3
        };
        DecryptIndex (index, scheme, (uint)index.Length);
    }
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name_buffer = new byte[0x104];
        Buffer.BlockCopy (index, (int)index_offset, name_buffer, 0, 0x104);
        var name = Binary.GetCString (name_buffer, 0);
        index_offset += 0x104;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        var buffer = new byte[8];
        Buffer.BlockCopy (index, (int)index_offset, buffer, 0, 8);
        entry.Offset = LittleEndian.ToUInt32 (buffer, 0);
        entry.Size = LittleEndian.ToUInt32 (buffer, 4);
        if (!index_encrypted)
        {
            var key = GetEntryKey (arc_key, name_buffer);
            entry.Offset ^= key;
            entry.Size ^= key;
        }
        entry.Offset += base_offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        index_offset += 8;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### ReadArcKey

```csharp
private static byte[] ReadArcKey (string dir_path) {
    var file_path = Path.Combine (dir_path, "system.dat");
    if (!File.Exists (file_path))
        return null;
    var info = new byte[260];
    using (var fs = File.OpenRead (file_path))
    {
        fs.Position = 0x10E;
        fs.Read (info, 0, 260);
        fs.Close ();
    }
    var key = new byte[4];
    var len = info.TakeWhile (x => x != 0).Count ();
    for (int i = len, j = 0; i != 0; i--)
    {
        key[j] += info[i];
        if (++j == 4)
            j = 0;
    }
    return key;
}
```

#### GetEntryKey

```csharp
private static uint GetEntryKey (byte[] arc_key, byte[] name) {
    var key = new byte[4];
    var len = name.TakeWhile (x => x != 0).Count ();
    for (int i = len, j = 0; i != 0; i--)
    {
        key[j] += name[i];
        if (++j == 4)
            j = 0;
    }
    key[0] += arc_key[3];
    key[1] += arc_key[2];
    key[2] += arc_key[1];
    key[3] += arc_key[0];
    return BitConverter.ToUInt32 (key, 0);
}
```

#### DecryptIndex

```csharp
public static void DecryptIndex (byte[] index, EncryptionScheme scheme, uint length) {
    var branch = false;
    for (int i = 0; i <= index.Length - 4; i++)
    {
        unsafe
        {
            fixed (byte* index_ptr = index)
            {
                uint* ptr = (uint*)(index_ptr + i);
                var key1 = branch ? scheme.OddKey1 : scheme.EvenKey1;
                var key2 = branch ? scheme.OddKey2 : scheme.EvenKey2;
                *ptr = Binary.RotR (*ptr - key1, key2) ^ length;
                branch = !branch;
            }
        }
    }
}
```

### GameRes.Formats.Valkyria.EncryptionScheme

#### 状态与常量

```csharp
public uint OddKey1 ;

public int  OddKey2 ;

public uint EvenKey1 ;

public int  EvenKey2 ;
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Valkyria/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
