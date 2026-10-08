# Unity / Asset：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Asset.Load` | `input.ReadInt32();` |
| `Asset.Load` | `input.ReadUInt32();` |
| `Asset.Load` | `m_format = input.ReadInt32();` |
| `Asset.Load` | `m_data_offset  = input.ReadUInt32();` |
| `Asset.Load` | `m_is_little_endian = 0 == input.ReadInt32();` |
| `Asset.Load` | `input.ReadInt64();` |
| `Asset.Load` | `m_data_offset = input.ReadInt64();` |
| `Asset.Load` | `long_ids = 0 != input.ReadInt32();` |
| `Asset.Load` | `int obj_count = input.ReadInt32();` |
| `Asset.Load` | `int count = input.ReadInt32();` |
| `Asset.Load` | `var file_id = input.ReadInt32();` |
| `Asset.Load` | `input.ReadCString();` |
| `AssetRef.Load` | `r.AssetPath = reader.ReadCString();` |
| `AssetRef.Load` | `r.Guid = new Guid (reader.ReadBytes (16));` |
| `AssetRef.Load` | `r.Type = reader.ReadInt32();` |
| `AssetRef.Load` | `r.FilePath = reader.ReadCString();` |
| `UnityObject.Load` | `Size = reader.ReadUInt32();` |
| `UnityObject.Load` | `TypeId = reader.ReadInt32();` |
| `UnityObject.Load` | `ClassId = reader.ReadInt16();` |
| `UnityObject.Load` | `var type_id = reader.ReadInt32();` |
| `UnityObject.Load` | `IsDestroyed = reader.ReadInt16() != 0;` |
| `UnityObject.Load` | `reader.ReadInt16();` |
| `UnityObject.Load` | `reader.ReadByte();` |
| `UnityObject.DeserializeType` | `int size = input.ReadInt32();` |
| `UnityObject.DeserializeType` | `obj = input.ReadBytes (size * data_field.Size);` |
| `UnityObject.DeserializeType` | `obj = input.ReadString();` |
| `UnityObject.DeserializeType` | `obj = input.ReadInt32();` |
| `UnityObject.DeserializeType` | `obj = input.ReadUInt32();` |
| `TypeTree.LoadRaw` | `Type = reader.ReadCString();` |
| `TypeTree.LoadRaw` | `Name = reader.ReadCString();` |
| `TypeTree.LoadRaw` | `Size = reader.ReadInt32();` |
| `TypeTree.LoadRaw` | `Index = reader.ReadUInt32();` |
| `TypeTree.LoadRaw` | `IsArray = reader.ReadInt32() != 0;` |
| `TypeTree.LoadRaw` | `Version = reader.ReadInt32();` |
| `TypeTree.LoadRaw` | `Flags = reader.ReadInt32();` |
| `TypeTree.LoadRaw` | `int count = reader.ReadInt32();` |
| `TypeTree.LoadBlob` | `int count = reader.ReadInt32();` |
| `TypeTree.LoadBlob` | `int buffer_bytes = reader.ReadInt32();` |
| `TypeTree.LoadBlob` | `var node_data = reader.ReadBytes (node_size * count);` |
| `TypeTree.LoadBlob` | `m_data = reader.ReadBytes (buffer_bytes);` |
| `TypeTree.LoadBlob` | `int version = buf.ReadInt16();` |
| `TypeTree.LoadBlob` | `int depth = buf.ReadUInt8();` |
| `TypeTree.LoadBlob` | `current.IsArray = buf.ReadUInt8() != 0;` |
| `TypeTree.LoadBlob` | `current.Type = GetString (buf.ReadInt32());` |
| `TypeTree.LoadBlob` | `current.Name = GetString (buf.ReadInt32());` |
| `TypeTree.LoadBlob` | `current.Size = buf.ReadInt32();` |
| `TypeTree.LoadBlob` | `current.Index = buf.ReadUInt32();` |
| `TypeTree.LoadBlob` | `current.Flags = buf.ReadInt32();` |
| `TypeTree.LoadBlob` | `buf.ReadInt64();` |
| `UnityTypeData.Load` | `m_version = reader.ReadCString();` |
| `UnityTypeData.Load` | `var platform = reader.ReadInt32 ();` |
| `UnityTypeData.Load` | `int count = reader.ReadInt32 ();` |
| `UnityTypeData.Load` | `int class_id = reader.ReadInt32 ();` |
| `UnityTypeData.Load` | `reader.ReadByte ();` |
| `UnityTypeData.Load` | `int script_id = reader.ReadInt16 ();` |
| `UnityTypeData.Load` | `byte[] hash = reader.ReadBytes (class_id < 0 ? 0x20 : 0x10);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Unity.Asset

#### 状态与常量

```csharp
int                     m_format ;

