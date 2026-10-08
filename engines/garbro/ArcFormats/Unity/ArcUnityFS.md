# Unity / ArcUnityFS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `UNITY/FS` / `GameRes.Formats.Unity.UnityFSOpener` | ``, `unity3d`, `asset` | `556e6974` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `UnityFSOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "UnityFS\0"))` |
| `UnityFSOpener.TryOpen` | `int arc_version = Binary.BigEndian (file.View.ReadInt32 (8));` |
| `UnityFSOpener.TryOpen` | `input.ReadCString (Encoding.UTF8);` |
| `UnityFSOpener.TryOpen` | `long file_size = Binary.BigEndian (input.ReadInt64());` |
| `UnityFSOpener.TryOpen` | `int packed_index_size = Binary.BigEndian (input.ReadInt32());` |
| `UnityFSOpener.TryOpen` | `int index_size = Binary.BigEndian (input.ReadInt32());` |
| `UnityFSOpener.TryOpen` | `int flags = Binary.BigEndian (input.ReadInt32());` |
| `UnityFSOpener.TryOpen` | `var packed = input.ReadBytes (packed_index_size);` |
| `AssetDeserializer.Parse` | `int segment_count = Binary.BigEndian (index.ReadInt32());` |
| `AssetDeserializer.Parse` | `segment.UnpackedSize = Binary.BigEndian (index.ReadUInt32());` |
| `AssetDeserializer.Parse` | `segment.PackedSize = Binary.BigEndian (index.ReadUInt32());` |
| `AssetDeserializer.Parse` | `segment.Compression = Binary.BigEndian (index.ReadUInt16());` |
| `AssetDeserializer.Parse` | `int count = Binary.BigEndian (index.ReadInt32());` |
| `AssetDeserializer.Parse` | `entry.Offset = Binary.BigEndian (index.ReadInt64());` |
| `AssetDeserializer.Parse` | `entry.Size = (uint)Binary.BigEndian (index.ReadInt64());` |
| `AssetDeserializer.Parse` | `entry.Flags = Binary.BigEndian (index.ReadUInt32());` |
| `AssetDeserializer.Parse` | `entry.Name = index.ReadCString (Encoding.UTF8);` |
| `AssetDeserializer.ReadAssetBundle` | `var name = reader.ReadString();` |
| `AssetDeserializer.ReadAssetBundle` | `int count = reader.ReadInt32();` |
| `AssetDeserializer.ReadAssetBundle` | `reader.ReadInt32();` |
| `AssetDeserializer.ReadAssetBundle` | `reader.ReadInt64();` |
| `AssetDeserializer.ReadAssetBundle` | `count = reader.ReadInt32();` |
| `AssetDeserializer.ReadAssetBundle` | `name = reader.ReadString();` |
| `AssetDeserializer.ReadAssetBundle` | `long id = reader.ReadInt64();` |
| `AssetDeserializer.GetObjectName` | `var name = reader.ReadString();` |
| `AssetDeserializer.ReadTextAsset` | `var name = reader.ReadString();` |
| `AssetDeserializer.ReadTextAsset` | `uint size = reader.ReadUInt32();` |
| `AssetDeserializer.ReadTextAsset` | `uint signature = reader.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Unity.UnityFSOpener

继承/接口：`ArchiveFormat`。

#### UnityFSOpener

```csharp
public UnityFSOpener () {
    Extensions = new string[] { "", "unity3d", "asset" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "UnityFS\0"))
        return null;
    int arc_version = Binary.BigEndian (file.View.ReadInt32 (8));
    if (arc_version != 6)
        return null;
    long data_offset;
    byte[] index_data;
    using (var input = file.CreateStream())
    {
        input.Position = 0xC;
        input.ReadCString (Encoding.UTF8);
        input.ReadCString (Encoding.UTF8);
        long file_size = Binary.BigEndian (input.ReadInt64());
        int packed_index_size = Binary.BigEndian (input.ReadInt32());
        int index_size = Binary.BigEndian (input.ReadInt32());
        int flags = Binary.BigEndian (input.ReadInt32());
        long index_offset;
        if (0 == (flags & 0x80))
        {
            index_offset = input.Position;
            data_offset = index_offset + packed_index_size;
        }
        else
        {
            index_offset = file_size - packed_index_size;
            data_offset = input.Position;
        }
        input.Position = index_offset;
        var packed = input.ReadBytes (packed_index_size);
        switch (flags & 0x3F)
        {
        case 0:
            index_data = packed;
            break;
        case 1:
            index_data = UnpackLzma (packed, index_size);
            break;
        case 2:
        case 3:
            index_data = new byte[index_size];
            Lz4Compressor.DecompressBlock (packed, packed.Length, index_data, index_data.Length);
            break;
        default:
            return null;
        }
    }
    var index = new AssetDeserializer (file, data_offset);
    using (var input = new BinMemoryStream (index_data))
        index.Parse (input);
    var dir = index.LoadObjects();
    return new UnityBundle (file, this, dir, index.Segments, index.Bundles);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var uarc = (UnityBundle)arc;
    Stream input = new BundleStream (uarc.File, uarc.Segments);
    input = new StreamRegion (input, entry.Offset, entry.Size);
    var aent = entry as AssetEntry;
    if (null == aent || !aent.IsEncrypted)
        return input;
    using (input)
    {
        var data = new byte[entry.Size];
        input.Read (data, 0, data.Length);
        DecryptAsset (data);
        return new BinMemoryStream (data);
    }
}
```

#### UnpackLzma

```csharp
internal static byte[] UnpackLzma (byte[] input, int unpacked_size) {
    throw new NotImplementedException();
}
```

#### DecryptAsset

```csharp
internal void DecryptAsset (byte[] data) {
    uint key = 0xBF8766F5u;
    for (int i = 0; i < data.Length; ++i)
    {
        key = ((0x343FD * key + 0x269EC3) >> 16) & 0x7FFF;
        data[i] ^= (byte)key;
    }
}
```

### GameRes.Formats.Unity.BundleEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint Flags ;
```

