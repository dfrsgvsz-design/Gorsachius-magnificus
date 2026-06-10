# Project-specific R8/ProGuard rules.
#
# Capacitor discovers and invokes plugins via reflection (@CapacitorPlugin /
# @PluginMethod annotations), so plugin classes and annotated members must
# survive shrinking and keep their original names.

# --- Capacitor core & bridge ---
-keep class com.getcapacitor.** { *; }
-keep public class * extends com.getcapacitor.Plugin
-keep @com.getcapacitor.annotation.CapacitorPlugin public class * {
    @com.getcapacitor.annotation.PermissionCallback <methods>;
    @com.getcapacitor.annotation.ActivityCallback <methods>;
    @com.getcapacitor.PluginMethod public <methods>;
}
-keepattributes RuntimeVisibleAnnotations, RuntimeVisibleParameterAnnotations

# --- Cordova compatibility layer (capacitor-cordova-android-plugins) ---
-keep class org.apache.cordova.** { *; }
-keep public class * extends org.apache.cordova.CordovaPlugin

# --- WebView JavaScript bridge ---
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

# --- @capacitor-community/sqlite (bundles SQLCipher via JNI) ---
-keep class com.getcapacitor.community.** { *; }
-keep class net.sqlcipher.** { *; }
-keep class net.zetetic.** { *; }
-dontwarn net.sqlcipher.**
-dontwarn net.zetetic.**

# --- Crash report readability (mapping.txt still de-obfuscates) ---
-keepattributes SourceFile, LineNumberTable
