# Kaas / ArcKAAS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PD/KAAS` / `GameRes.Formats.KAAS.PdOpener` | `pd` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PdOpener.TryOpen` | `int index_offset = file.View.ReadByte (0);` |
| `PdOpener.TryOpen` | `byte key = file.View.ReadByte (1);` |
| `PdOpener.TryOpen` | `int count = 0xfff & file.View.ReadUInt16 (index_offset);` |
| `PdOpener.ReadIndex` | `uint offset = LittleEndian.ToUInt32 (index, index_offset);` |
| `PdOpener.ReadIndex` | `uint size   = LittleEndian.ToUInt32 (index, index_offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.KAAS.PdImageEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int  Number ;
```

### GameRes.Formats.KAAS.PdOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly IEnumerable<IIndexDecryptor> KnownDecryptors = new IIndexDecryptor[] {
    new DiscoveryDecryptor(),
    new OldDecryptor(),
}

static readonly Lazy<ImageFormat> s_picFormat = new Lazy<ImageFormat> (() => ImageFormat.FindByTag ("PIC/KAAS")) ;
```

#### PdOpener

```csharp
public PdOpener () {
    Extensions = new string[] { "pd" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int index_offset = file.View.ReadByte (0);
    if (index_offset <= 2 || index_offset >= file.MaxOffset)
        return null;
    byte key = file.View.ReadByte (1);
    int count = 0xfff & file.View.ReadUInt16 (index_offset);
    if (0 == count)
        return null;
    index_offset += 16;
    var index = new byte[count*8];
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry> (count);
    int data_offset = index_offset + index.Length;

    foreach (var decryptor in KnownDecryptors)
    {
        if (index.Length != file.View.Read (index_offset, index, 0, (uint)(index.Length)))
            return null;
        decryptor.Decrypt (index, key);
        try
        {
            if (ReadIndex (index, dir, base_name, data_offset, file.MaxOffset)
                && dir.Count > 0)
                return new ArcFile (file, this, dir);
        }
        catch {  }
        dir.Clear();
    }
    return null;
}
```

#### ReadIndex

```csharp
bool ReadIndex (byte[] index, List<Entry> dir, string base_name, long data_offset, long max_offset) {
    int index_offset = 0;
    int count = index.Length / 8;
    for (int i = 0; i < count; ++i)
    {
        uint offset = LittleEndian.ToUInt32 (index, index_offset);
        uint size   = LittleEndian.ToUInt32 (index, index_offset+4);
        if (offset < data_offset || offset >= max_offset)
            return false;
        if (size > 0)
        {
            var entry = new PdImageEntry {
                Name = string.Format ("{0}#{1:D4}", base_name, i),
                Type = "image",
                Offset = offset,
                Size = size,
                Number = dir.Count
            };
            if (!entry.CheckPlacement (max_offset))
                return false;
            dir.Add (entry);
        }
        index_offset += 8;
    }
    return true;
}
```

### GameRes.Formats.KAAS.OldDecryptor

继承/接口：`IIndexDecryptor`。

#### Decrypt

```csharp
public void Decrypt (byte[] data, byte key) {
    for (int i = 0; i != data.Length; ++i)
    {
        int k = i + 14;
        int r = 9 - (k & 7) * (k + 5) * key * 0x77;
        data[i] -= (byte)r;
    }
}
```

### GameRes.Formats.KAAS.DiscoveryDecryptor

继承/接口：`IIndexDecryptor`。

#### Decrypt

```csharp
public void Decrypt (byte[] data, byte key) {
    for (int i = 0; i != data.Length; ++i)
    {
        int k = i + 14;
        int r = ((k * 0x6b) % (k / 2 + 1)) + key * 0x3b * (k + 11) * (k % (k + 17));
        data[i] -= (byte)r;
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Kaas/ArcKAAS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