### GameRes.Formats.Unity.AssetEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public BundleEntry  Bundle ;

public UnityObject  AssetObject ;

public bool         IsEncrypted ;
```

### GameRes.Formats.Unity.UnityBundle

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly List<BundleSegment> Segments ;

public readonly List<BundleEntry>   Bundles ;
```

#### UnityBundle

```csharp
public UnityBundle (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, List<BundleSegment> segments, List<BundleEntry> bundles)
    : base (arc, impl, dir) {
    Segments = segments;
    Bundles = bundles;
}
```

### GameRes.Formats.Unity.BundleSegment

#### 状态与常量

```csharp
public long Offset ;

public uint PackedSize ;

public long UnpackedOffset ;

public uint UnpackedSize ;

public int  Compression ;

public bool IsCompressed { get { return (Compression & 0x3F) != 0; } }
```

### GameRes.Formats.Unity.AssetDeserializer

#### 状态与常量

```csharp
readonly ArcView    m_file ;

readonly long       m_data_offset ;

List<BundleSegment> m_segments ;

List<BundleEntry>   m_bundles ;

public List<BundleSegment> Segments { get { return m_segments; } }

public List<BundleEntry>    Bundles { get { return m_bundles; } }
```

#### AssetDeserializer

```csharp
public AssetDeserializer (ArcView file, long data_offset) {
    m_file = file;
    m_data_offset = data_offset;
}
```

#### Parse

```csharp
public void Parse (IBinaryStream index) {
    index.Position = 16;
    int segment_count = Binary.BigEndian (index.ReadInt32());
    m_segments = new List<BundleSegment> (segment_count);
    long packed_offset = m_data_offset;
    long unpacked_offset = 0;
    for (int i = 0; i < segment_count; ++i)
    {
        var segment = new BundleSegment();
        segment.Offset = packed_offset;
        segment.UnpackedOffset = unpacked_offset;
        segment.UnpackedSize = Binary.BigEndian (index.ReadUInt32());
        segment.PackedSize = Binary.BigEndian (index.ReadUInt32());
        segment.Compression = Binary.BigEndian (index.ReadUInt16());
        m_segments.Add (segment);
        packed_offset += segment.PackedSize;
        unpacked_offset += segment.UnpackedSize;
    }
    int count = Binary.BigEndian (index.ReadInt32());
    m_bundles = new List<BundleEntry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new BundleEntry();
        entry.Offset = Binary.BigEndian (index.ReadInt64());
        entry.Size = (uint)Binary.BigEndian (index.ReadInt64());
        entry.Flags = Binary.BigEndian (index.ReadUInt32());
        entry.Name = index.ReadCString (Encoding.UTF8);
        m_bundles.Add (entry);
    }
}
```

#### LoadObjects

```csharp
public List<Entry> LoadObjects () {
    var dir = new List<Entry>();
    using (var stream = new BundleStream (m_file, m_segments))
    {
        foreach (BundleEntry bundle in m_bundles)
        {
            if (bundle.Name.HasAnyOfExtensions (".resource", ".resS"))
                continue;
            using (var asset_stream = new StreamRegion (stream, bundle.Offset, bundle.Size, true))
            using (var reader = new AssetReader (asset_stream, bundle.Name))
            {
                var asset = new Asset();
                asset.Load (reader);
                var object_dir = ParseAsset (stream, bundle, asset);
                dir.AddRange (object_dir);
            }
        }
        if (0 == dir.Count)
            dir.AddRange (m_bundles);
    }
    return dir;
}
```

#### ParseAsset

