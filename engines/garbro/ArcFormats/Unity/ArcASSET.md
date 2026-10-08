# Unity / ArcASSET：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ASSETS/UNITY` / `GameRes.Formats.Unity.UnityAssetOpener` | `assets` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `UnityAssetOpener.TryOpen` | `uint header_size = Binary.BigEndian (file.View.ReadUInt32 (0));` |
| `UnityAssetOpener.TryOpen` | `long file_size = Binary.BigEndian (file.View.ReadUInt32 (4));` |
| `UnityAssetOpener.TryOpen` | `int format = Binary.BigEndian (file.View.ReadInt32 (8));` |
| `UnityAssetOpener.TryOpen` | `long data_offset = Binary.BigEndian (file.View.ReadUInt32 (12));` |
| `UnityAssetOpener.TryOpen` | `header_size = Binary.BigEndian (file.View.ReadUInt32 (0x14));` |
| `UnityAssetOpener.TryOpen` | `file_size = Binary.BigEndian (file.View.ReadInt64 (0x18));` |
| `UnityAssetOpener.TryOpen` | `data_offset = Binary.BigEndian (file.View.ReadInt64 (0x20));` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Unity.UnityAssetOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint header_size = Binary.BigEndian (file.View.ReadUInt32 (0));
    long file_size = Binary.BigEndian (file.View.ReadUInt32 (4));
    int format = Binary.BigEndian (file.View.ReadInt32 (8));
    if (format <= 0 || format > 0x100)
        return null;
    long data_offset = Binary.BigEndian (file.View.ReadUInt32 (12));
    if (format >= 22)
    {
        header_size = Binary.BigEndian (file.View.ReadUInt32 (0x14));
        file_size = Binary.BigEndian (file.View.ReadInt64 (0x18));
        data_offset = Binary.BigEndian (file.View.ReadInt64 (0x20));
    }
    if (file_size != file.MaxOffset || header_size > file_size || 0 == header_size
        || data_offset >= file_size || data_offset < header_size)
        return null;
    using (var stream = file.CreateStream())
    using (var input = new AssetReader (stream))
    {
        var index = new ResourcesAssetsDeserializer (file.Name);
        var dir = index.Parse (input);
        if (null == dir || 0 == dir.Count)
            return null;
        var res_map = index.GenerateResourceMap (dir);
        return new UnityResourcesAsset (file, this, dir, res_map);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var uarc = (UnityResourcesAsset)arc;
    var uent = (AssetEntry)entry;
    if (null == uent.Bundle || !uarc.ResourceMap.ContainsKey (uent.Bundle.Name))
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var bundle = uarc.ResourceMap[uent.Bundle.Name];
    return bundle.CreateStream (entry.Offset, entry.Size);
}
```

### GameRes.Formats.Unity.UnityResourcesAsset

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly IDictionary<string, ArcView> ResourceMap ;

bool m_disposed = false ;
```

#### UnityResourcesAsset

```csharp
public UnityResourcesAsset (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, IDictionary<string, ArcView> res_map)
    : base (arc, impl, dir) {
    ResourceMap = res_map;
}
```

## 配套算法与外部条件

- [ArcFormats/Unity/AssetReader.cs](AssetReader.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/ResourcesAssets.cs](ResourcesAssets.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Unity/ArcASSET.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
