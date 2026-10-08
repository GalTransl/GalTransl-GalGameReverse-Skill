# Unity / Texture2D：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Texture2D.Load` | `m_Name = reader.ReadString();` |
| `Texture2D.Load` | `m_Width = reader.ReadInt32();` |
| `Texture2D.Load` | `m_Height = reader.ReadInt32();` |
| `Texture2D.Load` | `m_CompleteImageSize = reader.ReadInt32();` |
| `Texture2D.Load` | `m_TextureFormat = (TextureFormat)reader.ReadInt32();` |
| `Texture2D.Load` | `m_MipCount = reader.ReadInt32();` |
| `Texture2D.Load` | `m_ImageCount = reader.ReadInt32();` |
| `Texture2D.Load` | `m_TextureDimension = reader.ReadInt32();` |
| `Texture2D.Load` | `m_FilterMode = reader.ReadInt32();` |
| `Texture2D.Load` | `m_Aniso = reader.ReadInt32();` |
| `Texture2D.Load` | `m_WrapMode = reader.ReadInt32();` |
| `Texture2D.Load` | `m_LightFormat = reader.ReadInt32();` |
| `Texture2D.Load` | `m_ColorSpace = reader.ReadInt32();` |
| `Texture2D.Load` | `m_DataLength = reader.ReadInt32();` |
| `Texture2D.Load` | `reader.ReadInt64();` |
| `Texture2D.Load` | `reader.ReadInt32();` |
| `Texture2D.Load2017` | `m_Name = reader.ReadString();` |
| `Texture2D.Load2017` | `reader.ReadInt32();` |
| `Texture2D.Load2017` | `m_Width = reader.ReadInt32();` |
| `Texture2D.Load2017` | `m_Height = reader.ReadInt32();` |
| `Texture2D.Load2017` | `m_CompleteImageSize = reader.ReadInt32();` |
| `Texture2D.Load2017` | `m_TextureFormat = (TextureFormat)reader.ReadInt32();` |
| `Texture2D.Load2017` | `m_MipCount = reader.ReadInt32();` |
| `Texture2D.Load2017` | `m_ImageCount = reader.ReadInt32();` |
| `Texture2D.Load2017` | `m_TextureDimension = reader.ReadInt32();` |
| `Texture2D.Load2017` | `m_FilterMode = reader.ReadInt32();` |
| `Texture2D.Load2017` | `m_Aniso = reader.ReadInt32();` |
| `Texture2D.Load2017` | `m_WrapMode = reader.ReadInt32();` |
| `Texture2D.Load2017` | `m_ColorSpace = reader.ReadInt32();` |
| `Texture2D.Load2017` | `m_DataLength = reader.ReadInt32();` |
| `Texture2D.Load2021` | `m_Name = reader.ReadString();` |
| `Texture2D.Load2021` | `reader.ReadInt32();` |
| `Texture2D.Load2021` | `m_Width = reader.ReadInt32();` |
| `Texture2D.Load2021` | `m_Height = reader.ReadInt32();` |
| `Texture2D.Load2021` | `m_CompleteImageSize = reader.ReadInt32();` |
| `Texture2D.Load2021` | `m_TextureFormat = (TextureFormat)reader.ReadInt32();` |
| `Texture2D.Load2021` | `m_MipCount = reader.ReadInt32();` |
| `Texture2D.Load2021` | `m_ImageCount = reader.ReadInt32();` |
| `Texture2D.Load2021` | `m_TextureDimension = reader.ReadInt32();` |
| `Texture2D.Load2021` | `m_FilterMode = reader.ReadInt32();` |
| `Texture2D.Load2021` | `m_Aniso = reader.ReadInt32();` |
| `Texture2D.Load2021` | `m_WrapMode = reader.ReadInt32();` |
| `Texture2D.Load2021` | `m_ColorSpace = reader.ReadInt32();` |
| `Texture2D.Load2021` | `m_DataLength = reader.ReadInt32();` |
| `Texture2D.LoadData` | `m_Data = reader.ReadBytes (m_DataLength);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum TextureFormat : int
    {
        Alpha8 = 1,
        ARGB4444 = 2,
        RGB24 = 3,
        RGBA32 = 4,
        ARGB32 = 5,
        R16 = 6,
        RGB565 = 7,
        DXT1 = 10,
        DXT5 = 12,
        RGBA4444 = 13,
        BGRA32 = 14,
        BC7 = 25,
        DXT1Crunched = 28,
        DXT5Crunched = 29,
    }
```

### GameRes.Formats.Unity.Texture2D

#### 状态与常量

```csharp
public string   m_Name ;

public int      m_Width ;

public int      m_Height ;

public int      m_CompleteImageSize ;

public TextureFormat m_TextureFormat ;

public int      m_MipCount ;

public bool     m_IsReadable ;

public bool     m_ReadAllowed ;

public int      m_ImageCount ;

public int      m_TextureDimension ;

public int      m_FilterMode ;

public int      m_Aniso ;

public float    m_MipBias ;

public int      m_WrapMode ;

public int      m_LightFormat ;

public int      m_ColorSpace ;

public int      m_DataLength ;

public byte[]   m_Data ;
```

#### Load

