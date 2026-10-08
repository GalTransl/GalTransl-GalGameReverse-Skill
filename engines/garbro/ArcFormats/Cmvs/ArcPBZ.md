# Cmvs / ArcPBZ：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PBZ` / `GameRes.Formats.Pvns.PbzOpener` | `pbz` | `50425a31` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PbzOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `PbzOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (8);` |
| `PbzOpener.TryOpen` | `var index = file.View.ReadBytes (0x10, index_size);` |
| `PbzOpener.TryOpen` | `int entry_size = LittleEndian.ToInt32 (index, index_pos);` |
| `PbzOpener.TryOpen` | `entry.Size   = LittleEndian.ToUInt32 (index, index_pos+4);` |
| `PbzOpener.TryOpen` | `entry.Offset = base_offset + LittleEndian.ToUInt32 (index, index_pos+8);` |
| `PbzOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `PbzOpener.OpenEntry` | `&& Binary.AsciiEqual (data, "PSRA") && data.Length > 20)` |
| `PbzOpener.DecryptScript` | `uint checksum = LittleEndian.ToUInt32 (data, 4);` |
| `PbzOpener.DecryptScript` | `int unpacked_size = LittleEndian.ToInt32 (data, 0x10);` |
| `PbzOpener.DecryptScript` | `src = 0x14 + LittleEndian.ToInt32 (data, 8);` |
| `PbzOpener.DecryptScript` | `int u = LittleEndian.ToUInt16 (data, src);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Pvns.PbzArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] ArcKey ;

public readonly byte[] ScriptKey ;
```

#### PbzArchive

```csharp
public PbzArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, PbzKeys scheme)
    : base (arc, impl, dir) {
    ArcKey = scheme.ArcKey;
    ScriptKey = scheme.ScriptKey;
}
```

### GameRes.Formats.Pvns.PbzKeys

#### 状态与常量

```csharp
public byte[]   ArcKey ;

public byte[]   ScriptKey ;
```

### GameRes.Formats.Pvns.PbzOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (0 == KnownSchemes.Count)
        return null;
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;
    uint index_size = file.View.ReadUInt32 (8);
    var index = file.View.ReadBytes (0x10, index_size);
    if (index.Length != index_size)
        return null;

    var scheme = KnownSchemes.Values.First();
    Decrypt (index, scheme.ArcKey);

    long base_offset = 0x10 + index_size;
    int index_pos = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int entry_size = LittleEndian.ToInt32 (index, index_pos);
        if (entry_size <= 0x18)
            return null;
        var name = Binary.GetCString (index, index_pos+0x18, entry_size - 0x18);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Size   = LittleEndian.ToUInt32 (index, index_pos+4);
        entry.Offset = base_offset + LittleEndian.ToUInt32 (index, index_pos+8);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_pos += entry_size;
    }
    return new PbzArchive (file, this, dir, scheme);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var parc = arc as PbzArchive;
    if (null == parc)
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    Decrypt (data, parc.ArcKey);
    if (entry.Name.HasExtension (".scr")
        && Binary.AsciiEqual (data, "PSRA") && data.Length > 20)
    {
        data = DecryptScript (data, parc.ScriptKey);
    }
    return new BinMemoryStream (data, entry.Name);
}
```

#### Decrypt

```csharp
static void Decrypt (byte[] data, byte[] key) {
    if (0 == key.Length)
        return;
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] = (byte)((data[i] ^ key[i % key.Length]) + 0x80);
    }
}
```

#### DecryptScript

```csharp
byte[] DecryptScript (byte[] data, byte[] key) {
    int input_size = data.Length - 0x14;
    for (int i = 4; i < 0x14; ++i)
    {
        data[i] = (byte)((data[i] ^ 0xF5) - 0x10);
    }
    if (0 != (input_size & -4))
    {
        unsafe
        {
            fixed (byte* data8 = &data[0x14])
            {
                uint m = 0x817543;
                uint* data32 = (uint*)data8;
                for (int length = (((input_size & -4) - 1) >> 2) + 1; length > 0; --length)
                {
                    *data32 ^= m;
                    m += 0x1352467u;
                    ++data32;
                }
            }
        }
    }
    uint checksum = LittleEndian.ToUInt32 (data, 4);
    for (int i = 0x14; i < data.Length; ++i)
    {
        checksum -= data[i];
    }
    if (checksum != 0)
        throw new InvalidEncryptionScheme();

    for (int i = 0x14; i < data.Length; ++i)
    {
        data[i] = Binary.RotByteR (data[i], 3);
    }
    int src = 0x14;
    for (int count = ((input_size - 2) >> 1) + 1; count > 0; --count)
    {
        byte t = data[src];
        data[src] = data[src+1];
        data[src+1] = t;
        src += 2;
    }
    int k = 0;
    for (int i = 0x14; i < data.Length; ++i)
    {
        data[i] = (byte)((data[i] ^ key[k++]) + 0x35);
        k %= key.Length;
    }
    int unpacked_size = LittleEndian.ToInt32 (data, 0x10);
    var output = new byte[unpacked_size];
    src = 0x14 + LittleEndian.ToInt32 (data, 8);
    int dst = 0;
    int bit_mask = 0x80;
    int bits = 0x14;
    while (dst < output.Length)
    {
        if (0 == bit_mask)
        {
            bit_mask = 0x80;
            ++bits;
        }
        if (0 != (bit_mask & data[bits]))
        {
            int u = LittleEndian.ToUInt16 (data, src);
            src += 2;
            int offset = (u >> 5) + 1;
            int count = (u & 0x1F) + 3;
            Binary.CopyOverlapped (output, dst - offset, dst, count);
            dst += count;
        }
        else
        {
            output[dst++] = data[src++];
        }
        bit_mask >>= 1;
    }
    for (int i = 0; i < output.Length; ++i)
    {
        output[i] ^= 0x7E;
    }
    return output;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Cmvs/ArcPBZ.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
