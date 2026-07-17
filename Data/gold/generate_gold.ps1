# =========================================================
# generate_gold.ps1 - sinh gold sets tu Neo4j (quote = substring that)
# Chay:  powershell -File Data/gold/generate_gold.ps1
# Xuat: gold/citations.json, gold/links.json, gold/nli.json
# Nguyen tac: quote/premise lay truc tiep tu Khoan.noi_dung trong Neo4j
#            -> dam bao khop substring (validator BE) va nguon that.
# =========================================================
$ErrorActionPreference = 'Stop'
$env:Path = "C:\Program Files\Docker\Docker\resources\bin;" + $env:Path

$DIR = $PSScriptRoot
$NEO4J_PW = if ($env:NEO4J_PASSWORD) { $env:NEO4J_PASSWORD } else { 'change_me_neo4j' }

# --- Lay tat ca Khoan (delimiter ||| de tach an toan) ---
$q = "MATCH (k:Khoan) RETURN k.khoan_id + '|||' + coalesce(k.noi_dung,'') + '|||' + coalesce(k.van_ban_id,'') AS row ORDER BY k.khoan_id;"
$raw = $q | docker exec -i legal_neo4j cypher-shell -u neo4j -p $NEO4J_PW --format plain

$khoans = @()
foreach ($line in $raw) {
  $l = $line.Trim()
  if ($l -eq '' -or $l -eq 'row') { continue }
  $l = $l.Trim('"')                      # bo dau nhay cua --format plain
  $parts = $l -split '\|\|\|', 3
  if ($parts.Count -lt 2) { continue }
  $khoans += [pscustomobject]@{ khoan_id = $parts[0]; noi_dung = $parts[1]; van_ban_id = $parts[2] }
}
Write-Host ("Doc duoc {0} Khoan tu Neo4j" -f $khoans.Count)

# Lay 1 lat cat lien tuc (bo tu dau + tu cuoi) -> chac chan la substring
function Get-Quote($text) {
  $t = $text.TrimEnd('.', ';', ':')
  $w = $t -split ' '
  if ($w.Count -ge 4) { return ($w[1..($w.Count - 2)] -join ' ') }
  return $t
}

$citations = @()
$links = @()
$nli = @()
$labels = @('khop', 'mau_thuan', 'khong_ro')
$i = 0
foreach ($k in $khoans) {
  $quote = Get-Quote $k.noi_dung

  # citations.json: Q-A voi quote la substring nguyen van
  $citations += [ordered]@{
    id       = "qa-$($i+1)"
    question = "Quy dinh lien quan den noi dung tai khoan $($k.khoan_id) la gi?"
    answer   = "Theo $($k.van_ban_id): $($k.noi_dung)"
    citations = @(@{ khoan_id = $k.khoan_id; quote = $quote })
  }

  # links.json: bai MXH -> expected_khoan_ids
  $links += [ordered]@{
    id                 = "post-$($i+1)"
    platform           = @('facebook','youtube','forum')[$i % 3]
    content            = "Nghe noi $($quote). Dieu nay co dung khong?"
    expected_khoan_ids = @($k.khoan_id)
  }

  # nli.json: phan bo deu 3 nhan
  $label = $labels[$i % 3]
  switch ($label) {
    'khop'      { $hyp = $quote }                                   # phat bieu lai -> khop
    'mau_thuan' { $hyp = "Khong dung rang $($quote)." }              # phu dinh -> mau thuan
    'khong_ro'  { $hyp = "Van de nay chua duoc quy dinh ro rang." }  # mo ho -> khong ro
  }
  $nli += [ordered]@{
    id         = "nli-$($i+1)"
    khoan_id   = $k.khoan_id
    premise    = $k.noi_dung
    hypothesis = $hyp
    label      = $label
  }
  $i++
}

$enc = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $DIR 'citations.json'), ($citations | ConvertTo-Json -Depth 6), $enc)
[System.IO.File]::WriteAllText((Join-Path $DIR 'links.json'),     ($links     | ConvertTo-Json -Depth 6), $enc)
[System.IO.File]::WriteAllText((Join-Path $DIR 'nli.json'),       ($nli       | ConvertTo-Json -Depth 6), $enc)

Write-Host ("citations: {0} | links: {1} | nli: {2}" -f $citations.Count, $links.Count, $nli.Count)
Write-Host "DONE generate gold."
