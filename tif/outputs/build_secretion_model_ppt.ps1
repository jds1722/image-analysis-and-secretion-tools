$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$FinalPptx = "C:\Users\jds17\Documents\Codex\2026-06-17\Secretion-model\outputs\secretion_model_algorithm_presentation.pptx"
$Scratch = Join-Path $env:TEMP "codex_secretion_model_ppt"
if (Test-Path $Scratch) {
    Remove-Item -LiteralPath $Scratch -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $Scratch | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Scratch "_rels") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Scratch "ppt\_rels") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Scratch "ppt\slides\_rels") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Scratch "ppt\slideMasters\_rels") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Scratch "ppt\slideLayouts\_rels") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Scratch "ppt\theme") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Scratch "docProps") | Out-Null

function XmlEscape([string]$Text) {
    if ($null -eq $Text) { return "" }
    return [System.Security.SecurityElement]::Escape($Text)
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

function Emu([double]$Inch) {
    return [int][Math]::Round($Inch * 914400)
}

function Pct([int]$Percent) {
    return $Percent * 1000
}

function ShapeXml(
    [int]$Id,
    [string]$Name,
    [double]$X,
    [double]$Y,
    [double]$W,
    [double]$H,
    [string]$Text,
    [int]$FontSize = 18,
    [string]$Color = "17324D",
    [string]$Fill = "FFFFFF",
    [string]$Line = "",
    [bool]$Bold = $false,
    [string]$Align = "l",
    [string]$ShapeType = "rect"
) {
    $xEmu = Emu $X
    $yEmu = Emu $Y
    $wEmu = Emu $W
    $hEmu = Emu $H
    $sz = $FontSize * 100
    $b = if ($Bold) { ' b="1"' } else { "" }
    $fillXml = if ($Fill -eq "none") {
        "<a:noFill/>"
    } else {
        "<a:solidFill><a:srgbClr val=""$Fill""/></a:solidFill>"
    }
    $lineXml = if ($Line -eq "none") {
        "<a:ln><a:noFill/></a:ln>"
    } elseif ($Line -ne "") {
        "<a:ln w=""12700""><a:solidFill><a:srgbClr val=""$Line""/></a:solidFill></a:ln>"
    } else {
        "<a:ln><a:noFill/></a:ln>"
    }
    $paragraphs = @()
    foreach ($lineText in ($Text -split "`n")) {
        $escaped = XmlEscape $lineText
        $paragraphs += "<a:p><a:pPr algn=""$Align""/><a:r><a:rPr lang=""en-US"" sz=""$sz"" dirty=""0""$b><a:solidFill><a:srgbClr val=""$Color""/></a:solidFill></a:rPr><a:t>$escaped</a:t></a:r><a:endParaRPr lang=""en-US"" sz=""$sz"" dirty=""0""/></a:p>"
    }
    $txBody = "<p:txBody><a:bodyPr wrap=""square"" lIns=""91440"" tIns=""45720"" rIns=""91440"" bIns=""45720"" anchor=""mid""/><a:lstStyle/>$($paragraphs -join '')</p:txBody>"
    return @"
<p:sp>
  <p:nvSpPr><p:cNvPr id="$Id" name="$Name"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="$xEmu" y="$yEmu"/><a:ext cx="$wEmu" cy="$hEmu"/></a:xfrm>
    <a:prstGeom prst="$ShapeType"><a:avLst/></a:prstGeom>
    $fillXml
    $lineXml
  </p:spPr>
  $txBody
</p:sp>
"@
}

function SlideXml([int]$SlideNo, [array]$Shapes) {
    return @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:bg><p:bgPr><a:solidFill><a:srgbClr val="F7F8FA"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
      $($Shapes -join "`n")
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>
"@
}

$slides = @(
    @{
        Title="Cell Secretor Classifier"
        Subtitle="Algorithm overview for multilayer nanowell TIFF images"
        Points=@("Goal: classify each ROI/image as low or high secretor", "Core idea: use morphology channels for prediction and bead channels only for masking/QC")
    },
    @{
        Title="1. Input And Label Setup"
        Subtitle="Each sample is one multilayer TIFF plus a binary label."
        Points=@("Manifest CSV stores path, label, and split: train / val / test", "Labels are mapped to two classes: low and high", "Images are read as layer x height x width arrays")
    },
    @{
        Title="2. Layer Usage"
        Subtitle="The model sees only BF and nucleus morphology."
        Points=@("Layer 0: brightfield (BF), used as model input", "Layer 1: nuclear fluorescence, used as model input", "Layer 5: INS beads, used only for bead masking", "Layer 7: GCG beads, used only for bead masking", "Layers 2, 3, 4, and 6 are ignored")
    },
    @{
        Title="3. Bead Masking"
        Subtitle="Bead signal is removed before the classifier sees the image."
        Points=@("bead_signal = maximum(INS bead layer, GCG bead layer)", "Threshold at the 99th percentile to identify bright bead regions", "Remove tiny objects, then dilate mask by 3 px", "Fill masked BF/nucleus pixels with the median intensity")
    },
    @{
        Title="4. Normalization And Input Tensor"
        Subtitle="After masking, each morphology channel is robustly normalized."
        Points=@("BF and nucleus are normalized independently", "Default range: 0.5th to 99.5th percentile", "Values are clipped and scaled to 0-1", "Final tensor shape: 2 channels x 224 x 224")
    },
    @{
        Title="5. Model Architecture"
        Subtitle="A ResNet18 backbone is adapted for two-channel microscopy input."
        Points=@("First convolution is changed from 3 input channels to 2", "Final fully connected layer is changed to 2 outputs", "Softmax converts logits into low/high probabilities", "Optional pretrained weights can initialize the backbone")
    },
    @{
        Title="6. Training Loop"
        Subtitle="Training optimizes binary classification and keeps the best validation model."
        Points=@("Loss: cross entropy", "Optimizer: AdamW", "Validation metrics: accuracy and AUROC", "Best checkpoint is saved as best_model.pt", "Test metrics are computed after training")
    },
    @{
        Title="7. Prediction Workflow"
        Subtitle="Inference repeats the same preprocessing and writes a CSV result."
        Points=@("Read each TIFF and create the same 2-channel input", "Load best_model.pt", "Run ResNet18 and apply softmax", "Output: path, predicted_label, prob_low, prob_high")
    },
    @{
        Title="Why ResNet18?"
        Subtitle="It is a practical baseline for limited microscopy datasets."
        Points=@("Small enough to train and test quickly", "Residual blocks handle deeper feature extraction without unstable training", "Strong image-classification baseline with widely understood behavior", "Can use pretrained initialization, while adapting input/output layers", "Good first model before comparing larger CNNs or ViTs")
    },
    @{
        Title="Key Message For The Talk"
        Subtitle="The pipeline intentionally separates morphology prediction from secretion-marker leakage."
        Points=@("BF + nucleus describe cell morphology", "INS/GCG bead layers are not passed to the classifier", "Bead channels are used only to remove artifacts and flag overlap QC", "The final prediction is a low/high secretor probability from a leakage-controlled input")
    }
)

for ($i = 0; $i -lt $slides.Count; $i++) {
    $s = $slides[$i]
    $shapes = @()
    $id = 2
    if ($i -eq 0) {
        $shapes += ShapeXml $id "Title" 0.75 1.25 11.8 1.1 $s.Title 54 "0B1F33" "none" "none" $true "c"; $id++
        $shapes += ShapeXml $id "Subtitle" 1.55 2.35 10.2 0.55 $s.Subtitle 24 "375A7F" "none" "none" $false "c"; $id++
        $shapes += ShapeXml $id "Accent" 4.6 3.2 4.15 0.08 "" 1 "FFFFFF" "2BB3A3" "none" $false "c"; $id++
        $y = 4.05
        foreach ($p in $s.Points) {
            $shapes += ShapeXml $id "Point$id" 1.55 $y 10.2 0.52 $p 19 "17324D" "FFFFFF" "D6DEE8" $false "c"; $id++
            $y += 0.68
        }
    } else {
        $shapes += ShapeXml $id "Title" 0.55 0.35 12.25 0.62 $s.Title 36 "0B1F33" "none" "none" $true "l"; $id++
        $shapes += ShapeXml $id "Subtitle" 0.62 1.02 11.7 0.42 $s.Subtitle 18 "45657F" "none" "none" $false "l"; $id++
        $shapes += ShapeXml $id "Rule" 0.62 1.55 12.05 0.04 "" 1 "FFFFFF" "2BB3A3" "none" $false "l"; $id++
        $y = 2.0
        foreach ($p in $s.Points) {
            $shapes += ShapeXml $id "Bullet$id" 0.95 $y 0.28 0.28 "" 1 "FFFFFF" "2BB3A3" "none" $false "c" "ellipse"; $id++
            $shapes += ShapeXml $id "Point$id" 1.35 ($y - 0.08) 10.95 0.46 $p 20 "17324D" "none" "none" $false "l"; $id++
            $y += 0.72
        }
        $slideNumber = "$($i + 1)"
        $shapes += ShapeXml $id "Footer" 11.85 6.85 0.8 0.28 $slideNumber 10 "8090A0" "none" "none" $false "r"; $id++
    }
    Write-Utf8NoBom (Join-Path $Scratch "ppt\slides\slide$($i + 1).xml") (SlideXml ($i + 1) $shapes)
    Write-Utf8NoBom (Join-Path $Scratch "ppt\slides\_rels\slide$($i + 1).xml.rels") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>
"@
}

$contentOverrides = @(
    '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
    '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
    '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
    '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>',
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
    '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
)
for ($i = 1; $i -le $slides.Count; $i++) {
    $contentOverrides += "<Override PartName=""/ppt/slides/slide$i.xml"" ContentType=""application/vnd.openxmlformats-officedocument.presentationml.slide+xml""/>"
}
Write-Utf8NoBom (Join-Path $Scratch "[Content_Types].xml") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  $($contentOverrides -join "`n  ")
</Types>
"@

Write-Utf8NoBom (Join-Path $Scratch "_rels\.rels") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"@

$slideIds = @()
$rels = @(
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>',
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>'
)
for ($i = 1; $i -le $slides.Count; $i++) {
    $relId = $i + 2
    $slideId = 255 + $i
    $slideIds += "<p:sldId id=""$slideId"" r:id=""rId$relId""/>"
    $rels += "<Relationship Id=""rId$relId"" Type=""http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"" Target=""slides/slide$i.xml""/>"
}
Write-Utf8NoBom (Join-Path $Scratch "ppt\presentation.xml") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:sldIdLst>
    $($slideIds -join "`n    ")
  </p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000" type="wide"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>
"@
Write-Utf8NoBom (Join-Path $Scratch "ppt\_rels\presentation.xml.rels") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  $($rels -join "`n  ")
</Relationships>
"@

Write-Utf8NoBom (Join-Path $Scratch "ppt\slideMasters\slideMaster1.xml") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>
</p:sldMaster>
"@
Write-Utf8NoBom (Join-Path $Scratch "ppt\slideMasters\_rels\slideMaster1.xml.rels") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>
"@
Write-Utf8NoBom (Join-Path $Scratch "ppt\slideLayouts\slideLayout1.xml") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>
"@
Write-Utf8NoBom (Join-Path $Scratch "ppt\slideLayouts\_rels\slideLayout1.xml.rels") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>
"@
Write-Utf8NoBom (Join-Path $Scratch "ppt\theme\theme1.xml") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="SecretionModel">
  <a:themeElements>
    <a:clrScheme name="SecretionModel">
      <a:dk1><a:srgbClr val="0B1F33"/></a:dk1><a:lt1><a:srgbClr val="F7F8FA"/></a:lt1>
      <a:dk2><a:srgbClr val="17324D"/></a:dk2><a:lt2><a:srgbClr val="FFFFFF"/></a:lt2>
      <a:accent1><a:srgbClr val="2BB3A3"/></a:accent1><a:accent2><a:srgbClr val="375A7F"/></a:accent2>
      <a:accent3><a:srgbClr val="F2B84B"/></a:accent3><a:accent4><a:srgbClr val="D84C4C"/></a:accent4>
      <a:accent5><a:srgbClr val="7A8CA3"/></a:accent5><a:accent6><a:srgbClr val="CED7E2"/></a:accent6>
      <a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Aptos"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme>
    <a:fmtScheme name="Clean"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme>
  </a:themeElements>
</a:theme>
"@
Write-Utf8NoBom (Join-Path $Scratch "docProps\core.xml") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Secretion Model Algorithm Presentation</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-06-24T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-06-24T00:00:00Z</dcterms:modified>
</cp:coreProperties>
"@
Write-Utf8NoBom (Join-Path $Scratch "docProps\app.xml") @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex</Application>
  <Slides>$($slides.Count)</Slides>
</Properties>
"@

if (Test-Path $FinalPptx) {
    Remove-Item -LiteralPath $FinalPptx -Force
}
[System.IO.Compression.ZipFile]::CreateFromDirectory($Scratch, $FinalPptx)
Write-Output $FinalPptx
