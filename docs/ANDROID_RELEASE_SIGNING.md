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

Without keystore properties, release signing is unavailable and the build must fail closed rather than shipping an unsigned “production” claim.
