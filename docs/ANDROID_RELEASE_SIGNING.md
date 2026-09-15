# Android release signing

Production releases require a local keystore that is **never** committed.

## Setup (once)

```bash
keytool -genkeypair -v -keystore van-release.jks -keyalg RSA -keysize 2048 -validity 10000 -alias van
```

Create `android/keystore.properties` (gitignored):

```properties
storeFile=../van-release.jks
storePassword=...
keyAlias=van
keyPassword=...
```

## Build

```bat
cd android
gradlew.bat :app:assembleRelease
```

Without `android/keystore.properties` (and a resolvable `storeFile`), `:app:assembleRelease` / `:app:bundleRelease` **fail closed** and refuse to produce an unsigned release artifact.
