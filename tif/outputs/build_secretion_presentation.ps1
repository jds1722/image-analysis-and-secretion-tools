param(
  [string]$OutputPath = "C:\Users\jds17\Documents\Codex\2026-06-17\tif\outputs\secretion_model_algorithm_presentation.pptx"
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$outDir = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$tmpRoot = Join-Path $outDir "secretion_pptx_build_tmp"
if (Test-Path $tmpRoot) {
  Remove-Item -LiteralPath $tmpRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $tmpRoot -Force | Out-Null

$slideW = 12192000
$slideH = 6858000
$emu = 9525

$global:shapeId = 1

function X([string]$s) {
  return [System.Security.SecurityElement]::Escape($s)
}

function Emu([double]$px) {
  return [int][Math]::Round($px * $script:emu)
}

function Font([double]$pt) {
  return [int][Math]::Round($pt * 100)
}

function ShapeXml {
  param(
    [string]$Name,
    [double]$X,
    [double]$Y,
    [double]$W,
    [double]$H,
    [string]$Text = "",
    [double]$FontSize = 18,
    [string]$Color = "1F2937",
    [string]$Fill = "",
    [string]$Line = "",
    [string]$Bold = "0",
    [string]$Align = "l",
    [string]$Valign = "mid",
    [string]$Bullet = "0",
    [string]$Geom = "rect",
    [int]$Margin = 10
  )
  $id = $global:shapeId
  $global:shapeId++
  $xEmu = Emu $X
  $yEmu = Emu $Y
  $wEmu = Emu $W
  $hEmu = Emu $H
  $fontSz = Font $FontSize
  $mar = Emu $Margin
  $fillXml = if ($Fill -eq "") {
    "<a:noFill/>"
  } else {
    "<a:solidFill><a:srgbClr val=`"$Fill`"/></a:solidFill>"
  }
  $lineXml = if ($Line -eq "") {
    "<a:ln><a:noFill/></a:ln>"
  } else {
    "<a:ln w=`"12700`"><a:solidFill><a:srgbClr val=`"$Line`"/></a:solidFill></a:ln>"
  }

  $paragraphs = ""
  if ($Text -ne "") {
    $lines = $Text -split "`n"
    foreach ($lineText in $lines) {
      $bu = if ($Bullet -eq "1") { '<a:buChar char="&#8226;"/>' } else { "" }
      $paragraphs += @"
<a:p><a:pPr algn="$Align">$bu</a:pPr><a:r><a:rPr lang="ko-KR" sz="$fontSz" b="$Bold"><a:solidFill><a:srgbClr val="$Color"/></a:solidFill><a:latin typeface="Aptos"/><a:ea typeface="Malgun Gothic"/></a:rPr><a:t>$(X $lineText)</a:t></a:r><a:endParaRPr lang="ko-KR" sz="$fontSz"/></a:p>
"@
    }
  } else {
    $paragraphs = "<a:p/>"
  }

  return @"
<p:sp>
  <p:nvSpPr><p:cNvPr id="$id" name="$(X $Name)"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr>
    <a:xfrm><a:off x="$xEmu" y="$yEmu"/><a:ext cx="$wEmu" cy="$hEmu"/></a:xfrm>
    <a:prstGeom prst="$Geom"><a:avLst/></a:prstGeom>
    $fillXml
    $lineXml
  </p:spPr>
  <p:txBody>
    <a:bodyPr wrap="square" anchor="$Valign" lIns="$mar" rIns="$mar" tIns="$mar" bIns="$mar"/>
    <a:lstStyle/>
    $paragraphs
  </p:txBody>
</p:sp>
"@
}

function AddTitle {
  param([string]$Title, [string]$Eyebrow = "")
  $xml = ""
  if ($Eyebrow -ne "") {
    $xml += ShapeXml -Name "eyebrow" -X 64 -Y 42 -W 460 -H 26 -Text $Eyebrow -FontSize 13 -Color "0B7285" -Bold "1" -Valign "mid"
  }
  $xml += ShapeXml -Name "title" -X 64 -Y 76 -W 1120 -H 54 -Text $Title -FontSize 35 -Color "102A43" -Bold "1" -Valign "mid"
  $xml += ShapeXml -Name "title-rule" -X 64 -Y 142 -W 190 -H 5 -Fill "0B7285" -Line "0B7285"
  return $xml
}

function Footer {
  param([int]$Num)
  return ShapeXml -Name "footer" -X 64 -Y 680 -W 1120 -H 20 -Text "Secretion-model algorithm  |  $Num" -FontSize 10 -Color "64748B" -Valign "mid"
}

function SlideXml {
  param([string]$Content)
  return @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:bg><p:bgPr><a:solidFill><a:srgbClr val="F8FAFC"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
      $Content
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>
"@
}

function Box {
  param([double]$X,[double]$Y,[double]$W,[double]$H,[string]$Header,[string]$Body,[string]$Fill="FFFFFF",[string]$Accent="0B7285")
  $xml = ShapeXml -Name "box-bg" -X $X -Y $Y -W $W -H $H -Fill $Fill -Line "CBD5E1"
  $xml += ShapeXml -Name "box-header" -X ($X+16) -Y ($Y+14) -W ($W-32) -H 30 -Text $Header -FontSize 20 -Color $Accent -Bold "1"
  $xml += ShapeXml -Name "box-body" -X ($X+16) -Y ($Y+54) -W ($W-32) -H ($H-66) -Text $Body -FontSize 16 -Color "334155" -Valign "top"
  return $xml
}

function FlowBox {
  param([double]$X,[double]$Y,[double]$W,[double]$H,[string]$Text,[string]$Fill,[string]$Color="FFFFFF")
  return ShapeXml -Name "flow" -X $X -Y $Y -W $W -H $H -Text $Text -FontSize 17 -Color $Color -Fill $Fill -Line $Fill -Bold "1" -Align "ctr"
}

$slides = @()

$s = ""
$s += ShapeXml -Name "title-band" -X 0 -Y 0 -W 1280 -H 720 -Fill "F8FAFC" -Line "F8FAFC"
$s += ShapeXml -Name "accent" -X 0 -Y 0 -W 22 -H 720 -Fill "0B7285" -Line "0B7285"
$s += ShapeXml -Name "deck-title" -X 84 -Y 170 -W 920 -H 130 -Text "Secretion-model`nAlgorithm Presentation" -FontSize 50 -Color "102A43" -Bold "1" -Valign "mid"
$s += ShapeXml -Name "deck-subtitle" -X 88 -Y 335 -W 920 -H 88 -Text "A morphology-only deep learning pipeline for classifying high vs. low secretors from multilayer TIFF images" -FontSize 24 -Color "475569"
$s += ShapeXml -Name "takeaway" -X 86 -Y 500 -W 780 -H 54 -Text "Key message: bead fluorescence is used only to create a mask, then removed from the model input." -FontSize 18 -Color "0F172A" -Fill "E0F2FE" -Line "7DD3FC"
$s += Footer 1
$slides += SlideXml $s

$s = AddTitle -Title "1. Problem definition" -Eyebrow "Problem Definition"
$s += Box -X 70 -Y 190 -W 350 -H 310 -Header "Input" -Body "- Multilayer TIFF image`n- Layer 0: brightfield (BF)`n- Layer 1: nucleus fluorescence`n- Layer 5/7: bead fluorescence" -Fill "FFFFFF"
$s += Box -X 465 -Y 190 -W 350 -H 310 -Header "Goal" -Body "- Classify each cell or image by secretion phenotype`n- Low secretor vs. high secretor`n- Avoid a model that simply memorizes bead signal" -Fill "FFFFFF"
$s += Box -X 860 -Y 190 -W 350 -H 310 -Header "Output" -Body "- predicted_label`n- prob_low, prob_high`n- Training metrics: accuracy and AUROC" -Fill "FFFFFF"
$s += Footer 2
$slides += SlideXml $s

$s = AddTitle -Title "2. Layer usage strategy" -Eyebrow "Input Design"
$s += ShapeXml -Name "table-head" -X 96 -Y 180 -W 1088 -H 48 -Text "Role of each TIFF layer" -FontSize 24 -Color "FFFFFF" -Fill "102A43" -Line "102A43" -Bold "1" -Align "ctr"
$rows = @(
  @("Layer 0", "Brightfield", "Model input", "Cell shape and well morphology"),
  @("Layer 1", "Nucleus", "Model input", "Cell presence from nuclear signal"),
  @("Layer 5", "INS bead", "Mask only", "Detect bead locations"),
  @("Layer 7", "GCG bead", "Mask only", "Detect bead locations")
)
$y = 242
foreach ($r in $rows) {
  $fill = if (($y/62)%2 -lt 1) { "FFFFFF" } else { "EFF6FF" }
  $s += ShapeXml -Name "row" -X 96 -Y $y -W 1088 -H 56 -Fill $fill -Line "CBD5E1"
  $s += ShapeXml -Name "c1" -X 116 -Y ($y+10) -W 130 -H 32 -Text $r[0] -FontSize 17 -Color "0F172A" -Bold "1"
  $s += ShapeXml -Name "c2" -X 270 -Y ($y+10) -W 210 -H 32 -Text $r[1] -FontSize 17 -Color "334155"
  $s += ShapeXml -Name "c3" -X 520 -Y ($y+10) -W 180 -H 32 -Text $r[2] -FontSize 17 -Color "0B7285" -Bold "1"
  $s += ShapeXml -Name "c4" -X 730 -Y ($y+10) -W 410 -H 32 -Text $r[3] -FontSize 17 -Color "334155"
  $y += 62
}
$s += ShapeXml -Name "callout" -X 130 -Y 545 -W 1020 -H 52 -Text "Design principle: bead fluorescence can reveal the secretion readout, so it is excluded from model input and used only for masking." -FontSize 18 -Color "0F172A" -Fill "FEF3C7" -Line "F59E0B"
$s += Footer 3
$slides += SlideXml $s

$s = AddTitle -Title "3. Preprocessing algorithm" -Eyebrow "Image Processing"
$x = 70
$steps = @(
  @("Read TIFF", "layers x H x W", "0B7285"),
  @("Bead mask", "max(layer5, layer7)", "0284C7"),
  @("Clean mask", "percentile threshold`nremove small objects`ndilation", "2563EB"),
  @("Remove bead", "median-fill mask area`nin BF / nucleus", "7C3AED"),
  @("Normalize", "0.5-99.5 percentile`nrobust normalize", "DB2777"),
  @("2-channel input", "[BF, nucleus]", "16A34A")
)
foreach ($step in $steps) {
  $s += FlowBox -X $x -Y 230 -W 165 -H 112 -Text ($step[0] + "`n" + $step[1]) -Fill $step[2]
  if ($x -lt 940) {
    $s += ShapeXml -Name "arrow" -X ($x+166) -Y 272 -W 36 -H 28 -Text "->" -FontSize 28 -Color "64748B" -Bold "1" -Align "ctr"
  }
  $x += 195
}
$s += Box -X 100 -Y 430 -W 500 -H 135 -Header "Bead mask creation" -Body "The maximum of INS and GCG bead layers is thresholded at a high percentile. Small objects are removed and dilation stabilizes the mask." -Fill "FFFFFF"
$s += Box -X 680 -Y 430 -W 500 -H 135 -Header "Model input creation" -Body "Masked bead pixels are median-filled in BF and nucleus layers, then robust-normalized. The final input is a 2-channel tensor." -Fill "FFFFFF"
$s += Footer 4
$slides += SlideXml $s

$s = AddTitle -Title "4. Why bead leakage must be controlled" -Eyebrow "Leakage Control"
$s += Box -X 88 -Y 185 -W 500 -H 330 -Header "Risk" -Body "Bead fluorescence is directly connected to the secretion readout. If the model sees these channels, it can learn a shortcut based on bead intensity rather than morphology." -Fill "FFFFFF" -Accent "DC2626"
$s += Box -X 690 -Y 185 -W 500 -H 330 -Header "Solution" -Body "Layers 5 and 7 are used only to find bead positions. Those positions are median-filled in BF and nucleus images before the tensor reaches the model." -Fill "FFFFFF" -Accent "16A34A"
$s += ShapeXml -Name "principle" -X 190 -Y 565 -W 900 -H 46 -Text "This encourages the classifier to use cell shape and nuclear signal instead of direct fluorescence intensity." -FontSize 18 -Color "0F172A" -Fill "DCFCE7" -Line "86EFAC"
$s += Footer 5
$slides += SlideXml $s

$s = AddTitle -Title "5. Dataset construction and split" -Eyebrow "Data Pipeline"
$s += FlowBox -X 160 -Y 220 -W 210 -H 88 -Text "data/raw/high`ndata/raw/low" -Fill "0B7285"
$s += ShapeXml -Name "arrow1" -X 388 -Y 246 -W 52 -H 28 -Text "->" -FontSize 30 -Color "64748B" -Bold "1" -Align "ctr"
$s += FlowBox -X 465 -Y 220 -W 210 -H 88 -Text "manifest.csv`npath, label, split" -Fill "2563EB"
$s += ShapeXml -Name "arrow2" -X 693 -Y 246 -W 52 -H 28 -Text "->" -FontSize 30 -Color "64748B" -Bold "1" -Align "ctr"
$s += FlowBox -X 770 -Y 220 -W 210 -H 88 -Text "train / val / test`nstratified split" -Fill "7C3AED"
$s += Box -X 130 -Y 390 -W 460 -H 145 -Header "Label encoding" -Body "low -> 0`nhigh -> 1`nLabels become class indices for CrossEntropyLoss during training." -Fill "FFFFFF"
$s += Box -X 690 -Y 390 -W 460 -H 145 -Header "Resize" -Body "The model input is resized to 224 x 224, matching the conventional ResNet image-classification setup." -Fill "FFFFFF"
$s += Footer 6
$slides += SlideXml $s

$s = AddTitle -Title "6. Model architecture: modified ResNet18" -Eyebrow "Architecture"
$s += FlowBox -X 95 -Y 225 -W 190 -H 100 -Text "2-channel image`nBF + nucleus" -Fill "0B7285"
$s += ShapeXml -Name "arr" -X 302 -Y 260 -W 40 -H 28 -Text "->" -FontSize 30 -Color "64748B" -Bold "1" -Align "ctr"
$s += FlowBox -X 365 -Y 225 -W 210 -H 100 -Text "conv1 change`n3ch -> 2ch" -Fill "2563EB"
$s += ShapeXml -Name "arr" -X 592 -Y 260 -W 40 -H 28 -Text "->" -FontSize 30 -Color "64748B" -Bold "1" -Align "ctr"
$s += FlowBox -X 655 -Y 225 -W 210 -H 100 -Text "ResNet18 blocks`nresidual learning" -Fill "7C3AED"
$s += ShapeXml -Name "arr" -X 882 -Y 260 -W 40 -H 28 -Text "->" -FontSize 30 -Color "64748B" -Bold "1" -Align "ctr"
$s += FlowBox -X 945 -Y 225 -W 210 -H 100 -Text "FC layer`n2 classes" -Fill "16A34A"
$s += Box -X 110 -Y 415 -W 470 -H 125 -Header "Pretrained option" -Body "When pretrained=True, RGB conv1 weights are averaged across channels and copied into the 2-channel first convolution." -Fill "FFFFFF"
$s += Box -X 700 -Y 415 -W 470 -H 125 -Header "Output" -Body "The final fully connected layer produces two logits. Prediction converts them to prob_low and prob_high with softmax." -Fill "FFFFFF"
$s += Footer 7
$slides += SlideXml $s

$s = AddTitle -Title "7. Training algorithm" -Eyebrow "Optimization"
$s += Box -X 80 -Y 185 -W 330 -H 280 -Header "Training setup" -Body "- optimizer: AdamW`n- loss: CrossEntropyLoss`n- epochs: default 40`n- batch size: default 32`n- learning rate: 3e-4" -Fill "FFFFFF"
$s += Box -X 475 -Y 185 -W 330 -H 280 -Header "Validation metrics" -Body "- accuracy`n- AUROC`n- best checkpoint selected by validation AUROC`n- accuracy fallback if AUROC is unavailable" -Fill "FFFFFF"
$s += Box -X 870 -Y 185 -W 330 -H 280 -Header "Saved outputs" -Body "- best_model.pt`n- history.json`n- test_metrics.json`n- config-driven reproducibility" -Fill "FFFFFF"
$s += ShapeXml -Name "note" -X 130 -Y 545 -W 1020 -H 52 -Text "Presentation point: train/val/test are separated, and the test set is used only for final performance reporting." -FontSize 18 -Color "0F172A" -Fill "E0F2FE" -Line "7DD3FC"
$s += Footer 8
$slides += SlideXml $s

$s = AddTitle -Title "8. Prediction algorithm" -Eyebrow "Inference"
$x = 150
$predSteps = @(
  @("checkpoint load", "best_model.pt", "0B7285"),
  @("same preprocess", "bead mask + normalize", "2563EB"),
  @("forward pass", "ResNet18 logits", "7C3AED"),
  @("softmax", "prob_low / prob_high", "DB2777"),
  @("CSV output", "predicted_label", "16A34A")
)
foreach ($step in $predSteps) {
  $s += FlowBox -X $x -Y 235 -W 170 -H 100 -Text ($step[0] + "`n" + $step[1]) -Fill $step[2]
  if ($x -lt 910) {
    $s += ShapeXml -Name "arrow" -X ($x+178) -Y 270 -W 38 -H 28 -Text "->" -FontSize 28 -Color "64748B" -Bold "1" -Align "ctr"
  }
  $x += 205
}
$s += Box -X 180 -Y 450 -W 920 -H 100 -Header "Important point" -Body "Training and prediction use the same preprocessing. This keeps the inference input distribution aligned with what the model saw during training." -Fill "FFFFFF"
$s += Footer 9
$slides += SlideXml $s

$s = AddTitle -Title "9. Why ResNet18?" -Eyebrow "Model Choice"
$s += Box -X 78 -Y 180 -W 350 -H 340 -Header "Strong baseline for small datasets" -Body "ResNet18 is not too large, so it is less likely to overfit than heavier CNNs and is easy to explain as a first microscopy-classification baseline." -Fill "FFFFFF"
$s += Box -X 465 -Y 180 -W 350 -H 340 -Header "Residual connection" -Body "Skip connections stabilize gradient flow and make deeper CNN training more reliable." -Fill "FFFFFF"
$s += Box -X 852 -Y 180 -W 350 -H 340 -Header "Transfer learning option" -Body "The model can use pretrained weights. Only the first convolution needs to be adapted from 3 channels to 2 channels." -Fill "FFFFFF"
$s += ShapeXml -Name "summary" -X 160 -Y 575 -W 960 -H 44 -Text "Summary: ResNet18 balances performance, stability, interpretability, and implementation complexity." -FontSize 20 -Color "FFFFFF" -Fill "102A43" -Line "102A43" -Bold "1" -Align "ctr"
$s += Footer 10
$slides += SlideXml $s

$s = AddTitle -Title "10. Take-home message" -Eyebrow "Summary"
$s += ShapeXml -Name "big" -X 100 -Y 175 -W 1080 -H 74 -Text "The model is designed to predict high/low secretion phenotype from morphology, without directly seeing bead intensity." -FontSize 25 -Color "102A43" -Bold "1" -Fill "E0F2FE" -Line "7DD3FC"
$s += Box -X 95 -Y 310 -W 330 -H 210 -Header "Strengths" -Body "- leakage control design`n- reproducible preprocessing`n- compact binary classifier" -Fill "FFFFFF" -Accent "16A34A"
$s += Box -X 475 -Y 310 -W 330 -H 210 -Header "Checks needed" -Body "- sample size and class balance`n- well-position or plate-batch bias`n- external validation" -Fill "FFFFFF" -Accent "F59E0B"
$s += Box -X 855 -Y 310 -W 330 -H 210 -Header "Next steps" -Body "- inspect rationale with Grad-CAM`n- compare against baseline models`n- relate bead-overlap QC to performance" -Fill "FFFFFF" -Accent "2563EB"
$s += Footer 11
$slides += SlideXml $s

$contentTypes = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
"@
for ($i=1; $i -le $slides.Count; $i++) {
  $contentTypes += "  <Override PartName=`"/ppt/slides/slide$i.xml`" ContentType=`"application/vnd.openxmlformats-officedocument.presentationml.slide+xml`"/>`n"
}
$contentTypes += "</Types>"

New-Item -ItemType Directory -Path (Join-Path $tmpRoot "_rels") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $tmpRoot "docProps") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $tmpRoot "ppt\_rels") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $tmpRoot "ppt\slides\_rels") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $tmpRoot "ppt\theme") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $tmpRoot "ppt\slideMasters\_rels") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $tmpRoot "ppt\slideLayouts\_rels") -Force | Out-Null

Set-Content -LiteralPath (Join-Path $tmpRoot "[Content_Types].xml") -Value $contentTypes -Encoding UTF8

Set-Content -LiteralPath (Join-Path $tmpRoot "_rels\.rels") -Value @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"@ -Encoding UTF8

$created = (Get-Date).ToUniversalTime().ToString("s") + "Z"
Set-Content -LiteralPath (Join-Path $tmpRoot "docProps\core.xml") -Value @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Secretion-model algorithm presentation</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">$created</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">$created</dcterms:modified>
</cp:coreProperties>
"@ -Encoding UTF8

Set-Content -LiteralPath (Join-Path $tmpRoot "docProps\app.xml") -Value @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft PowerPoint</Application>
  <PresentationFormat>On-screen Show (16:9)</PresentationFormat>
  <Slides>$($slides.Count)</Slides>
  <Notes>0</Notes>
  <HiddenSlides>0</HiddenSlides>
  <ScaleCrop>false</ScaleCrop>
</Properties>
"@ -Encoding UTF8

$slideIdList = ""
$rels = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
"@
for ($i=1; $i -le $slides.Count; $i++) {
  $rid = $i + 2
  $sid = 255 + $i
  $slideIdList += "    <p:sldId id=`"$sid`" r:id=`"rId$rid`"/>`n"
  $rels += "  <Relationship Id=`"rId$rid`" Type=`"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide`" Target=`"slides/slide$i.xml`"/>`n"
}
$rels += "</Relationships>"

Set-Content -LiteralPath (Join-Path $tmpRoot "ppt\presentation.xml") -Value @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:sldIdLst>
$slideIdList  </p:sldIdLst>
  <p:sldSz cx="$slideW" cy="$slideH" type="wide"/>
  <p:notesSz cx="6858000" cy="9144000"/>
  <p:defaultTextStyle/>
</p:presentation>
"@ -Encoding UTF8

Set-Content -LiteralPath (Join-Path $tmpRoot "ppt\_rels\presentation.xml.rels") -Value $rels -Encoding UTF8

Set-Content -LiteralPath (Join-Path $tmpRoot "ppt\theme\theme1.xml") -Value @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Secretion Theme">
  <a:themeElements>
    <a:clrScheme name="Secretion">
      <a:dk1><a:srgbClr val="102A43"/></a:dk1><a:lt1><a:srgbClr val="F8FAFC"/></a:lt1>
      <a:dk2><a:srgbClr val="1F2937"/></a:dk2><a:lt2><a:srgbClr val="FFFFFF"/></a:lt2>
      <a:accent1><a:srgbClr val="0B7285"/></a:accent1><a:accent2><a:srgbClr val="2563EB"/></a:accent2>
      <a:accent3><a:srgbClr val="16A34A"/></a:accent3><a:accent4><a:srgbClr val="F59E0B"/></a:accent4>
      <a:accent5><a:srgbClr val="DB2777"/></a:accent5><a:accent6><a:srgbClr val="7C3AED"/></a:accent6>
      <a:hlink><a:srgbClr val="2563EB"/></a:hlink><a:folHlink><a:srgbClr val="7C3AED"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="Secretion Fonts">
      <a:majorFont><a:latin typeface="Aptos Display"/><a:ea typeface="Malgun Gothic"/></a:majorFont>
      <a:minorFont><a:latin typeface="Aptos"/><a:ea typeface="Malgun Gothic"/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="Secretion Format"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst></a:fmtScheme>
  </a:themeElements>
  <a:objectDefaults/>
  <a:extraClrSchemeLst/>
</a:theme>
"@ -Encoding UTF8

Set-Content -LiteralPath (Join-Path $tmpRoot "ppt\slideMasters\slideMaster1.xml") -Value @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>
</p:sldMaster>
"@ -Encoding UTF8

Set-Content -LiteralPath (Join-Path $tmpRoot "ppt\slideMasters\_rels\slideMaster1.xml.rels") -Value @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>
"@ -Encoding UTF8

Set-Content -LiteralPath (Join-Path $tmpRoot "ppt\slideLayouts\slideLayout1.xml") -Value @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>
"@ -Encoding UTF8

Set-Content -LiteralPath (Join-Path $tmpRoot "ppt\slideLayouts\_rels\slideLayout1.xml.rels") -Value @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>
"@ -Encoding UTF8

for ($i=1; $i -le $slides.Count; $i++) {
  Set-Content -LiteralPath (Join-Path $tmpRoot "ppt\slides\slide$i.xml") -Value $slides[$i-1] -Encoding UTF8
  Set-Content -LiteralPath (Join-Path $tmpRoot "ppt\slides\_rels\slide$i.xml.rels") -Value @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>
"@ -Encoding UTF8
}

if (Test-Path $OutputPath) {
  Remove-Item -LiteralPath $OutputPath -Force
}

$fs = [System.IO.File]::Open($OutputPath, [System.IO.FileMode]::Create)
try {
  $zip = New-Object System.IO.Compression.ZipArchive($fs, [System.IO.Compression.ZipArchiveMode]::Create)
  try {
    Get-ChildItem -LiteralPath $tmpRoot -Recurse -File | ForEach-Object {
      $relative = $_.FullName.Substring($tmpRoot.Length + 1).Replace("\", "/")
      $entry = $zip.CreateEntry($relative, [System.IO.Compression.CompressionLevel]::Optimal)
      $inStream = [System.IO.File]::OpenRead($_.FullName)
      try {
        $outStream = $entry.Open()
        try {
          $inStream.CopyTo($outStream)
        } finally {
          $outStream.Dispose()
        }
      } finally {
        $inStream.Dispose()
      }
    }
  } finally {
    $zip.Dispose()
  }
} finally {
  $fs.Dispose()
}

$qaPath = Join-Path $outDir "secretion_model_algorithm_presentation_qa.txt"
$qa = @()
$qa += "PPTX generated: $OutputPath"
$qa += "Slide count: $($slides.Count)"
$qa += "Deck title font: 50 pt"
$qa += "Slide title font: 35 pt"
$qa += "Body text font: 16-18 pt"
$qa += "No external image assets used; content derived from local repository files."
$qa += "Main source files: src/preprocess.py, src/model.py, src/dataset.py, train.py, predict.py, configs/default.yaml"
Set-Content -LiteralPath $qaPath -Value ($qa -join "`r`n") -Encoding UTF8

Write-Output $OutputPath
