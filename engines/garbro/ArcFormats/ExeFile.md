# ArcFormats / ExeFile：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ExeFile.ExeFile` | `if (!file.View.AsciiEqual (0, "MZ"))` |
| `ExeFile.IsNe` | `uint ne_offset = View.ReadUInt32 (0x3C);` |
| `ExeFile.IsNe` | `return ne_offset < m_file.MaxOffset-2 && View.AsciiEqual (ne_offset, "NE");` |
| `ExeFile.GetCString` | `return View.ReadString (offset, (uint)(eos - offset), enc);` |
| `ExeFile.InitImageBase` | `if (View.ReadUInt16 (hdr_offset) != 0x010B)` |
| `ExeFile.InitImageBase` | `m_image_base = View.ReadUInt32 (hdr_offset+0x1C);` |
| `ExeFile.GetHeaderOffset` | `long pe_offset = View.ReadUInt32 (0x3C);` |
| `ExeFile.GetHeaderOffset` | `if (pe_offset >= m_file.MaxOffset-0x58 \|\| !View.AsciiEqual (pe_offset, "PE\0\0"))` |
| `ExeFile.InitSectionTable` | `int opt_header = View.ReadUInt16 (pe_offset+0x14);` |
| `ExeFile.InitSectionTable` | `long offset = View.ReadUInt32 (pe_offset+0x54);` |
| `ExeFile.InitSectionTable` | `int count = View.ReadUInt16 (pe_offset+6);` |
| `ExeFile.InitSectionTable` | `var name = View.ReadString (section_table, 8);` |
| `ExeFile.InitSectionTable` | `VirtualSize      = View.ReadUInt32 (section_table+0x08),` |
| `ExeFile.InitSectionTable` | `VirtualAddress   = View.ReadUInt32 (section_table+0x0C),` |
| `ExeFile.InitSectionTable` | `SizeOfRawData    = View.ReadUInt32 (section_table+0x10),` |
| `ExeFile.InitSectionTable` | `PointerToRawData = View.ReadUInt32 (section_table+0x14),` |
| `ExeFile.InitSectionTable` | `Characteristics  = View.ReadUInt32 (section_table+0x24),` |
| `ExeFile.InitNe` | `uint ne_offset = m_file.View.ReadUInt32 (0x3C);` |
| `ExeFile.InitNe` | `int segment_count = m_file.View.ReadUInt16 (ne_offset + 0x1C);` |
| `ExeFile.InitNe` | `uint seg_table = m_file.View.ReadUInt16 (ne_offset + 0x22) + ne_offset;` |
| `ExeFile.InitNe` | `int shift = m_file.View.ReadUInt16 (ne_offset + 0x32);` |
| `ExeFile.InitNe` | `uint offset = (uint)m_file.View.ReadUInt16 (seg_table) << shift;` |
| `ExeFile.InitNe` | `uint size   = m_file.View.ReadUInt16 (seg_table+2);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.ExeFile

#### 状态与常量

```csharp
ArcView                     m_file ;

Dictionary<string, Section> m_section_table ;

Section                     m_overlay ;

uint                        m_image_base = 0 ;

List<ImageSection>          m_section_list ;

bool?                       m_is_NE ;

public ArcView.Frame View { get { return m_file.View; } }

public Section Whole { get; private set; }

public bool IsWin16 => m_is_NE ?? (m_is_NE = IsNe()).Value;

public IReadOnlyDictionary<string, Section> Sections {
    get
    {
        if (null == m_section_table)
            InitSectionTable();
        return m_section_table;
    }
}

public Section Overlay {
    get
    {
        if (null == m_section_table)
            InitSectionTable();
        return m_overlay;
    }
}

public uint ImageBase {
    get
    {
        if (0 == m_image_base)
            InitImageBase();
        return m_image_base;
    }
}

