# GameSystem / ArcCMP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CMP` / `GameRes.Formats.GameSystem.CmpOpener` | `cmp` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CmpOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (file.MaxOffset-8);` |
| `CmpOpener.TryOpen` | `uint pack_key = key.ToUInt32 (0);` |
| `CmpOpener.ReadIndex` | `uint index_offset = file.View.ReadUInt32 (file.MaxOffset-4);` |
| `CmpOpener.ReadIndex` | `int index_size = file.View.ReadInt32 (index_offset);` |
| `CmpOpener.ReadIndex` | `uint offset = LittleEndian.ToUInt32 (index, index_pos);` |
| `CmpOpener.ReadIndex` | `uint next_offset = LittleEndian.ToUInt32 (index, index_pos);` |
| `CmpOpener.LzUnpack` | `byte ctl = input.ReadUInt8();` |
| `CmpOpener.LzUnpack` | `int num = input.ReadUInt8() + (ctl << 8);` |
| `CmpOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.GameSystem.CmpOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static CmpScheme GameScheme = new CmpScheme { KnownKeys = new Dictionary<string, byte[]> () }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset <= 8)
        return null;
    List<Entry> dir = null;
    uint signature = file.View.ReadUInt32 (file.MaxOffset-8);
    if (0x4B434150 == signature)
    {
        dir = ReadIndex (file);
    }
    else
    {
        foreach (var key in KnownKeys.Values)
        {
            uint pack_key = key.ToUInt32 (0);
            if (0x4B434150 == (signature ^ pack_key))
            {
                dir = ReadIndex (file, key);
                break;
            }
        }
    }
    if (null == dir || 0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### ReadIndex

```csharp
List<Entry> ReadIndex (ArcView file, byte[] key = null) {
    bool is_encrypted = key != null;
    uint index_offset = file.View.ReadUInt32 (file.MaxOffset-4);
    if (index_offset >= file.MaxOffset)
        return null;
    int index_size = file.View.ReadInt32 (index_offset);
    if (index_size <= 0)
        return null;
    var index = new byte[index_size];
    Stream input = file.CreateStream (index_offset+4);
    if (is_encrypted)
        input = new ByteStringEncryptedStream (input, key);
    using (var packed = BinaryStream.FromStream (input, ""))
        LzUnpack (packed, index);
    var dir = new List<Entry>();
    int index_pos = 0;
    uint offset = LittleEndian.ToUInt32 (index, index_pos);
    while (index_pos < index.Length)
    {
        index_pos += 4;
        int name_length = index[index_pos];
        if (0 == name_length)
            break;
        bool is_packed = index[index_pos+1] != 0;
        index_pos += 6;
        name_length *= 2;
        var name = Encoding.Unicode.GetString (index, index_pos, name_length);
        index_pos += name_length;
        uint next_offset = LittleEndian.ToUInt32 (index, index_pos);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset = offset;
        entry.Size = next_offset - offset;
        entry.IsPacked = is_packed;
        if (!entry.CheckPlacement (index_offset))
            return null;
        dir.Add (entry);
        offset = next_offset;
    }
    return dir;
}
```

#### LzUnpack

```csharp
void LzUnpack (IBinaryStream input, byte[] output) {
    int dst = 0;
    while (dst < output.Length)
    {
        byte ctl = input.ReadUInt8();
        if (0 != (ctl & 0x80))
        {
            int num = input.ReadUInt8() + (ctl << 8);
            int offset = num & 0x7FF;
            int count = Math.Min (((num >> 10) & 0x1E) + 2, output.Length - dst);
            Binary.CopyOverlapped (output, dst-offset-1, dst, count);
            dst += count;
        }
        else
        {
            int count = Math.Min (ctl + 1, output.Length - dst);
            input.Read (output, dst, count);
            dst += count;
        }
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return base.OpenEntry (arc, entry);
    if (0 == pent.UnpackedSize)
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset);
    var data = new byte[pent.UnpackedSize];
    using (var input = arc.File.CreateStream (entry.Offset+4, entry.Size-4))
        LzUnpack (input, data);
    return new BinMemoryStream (data, entry.Name);
}
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/GameSystem/ArcCMP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
