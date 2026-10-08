# BRoom / ArcCPC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CPC` / `GameRes.Formats.BRoom.CpcOpener` | `cpc` | `43504347` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CpcOpener.TryOpen` | `int count = (int)(file.View.ReadUInt32 (4) ^ 0xFF559977);` |
| `CpcOpener.TryOpen` | `bool encryption_flag = (file.View.ReadByte (8) ^ 0x8A) != 0;` |
| `CpcOpener.TryOpen` | `int key_index = file.View.ReadByte (9) ^ 0xCE;` |
| `CpcOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset);` |
| `CpcOpener.TryOpen` | `uint size   = file.View.ReadUInt32 (index_offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.BRoom.CpcOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] NameKey = {
    0x13, 0x60, 0xFC, 0x4D, 0xDE, 0xD0, 0x79, 0xB3, 0x51, 0xC5, 0xEC, 0x9E, 0x06, 0x82, 0x63, 0x73,
    0x21, 0xAB, 0xBF, 0x1A, 0x32, 0x9C, 0xBA, 0xFA, 0x5D, 0xFF, 0x29, 0x25, 0xB8, 0x7F, 0xCF, 0xF4,
    0x75, 0x93, 0x05, 0x40, 0x0C, 0xA3, 0x6A, 0x04, 0x98, 0x67, 0x47, 0xEF, 0x8B, 0xAD, 0x56, 0x65,
}

static readonly ushort[] IndexKey = {
    0x27F6, 0x940B, 0x611F, 0xD845, 0xE733, 0xE871, 0x8A11, 0x360E, 0xC7AA, 0x31BB, 0xB23A, 0xC957,
    0x28D2, 0xBF73, 0x1DFF, 0x29EB, 0xD3C2, 0x6CC6, 0xDF7B, 0xA22E, 0xB82B, 0x9256, 0xCEEC, 0xDC08,
    0xA96A, 0xE52D, 0x5F96, 0x7959, 0x81A4, 0x990D, 0x6826, 0xAF38, 0x1B01, 0x2A19, 0x679D, 0x494E,
    0x555C, 0xE623, 0xB797, 0x6214, 0x3CAD, 0xDECD, 0x775B, 0x16A7, 0x37CC, 0xE3AE, 0xD6D5, 0x9F9B,
    0x8C1E, 0xCAF3, 0x8BB1, 0x6DC5, 0x1320, 0xBA1A, 0x42BC, 0xED2F, 0xDAB9, 0xA89C, 0x53F9, 0x4691,
    0xF4E4, 0xFBD1, 0xE982, 0xBEB4,
}

static readonly uint[] OffsetKey = { 0x89D9A054, 0x74E297E9, 0xEECA074F, 0xF2A42CE8, 0x2D6FBE0E }

static readonly uint[] LengthKey = { 0x101C2885, 0x5F7E52F8, 0x3812A6B4, 0x99696CA1, 0x6B0BA9A7 }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = (int)(file.View.ReadUInt32 (4) ^ 0xFF559977);
    if (!IsSaneCount (count))
        return null;
    bool encryption_flag = (file.View.ReadByte (8) ^ 0x8A) != 0;
    int key_index = file.View.ReadByte (9) ^ 0xCE;
    if (encryption_flag && key_index > OffsetKey.Length)
        return null;
    uint index_offset = 12;
    var name_buffer = new byte[0x30];
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint offset = file.View.ReadUInt32 (index_offset);
        uint size   = file.View.ReadUInt32 (index_offset+4);
        if (encryption_flag)
        {
            uint key = IndexKey[i & 0x3F];
            offset ^= key ^ OffsetKey[key_index];
            size   ^= key ^ LengthKey[key_index];
        }
        else
        {
            offset ^= (uint)i ^ 0x35846u;
            size   ^= (uint)i ^ 0x57982525u;
        }
        file.View.Read (index_offset+8, name_buffer, 0, 0x30);
        int j;
        for (j = 0; j < 0x30; ++j)
        {
            name_buffer[j] ^= NameKey[j];
            if (0 == name_buffer[j])
                break;
        }
        var name = Encodings.cp932.GetString (name_buffer, 0, j);
        if (string.IsNullOrWhiteSpace (name))
            return null;
        var entry = Create<Entry> (name);
        entry.Offset = offset;
        entry.Size   = size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x38;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/BRoom/ArcCPC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