```csharp
public void Load (AssetReader reader) {
    m_Name = reader.ReadString();
    reader.Align();
    m_Width = reader.ReadInt32();
    m_Height = reader.ReadInt32();
    m_CompleteImageSize = reader.ReadInt32();
    m_TextureFormat = (TextureFormat)reader.ReadInt32();
    m_MipCount = reader.ReadInt32();
    if (reader.Format > 9)
    {
        m_IsReadable = reader.ReadBool();
        m_ReadAllowed = reader.ReadBool();
        reader.Align();
    }
    m_ImageCount = reader.ReadInt32();
    m_TextureDimension = reader.ReadInt32();
    m_FilterMode = reader.ReadInt32();
    m_Aniso = reader.ReadInt32();
    m_MipBias = reader.ReadFloat();
    m_WrapMode = reader.ReadInt32();
    m_LightFormat = reader.ReadInt32();
    m_ColorSpace = reader.ReadInt32();
    m_DataLength = reader.ReadInt32();
}
```

#### Load

```csharp
public void Load (AssetReader reader, UnityTypeData type) {
    if ("2021.1.3f1" == type.Version)
    {
        Load2021 (reader);
        return;
    }
    if (type.Version != "2017.3.1f1" && type.Version != "2019.3.0f1" && type.Version != "2017.4.3f1")
    {
        Load (reader);
        if (0 == m_DataLength && type.Version.StartsWith ("2017."))
            reader.ReadInt64();
        return;
    }

    m_Name = reader.ReadString();
    reader.Align();
    reader.ReadInt32();
    reader.ReadInt32();
    m_Width = reader.ReadInt32();
    m_Height = reader.ReadInt32();
    m_CompleteImageSize = reader.ReadInt32();
    m_TextureFormat = (TextureFormat)reader.ReadInt32();
    m_MipCount = reader.ReadInt32();
    m_IsReadable = reader.ReadBool();
    reader.Align();
    if ("2019.3.0f1" == type.Version)
        reader.ReadInt32();
    m_ImageCount = reader.ReadInt32();
    m_TextureDimension = reader.ReadInt32();
    m_FilterMode = reader.ReadInt32();
    m_Aniso = reader.ReadInt32();
    m_MipBias = reader.ReadFloat();
    m_WrapMode = reader.ReadInt32();
    reader.ReadInt32();
    reader.ReadInt32();
    reader.ReadInt32();
    m_ColorSpace = reader.ReadInt32();
    m_DataLength = reader.ReadInt32();
}
```

#### Load2017

```csharp
public void Load2017 (AssetReader reader) {
    m_Name = reader.ReadString();
    reader.Align();
    reader.ReadInt32();
    reader.ReadInt32();
    m_Width = reader.ReadInt32();
    m_Height = reader.ReadInt32();
    m_CompleteImageSize = reader.ReadInt32();
    m_TextureFormat = (TextureFormat)reader.ReadInt32();
    m_MipCount = reader.ReadInt32();
    m_IsReadable = reader.ReadBool();
    reader.Align();
    m_ImageCount = reader.ReadInt32();
    m_TextureDimension = reader.ReadInt32();
    m_FilterMode = reader.ReadInt32();
    m_Aniso = reader.ReadInt32();
    m_MipBias = reader.ReadFloat();
    m_WrapMode = reader.ReadInt32();
    reader.ReadInt32();
    reader.ReadInt32();
    reader.ReadInt32();
    m_ColorSpace = reader.ReadInt32();
    m_DataLength = reader.ReadInt32();
}
```

#### Load2021

```csharp
public void Load2021 (AssetReader reader) {
    m_Name = reader.ReadString();
    reader.Align();
    reader.ReadInt32();
    reader.ReadInt32();
    m_Width = reader.ReadInt32();
    m_Height = reader.ReadInt32();
    m_CompleteImageSize = reader.ReadInt32();
    reader.ReadInt32();
    m_TextureFormat = (TextureFormat)reader.ReadInt32();
    m_MipCount = reader.ReadInt32();
    m_IsReadable = reader.ReadBool();
    reader.Align();
    reader.ReadInt32();
    m_ImageCount = reader.ReadInt32();
    m_TextureDimension = reader.ReadInt32();
    m_FilterMode = reader.ReadInt32();
    m_Aniso = reader.ReadInt32();
    m_MipBias = reader.ReadFloat();
    m_WrapMode = reader.ReadInt32();
    reader.ReadInt32();
    reader.ReadInt32();
    reader.ReadInt32();
    m_ColorSpace = reader.ReadInt32();
    reader.ReadInt32();
    m_DataLength = reader.ReadInt32();
}
```

#### LoadData

```csharp
public void LoadData (AssetReader reader) {
    m_Data = reader.ReadBytes (m_DataLength);
}
```

#### Import

```csharp
public void Import (IDictionary fields) {
    m_Name = fields["m_Name"] as string ?? "";
    m_Width = (int)(fields["m_Width"] ?? 0);
    m_Height = (int)(fields["m_Height"] ?? 0);
    m_CompleteImageSize = (int)(fields["m_CompleteImageSize"] ?? 0);
    m_TextureFormat = (TextureFormat)(fields["m_TextureFormat"] ?? 0);
    m_MipCount = (int)(fields["m_MipCount"] ?? 0);
    m_ImageCount = (int)(fields["m_ImageCount"] ?? 0);
    m_TextureDimension = (int)(fields["m_TextureDimension"] ?? 0);
    m_IsReadable = (bool)(fields["m_IsReadable"] ?? false);
    m_Data = fields["image data"] as byte[] ?? Array.Empty<byte>();
}
```

## 配套算法与外部条件

- [ArcFormats/Unity/Asset.cs](Asset.md)：本页引用的随包算法资料。
- [ArcFormats/Unity/AssetReader.cs](AssetReader.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Unity/Texture2D.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
