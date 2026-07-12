# Flutter Build & Publish Guide

**FamilyRoots — From Local Machine to App Store & Google Play**

---

## PART 1 — LOCAL ENVIRONMENT SETUP

### Step 1.1 — Install Flutter SDK

```bash
# macOS (via Homebrew)
brew install --cask flutter

# Or download directly:
# https://docs.flutter.dev/get-started/install

# Verify installation
flutter doctor
```

Expected `flutter doctor` output:

```
[✓] Flutter (Channel stable, 3.x.x)
[✓] Android toolchain - develop for Android devices
[✓] Xcode - develop for iOS and macOS
[✓] Chrome - develop for the web
[✓] Android Studio
[✓] VS Code
[✓] Connected device
```

Fix any `[✗]` or `[!]` items before continuing. Most issues have direct fix instructions in the output.

### Step 1.2 — Install Android Studio (for Android)

1. Download Android Studio: https://developer.android.com/studio
2. Open Android Studio → Settings → SDK Manager and install:
   - Android SDK Platform 34 (Android 14) or higher
   - Android SDK Build-Tools
   - Android Emulator
3. Accept SDK licenses:

```bash
flutter doctor --android-licenses
# Press 'y' to accept all prompts
```

### Step 1.3 — Install Xcode (for iOS — macOS only)

1. Download Xcode from the Mac App Store (~15 GB, free)
2. Open Xcode once to complete initial setup
3. Install command line tools:

```bash
sudo xcode-select --install
sudo xcodebuild -runFirstLaunch
```

4. Install CocoaPods (iOS dependency manager):

```bash
sudo gem install cocoapods
# Or via Homebrew:
brew install cocoapods
```

### Step 1.4 — Install VS Code Extensions

- **Flutter** (by Dart Code)
- **Dart** (by Dart Code)
- **Pubspec Assist** (optional but useful for managing dependencies)

---

## PART 2 — RUNNING THE APP LOCALLY

### Step 2.1 — Install Dependencies

```bash
# Navigate to the mobile project
cd mobile
flutter pub get
```

> **Note:** `web/` is a Next.js project, not Flutter — its dependencies are
> installed with `pnpm install` (see the onboarding guide).

### Step 2.2 — Create a .env File

```bash
cd mobile
cp .env.example .env
# Fill in the actual values:
# API_BASE_URL=http://localhost:8000/api/v1
# SUPABASE_URL=https://xxxx.supabase.co
# ...
```

### Step 2.3 — Run on Android Emulator

```bash
# Create a Virtual Device in Android Studio:
# Android Studio → Device Manager → Create Device
# Recommended: Pixel 8, Android 14 (API 34)

# Confirm emulator is running
flutter devices
# Example output: emulator-5554 • Android SDK built for x86_64 • android-x64

# Run the app
cd mobile
flutter run

# Or target a specific device
flutter run -d emulator-5554
```

### Step 2.4 — Run on iOS Simulator (macOS only)

```bash
# Open iOS Simulator
open -a Simulator

# Confirm simulator is detected
flutter devices
# Example output: iPhone 15 Pro • iOS 17.x

# Run the app
flutter run -d "iPhone 15 Pro"
```

### Step 2.5 — Run on a Physical Android Device

1. On your Android phone: Settings → About Phone → tap "Build Number" 7 times to enable Developer Mode
2. Go to Settings → Developer Options → Enable USB Debugging
3. Connect the phone via USB and allow the connection when prompted

```bash
flutter devices   # Your phone should appear in the list
flutter run       # Automatically targets the physical device
```

### Step 2.6 — Run on a Physical iPhone (macOS only)

1. Connect your iPhone to your Mac via USB
2. Open Xcode → Window → Devices and Simulators → Trust the device
3. Sign in with your Apple ID: Xcode → Settings → Accounts
4. Open `mobile/ios/Runner.xcworkspace` in Xcode → select your Team → click Build

Or run directly from the terminal:

```bash
flutter run -d "Your iPhone Name"
```

> **Note:** A free Apple Developer account works, but apps installed this way expire after 7 days and must be reinstalled.

### Step 2.7 — Hot Reload & Hot Restart

While the app is running in your terminal:

| Key | Action |
|-----|--------|
| `r` | Hot Reload — updates UI instantly, preserves state |
| `R` | Hot Restart — restarts the app, resets state |
| `q` | Quit |

---

## PART 3 — BUILDING FOR RELEASE (APK / IPA)

### Step 3.1 — Build Android APK (for internal testing)

