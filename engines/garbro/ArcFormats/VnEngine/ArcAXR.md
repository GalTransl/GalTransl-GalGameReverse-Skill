# VnEngine / ArcAXR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AXR` / `GameRes.Formats.VnEngine.AxrOpener` | `axr` | `41585265` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AxrOpener.TryOpen` | `var header = file.View.ReadBytes (0, 0x10);` |
| `AxrOpener.TryOpen` | `uint t = MutateKey (MutateKey (LittleEndian.ToUInt32 (header, 8) ^ LittleEndian.ToUInt32 (header, 0)));` |
| `AxrOpener.TryOpen` | `uint key = LittleEndian.ToUInt32 (header, 4);` |
| `AxrOpener.TryOpen` | `uint stored_checksum = LittleEndian.ToUInt32 (header, 12) ^ MutateKey (t);` |
| `AxrOpener.TryOpen` | `uint offset = LittleEndian.ToUInt32 (index, current_offset);` |
| `AxrOpener.TryOpen` | `uint size   = LittleEndian.ToUInt32 (index, current_offset+4);` |
| `AxrEncryptedStream.ReadByte` | `public override int ReadByte () {` |
| `AxrEncryptedStream.ReadByte` | `int b = BaseStream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.VnEngine.AxrArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[]  KeyTable = new byte[0x400] ;
```

#### AxrArchive

```csharp
public AxrArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, uint key)
    : base (arc, impl, dir) {
    AxrOpener.Decrypt (KeyTable, key, 0x400);
}
```

### GameRes.Formats.VnEngine.AxrOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var header = file.View.ReadBytes (0, 0x10);
    byte checksum = header[4];
    for (int i = 1; i < 8; ++i)
    {
        checksum ^= Binary.RotByteR (header[4+i], i);
    }
    uint t = MutateKey (MutateKey (LittleEndian.ToUInt32 (header, 8) ^ LittleEndian.ToUInt32 (header, 0)));
    uint key = LittleEndian.ToUInt32 (header, 4);
    uint index_size = t ^ key;
    uint stored_checksum = LittleEndian.ToUInt32 (header, 12) ^ MutateKey (t);
    if (index_size < 8 || checksum != stored_checksum)
        return null;
    var index = new byte[(index_size + 4) & ~3u];
    if (index_size != file.View.Read (0x10, index, 0, index_size))
        return null;
    Decrypt (index, index_size, index.Length);
    index[index_size] = 0;
    var dir = new List<Entry>();
    int current_offset = 0;
    while (current_offset+8 < (int)index_size)
    {
        uint offset = LittleEndian.ToUInt32 (index, current_offset);
        uint size   = LittleEndian.ToUInt32 (index, current_offset+4);
        current_offset += 8;
        int name_end = Array.IndexOf<byte> (index, 0, current_offset);
        int name_length = name_end - current_offset;
        if (0 == name_length)
            break;
        var name = Encodings.cp932.GetString (index, current_offset, name_length);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = offset;
        entry.Size   = size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        current_offset += (name_length + 4) & -4;
    }
    if (0 == dir.Count)
        return null;
    return new AxrArchive (file, this, dir, key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var axr = arc as AxrArchive;
    if (null == axr)
        return input;
    return new AxrEncryptedStream (input, axr.KeyTable);
}
```

#### MutateKey

```csharp
static uint MutateKey (uint key) {
    key ^= (key & 0xFFF) << 17;
    return ~(key ^ (key << 18 | key >> 15));
}
```

#### Decrypt

```csharp
internal static void Decrypt (byte[] data, uint key, int count) {
    if (count > data.Length)
        throw new ArgumentException ("count");
    count /= 4;
    if (0 == count)
        return;
    unsafe
    {
        fixed (byte* data8 = data)
        {
            uint* data32 = (uint*)data8;
            for (int i = 0; i < count; ++i)
            {
                key = MutateKey (key);
                uint v = *data32 ^ key;
                *data32++ = v;
                key += v;
            }
        }
    }
}
```

### GameRes.Formats.VnEngine.AxrEncryptedStream

继承/接口：`InputProxyStream`。

#### 状态与常量

```csharp
byte[]  m_key ;
```

#### AxrEncryptedStream

```csharp
public AxrEncryptedStream (Stream input, byte[] key, bool leave_open = false)
    : base (input, leave_open) {
    m_key = key;
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int start = (int)Position;
    int read = BaseStream.Read (buffer, offset, count);
    for (int i = 0; i < read; ++i)
    {
        buffer[offset+i] ^= m_key[start++ & 0x3FF];
    }
    return read;
}
```

#### ReadByte

```csharp
public override int ReadByte () {
    int start = (int)Position & 0x3FF;
    int b = BaseStream.ReadByte();
    if (-1 != b)
        b ^= m_key[start];
    return b;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/VnEngine/ArcAXR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
