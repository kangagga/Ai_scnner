# ProGuard rules for AI Scanner
# Keep Gson model fields (they use @SerializedName)
-keep class com.aiscanner.app.data.api.** { *; }
-keepattributes Signature
-keepattributes *Annotation*