```bash
cd mobile

# Debug build (quick testing)
flutter build apk --debug

# Release build (for distribution)
flutter build apk --release
# Output: build/app/outputs/flutter-apk/app-release.apk

# Install directly to a connected Android device
flutter install --release
```

### Step 3.2 — Build Android App Bundle (for Play Store upload)

> Google Play requires an AAB (Android App Bundle), not a plain APK.

```bash
flutter build appbundle --release
# Output: build/app/outputs/bundle/release/app-release.aab
```

### Step 3.3 — Build iOS (macOS only)

```bash
flutter build ios --release
# This generates an Xcode archive.
# You must then use Xcode to upload it to App Store Connect.
```

---

## PART 4 — CODE SIGNING (REQUIRED BEFORE PUBLISHING)

### Android Signing

#### Step 4.1 — Generate a Keystore (one-time setup)

```bash
keytool -genkey -v \
  -keystore ~/family-roots-release.keystore \
  -alias family-roots \
  -keyAlg RSA \
  -keysize 2048 \
  -validity 10000

# When prompted:
# First and last name: FamilyRoots App
# Organization: Your organization name
# City, State, Country: Hanoi, HN, VN
# Set a strong password — store it somewhere safe immediately
```

> **⚠️ Critical:** Back up your `.keystore` file securely. If it is lost, you cannot publish updates to your existing Play Store app — you would need to create an entirely new listing.

#### Step 4.2 — Configure Signing in Flutter

Create `mobile/android/key.properties`:

```properties
storePassword=your-keystore-password
keyPassword=your-key-password
keyAlias=family-roots
storeFile=/Users/yourname/family-roots-release.keystore
```

Add the following to `mobile/android/app/build.gradle`:

```groovy
// Add before the android {} block
def keystoreProperties = new Properties()
def keystorePropertiesFile = rootProject.file('key.properties')
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(new FileInputStream(keystorePropertiesFile))
}

android {
    // ... existing config ...

    signingConfigs {
        release {
            keyAlias keystoreProperties['keyAlias']
            keyPassword keystoreProperties['keyPassword']
            storeFile keystoreProperties['storeFile'] ? file(keystoreProperties['storeFile']) : null
            storePassword keystoreProperties['storePassword']
        }
    }

    buildTypes {
        release {
            signingConfig signingConfigs.release
        }
    }
}
```

> **⚠️ Important:** Add `key.properties` to your `.gitignore`. Never commit this file to version control.

### iOS Signing (via Xcode)

#### Step 4.3 — Register an Apple Developer Account

1. Visit https://developer.apple.com/account
2. Enroll in the Apple Developer Program: $99/year
3. Wait for approval (typically 24–48 hours)

#### Step 4.4 — Configure Signing in Xcode

1. Open `mobile/ios/Runner.xcworkspace` in Xcode
2. Select **Runner** in the Project Navigator
3. Go to the **Signing & Capabilities** tab
4. Set **Team** to your Apple Developer account
5. Set **Bundle Identifier**: `com.yourcompany.familyroots` (must be globally unique)
6. Enable **Automatically manage signing** — Xcode will generate the Provisioning Profile automatically

---

## PART 5 — PUBLISHING TO GOOGLE PLAY STORE

### Step 5.1 — Create a Google Play Developer Account

1. Visit https://play.google.com/console
2. Pay the one-time $25 registration fee
3. Fill in your personal or organization details
4. Wait for verification (usually 1–2 business days)

### Step 5.2 — Create a New App in Play Console

1. Play Console → **Create app**
2. Fill in:
   - App name: **FamilyRoots - Family Tree**
   - Default language: English (or your primary language)
   - App or game: App
   - Free or paid: Free
3. Accept the policies → Create app

### Step 5.3 — Prepare Required Assets

| Asset | Size | Notes |
|-------|------|-------|
| App icon | 512×512 px PNG | No alpha/transparency |
| Feature graphic | 1024×500 px | Banner shown on Play Store listing |
| Phone screenshots | Min 2 images | 16:9 or 9:16 ratio |
| 7" tablet screenshots | Recommended | |
| 10" tablet screenshots | Recommended | |
| Short description | Max 80 characters | |
| Full description | Max 4,000 characters | |
| Privacy Policy URL | Required | Must be hosted and publicly accessible |

### Step 5.4 — Upload the AAB to Play Console

```bash
# Build a signed AAB
cd mobile
flutter build appbundle --release
# Output: build/app/outputs/bundle/release/app-release.aab
```