```csharp
IEnumerable<Entry> ParseAsset (Stream file, BundleEntry bundle, Asset asset) {
    Dictionary<long, string> id_map = null;
    var bundle_types = asset.Tree.TypeTrees.Where (t => t.Value.Type == "AssetBundle").Select (t => t.Key);
    if (bundle_types.Any())
    {

        int bundle_type_id = bundle_types.First();
        var asset_bundle = asset.Objects.FirstOrDefault (x => x.TypeId == bundle_type_id);
        if (asset_bundle != null)
        {
            id_map = ReadAssetBundle (file, asset_bundle);
        }
    }
    if (null == id_map)
        id_map = new Dictionary<long, string>();
    foreach (var obj in asset.Objects)
    {
        var entry = ReadAsset (file, obj);
        if (null == entry)
            continue;
        if (null == entry.Bundle)
            entry.Bundle = bundle;
        string name;
        if (!id_map.TryGetValue (obj.PathId, out name))
            name = GetObjectName (file, obj);
        else
            name = ShortenPath (name);
        entry.Name = name;
        yield return entry;
    }
}
```

#### ReadAsset

```csharp
AssetEntry ReadAsset (Stream file, UnityObject obj) {
    string type = obj.TypeName;
    if ("AudioClip" == type)
        return ReadAudioClip (file, obj);
    else if ("TextAsset" == type)
        return ReadTextAsset (file, obj);
    else if ("Texture2D" == type)
        type = "image";
    else if ("AssetBundle" == type)
        return null;

    return new AssetEntry {
        Type = type,
        AssetObject = obj,
        Offset = obj.Offset,
        Size = obj.Size,
    };
}
```

#### ReadAssetBundle

```csharp
Dictionary<long, string> ReadAssetBundle (Stream input, UnityObject bundle) {
    using (var reader = bundle.Open (input))
    {
        var name = reader.ReadString();
        reader.Align();
        int count = reader.ReadInt32();
        for (int i = 0; i < count; ++i)
        {
            reader.ReadInt32();
            reader.ReadInt64();
        }
        count = reader.ReadInt32();
        var id_map = new Dictionary<long, string> (count+1);
        id_map[bundle.PathId] = name;
        for (int i = 0; i < count; ++i)
        {
            name = reader.ReadString();
            reader.Align();
            reader.ReadInt32();
            reader.ReadInt32();
            reader.ReadInt32();
            long id = reader.ReadInt64();
            id_map[id] = name;
        }
        return id_map;
    }
}
```

#### GetObjectName

```csharp
string GetObjectName (Stream input, UnityObject obj) {
    var type = obj.Type;
    if (type != null && type.Children.Count > 0)
    {
        var first_field = type.Children[0];
        if ("m_Name" == first_field.Name && "string" == first_field.Type)
        {
            using (var reader = obj.Open (input))
            {
                var name = reader.ReadString();
                if (!string.IsNullOrEmpty (name))
                    return name;
            }
        }
    }
    return obj.PathId.ToString ("X16");
}
```

#### ReadTextAsset

```csharp
AssetEntry ReadTextAsset (Stream input, UnityObject obj) {
    var script = obj.Type.Children.FirstOrDefault (f => f.Name == "m_Script");
    if (null == script)
        return null;
    using (var reader = obj.Open (input))
    {
        var name = reader.ReadString();
        reader.Align();
        uint size = reader.ReadUInt32();
        var entry = new AssetEntry {
            AssetObject = obj,
            Offset = obj.Offset + reader.Position,
            Size = size,
            IsEncrypted = 0 != (script.Flags & 0x04000000),
        };
        if (entry.IsEncrypted)
        {
            uint signature = reader.ReadUInt32();
            if (0x0D15F641 == signature)
                entry.Type = "image";
            else if (0x474E5089 == signature)
            {
                entry.Type = "image";
                entry.IsEncrypted = false;
            }
        }
        return entry;
    }
}
```

#### ReadAudioClip

```csharp
AssetEntry ReadAudioClip (Stream input, UnityObject obj) {
    using (var reader = obj.Open (input))
    {
        var clip = new AudioClip();
        clip.Load (reader);
        var bundle_name = Path.GetFileName (clip.m_Source);
        var bundle = m_bundles.FirstOrDefault (b => b.Name == bundle_name);
        if (null == bundle)
            return null;
        return new AssetEntry {
            Type = "audio",
            Bundle = bundle,
            AssetObject = obj,
            Offset = bundle.Offset + clip.m_Offset,
            Size = (uint)clip.m_Size,
        };
    }
}
```

#### ShortenPath

```csharp
static string ShortenPath (string name) {
    int slash_pos = name.LastIndexOf ('/');
    if (-1 == slash_pos)
        return name;
    slash_pos = name.LastIndexOf ('/', slash_pos-1);
    if (-1 == slash_pos)
        return name;
    return name.Substring (slash_pos+1);
}
```

## 配套算法与外部条件

- [ArcFormats/Lz4Stream.cs](../Lz4Stream.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/Asset.cs](Asset.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/AssetReader.cs](AssetReader.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/AudioClip.cs](AudioClip.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/BundleStream.cs](BundleStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Unity/ArcUnityFS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
