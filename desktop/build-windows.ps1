$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$build = Join-Path $PSScriptRoot 'build'
$runtime = Join-Path $PSScriptRoot 'payload/python'
New-Item -ItemType Directory -Force $build,$runtime | Out-Null
$archive = Join-Path $build 'python-embed.zip'
Invoke-WebRequest 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-embed-amd64.zip' -OutFile $archive
if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLower() -ne '9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38') { throw 'Python archive checksum failed' }
Expand-Archive $archive -DestinationPath $runtime -Force
Set-Content -Encoding ascii (Join-Path $runtime 'python313._pth') "python313.zip`n.`n..`nLib/site-packages`nimport site`n"
python -m pip install --disable-pip-version-check --only-binary=:all: --target "$runtime/Lib/site-packages" 'playwright==1.64.1'
if ($LASTEXITCODE -ne 0) { throw 'Runtime dependencies failed' }
$compiler = "$env:WINDIR/Microsoft.NET/Framework64/v4.0.30319/csc.exe"
& $compiler /nologo /target:winexe /platform:x64 /optimize+ "/out:$build/MailAI.exe" "/win32icon:$PSScriptRoot/icon.ico" "/win32manifest:$PSScriptRoot/app.manifest" /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.Security.dll /reference:System.Web.Extensions.dll MailAI.cs AssemblyInfo.cs
if ($LASTEXITCODE -ne 0) { throw 'Desktop compilation failed' }
Copy-Item 'MailAI.exe.config' $build
python -m unittest discover -s . -p 'test_*.py'
if ($LASTEXITCODE -ne 0) { throw 'Email parsing tests failed' }
$env:MAILAI_DATA = Join-Path $env:RUNNER_TEMP 'MailAI-Layout-Data'
$env:MAILAI_SETUP_STAGE = '1'
$shot = Join-Path (Split-Path $PSScriptRoot) 'layout-screenshots'
$intent = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('{"activation_mode":"code","trigger_code":"0101","address":"demo.bot@gmail.com","allowed_sender":""}'))
$p = Start-Process "$build/MailAI.exe" -ArgumentList "--setup $intent --layout-test $shot" -PassThru
if (-not $p.WaitForExit(90000)) { $p.Kill(); throw 'Window layout check timed out' }
Get-Content "$shot/layout-result.json"
if ($p.ExitCode -ne 0) { throw 'Window layout overlap check failed' }
# Run the same isolated Python layout used by the installed app, without sys.path patches.
Copy-Item mailai.py,bot.py,thread_guard.py,web_reader.py (Split-Path $runtime)
$env:MAILAI_RUNTIME_APP = Split-Path $runtime
& "$runtime/python.exe" "$PSScriptRoot/runtime-self-test.py"
if ($LASTEXITCODE -ne 0) { throw 'Bundled Python/configuration integration failed' }
Remove-Item Env:MAILAI_DATA,Env:MAILAI_SETUP_STAGE,Env:MAILAI_RUNTIME_APP
$nsis = 'C:/Program Files (x86)/NSIS/makensis.exe'
if (-not (Test-Path $nsis)) { choco install nsis --yes --no-progress; if ($LASTEXITCODE -ne 0) { throw 'NSIS installation failed' } }
& $nsis /V2 installer.nsi
if ($LASTEXITCODE -ne 0) { throw 'Installer packaging failed' }
python package-parts.py
if ($LASTEXITCODE -ne 0) { throw 'Package integrity check failed' }