1. Play Console → App → Release → Production → **Create new release**
2. Upload `app-release.aab`
3. Add release notes (in English and any other supported languages)
4. Save → Review release

### Step 5.5 — Complete the Store Listing

Go to Play Console → Store presence → Main store listing:

- App name, short description, full description (all supported languages)
- Upload screenshots, feature graphic, and icon
- **Content rating:** Complete the questionnaire to receive an automatic rating
- **Target audience:** Select the appropriate age group
- **Privacy Policy:** Enter your hosted URL (required)

### Step 5.6 — Submit for Review

1. Ensure all sections in Play Console show a green checkmark
2. Go to Production → Review release → **Start rollout to Production**
3. Set rollout percentage to **20%** to start — this limits exposure if issues are found
4. Wait for Google review: 1–3 days for first submission, a few hours for subsequent updates

---

## PART 6 — PUBLISHING TO APPLE APP STORE

### Step 6.1 — Create the App in App Store Connect

1. Go to https://appstoreconnect.apple.com
2. My Apps → **+** → **New App**
3. Fill in:
   - Platform: iOS
   - Name: **FamilyRoots - Family Tree**
   - Primary Language: English
   - Bundle ID: Select the Bundle ID created in Step 4.4
   - SKU: `family-roots-ios` (internal identifier, not visible to users)

### Step 6.2 — Prepare Required Assets for App Store

