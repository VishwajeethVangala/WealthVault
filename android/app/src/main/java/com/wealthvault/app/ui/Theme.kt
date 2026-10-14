package com.wealthvault.app.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * The web app's design tokens ("Quiet surfaces, loud numbers", web/src/index.css), light and dark, one to one.
 * Screens read them from [Wv.c]; nothing in a screen hard-codes a colour.
 */
@Immutable
data class WvColors(
    val bg: Color,
    val surface: Color,
    val surface2: Color,
    val border: Color,
    val borderStrong: Color,
    val text: Color,
    val text2: Color,
    val text3: Color,
    val accent: Color,
    val accentWeak: Color,
    val onAccent: Color,
    val gain: Color,
    val gainWeak: Color,
    val loss: Color,
    val lossWeak: Color,
    val warn: Color,
    val warnWeak: Color,
    val classColors: Map<String, Color>,
)

private val classColors = mapOf(
    "EQUITY" to Color(0xFF3346D3),
    "MUTUAL_FUND" to Color(0xFF0E9AA7),
    "US_STOCKS" to Color(0xFFE07B39),
    "GOLD" to Color(0xFFC9A227),
    "DEBT" to Color(0xFF64748B),
    "NPS" to Color(0xFFD2557A),
)

val LightWv = WvColors(
    bg = Color(0xFFF5F6F8), surface = Color(0xFFFFFFFF), surface2 = Color(0xFFEFF1F4),
    border = Color(0xFFE3E6EB), borderStrong = Color(0xFFCDD2DA),
    text = Color(0xFF0F1720), text2 = Color(0xFF465061), text3 = Color(0xFF5F6876),
    accent = Color(0xFF3346D3), accentWeak = Color(0xFFECEEFC), onAccent = Color(0xFFFFFFFF),
    gain = Color(0xFF0A7347), gainWeak = Color(0xFFE5F3EB), loss = Color(0xFFBE3427), lossWeak = Color(0xFFFBEAE8),
    warn = Color(0xFF965800), warnWeak = Color(0xFFFDF2DF), classColors = classColors,
)

val DarkWv = WvColors(
    bg = Color(0xFF0B0E13), surface = Color(0xFF12161D), surface2 = Color(0xFF1A1F28),
    border = Color(0xFF232A35), borderStrong = Color(0xFF323A47),
    text = Color(0xFFE8ECF2), text2 = Color(0xFFB1B9C6), text3 = Color(0xFF8E97A5),
    accent = Color(0xFF8E9CFF), accentWeak = Color(0xFF1D2347), onAccent = Color(0xFF0B0E13),
    gain = Color(0xFF45CF8E), gainWeak = Color(0xFF0F2A1F), loss = Color(0xFFFF8172), lossWeak = Color(0xFF35191A),
    warn = Color(0xFFF2B455), warnWeak = Color(0xFF33260F), classColors = classColors,
)

private val LocalWv = staticCompositionLocalOf { LightWv }

object Wv {
    val c: WvColors @Composable get() = LocalWv.current

    // Type scale from the web app (14px body, 22px titles, 11px uppercase labels), numbers with tabular figures
    val h1 = TextStyle(fontSize = 22.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.4).sp)
    val title = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
    val body = TextStyle(fontSize = 14.sp, lineHeight = 20.sp)
    val sub = TextStyle(fontSize = 13.sp, lineHeight = 18.sp)
    val small = TextStyle(fontSize = 12.sp, lineHeight = 16.sp)
    val over = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.9.sp)
    val kpi = TextStyle(fontSize = 26.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.5).sp, fontFeatureSettings = "tnum")
    val num = TextStyle(fontSize = 14.sp, fontFeatureSettings = "tnum")
}

@Composable
fun WealthVaultTheme(theme: String, content: @Composable () -> Unit) {
    val dark = when (theme) {
        "dark" -> true
        "light" -> false
        else -> isSystemInDarkTheme()
    }
    val wv = if (dark) DarkWv else LightWv
    val scheme = if (dark) {
        darkColorScheme(primary = wv.accent, onPrimary = wv.onAccent, background = wv.bg, surface = wv.surface, onSurface = wv.text, onBackground = wv.text, outline = wv.border, error = wv.loss)
    } else {
        lightColorScheme(primary = wv.accent, onPrimary = wv.onAccent, background = wv.bg, surface = wv.surface, onSurface = wv.text, onBackground = wv.text, outline = wv.border, error = wv.loss)
    }
    CompositionLocalProvider(LocalWv provides wv) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}
