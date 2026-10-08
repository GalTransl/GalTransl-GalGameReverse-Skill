# Unity / ResourcesAssets：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ResourcesAssetsDeserializer.Parse` | `var name = input.ReadString();` |
| `ResourcesAssetsDeserializer.Parse` | `uint size = input.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Unity.ResourcesAssetsDeserializer

#### 状态与常量

```csharp
string                          m_res_name ;

Dictionary<string, BundleEntry> m_bundles ;
```

#### ResourcesAssetsDeserializer

```csharp
public ResourcesAssetsDeserializer (string arc_name) {
    m_res_name = arc_name;
}
```

#### Parse

```csharp
public List<Entry> Parse (AssetReader input, long base_offset = 0) {
    var asset = new Asset();
    asset.Load (input);
    var dir = new List<Entry>();
    m_bundles = new Dictionary<string, BundleEntry>();
    var used_names = new HashSet<string>();

    foreach (var obj in asset.Objects.Where (o => o.TypeId > 0))
    {
        input.Position = obj.Offset + base_offset;
        AssetEntry entry = null;
        int id = obj.TypeId > 0 ? obj.TypeId : obj.ClassId;
        switch (id)
        {
        case 48:
        case 114:
        default:
            break;

        case 28:
            {
                var tex = new Texture2D();
                tex.Load (input, asset.Tree);
                if (0 == tex.m_DataLength)
                {
                    var stream_data = new StreamingInfo();
                    stream_data.Load (input);
                    if (!string.IsNullOrEmpty (stream_data.Path))
                    {
                        entry = new AssetEntry {
                            Name = tex.m_Name,
                            Type = "image",
                            Offset = stream_data.Offset,
                            Size = stream_data.Size,
                            Bundle = GetBundle (stream_data.Path),
                        };
                    }
                }
                else
                {
                    entry = new AssetEntry {
                        Name = tex.m_Name,
                        Type = "image",
                        Offset = obj.Offset,
                        Size = obj.Size,
                    };
                }
                break;
            }
        case 83:
            {
                var clip = new AudioClip();
                clip.Load (input);
                if (!string.IsNullOrEmpty (clip.m_Source))
                {
                    entry = new AssetEntry {
                        Name = clip.m_Name,
                        Type = "audio",
                        Offset = clip.m_Offset,
                        Size = (uint)clip.m_Size,
                        Bundle = GetBundle (clip.m_Source),
                    };
                }
                else if (clip.m_Size != 0)
                {
                    entry = new AssetEntry {
                        Name = clip.m_Name,
                        Type = "audio",
                        Offset = input.Position,
                        Size = (uint)clip.m_Size,
                    };
                }
                break;
            }
        case 49:
            {
                var name = input.ReadString();
                input.Align();
                uint size = input.ReadUInt32();
                entry = new AssetEntry {
                    Name =  name,
                    Offset = input.Position,
                    Size = size,
                };
                if (name.HasAnyOfExtensions ("jpg", "png"))
                    entry.Type = "image";
                break;
            }
        case 128:
            {
                entry = new AssetEntry {
                    Offset = obj.Offset,
                    Size = obj.Size,
                };
                break;
            }
        }
        if (entry != null)
        {
            entry.AssetObject = obj;
            if (string.IsNullOrEmpty (entry.Name))
                entry.Name = string.Format ("{0:D4} [{1}]", obj.PathId, obj.TypeId);
            else if (!used_names.Add (entry.Name))
                entry.Name = string.Format ("{0}-{1}", entry.Name, obj.PathId);
            dir.Add (entry);
        }
    }
    return dir;
}
```

#### GenerateResourceMap

```csharp
public Dictionary<string, ArcView> GenerateResourceMap (List<Entry> dir) {
    var res_map = new Dictionary<string, ArcView>();
    var asset_dir = VFS.GetDirectoryName (m_res_name);
    foreach (AssetEntry entry in dir)
    {
        if (null == entry.Bundle)
            continue;
        if (res_map.ContainsKey (entry.Bundle.Name))
            continue;
        var bundle_name = VFS.CombinePath (asset_dir, entry.Bundle.Name);
        if (!VFS.FileExists (bundle_name))
        {
            entry.Bundle = null;
            entry.Offset = entry.AssetObject.Offset;
            entry.Size   = entry.AssetObject.Size;
            continue;
        }
        res_map[entry.Bundle.Name] = VFS.OpenView (bundle_name);
    }
    return res_map;
}
```

#### GetBundle

```csharp
BundleEntry GetBundle (string path) {
    BundleEntry bundle;
    if (!m_bundles.TryGetValue (path, out bundle))
    {
        bundle = new BundleEntry { Name = path };
        m_bundles[path] = bundle;
    }
    return bundle;
}
```

## 配套算法与外部条件

- [ArcFormats/Unity/ArcUnityFS.cs](ArcUnityFS.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/Asset.cs](Asset.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/AssetReader.cs](AssetReader.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/AudioClip.cs](AudioClip.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/Texture2D.cs](Texture2D.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Unity/ResourcesAssets.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
