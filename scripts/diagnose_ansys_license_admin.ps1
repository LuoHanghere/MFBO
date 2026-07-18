$ErrorActionPreference = 'SilentlyContinue'
$out = 'E:\Work\BOfm\runs\kumar_periodic_v2\ansys_license_admin_diagnostic.txt'
$lines = [System.Collections.Generic.List[string]]::new()

$lines.Add('=== Services ===')
Get-CimInstance Win32_Service |
    Where-Object { $_.Name -match 'ansys|flex|license' -or $_.DisplayName -match 'ansys|flex|license' } |
    ForEach-Object {
        $lines.Add(('Name={0}; DisplayName={1}; State={2}; StartName={3}; PathName={4}' -f `
            $_.Name, $_.DisplayName, $_.State, $_.StartName, $_.PathName))
    }

$lines.Add('')
$lines.Add('=== Licensing processes ===')
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -in @('lmgrd.exe', 'ansyslmd.exe', 'ansysli_server.exe') } |
    ForEach-Object {
        $version = ''
        if ($_.ExecutablePath) {
            $version = (Get-Item -LiteralPath $_.ExecutablePath).VersionInfo.FileVersion
        }
        $lines.Add(('PID={0}; PPID={1}; Name={2}; Path={3}; Version={4}; CommandLine={5}' -f `
            $_.ProcessId, $_.ParentProcessId, $_.Name, $_.ExecutablePath, $version, $_.CommandLine))
    }

$lines.Add('')
$lines.Add('=== Listener 1055 ===')
Get-NetTCPConnection -LocalPort 1055 |
    ForEach-Object {
        $lines.Add(('Local={0}:{1}; State={2}; PID={3}' -f `
            $_.LocalAddress, $_.LocalPort, $_.State, $_.OwningProcess))
    }

$lines.Add('')
$lines.Add('=== CFD feature versions (signatures omitted) ===')
$lic = 'D:\Ansys\Shared Files\Licensing\license_files\ansyslmd.lic'
Get-Content -LiteralPath $lic |
    Where-Object { $_ -match '^INCREMENT\s+(cfd_base|cfd_solve_level1|cfd_solve_level2|anshpc_pack|1cfxmshpr|acfd)\s' } |
    ForEach-Object {
        $p = $_ -split '\s+'
        $lines.Add(('Feature={0}; Daemon={1}; Version={2}; Expiry={3}; Count={4}' -f `
            $p[1], $p[2], $p[3], $p[4], $p[5]))
    }

$parent = Split-Path -Parent $out
New-Item -ItemType Directory -Force -Path $parent | Out-Null
$lines | Set-Content -LiteralPath $out -Encoding UTF8
