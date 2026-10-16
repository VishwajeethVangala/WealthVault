-keepattributes *Annotation*, InnerClasses
-keep,includedescriptorclasses class com.wealthvault.app.**$$serializer { *; }
-keepclassmembers class com.wealthvault.app.** { *** Companion; }
-keepclasseswithmembers class com.wealthvault.app.** { kotlinx.serialization.KSerializer serializer(...); }
-if class androidx.credentials.CredentialManager
-keep class androidx.credentials.playservices.** { *; }
# the app's API models are read by kotlinx.serialization by name
-keep class com.wealthvault.app.data.** { *; }
-dontwarn org.slf4j.**
-dontwarn javax.annotation.**
