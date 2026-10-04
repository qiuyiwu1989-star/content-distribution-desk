#!/bin/zsh
set -euo pipefail
PROJECT="${0:A:h:h}"
BUNDLE="$PROJECT/dist/内容分发台.app"
INSTALLED="$HOME/Applications/内容分发台.app"
mkdir -p "$BUNDLE/Contents/MacOS" "$BUNDLE/Contents/Resources"
PROJECT_PATH="$PROJECT" BUNDLE_PATH="$BUNDLE" /usr/bin/python3 - <<'PY'
import os, plistlib
from pathlib import Path
bundle=Path(os.environ['BUNDLE_PATH'])
info={'CFBundleName':'内容分发台','CFBundleDisplayName':'内容分发台','CFBundleIdentifier':'com.qiuyiwu.distributiondesk','CFBundleExecutable':'DistributionDesk','CFBundlePackageType':'APPL','CFBundleShortVersionString':'0.2.1','CFBundleVersion':'3','LSMinimumSystemVersion':'13.0','NSHighResolutionCapable':True,'DeskProjectPath':os.environ['PROJECT_PATH'],'CFBundleIconFile':'DistributionDesk.icns'}
with (bundle/'Contents/Info.plist').open('wb') as file:plistlib.dump(info,file)
PY
/usr/bin/swiftc -swift-version 5 -O -framework AppKit -framework WebKit "$PROJECT/mac-app/main.swift" -o "$BUNDLE/Contents/MacOS/DistributionDesk"
"$PROJECT/.venv/bin/python" "$PROJECT/mac-app/icon.py" "$BUNDLE/Contents/Resources/DistributionDesk.icns"
RESOURCE="$BUNDLE/Contents/Resources/Project"
mkdir -p "$RESOURCE/mac-app" "$RESOURCE/integrations"
for file in server.py distribution.py site_import.py adapters.py platform_rules.py wechat_bridge.py requirements.txt; do /bin/cp "$PROJECT/$file" "$RESOURCE/$file"; done
/usr/bin/rsync -a --delete "$PROJECT/static/" "$RESOURCE/static/"
/usr/bin/rsync -a --delete "$PROJECT/.venv/" "$RESOURCE/.venv/"
# Keep Python entry points inside the app instead of external symbolic links.
for runtime in .venv; do
  /bin/cp -L "$RESOURCE/$runtime/bin/python3" "$RESOURCE/$runtime/bin/python3.bundle"
  /bin/mv -f "$RESOURCE/$runtime/bin/python3.bundle" "$RESOURCE/$runtime/bin/python3"
done
/bin/cp "/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/Python3" "$RESOURCE/.venv/Python3"
/usr/bin/ditto "/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app" "$RESOURCE/.venv/Resources/Python.app"
/bin/cp "$PROJECT/mac-app/run-server.sh" "$RESOURCE/mac-app/run-server.sh"
chmod +x "$BUNDLE/Contents/MacOS/DistributionDesk" "$RESOURCE/mac-app/run-server.sh"
if [[ "${DESK_STAGE_ONLY:-0}" == "1" ]]; then
  printf 'Staged %s (installed app left running and unchanged)\n' "$BUNDLE"
  exit 0
fi
SUPPORT="$HOME/Library/Application Support/内容分发台"
mkdir -p "$SUPPORT/runtime/.sau-venv" "$SUPPORT/runtime/social-auto-upload"
/usr/bin/rsync -a "$PROJECT/.sau-venv/" "$SUPPORT/runtime/.sau-venv/"
/usr/bin/rsync -a "$PROJECT/integrations/social-auto-upload/" "$SUPPORT/runtime/social-auto-upload/"
mkdir -p "$HOME/Applications"
/usr/bin/ditto "$BUNDLE" "$INSTALLED"
/usr/bin/codesign --force --deep --sign - "$INSTALLED"
/usr/bin/codesign --verify --deep --strict "$INSTALLED"
PROJECT_PATH="$PROJECT" "$PROJECT/.venv/bin/python" "$PROJECT/mac-app/migrate_data.py"
printf 'Installed %s\n' "$INSTALLED"
