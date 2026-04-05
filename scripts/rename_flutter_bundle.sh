#!/bin/bash
# scripts/rename_flutter_bundle.sh
# Usage: ./scripts/rename_flutter_bundle.sh <old_bundle_id> <new_bundle_id>
# Run this from the root of the familyroots repository.

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <old_bundle_id> <new_bundle_id>"
    echo "Example: $0 com.example.family_roots_mobile com.microtecture.familyroots"
    exit 1
fi

OLD_ID=$1
NEW_ID=$2

OLD_PATH=$(echo "$OLD_ID" | tr '.' '/')
NEW_PATH=$(echo "$NEW_ID" | tr '.' '/')

echo "Renaming Flutter bundle ID from $OLD_ID to $NEW_ID in the 'mobile' directory..."

if [ ! -d "mobile" ]; then
    echo "Error: 'mobile' directory not found. Please run from the project root."
    exit 1
fi

cd mobile || exit 1

# Cross-platform sed for in-place editing
if [[ "$OSTYPE" == "darwin"* ]]; then
  SED_CMD="sed -i ''"
else
  SED_CMD="sed -i"
fi

# Files that commonly contain the bundle ID / Application ID
FILES_TO_MODIFY=(
  "macos/Runner/Configs/AppInfo.xcconfig"
  "macos/Runner.xcodeproj/project.pbxproj"
  "ios/Runner.xcodeproj/project.pbxproj"
  "linux/CMakeLists.txt"
  "android/app/build.gradle.kts"
  "android/app/build.gradle"
  "windows/runner/Runner.rc"
  "android/app/src/main/kotlin/$OLD_PATH/MainActivity.kt"
  "android/app/src/main/java/$OLD_PATH/MainActivity.java"
  "android/app/src/main/AndroidManifest.xml"
  "android/app/src/debug/AndroidManifest.xml"
  "android/app/src/profile/AndroidManifest.xml"
)

for FILE in "${FILES_TO_MODIFY[@]}"; do
  if [ -f "$FILE" ]; then
    echo "Updating $FILE..."
    $SED_CMD "s/$OLD_ID/$NEW_ID/g" "$FILE"
  fi
done

# Move Android Kotlin/Java source directories
for LANG in "kotlin" "java"; do
  if [ -d "android/app/src/main/$LANG/$OLD_PATH" ]; then
    echo "Moving Android $LANG directory from $OLD_PATH to $NEW_PATH..."
    mkdir -p "android/app/src/main/$LANG/$NEW_PATH"
    cp -r "android/app/src/main/$LANG/$OLD_PATH/"* "android/app/src/main/$LANG/$NEW_PATH/"
    rm -rf "android/app/src/main/$LANG/$OLD_PATH"
  fi
done

echo "Clean up cached build files..."
flutter clean
flutter pub get

echo "Done! Bundle ID successfully changed."