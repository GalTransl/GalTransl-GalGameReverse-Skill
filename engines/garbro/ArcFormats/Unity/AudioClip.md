# Unity / AudioClip：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AudioClip.Load` | `m_Name = reader.ReadString();` |
| `AudioClip.Load` | `m_LoadType = reader.ReadInt32();` |
| `AudioClip.Load` | `m_Channels = reader.ReadInt32();` |
| `AudioClip.Load` | `m_Frequency = reader.ReadInt32();` |
| `AudioClip.Load` | `m_BitsPerSample = reader.ReadInt32();` |
| `AudioClip.Load` | `m_SubsoundIndex = reader.ReadInt32();` |
| `AudioClip.Load` | `m_Source = reader.ReadString();` |
| `AudioClip.Load` | `m_Offset = reader.ReadInt64();` |
| `AudioClip.Load` | `m_Size = reader.ReadInt64();` |
| `AudioClip.Load` | `m_CompressionFormat = reader.ReadInt32();` |
| `AudioClip.Load` | `reader.ReadInt32();` |
| `AudioClip.Load` | `m_Size = reader.ReadUInt32();` |
| `StreamingInfo.Load` | `Size = reader.ReadUInt32();` |
| `StreamingInfo.Load` | `Path = reader.ReadString();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum AudioFormat : int
    {
        Unknown = 0,
        Acc = 1,
        Aiff = 2,
        It = 10,
        Mod = 12,
        Mpeg = 13,
        OggVorbis = 14,
        S3M = 17,
        Wav = 20,
        Xm = 21,
        Xma = 22,
        Vag = 23,
        AudioQueue = 24,
    }
```

### GameRes.Formats.Unity.AudioClip

#### 状态与常量

```csharp
public string   m_Name ;

public int      m_LoadType ;

public int      m_Channels ;

public int      m_Frequency ;

public int      m_BitsPerSample ;

public float    m_Length ;

public bool     m_IsTrackerFormat ;

public int      m_SubsoundIndex ;

public bool     m_PreloadAudioData ;

public bool     m_LoadInBackground ;

public bool     m_Legacy3D ;

public string   m_Source ;

public long     m_Offset ;

public long     m_Size ;

public int      m_CompressionFormat ;
```

#### Load

```csharp
public void Load (AssetReader reader) {
    m_Name = reader.ReadString();
    reader.Align();
    if (reader.Format > 9)
    {
        m_LoadType = reader.ReadInt32();
        m_Channels = reader.ReadInt32();
        m_Frequency = reader.ReadInt32();
        m_BitsPerSample = reader.ReadInt32();
        m_Length = reader.ReadFloat();
        m_IsTrackerFormat = reader.ReadBool();
        reader.Align();
        m_SubsoundIndex = reader.ReadInt32();
        m_PreloadAudioData = reader.ReadBool();
        m_LoadInBackground = reader.ReadBool();
        m_Legacy3D = reader.ReadBool();
        reader.Align();
        m_Source = reader.ReadString();
        reader.Align();
        m_Offset = reader.ReadInt64();
        m_Size = reader.ReadInt64();
        m_CompressionFormat = reader.ReadInt32();
    }
    else
    {
        m_LoadType = reader.ReadInt32();
        m_CompressionFormat = reader.ReadInt32();
        reader.ReadInt32();
        reader.ReadInt32();
        m_Size = reader.ReadUInt32();
    }
}
```

### GameRes.Formats.Unity.StreamingInfo

#### 状态与常量

```csharp
public long     Offset ;

public uint     Size ;

public string   Path ;
```

#### Load

```csharp
public void Load (AssetReader reader) {
    Offset = reader.ReadOffset();
    Size = reader.ReadUInt32();
    Path = reader.ReadString();
}
```

## 配套算法与外部条件

- [ArcFormats/Unity/AssetReader.cs](AssetReader.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Unity/AudioClip.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