| Asset | Size | Notes |
|-------|------|-------|
| App icon | 1024×1024 px PNG | No rounded corners, no alpha channel |
| iPhone screenshots (6.7") | 1290×2796 px | Minimum 3 images — required |
| iPhone screenshots (6.5") | 1242×2688 px | Required |
| iPad screenshots (12.9") | 2048×2732 px | Required if iPad is supported |
| App preview video | Optional | Significantly boosts conversion rate |
| Description | — | |
| Keywords | Max 100 characters | Used for App Store search ranking |
| Support URL | Required | |
| Privacy Policy URL | Required | |

### Step 6.3 — Build and Upload to App Store

**Option 1: Use Xcode (recommended for first submission)**

```bash
cd mobile
flutter build ios --release

# Open the Xcode workspace
open ios/Runner.xcworkspace
```

In Xcode:

1. Select scheme **Runner** and target **Any iOS Device (arm64)**
2. Go to **Product → Archive**
3. When archiving completes, the Organizer window opens automatically
4. Click **Distribute App → App Store Connect → Upload**
5. Wait for the upload to finish (a few minutes)

**Option 2: Use `flutter build ipa` + Transporter**

```bash
flutter build ipa --release
# Output: build/ios/ipa/family_roots.ipa

# Use the free Transporter app (Mac App Store) to upload the .ipa file
```

### Step 6.4 — Complete App Information on App Store Connect

- **App Information:** Category → Lifestyle or Reference
- **Pricing and Availability:** Free; select target countries
- **App Privacy:** Declare all data types collected (Name, Email, Photos, etc.)
- **Version Information:**
  - Description (English + other languages)
  - Keywords
  - Screenshots (from Step 6.2)
  - Build: select the build you just uploaded
- **Review Information:**
  - Demo account credentials (required if your app has a login — create a dedicated test account)
  - Notes for the reviewer (explain any special features or flows)

### Step 6.5 — Submit for Review

1. **Add for Review → Submit to App Review**
2. Wait for Apple's review: typically 24–48 hours for first submission, 24 hours for updates

Common reasons for rejection on first submission:

- Missing **Sign in with Apple** when another third-party login (e.g., Google) is present — this is mandatory per Apple's guidelines
- Privacy Policy URL is broken or returns an error
- Demo account credentials don't work for the reviewer
- App crashes during review
- Screenshots are the wrong size
- Missing **Privacy Manifest** (`PrivacyInfo.xcprivacy`) — required since 2024

---

## PART 7 — PUBLISHING UPDATES

### Android Update

```bash
# Increment the version in mobile/pubspec.yaml
# Format: version: 1.0.1+2  (semver + build_number)
# The build number MUST increase with every upload

flutter build appbundle --release
# Upload the new AAB via Play Console → Create new release
```

### iOS Update

```bash
# Increment the version in mobile/pubspec.yaml (same format as Android)

flutter build ios --release
# Then archive and upload from Xcode as before
```

---

## PART 8 — CI/CD AUTOMATION (GitHub Actions)

Once you've done a manual publish, automate future releases with GitHub Actions.

> **Note:** The project already has `mobile-ci.yml` (debug APK build + tests) and `web-ci.yml` (build + Vercel deploy). The workflow below adds **release** automation on top of the existing CI pipelines.

### Android Workflow (`.github/workflows/mobile-release.yml`)

```yaml
name: Mobile Release

on:
  push:
    tags:
      - 'v*'   # Triggers on tags like v1.0.0, v1.1.0, etc.

jobs:
  android:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
        with:
          flutter-version: '3.x'
          channel: 'stable'

      - name: Decode Keystore
        run: |
          echo "${{ secrets.ANDROID_KEYSTORE_BASE64 }}" | base64 -d > android/app/release.keystore

      - name: Build AAB
        run: flutter build appbundle --release
        env:
          ANDROID_KEYSTORE_PATH: android/app/release.keystore
          ANDROID_KEY_ALIAS: ${{ secrets.ANDROID_KEY_ALIAS }}
          ANDROID_KEYSTORE_PASSWORD: ${{ secrets.ANDROID_KEYSTORE_PASSWORD }}
          ANDROID_KEY_PASSWORD: ${{ secrets.ANDROID_KEY_PASSWORD }}

      - name: Upload to Play Store
        uses: r0adkll/upload-google-play@v1
        with:
          serviceAccountJsonPlainText: ${{ secrets.PLAY_STORE_SERVICE_ACCOUNT_JSON }}
          packageName: com.yourcompany.familyroots
          releaseFiles: build/app/outputs/bundle/release/app-release.aab
          track: production
```

### iOS Workflow (append to the same file)

```yaml
  ios:
    runs-on: macos-latest   # iOS builds MUST run on macOS
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2

      - name: Install Certificates
        uses: apple-actions/import-codesign-certs@v2
        with:
          p12-file-base64: ${{ secrets.CERTIFICATES_P12 }}
          p12-password: ${{ secrets.CERTIFICATES_P12_PASSWORD }}

      - name: Build IPA
        run: flutter build ipa --release

      - name: Upload to TestFlight
        uses: apple-actions/upload-testflight-build@v1
        with:
          app-path: build/ios/ipa/family_roots.ipa
          issuer-id: ${{ secrets.APPSTORE_ISSUER_ID }}
          api-key-id: ${{ secrets.APPSTORE_KEY_ID }}
          api-private-key: ${{ secrets.APPSTORE_PRIVATE_KEY }}
```

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `ANDROID_KEYSTORE_BASE64` | Base64-encoded `.keystore` file |
| `ANDROID_KEY_ALIAS` | Key alias used when creating the keystore |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore password |
| `ANDROID_KEY_PASSWORD` | Key password |
| `PLAY_STORE_SERVICE_ACCOUNT_JSON` | Service account JSON from Google Play Console |
| `CERTIFICATES_P12` | Apple signing certificate (base64-encoded) |
| `CERTIFICATES_P12_PASSWORD` | Apple certificate password |
| `APPSTORE_ISSUER_ID` | App Store Connect API issuer ID |
| `APPSTORE_KEY_ID` | App Store Connect API key ID |
| `APPSTORE_PRIVATE_KEY` | App Store Connect API private key |

To generate the `ANDROID_KEYSTORE_BASE64` secret:

```bash
base64 -i family-roots-release.keystore | pbcopy
```

---

## PART 9 — PRE-SUBMISSION CHECKLIST

### Android Checklist

- [ ] Version name updated in `pubspec.yaml`
- [ ] Build number incremented (must be higher than the previous upload)
- [ ] Tested on at least one physical Android device
- [ ] Tested on Android 10, 12, and 14
- [ ] App handles no-internet conditions gracefully (no crash)
- [ ] App icon set correctly (512×512 PNG, no alpha)
- [ ] Privacy Policy URL is live and accessible
- [ ] All screenshots are the correct dimensions

### iOS Checklist

- [ ] Version name updated in `pubspec.yaml`
- [ ] Build number incremented
- [ ] Tested on a physical iPhone
- [ ] Sign in with Apple implemented (mandatory if any third-party login is present)
- [ ] All required permissions declared in `Info.plist` (camera, photos, etc.)
- [ ] Demo account works correctly for Apple's reviewer
- [ ] App does not crash on iOS 16 or iOS 17
- [ ] Privacy Manifest (`PrivacyInfo.xcprivacy`) declared (required since 2024)
- [ ] Screenshots are the correct size (6.5" is mandatory)
- [ ] App icon is 1024×1024 PNG with no alpha channel