long                    m_data_offset ;

bool                    m_is_little_endian ;

UnityTypeData           m_tree = new UnityTypeData() ;

Dictionary<long, int>   m_adds ;

List<AssetRef>          m_refs ;

Dictionary<int, TypeTree>       m_types = new Dictionary<int, TypeTree>() ;

Dictionary<long, UnityObject>   m_objects = new Dictionary<long, UnityObject>() ;

public int          Format { get { return m_format; } }

public bool IsLittleEndian { get { return m_is_little_endian; } }

public long     DataOffset { get { return m_data_offset; } }

public UnityTypeData  Tree { get { return m_tree; } }

public IEnumerable<UnityObject> Objects { get { return m_objects.Values; } }
```

#### Load

```csharp
public void Load (AssetReader input) {
    input.ReadInt32();
    input.ReadUInt32();
    m_format = input.ReadInt32();
    m_data_offset  = input.ReadUInt32();
    if (m_format >= 9)
        m_is_little_endian = 0 == input.ReadInt32();
    if (m_format >= 22)
    {
        input.ReadInt32();
        input.ReadInt64();
        m_data_offset = input.ReadInt64();
        input.ReadInt64();
    }
    input.SetupReaders (this);
    m_tree.Load (input);

    bool long_ids = Format >= 14;
    if (Format >= 7 && Format < 14)
        long_ids = 0 != input.ReadInt32();
    input.SetupReadId (long_ids);

    int obj_count = input.ReadInt32();
    for (int i = 0; i < obj_count; ++i)
    {
        input.Align();
        var obj = new UnityObject (this);
        obj.Load (input);
        RegisterObject (obj);
    }
    if (Format >= 11)
    {
        int count = input.ReadInt32();
        m_adds = new Dictionary<long, int> (count);
        for (int i = 0; i < count; ++i)
        {
            input.Align();
            var file_id = input.ReadInt32();
            var id = input.ReadId();
            m_adds[id] = file_id;
        }
    }
    if (Format >= 6)
    {
        int count = input.ReadInt32();
        m_refs = new List<AssetRef> (count);
        for (int i = 0; i < count; ++i)
        {
            var asset_ref = AssetRef.Load (input);
            m_refs.Add (asset_ref);
        }
    }
    input.ReadCString();
}
```

#### RegisterObject

```csharp
void RegisterObject (UnityObject obj) {
    if (m_tree.TypeTrees.ContainsKey (obj.TypeId))
    {
        m_types[obj.TypeId] = m_tree.TypeTrees[obj.TypeId];
    }
    else if (!m_types.ContainsKey (obj.TypeId))
    {

        {
            Trace.WriteLine (string.Format ("Unknown type id {0}", obj.ClassId.ToString()), "[Unity.Asset]");
            m_types[obj.TypeId] = null;
        }
    }
    if (m_objects.ContainsKey (obj.PathId))
        throw new ApplicationException (string.Format ("Duplicate asset object {0} (PathId: {1})", obj, obj.PathId));
    m_objects[obj.PathId] = obj;
}
```

### GameRes.Formats.Unity.AssetRef

#### 状态与常量

```csharp
public string   AssetPath ;

public Guid     Guid ;

public int      Type ;

public string   FilePath ;

public object   Asset ;
```

#### Load

```csharp
public static AssetRef Load (AssetReader reader) {
    var r = new AssetRef();
    r.AssetPath = reader.ReadCString();
    r.Guid = new Guid (reader.ReadBytes (16));
    r.Type = reader.ReadInt32();
    r.FilePath = reader.ReadCString();
    r.Asset = null;
    return r;
}
```

### GameRes.Formats.Unity.UnityObject

#### 状态与常量

```csharp
public Asset    Asset ;

public long     PathId ;

public long     Offset ;

public uint     Size ;

public int      TypeId ;

public int      ClassId ;

public bool     IsDestroyed ;

public string TypeName {
    get {
        var type = this.Type;
        if (type != null)
            return type.Type;
        return string.Format ("[TypeId:{0}]", TypeId);
    }
}

