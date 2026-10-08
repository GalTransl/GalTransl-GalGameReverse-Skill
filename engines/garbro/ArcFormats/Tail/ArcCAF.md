# Tail / ArcCAF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CAF` / `GameRes.Formats.Tail.CafOpener` | `caf` | `43414630` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CafOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `CafOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0xC);` |
| `CafOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (0x10);` |
| `CafOpener.TryOpen` | `uint names_offset = file.View.ReadUInt32 (0x14);` |
| `CafOpener.TryOpen` | `uint names_size = file.View.ReadUInt32 (0x18);` |
| `CafOpener.TryOpen` | `var names = file.View.ReadBytes (names_offset, names_size);` |
| `CafOpener.TryOpen` | `int dir_name_offset = file.View.ReadInt32 (index_offset+4);` |
| `CafOpener.TryOpen` | `int name_offset = file.View.ReadInt32 (index_offset+8);` |
| `CafOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0xC) + data_offset;` |
| `CafOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x10);` |
| `CafOpener.UnpackPren` | `int unpacked_size = input.ReadInt32();` |
| `CafOpener.UnpackPren` | `byte rle_code = input.ReadUInt8();` |
| `CafOpener.UnpackPren` | `int v = input.ReadByte();` |
| `CafOpener.UnpackPren` | `byte count = input.ReadUInt8();` |
| `CafOpener.UnpackPren` | `x = input.ReadUInt8();` |
| `CafOpener.UnpackCfp0` | `int unpacked_size = input.ReadInt32();` |
| `CafOpener.UnpackCfp0` | `int cmd = input.ReadByte();` |
| `CafOpener.UnpackCfp0` | `count = input.ReadUInt8();` |
| `CafOpener.UnpackCfp0` | `count = input.ReadInt32();` |
| `CafOpener.UnpackCfp0` | `byte v = input.ReadUInt8();` |
| `CafOpener.UnpackCfp0` | `int offset = input.ReadUInt16();` |
| `CafOpener.UnpackCfp0` | `count = input.ReadUInt16();` |
| `CafOpener.UnpackHp` | `int unpacked_size = input.ReadInt32();` |
| `CafOpener.UnpackHp` | `int root_token = input.ReadInt32();` |
| `CafOpener.UnpackHp` | `int node_count = input.ReadInt32();` |
| `CafOpener.UnpackHp` | `int packed_count = input.ReadInt32();` |
| `CafOpener.UnpackHp` | `int node = 2 * input.ReadInt32();` |
| `CafOpener.UnpackHp` | `tree_nodes[node    ] = input.ReadInt32();` |
| `CafOpener.UnpackHp` | `tree_nodes[node + 1] = input.ReadInt32();` |
| `CafOpener.UnpackHp` | `bits = input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Tail.CafOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
const uint PrenSignature = 0x4E455250 ;

const uint Cfp0Signature = 0x30504643 ;

const uint HpSignature   = 0x00005048 ;

const uint RpSignature   = 0x00005052 ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = file.View.ReadUInt32 (0xC);
    uint index_size = file.View.ReadUInt32 (0x10);
    uint names_offset = file.View.ReadUInt32 (0x14);
    uint names_size = file.View.ReadUInt32 (0x18);
    var names = file.View.ReadBytes (names_offset, names_size);
    if (names.Length != names_size)
        return null;
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    var dir_map = new Dictionary<int, string>();
    long data_offset = names_offset + names_size;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int dir_name_offset = file.View.ReadInt32 (index_offset+4);
        int name_offset = file.View.ReadInt32 (index_offset+8);
        var name = Binary.GetCString (names, name_offset);
        if (dir_name_offset >= 0)
        {
            string dir_name;
            if (!dir_map.TryGetValue (dir_name_offset, out dir_name))
            {
                dir_name = Binary.GetCString (names, dir_name_offset).Replace ('/', '\\');
                dir_map[dir_name_offset] = dir_name;
            }
            name = Path.Combine (dir_name, name);
        }
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0xC) + data_offset;
        entry.Size   = file.View.ReadUInt32 (index_offset+0x10);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x14;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    IBinaryStream input = arc.File.CreateStream (entry.Offset, entry.Size, entry.Name);
    Func<IBinaryStream, byte[]> unpacker = null;
    for (;;)
    {
        switch (input.Signature)
        {
        case RpSignature:
        case PrenSignature: unpacker = UnpackPren; break;
        case Cfp0Signature: unpacker = UnpackCfp0; break;
        case HpSignature:   unpacker = UnpackHp; break;

        default: return input.AsStream;
        }
        byte[] data;
        using (input)
            data = unpacker (input);
        input = new BinMemoryStream (data, entry.Name);
    }
}
```

