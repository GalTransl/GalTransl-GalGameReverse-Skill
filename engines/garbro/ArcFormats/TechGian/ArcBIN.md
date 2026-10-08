# TechGian / ArcBIN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BIN/RFIL` / `GameRes.Formats.TechGian.BinOpener` | `bin` | `5246494c` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BinOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `BinOpener.TryOpen` | `bool is_encrypted = file.View.ReadInt32 (12) == 1234;` |
| `BinOpener.TryOpen` | `entry.Offset = buffer.ToUInt32 (0x34);` |
| `BinOpener.TryOpen` | `entry.Size = buffer.ToUInt32 (0x38);` |
| `BinOpener.TryOpen` | `entry.EncryptionMethod = buffer.ToInt32 (0x3C);` |
| `BinOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (rent.Offset, rent.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.TechGian.RfilEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int  EncryptionMethod ;

public bool IsEncrypted {
    get { return EncryptionMethod == 1 || EncryptionMethod == 2 || EncryptionMethod == 4; }
}
```

### GameRes.Formats.TechGian.BinOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    bool is_encrypted = file.View.ReadInt32 (12) == 1234;
    long index_pos = 0x10;
    var buffer = new byte[0x40];
    var rnd = new CRuntimeRandomGenerator();
    rnd.SRand (0);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        file.View.Read (index_pos, buffer, 0, 0x40);
        if (is_encrypted)
            DecryptRand (buffer, 0, 0x40, rnd);
        var name = Binary.GetCString (buffer, 0, 0x30);
        var entry = Create<RfilEntry> (name);
        entry.Offset = buffer.ToUInt32 (0x34);
        entry.Size = buffer.ToUInt32 (0x38);
        entry.EncryptionMethod = buffer.ToInt32 (0x3C);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_pos += 0x40;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var rent = (RfilEntry)entry;
    if (!rent.IsEncrypted)
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (rent.Offset, rent.Size);
    switch (rent.EncryptionMethod)
    {
    case 1:
        DecryptData (data, 0, data.Length);
        break;
    case 2:
        if (data.Length > 0)
            DecryptData (data, 0, (data.Length - 1) / 100 + 1);
        break;
    case 4:
        DecryptData (data, 0, Math.Min (1024, data.Length));
        break;
    }
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptData

```csharp
internal static void DecryptData (byte[] data, int pos, int length) {
    while (length --> 0)
    {
        data[pos++] ^= 0x7F;
    }
}
```

#### DecryptRand

```csharp
internal static void DecryptRand (byte[] data, int pos, int length, IRandomGenerator rnd) {
    while (length --> 0)
    {
        data[pos++] ^= (byte)rnd.Rand();
    }
}
```

## 配套算法与外部条件

- [ArcFormats/Eagls/ArcEAGLS.cs](../Eagls/ArcEAGLS.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/TechGian/ArcBIN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
