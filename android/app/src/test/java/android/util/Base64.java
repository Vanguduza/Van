package android.util;
/** SOURCE host adapter only: no claim of Android native runtime/Keystore acceptance. */
public final class Base64 {
 public static final int NO_WRAP=2;
 public static String encodeToString(byte[] b,int flags){return java.util.Base64.getEncoder().encodeToString(b);}
 public static byte[] decode(String b,int flags){return java.util.Base64.getDecoder().decode(b);}
}
