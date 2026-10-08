# Sophia / ArcNOR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NOR` / `GameRes.Formats.Sophia.NorOpener` | `nor` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `NorOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `NorOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "NRCOMB01\0") \|\| !IsSaneCount (count))` |
| `NorOpener.TryOpen` | `uint offset = index.ReadUInt32();` |
| `NorOpener.TryOpen` | `uint size   = index.ReadUInt32();` |
| `NorOpener.TryOpen` | `string name = index.ReadCString();` |
| `NorOpener.OpenEntry` | `\|\| !arc.File.View.AsciiEqual (nent.Offset, "NCMB01"))` |
| `NorOpener.OpenEntry` | `nent.Method = arc.File.View.ReadInt32 (nent.Offset+0x28);` |
| `NorOpener.OpenEntry` | `nent.Size = arc.File.View.ReadUInt32 (nent.Offset+0x24);` |
| `NorOpener.OpenEntry` | `nent.UnpackedSize = arc.File.View.ReadUInt32 (nent.Offset+0x24);` |
| `NorOpener.OpenEntry` | `nent.Size = arc.File.View.ReadUInt32 (nent.Offset+0x10);` |
| `NorOpener.NcmbDecompress` | `int root = input.ReadInt32();` |
| `NorOpener.NcmbDecompress` | `int tree_size = input.ReadInt32();` |
| `NorOpener.NcmbDecompress` | `int unpacked_size = input.ReadInt32();` |
| `NorOpener.NcmbDecompress` | `int token = 6 * input.ReadInt32();` |
| `NorOpener.NcmbDecompress` | `dict[token    ] = input.ReadInt32();` |
| `NorOpener.NcmbDecompress` | `dict[token + 1] = input.ReadInt32();` |
| `NorOpener.NcmbDecompress` | `cur_byte = input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Sophia.NorEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public int  Method ;
```

### GameRes.Formats.Sophia.NorOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!file.View.AsciiEqual (4, "NRCOMB01\0") || !IsSaneCount (count))
        return null;
    var dir = new List<Entry> (count);
    using (var index = file.CreateStream())
    {
        index.Position = 0x10;
        for (int i = 0; i < count; ++i)
        {
            uint offset = index.ReadUInt32();
            uint size   = index.ReadUInt32();
            string name = index.ReadCString();
            var entry = Create<NorEntry> (name);
            entry.Offset = offset;
            entry.Size = size;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var nent = (NorEntry)entry;
    if (!nent.IsPacked)
    {
        if (nent.Method == 0x1F4 || nent.Method == 0x67
            || !arc.File.View.AsciiEqual (nent.Offset, "NCMB01"))
            return base.OpenEntry (arc, nent);
        nent.Method = arc.File.View.ReadInt32 (nent.Offset+0x28);
        if (nent.Method == 0x1F4 || nent.Method == 0x67)
        {
            nent.Size = arc.File.View.ReadUInt32 (nent.Offset+0x24);
            nent.Offset += 0x2C;
            return base.OpenEntry (arc, nent);
        }
        nent.IsPacked = true;
        nent.UnpackedSize = arc.File.View.ReadUInt32 (nent.Offset+0x24);
        nent.Size = arc.File.View.ReadUInt32 (nent.Offset+0x10);
        nent.Offset += 0x2C;
    }
    using (var input = arc.File.CreateStream (nent.Offset, nent.Size))
    {
        var output = new byte[nent.UnpackedSize];
        NcmbDecompress (input, output);
        return new BinMemoryStream (output, nent.Name);
    }
}
```

#### NcmbDecompress

```csharp
internal static void NcmbDecompress (IBinaryStream input, byte[] output) {
    var dict = new int[0xC00];
    int root = input.ReadInt32();
    int tree_size = input.ReadInt32();
    int unpacked_size = input.ReadInt32();
    int count = root + tree_size - 0xFF;
    while (count --> 0)
    {
        int token = 6 * input.ReadInt32();
        dict[token    ] = input.ReadInt32();
        dict[token + 1] = input.ReadInt32();
    }
    if (unpacked_size > 0)
    {
        int cur_byte = 0;
        int mask = 0;
        for (int dst = 0; dst < unpacked_size; ++dst)
        {
            int token = root;
            do
            {
                if (0 == mask)
                {
                    cur_byte = input.ReadUInt8();
                    mask = 0x80;
                }
                if ((cur_byte & mask) != 0)
                    token = dict[6 * token + 1];
                else
                    token = dict[6 * token];
                mask >>= 1;
            }
            while (dict[6 * token] != -1);
            output[dst] = (byte)token;
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Sophia/ArcNOR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
