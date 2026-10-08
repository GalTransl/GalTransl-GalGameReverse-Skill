# Morning / ArcPAK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/MORNING` / `GameRes.Formats.Morning.PakOpener` | `pak` | `8b8f6658` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `uint block_count = file.View.ReadUInt32 (4);` |
| `PakOpener.TryOpen` | `var index = file.View.ReadBytes (8, block_count * 0x200u);` |
| `PakOpener.TryOpen` | `int count = index.ToInt32 (block_offset);` |
| `PakOpener.TryOpen` | `int name_offset = index.ToInt32 (current_entry);` |
| `PakOpener.TryOpen` | `entry.Offset = index.ToUInt32 (current_entry+4);` |
| `PakOpener.TryOpen` | `entry.Size   = index.ToUInt32 (current_entry+8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Morning.PakOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] PngIHdr   = { 0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52 }

MorningScheme DefaultScheme = new MorningScheme() ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint block_count = file.View.ReadUInt32 (4);
    var key = QueryKey (file.Name);
    if (null == key)
        return null;
    var index = file.View.ReadBytes (8, block_count * 0x200u);
    DecryptIndex (index, key);

    var dir = new List<Entry>();
    int block_offset = 0;
    for (uint i = 0; i < block_count; ++i)
    {
        int count = index.ToInt32 (block_offset);
        if (!IsSaneCount (count))
            return null;
        int current_entry = block_offset + 4;
        for (int j = 0; j < count; ++j)
        {
            int name_offset = index.ToInt32 (current_entry);
            var name = Binary.GetCString (index, block_offset + name_offset);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = index.ToUInt32 (current_entry+4);
            entry.Size   = index.ToUInt32 (current_entry+8);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            current_entry += 12;
        }
        block_offset += 0x200;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Size <= 8 || !arc.File.View.BytesEqual (entry.Offset, PngIHdr))
        return base.OpenEntry (arc, entry);
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new PrefixStream (PngFormat.HeaderBytes, input);
}
```

#### DecryptIndex

```csharp
void DecryptIndex (byte[] data, byte[] key) {
    int index_mask = key.Length-1;
    Debug.Assert ((key.Length & index_mask) == 0);
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] ^= key[i & index_mask];
    }
}
```

#### QueryKey

```csharp
byte[] QueryKey (string arc_name) {
    return DefaultScheme.DefaultKey;
}
```

### GameRes.Formats.Morning.MorningScheme

继承/接口：`ResourceScheme`。

#### 状态与常量

```csharp
public byte[] DefaultKey ;
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Morning/ArcPAK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
