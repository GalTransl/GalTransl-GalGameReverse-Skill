# Nekopack / ArcNEKO3：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NEKOPACK/3` / `GameRes.Formats.Neko.Pak3Opener` | `dat` | `4e454b4f` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Pak3Opener.TryOpen` | `if (!file.View.AsciiEqual (4, "PACK") \|\| file.MaxOffset <= 0x410)` |
| `Pak3Opener.TryOpen` | `uint seed = file.View.ReadUInt32 (0xC);` |
| `Pak3Opener.TryOpen` | `var key = file.View.ReadBytes (0x10, 0x400);` |
| `Pak3Opener.TryOpen` | `seed = file.View.ReadUInt16 (0x410);` |
| `Pak3Opener.TryOpen` | `var index_info = file.View.ReadBytes (0x414, 8);` |
| `Pak3Opener.TryOpen` | `uint index_size = LittleEndian.ToUInt32 (index_info, 0);` |
| `Pak3Opener.TryOpen` | `var index = file.View.ReadBytes (0x41C, index_size);` |
| `Pak3Opener.TryOpen` | `int dir_count = input.ReadInt32();` |
| `Pak3Opener.TryOpen` | `int name_len = input.ReadUInt8();` |
| `Pak3Opener.TryOpen` | `string dir_name = input.ReadCString (name_len);` |
| `Pak3Opener.TryOpen` | `int file_count = input.ReadInt32();` |
| `Pak3Opener.TryOpen` | `input.ReadByte();` |
| `Pak3Opener.TryOpen` | `name_len = input.ReadUInt8();` |
| `Pak3Opener.TryOpen` | `string name = input.ReadCString (name_len);` |
| `Pak3Opener.TryOpen` | `entry.Offset = data_offset + input.ReadUInt32();` |
| `Pak3Opener.TryOpen` | `entry.Seed = file.View.ReadUInt16 (entry.Offset);` |
| `Pak3Opener.TryOpen` | `entry.Size = LittleEndian.ToUInt32 (buffer, 0);` |
| `Pak3Opener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `Pak3Opener.Decrypt` | `uint d = s ^ LittleEndian.ToUInt32 (key, seed);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Neko.Neko3Archive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### Neko3Archive

```csharp
public Neko3Archive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Neko.Neko3Entry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public ushort   Seed ;
```

### GameRes.Formats.Neko.Pak3Opener

继承/接口：`ArchiveFormat`。

#### Pak3Opener

```csharp
public Pak3Opener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "PACK") || file.MaxOffset <= 0x410)
        return null;

    uint seed = file.View.ReadUInt32 (0xC);
    int count = (int)(seed % 7u) + 3;
    var key = file.View.ReadBytes (0x10, 0x400);
    while (count --> 0)
    {
        Decrypt (key, 0x400, key, (ushort)seed, true);
    }
    seed = file.View.ReadUInt16 (0x410);
    var index_info = file.View.ReadBytes (0x414, 8);
    Decrypt (index_info, 8, key, (ushort)seed);
    uint index_size = LittleEndian.ToUInt32 (index_info, 0);
    long data_offset = 0x41CL + index_size;
    if (data_offset >= file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (0x41C, index_size);
    Decrypt (index, index.Length, key, (ushort)seed);

    var dir = new List<Entry>();
    using (var input = new BinMemoryStream (index, file.Name))
    {
        int dir_count = input.ReadInt32();
        if (!IsSaneCount (dir_count))
            return null;
        for (int d = 0; d < dir_count; ++d)
        {
            int name_len = input.ReadUInt8();
            string dir_name = input.ReadCString (name_len);
            if (string.IsNullOrEmpty (dir_name))
                return null;
            int file_count = input.ReadInt32();
            if (!IsSaneCount (file_count))
                return null;
            for (int i = 0; i < file_count; ++i)
            {
                input.ReadByte();
                name_len = input.ReadUInt8();
                string name = input.ReadCString (name_len);
                name = string.Join ("/", dir_name, name);
                var entry = Create<Neko3Entry> (name);
                entry.Offset = data_offset + input.ReadUInt32();
                dir.Add (entry);
            }
        }
    }
    var buffer = new byte[12];
    foreach (Neko3Entry entry in dir)
    {
        entry.Seed = file.View.ReadUInt16 (entry.Offset);
        file.View.Read (entry.Offset+4, buffer, 0, 8);
        Decrypt (buffer, 8, key, entry.Seed);
        entry.Size = LittleEndian.ToUInt32 (buffer, 0);
        entry.Offset += 12;
    }
    return new Neko3Archive (file, this, dir, key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var narc = (Neko3Archive)arc;
    var nent = (Neko3Entry)entry;
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    Decrypt (data, data.Length, narc.Key, nent.Seed);
    return new BinMemoryStream (data, entry.Name);
}
```

#### Decrypt

```csharp
void Decrypt (byte[] data, int length, byte[] key, ushort seed, bool init = false) {
    int count = length / 4;
    unsafe
    {
        fixed (byte* data8 = data)
        {
            uint* data32 = (uint*)data8;
            while (count --> 0)
            {
                uint s = *data32;
                seed = (ushort)((seed + 0xC3) & 0x1FF);
                uint d = s ^ LittleEndian.ToUInt32 (key, seed);
                if (init)
                    seed += (ushort)s;
                else
                    seed += (ushort)d;
                *data32++ = d;
            }
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Nekopack/ArcNEKO3.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
