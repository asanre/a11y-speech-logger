package io.github.asanre.a11ylogger

import android.content.ComponentName
import android.os.Bundle
import android.provider.Settings
import android.view.accessibility.AccessibilityManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** Intro and setup FAQ. Capturing works without opening it; it only documents how to use the app. */
class MainActivity : ComponentActivity() {

    private var setup by mutableStateOf<Setup?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { AppTheme { setup?.let { HomeScreen(it) } } }
    }

    // Read on every resume: the user may have changed services or the engine in Settings meanwhile.
    override fun onResume() {
        super.onResume()
        setup = Setup(
            packageName = packageName,
            focusLogger = ComponentName(this, FocusLoggerService::class.java).flattenToShortString(),
            talkBack = findTalkBack(),
            enabledServices = enabledServices(),
        )
    }

    /** The installed TalkBack (Google's or a vendor build), as a short component name. */
    private fun findTalkBack(): String? =
        getSystemService(AccessibilityManager::class.java)
            .installedAccessibilityServiceList
            .map { it.resolveInfo.serviceInfo }
            .firstOrNull { "talkback" in it.packageName }
            ?.let { ComponentName(it.packageName, it.name).flattenToShortString() }

    private fun enabledServices(): List<String> =
        Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES)
            .orEmpty()
            .split(':')
            .mapNotNull { ComponentName.unflattenFromString(it)?.flattenToShortString() }
}