static readonly byte[] ZeroByte = new byte[1] { 0 }
```

#### ExeFile

```csharp
public ExeFile (ArcView file) {
    if (!file.View.AsciiEqual (0, "MZ"))
        throw new InvalidFormatException ("File is not a valid win32 executable.");
    m_file = file;
    Whole = new Section { Offset = 0, Size = (uint)Math.Min (m_file.MaxOffset, uint.MaxValue) };
}
```

#### IsNe

```csharp
private bool IsNe () {
    uint ne_offset = View.ReadUInt32 (0x3C);
    return ne_offset < m_file.MaxOffset-2 && View.AsciiEqual (ne_offset, "NE");
}
```

#### ContainsSection

```csharp
public bool ContainsSection (string name) {
    return Sections.ContainsKey (name);
}
```

#### FindString

```csharp
public long FindString (Section section, byte[] seq, int step = 1) {
    if (step <= 0)
        throw new ArgumentOutOfRangeException ("step", "Search step should be positive integer.");
    long offset = section.Offset;
    if (offset < 0 || offset > m_file.MaxOffset)
        throw new ArgumentOutOfRangeException ("section", "Invalid executable file section specified.");
    uint seq_length = (uint)seq.Length;
    if (0 == seq_length || section.Size < seq_length)
        return -1;
    long end_offset = Math.Min (m_file.MaxOffset, offset + section.Size);
    unsafe
    {
        while (offset < end_offset)
        {
            uint page_size = (uint)Math.Min (0x10000L, end_offset - offset);
            if (page_size < seq_length)
                break;
            using (var view = m_file.CreateViewAccessor (offset, page_size))
            using (var ptr = new ViewPointer (view, offset))
            {
                byte* page_begin = ptr.Value;
                byte* page_end   = page_begin + page_size - seq_length;
                byte* p;
                for (p = page_begin; p <= page_end; p += step)
                {
                    int i = 0;
                    while (p[i] == seq[i])
                    {
                        if (++i == seq.Length)
                            return offset + (p - page_begin);
                    }
                }
                offset += p - page_begin;
            }
        }
    }
    return -1;
}
```

#### SectionByOffset

```csharp
public Section SectionByOffset (long offset) {
    foreach (var section in Sections.Values)
    {
        if (offset >= section.Offset && offset < section.Offset + section.Size)
            return section;
    }
    return new Section { Offset = Whole.Size, Size = 0 };
}
```

#### FindAsciiString

```csharp
public long FindAsciiString (Section section, string seq, int step = 1) {
    return FindString (section, Encoding.ASCII.GetBytes (seq), step);
}
```

#### FindSignature

```csharp
public long FindSignature (Section section, uint signature, int step = 4) {
    var bytes = new byte[4];
    LittleEndian.Pack (signature, bytes, 0);
    return FindString (section, bytes, step);
}
```

#### GetAddressOffset

```csharp
public long GetAddressOffset (uint address) {
    var section = GetAddressSection (address);
    if (null == section)
        return m_file.MaxOffset;
    uint rva = address - ImageBase;
    return section.PointerToRawData + (rva - section.VirtualAddress);
}
```

#### GetCString

```csharp
public string GetCString (uint address) {
    return GetCString (address, Encodings.cp932);
}
```

#### GetCString

```csharp
public string GetCString (uint address, Encoding enc) {
    var section = GetAddressSection (address);
    if (null == section)
        return null;
    uint rva = address - ImageBase;
    uint offset = section.PointerToRawData + (rva - section.VirtualAddress);
    uint size   = section.PointerToRawData + section.SizeOfRawData - offset;
    long eos = FindString (new Section { Offset = offset, Size = size }, ZeroByte);
    if (eos < 0)
        return null;
    return View.ReadString (offset, (uint)(eos - offset), enc);
}
```

#### GetAddressSection

```csharp
private ImageSection GetAddressSection (uint address) {
    var img_base = ImageBase;
    if (address < img_base)
        throw new ArgumentException ("Invalid virtual address.");
    if (null == m_section_list)
        InitSectionTable();
    uint rva = address - img_base;
    foreach (var section in m_section_list)
    {
        if (rva >= section.VirtualAddress && rva < section.VirtualAddress + section.SizeOfRawData)
            return section;
    }
    return null;
}
```

#### InitImageBase

```csharp
private void InitImageBase () {
    long hdr_offset = GetHeaderOffset() + 0x18;
    if (View.ReadUInt16 (hdr_offset) != 0x010B)
        throw new InvalidFormatException ("File is not a valid Windows 32-bit executable.");
    m_image_base = View.ReadUInt32 (hdr_offset+0x1C);
}
```

#### GetHeaderOffset

```csharp
private long GetHeaderOffset () {
    long pe_offset = View.ReadUInt32 (0x3C);
    if (pe_offset >= m_file.MaxOffset-0x58 || !View.AsciiEqual (pe_offset, "PE\0\0"))
        throw new InvalidFormatException ("File is not a valid Windows 32-bit executable.");
    return pe_offset;
}
```

#### InitSectionTable

```csharp
private void InitSectionTable () {
    if (IsWin16)
    {
        InitNe();
        return;
    }
    long pe_offset = GetHeaderOffset();
    int opt_header = View.ReadUInt16 (pe_offset+0x14);
    long section_table = pe_offset+opt_header+0x18;
    long offset = View.ReadUInt32 (pe_offset+0x54);
    int count = View.ReadUInt16 (pe_offset+6);
    var table = new Dictionary<string, Section> (count);
    var list = new List<ImageSection> (count);
    if (section_table + 0x28*count < m_file.MaxOffset)
    {
        for (int i = 0; i < count; ++i)
        {
            var name = View.ReadString (section_table, 8);
            var img_section = new ImageSection {
                Name = name,
                VirtualSize      = View.ReadUInt32 (section_table+0x08),
                VirtualAddress   = View.ReadUInt32 (section_table+0x0C),
                SizeOfRawData    = View.ReadUInt32 (section_table+0x10),
                PointerToRawData = View.ReadUInt32 (section_table+0x14),
                Characteristics  = View.ReadUInt32 (section_table+0x24),
            };
            var section = new Section {
                Offset = img_section.PointerToRawData,
                Size  = img_section.SizeOfRawData
            };
            list.Add (img_section);
            if (!table.ContainsKey (name))
                table.Add (name, section);
            if (0 != section.Size)
                offset = Math.Max (section.Offset + section.Size, offset);
            section_table += 0x28;
        }
    }
    offset = Math.Min ((offset + 0xF) & ~0xFL, m_file.MaxOffset);
    m_overlay.Offset = offset;
    m_overlay.Size = (uint)(m_file.MaxOffset - offset);
    m_section_table = table;
    m_section_list = list;
}
```

#### InitNe

```csharp
void InitNe () {
    uint ne_offset = m_file.View.ReadUInt32 (0x3C);
    int segment_count = m_file.View.ReadUInt16 (ne_offset + 0x1C);
    uint seg_table = m_file.View.ReadUInt16 (ne_offset + 0x22) + ne_offset;
    int shift = m_file.View.ReadUInt16 (ne_offset + 0x32);
    uint last_seg_end = 0;
    for (int i = 0; i < segment_count; ++i)
    {
        uint offset = (uint)m_file.View.ReadUInt16 (seg_table) << shift;
        uint size   = m_file.View.ReadUInt16 (seg_table+2);
        if (offset + size > last_seg_end)
            last_seg_end = offset + size;
    }
    m_overlay.Offset = last_seg_end;
    m_overlay.Size = (uint)(m_file.MaxOffset - last_seg_end);
    m_section_table = new Dictionary<string, Section>();
    m_section_list = new List<ImageSection>();
}
```

### GameRes.Formats.ExeFile.Section

#### 状态与常量

```csharp
public long Offset ;

public uint Size ;
```

### GameRes.Formats.ExeFile.ImageSection

#### 状态与常量

```csharp
public string   Name ;

public uint     VirtualSize ;

public uint     VirtualAddress ;

public uint     SizeOfRawData ;

public uint     PointerToRawData ;

public uint     Characteristics ;
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/ExeFile.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