#### UnpackPren

```csharp
byte[] UnpackPren (IBinaryStream input) {
    input.Position = 8;
    int unpacked_size = input.ReadInt32();
    byte rle_code = input.ReadUInt8();
    input.Seek (3, SeekOrigin.Current);
    var output = new byte[unpacked_size];
    int dst = 0;
    while (dst < output.Length)
    {
        int v = input.ReadByte();
        if (-1 == v)
            break;
        if (rle_code == v)
        {
            byte count = input.ReadUInt8();
            byte x = rle_code;
            if (count > 2)
                x = input.ReadUInt8();

            while (count --> 0)
                output[dst++] = x;
        }
        else
        {
            output[dst++] = (byte)v;
        }
    }
    return output;
}
```

#### UnpackCfp0

```csharp
byte[] UnpackCfp0 (IBinaryStream input) {
    input.Position = 8;
    int unpacked_size = input.ReadInt32();
    var output = new byte[unpacked_size];
    int dst = 0;
    while (dst < output.Length)
    {
        int cmd = input.ReadByte();
        int count = 0;
        switch (cmd)
        {
        case 0:
            count = input.ReadUInt8();
            input.Read (output, dst, count);
            break;
        case 1:
            count = input.ReadInt32();
            input.Read (output, dst, count);
            break;
        case 2:
            {
                count = input.ReadUInt8();
                byte v = input.ReadUInt8();
                for (int i = 0; i < count; ++i)
                    output[dst+i] = v;
                break;
            }
        case 3:
            {
                count = input.ReadInt32();
                byte v = input.ReadUInt8();
                for (int i = 0; i < count; ++i)
                    output[dst+i] = v;
                break;
            }
        case 6:
            int offset = input.ReadUInt16();
            count = input.ReadUInt16();
            Binary.CopyOverlapped (output, dst-offset, dst, count);
            break;

        case 15:
        case -1:
            return output;
        }
        dst += count;
    }
    return output;
}
```

#### UnpackHp

```csharp
byte[] UnpackHp (IBinaryStream input) {
    input.Position = 8;
    int unpacked_size = input.ReadInt32();
    int root_token = input.ReadInt32();
    int node_count = input.ReadInt32();
    int packed_count = input.ReadInt32();
    var tree_nodes = new int[0x400];
    node_count += root_token - 0xFF;
    while (node_count --> 0)
    {
        int node = 2 * input.ReadInt32();
        tree_nodes[node    ] = input.ReadInt32();
        tree_nodes[node + 1] = input.ReadInt32();
    }
    var output = new byte[unpacked_size];
    int dst = 0;
    byte bits = 0;
    byte bit_mask = 0;
    for (int i = 0; i < packed_count; ++i)
    {
        int symbol = root_token;
        do
        {
            if (0 == bit_mask)
            {
                bits = input.ReadUInt8();
                bit_mask = 128;
            }
            int node = 2 * symbol;
            node += ((bits & bit_mask) != 0) ? 1 : 0;
            symbol = tree_nodes[node];
            bit_mask >>= 1;
        }
        while (tree_nodes[2 * symbol] != -1);
        output[dst++] = (byte)symbol;
    }
    return output;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Tail/ArcCAF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
