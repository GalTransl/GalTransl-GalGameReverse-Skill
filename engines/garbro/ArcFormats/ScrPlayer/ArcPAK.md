# ScrPlayer / ArcPAK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/ScrPlayer` / `GameRes.Formats.ScrPlayer.PakOpener` | `pak` | `7061636b`, `70616332` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (4);` |
| `PakOpener.TryOpen` | `bool is_encrypted = file.View.ReadByte (3) == '2';` |
| `PakOpener.TestAlign` | `int first_offset = index.ReadInt32();` |
| `PakOpener.TestAlign` | `int size = index.ReadInt32();` |
| `PakOpener.TestAlign` | `int name_length = index.ReadUInt8();` |
| `PakOpener.TestAlign` | `return second_offset == index.ReadInt32();` |
| `PakOpener.ReadIndex` | `uint offset = index.ReadUInt32();` |
| `PakOpener.ReadIndex` | `uint size        = index.ReadUInt32();` |
| `PakOpener.ReadIndex` | `byte name_length = index.ReadUInt8();` |
| `PakOpener.ReadIndex` | `var name = index.ReadCString (name_length);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.ScrPlayer.PakOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly uint[] EncryptionKey = {
    0x305325A0, 0x306F308C, 0x672C5742, 0x5C0B5343,
    0x8457306E, 0x72694F5C, 0x30423067, 0x0000308B,
}
```

#### PakOpener

```csharp
public PakOpener () {
    Signatures = new uint[] { 0x6B636170, 0x32636170 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_size = file.View.ReadUInt32 (4);
    if (index_size < 0x10 || index_size >= file.MaxOffset)
        return null;
    IBinaryStream index;
    bool is_encrypted = file.View.ReadByte (3) == '2';
    if (is_encrypted)
    {
        var index_bytes = new byte[(index_size + 3) & ~3u];
        file.View.Read (8, index_bytes, 0, index_size);
        DecryptIndex (index_bytes, (int)index_size);
        index = new BinMemoryStream (index_bytes, 0, (int)index_size, file.Name);
    }
    else
        index = file.CreateStream (8, index_size);
    using (index)
    {
        int align = TestAlign (index, 8) ? 8 : 4;
        var dir = ReadIndex (index, file.MaxOffset, align);
        if (null == dir && 8 == align)
            dir = ReadIndex (index, file.MaxOffset, 4);
        if (null == dir || 0 == dir.Count)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

#### TestAlign

```csharp
bool TestAlign (IBinaryStream index, int align) {
    int first_offset = index.ReadInt32();
    int size = index.ReadInt32();
    int second_offset = (first_offset + size + 7) & -8;
    int name_length = index.ReadUInt8();
    index.Position = ((align + 1 + name_length) & -align) + 8;
    return second_offset == index.ReadInt32();
}
```

#### ReadIndex

```csharp
List<Entry> ReadIndex (IBinaryStream index, long max_offset, int align) {
    var index_length = index.Length;
    int index_pos = 0;
    var dir = new List<Entry>();
    while (index_pos < index_length)
    {
        index.Position = index_pos;
        uint offset = index.ReadUInt32();
        if (0 == offset)
            break;
        uint size        = index.ReadUInt32();
        byte name_length = index.ReadUInt8();
        var name = index.ReadCString (name_length);
        index_pos += ((align + 1 + name_length) & -align) + 8;

        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = offset;
        entry.Size   = size;
        if (!entry.CheckPlacement (max_offset))
            return null;
        dir.Add (entry);
    }
    return dir;
}
```

#### DecryptIndex

```csharp
unsafe void DecryptIndex (byte[] data, int length) {
    int aligned_count = ((length - 1) >> 2) + 1;
    if (aligned_count * 4 > length)
        throw new ArgumentException ("Can't decrypt non-aligned array.");
    fixed (byte* data8 = data)
    {
        uint* data32 = (uint*)data8;
        for (int i = 0; i < aligned_count; ++i)
            *data32++ ^= EncryptionKey[i & 7];
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/ScrPlayer/ArcPAK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