public TypeTree Type {
    get {
        TypeTree type;
        Asset.Tree.TypeTrees.TryGetValue (TypeId, out type);
        return type;
    }
}
```

#### UnityObject

```csharp
public UnityObject (Asset owner) {
    Asset = owner;
}
```

#### Open

```csharp
public AssetReader Open (Stream input) {
    var stream = new StreamRegion (input, Offset, Size, true);
    var reader = new AssetReader (stream, "");
    reader.SetupReaders (Asset);
    return reader;
}
```

#### Load

```csharp
public void Load (AssetReader reader) {
    PathId = reader.ReadId();
    Offset = reader.ReadOffset();
    Offset += Asset.DataOffset;
    Size = reader.ReadUInt32();
    if (Asset.Format < 17)
    {
        TypeId = reader.ReadInt32();
        ClassId = reader.ReadInt16();
    }
    else
    {
        var type_id = reader.ReadInt32();
        var class_id = Asset.Tree.ClassIds[type_id];
        TypeId = class_id;
        ClassId = class_id;
    }
    if (Asset.Format <= 10)
        IsDestroyed = reader.ReadInt16() != 0;
    if (Asset.Format >= 11 && Asset.Format < 17)
        reader.ReadInt16();
    if (Asset.Format >= 15 && Asset.Format < 17)
        reader.ReadByte();
}
```

#### Deserialize

```csharp
public IDictionary Deserialize (AssetReader input) {
    var type_tree = Asset.Tree.TypeTrees;
    if (!type_tree.ContainsKey (TypeId))
        return null;
    var type_map = new Hashtable();
    var type = type_tree[TypeId];
    foreach (var node in type.Children)
    {
        type_map[node.Name] = DeserializeType (input, node);
    }
    return type_map;
}
```

#### DeserializeType

```csharp
object DeserializeType (AssetReader input, TypeTree node) {
    object obj = null;
    if (node.IsArray)
    {
        int size = input.ReadInt32();
        var data_field = node.Children.FirstOrDefault (n => n.Name == "data");
        if (data_field != null)
        {
            if ("TypelessData" == node.Type)
                obj = input.ReadBytes (size * data_field.Size);
            else
                obj = DeserializeArray (input, size, data_field);
        }
    }
    else if (node.Size < 0)
    {
        if (node.Type == "string")
        {
            obj = input.ReadString();
            if (node.Children[0].IsAligned)
                input.Align();
        }
        else if (node.Type == "StreamingInfo")
        {
            var info = new StreamingInfo();
            info.Load (input);
            obj = info;
        }
        else
            throw new NotImplementedException ("Unknown class encountered in asset deserialization.");
    }
    else if ("int" == node.Type)
        obj = input.ReadInt32();
    else if ("unsigned int" == node.Type)
        obj = input.ReadUInt32();
    else if ("bool" == node.Type)
        obj = input.ReadBool();
    else
        input.Position += node.Size;
    if (node.IsAligned)
        input.Align();
    return obj;
}
```

#### DeserializeArray

```csharp
object[] DeserializeArray (AssetReader input, int length, TypeTree elem) {
    var array = new object[length];
    for (int i = 0; i < length; ++i)
        array[i] = DeserializeType (input, elem);
    return array;
}
```

### GameRes.Formats.Unity.TypeTree

#### 状态与常量

```csharp
int             m_format ;

List<TypeTree>  m_children = new List<TypeTree>() ;

public int      Version ;

public bool     IsArray ;

public string   Type ;

public string   Name ;

public int      Size ;

public uint     Index ;

public int      Flags ;

public IList<TypeTree> Children { get { return m_children; } }

public bool           IsAligned { get { return (Flags & 0x4000) != 0; } }

static readonly string          Null = "(null)" ;

static readonly Lazy<byte[]>    StringsDat = new Lazy<byte[]> (() => LoadResource ("strings.dat")) ;

byte[] m_data ;
```

#### TypeTree

```csharp
public TypeTree (int format) {
    m_format = format;
}
```

#### Load

```csharp
public void Load (AssetReader reader) {
    if (10 == m_format || m_format >= 12)
        LoadBlob (reader);
    else
        LoadRaw (reader);
}
```

#### LoadRaw

```csharp
void LoadRaw (AssetReader reader) {
    Type = reader.ReadCString();
    Name = reader.ReadCString();
    Size = reader.ReadInt32();
    Index = reader.ReadUInt32();
    IsArray = reader.ReadInt32() != 0;
    Version = reader.ReadInt32();
    Flags = reader.ReadInt32();
    int count = reader.ReadInt32();
    for (int i = 0; i < count; ++i)
    {
        var child = new TypeTree (m_format);
        child.Load (reader);
        Children.Add (child);
    }
}
```

#### LoadBlob

```csharp
void LoadBlob (AssetReader reader) {
    int count = reader.ReadInt32();
    int buffer_bytes = reader.ReadInt32();
    int node_size = m_format >= 18 ? 32 : 24;
    var node_data = reader.ReadBytes (node_size * count);
    m_data = reader.ReadBytes (buffer_bytes);
    if (m_format >= 21)
        reader.Skip (4);

    var parents = new Stack<TypeTree>();
    parents.Push (this);
    using (var buf = new BinMemoryStream (node_data))
    {
        for (int i = 0; i < count; ++i)
        {
            int version = buf.ReadInt16();
            int depth = buf.ReadUInt8();
            TypeTree current;
            if (0 == depth)
            {
                current = this;
            }
            else
            {
                while (parents.Count > depth)
                    parents.Pop();
                current = new TypeTree (m_format);
                parents.Peek().Children.Add (current);
                parents.Push (current);
            }
            current.Version = version;
            current.IsArray = buf.ReadUInt8() != 0;
            current.Type = GetString (buf.ReadInt32());
            current.Name = GetString (buf.ReadInt32());
            current.Size = buf.ReadInt32();
            current.Index = buf.ReadUInt32();
            current.Flags = buf.ReadInt32();
            if (m_format >= 18)
                buf.ReadInt64();
        }
    }
}
```

#### GetString

```csharp
string GetString (int offset) {
    byte[] strings;
    if (offset < 0)
    {
        offset &= 0x7FFFFFFF;
        strings = StringsDat.Value;
    }
    else if (offset < m_data.Length)
        strings = m_data;
    else
        return Null;
    return Binary.GetCString (strings, offset, strings.Length-offset, Encoding.UTF8);
}
```

#### LoadResource

```csharp
internal static byte[] LoadResource (string name) {
    var res = EmbeddedResource.Load (name, typeof(TypeTree));
    if (null == res)
        throw new FileNotFoundException ("Resource not found.", name);
    return res;
}
```

### GameRes.Formats.Unity.UnityTypeData

#### 状态与常量

```csharp
string                      m_version ;

List<int>                   m_class_ids = new List<int> () ;

Dictionary<int, byte[]>     m_hashes = new Dictionary<int, byte[]> () ;

Dictionary<int, TypeTree>   m_type_trees = new Dictionary<int, TypeTree> () ;

public string                       Version { get { return m_version; } }

public IList<int>                  ClassIds { get { return m_class_ids; } }

public IDictionary<int, byte[]>      Hashes { get { return m_hashes; } }

public IDictionary<int, TypeTree> TypeTrees { get { return m_type_trees; } }
```

#### Load

```csharp
public void Load (AssetReader reader) {
    int format = reader.Format;
    m_version = reader.ReadCString();
    var platform = reader.ReadInt32 ();
    if (format >= 13)
    {
        bool has_type_trees = reader.ReadBool ();
        int count = reader.ReadInt32 ();
        for (int i = 0; i < count; ++i)
        {
            int class_id = reader.ReadInt32 ();
            if (format >= 17)
            {
                reader.ReadByte ();
                int script_id = reader.ReadInt16 ();
                if (114 == class_id)
                {
                    if (script_id >= 0)
                        class_id = -2 - script_id;
                    else
                        class_id = -1;
                }
            }
            m_class_ids.Add (class_id);
            byte[] hash = reader.ReadBytes (class_id < 0 ? 0x20 : 0x10);
            m_hashes[class_id] = hash;
            if (has_type_trees)
            {
                var tree = new TypeTree (format);
                tree.Load (reader);
                m_type_trees[class_id] = tree;
            }
        }
    }
    else
    {
        int count = reader.ReadInt32 ();
        for (int i = 0; i < count; ++i)
        {
            int class_id = reader.ReadInt32 ();
            var tree = new TypeTree (format);
            tree.Load (reader);
            m_type_trees[class_id] = tree;
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/EmbeddedResource.cs](../EmbeddedResource.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/AssetReader.cs](AssetReader.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/AudioClip.cs](AudioClip.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Unity/Asset.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
